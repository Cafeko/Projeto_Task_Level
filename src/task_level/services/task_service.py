"""Task service: CRUD + atributos + fases + validacao de ciclos (Parte 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from task_level.data import UnitOfWork
from task_level.domain import (
    AttributeType,
    CircularReferenceError,
    NotFoundError,
    Task,
    TaskAttribute,
    ValidationError,
    utcnow,
)


def _has_value(attr: TaskAttribute, attr_type: str) -> bool:
    if attr_type == AttributeType.TEXT.value:
        return attr.value_text is not None and attr.value_text != ""
    if attr_type == AttributeType.NUMBER.value:
        return attr.value_number is not None
    if attr_type == AttributeType.BOOLEAN.value:
        return attr.value_boolean is not None
    if attr_type == AttributeType.REFERENCE_TASK.value:
        return attr.value_reference_task_id is not None
    if attr_type == AttributeType.REFERENCE_ATTRIBUTE.value:
        return attr.value_reference_attribute_id is not None
    return False


class TaskService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    # -- criacao/listagem -------------------------------------------------

    def create_task(
        self,
        project_id: int,
        task_type_id: int,
        title: str,
        description: str = "",
        values: dict[str, Any] | None = None,
    ) -> Task:
        with UnitOfWork.open(self._db_path) as uow:
            task_type = uow.task_types.get(task_type_id)
            if task_type is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            if task_type.project_id != project_id:
                raise ValidationError("task_type nao pertence ao project informado")
            initial = uow.phases.initial_of_type(task_type_id)
            if initial is None:
                raise ValidationError("task_type sem fase inicial")
            task = uow.tasks.add(
                Task(
                    project_id=project_id,
                    task_type_id=task_type_id,
                    phase_id=initial.id,
                    title=title,
                    description=description,
                )
            )
            assert task.id is not None
            for name, value in (values or {}).items():
                self._set_attribute(uow, task.id, task_type_id, name, value)
            return task

    def list_by_project(
        self,
        project_id: int,
        task_type_id: int | None = None,
        phase_id: int | None = None,
    ) -> list[Task]:
        with UnitOfWork.open(self._db_path) as uow:
            return uow.tasks.list_by_project(project_id, task_type_id, phase_id)

    def get(self, task_id: int) -> Task:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"task {task_id} nao encontrada")
        return task

    def delete(self, task_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.tasks.get(task_id) is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            uow.tasks.delete(task_id)

    # -- atributos ----------------------------------------------------------

    def set_attribute(self, task_id: int, attr_name: str, value: Any) -> TaskAttribute:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            return self._set_attribute(uow, task_id, task.task_type_id, attr_name, value)

    def _set_attribute(
        self,
        uow: UnitOfWork,
        task_id: int,
        task_type_id: int,
        attr_name: str,
        value: Any,
    ) -> TaskAttribute:
        definition = uow.attribute_definitions.get_by_name(task_type_id, attr_name)
        if definition is None:
            raise NotFoundError(f"atributo '{attr_name}' nao existe neste tipo")
        assert definition.id is not None
        attr = self._build_attribute(
            uow, task_id, definition.id, definition.type, value
        )
        return uow.task_attributes.set(attr, definition.type)

    def _build_attribute(
        self,
        uow: UnitOfWork,
        task_id: int,
        definition_id: int,
        attr_type: str,
        value: Any,
    ) -> TaskAttribute:
        if attr_type == AttributeType.TEXT.value:
            return TaskAttribute(task_id, definition_id, value_text=str(value))
        if attr_type == AttributeType.NUMBER.value:
            try:
                number = float(value)
            except (TypeError, ValueError) as e:
                raise ValidationError(f"valor numerico invalido: {value!r}") from e
            return TaskAttribute(task_id, definition_id, value_number=number)
        if attr_type == AttributeType.BOOLEAN.value:
            if not isinstance(value, bool):
                raise ValidationError(f"valor booleano invalido: {value!r}")
            return TaskAttribute(task_id, definition_id, value_boolean=value)
        if attr_type == AttributeType.REFERENCE_TASK.value:
            ref_id = int(value)
            if uow.tasks.get(ref_id) is None:
                raise NotFoundError(f"task referenciada {ref_id} nao encontrada")
            self._reject_cycle(uow, task_id, ref_id)
            return TaskAttribute(
                task_id, definition_id, value_reference_task_id=ref_id
            )
        if attr_type == AttributeType.REFERENCE_ATTRIBUTE.value:
            ref_task_id, ref_attr_id = self._parse_attr_reference(value)
            target = uow.task_attributes.get_by_id(ref_attr_id)
            if target is None:
                raise NotFoundError(f"atributo referenciado {ref_attr_id} nao existe")
            if target.task_id != ref_task_id:
                raise ValidationError("atributo referenciado nao pertence a task indicada")
            self._reject_cycle(uow, task_id, ref_task_id)
            return TaskAttribute(
                task_id,
                definition_id,
                value_reference_task_id=ref_task_id,
                value_reference_attribute_id=ref_attr_id,
            )
        raise ValidationError(f"tipo de atributo desconhecido: {attr_type}")

    @staticmethod
    def _parse_attr_reference(value: Any) -> tuple[int, int]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return int(value[0]), int(value[1])
        if isinstance(value, dict) and "task_id" in value and "attribute_id" in value:
            return int(value["task_id"]), int(value["attribute_id"])
        raise ValidationError(
            "referencia de atributo: esperado (task_id, attribute_id) ou "
            "{task_id, attribute_id}"
        )

    # -- ciclos ---------------------------------------------------------------

    def _reject_cycle(self, uow: UnitOfWork, task_id: int, ref_task_id: int) -> None:
        if ref_task_id == task_id or self._reaches(uow, ref_task_id, task_id):
            raise CircularReferenceError("referencia criaria ciclo entre tasks")

    def _reaches(self, uow: UnitOfWork, start_id: int, goal_id: int) -> bool:
        """DFS: start_id alcanca goal_id via referencias existentes?"""
        visited: set[int] = set()
        stack = [start_id]
        while stack:
            current = stack.pop()
            if current == goal_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(uow.task_attributes.referenced_task_ids(current) - visited)
        return False

    # -- fases ------------------------------------------------------------------

    def move_phase(self, task_id: int, phase_id: int) -> Task:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            phase = uow.phases.get(phase_id)
            if phase is None:
                raise NotFoundError(f"phase {phase_id} nao encontrada")
            if phase.task_type_id != task.task_type_id:
                raise ValidationError("phase pertence a outro task_type")
            if phase.is_final:
                self._require_required_attributes(uow, task)
                task.completed_at = utcnow()
            else:
                task.completed_at = None
            task.phase_id = phase_id
            task.updated_at = utcnow()
            uow.tasks.update(task)
            return task

    def _require_required_attributes(self, uow: UnitOfWork, task: Task) -> None:
        assert task.id is not None
        missing: list[str] = []
        for definition in uow.attribute_definitions.list_by_task_type(task.task_type_id):
            if not definition.required:
                continue
            assert definition.id is not None
            attr = uow.task_attributes.get(task.id, definition.id)
            if attr is None or not _has_value(attr, definition.type):
                missing.append(definition.label)
        if missing:
            raise ValidationError(
                "atributos obrigatorios sem valor: " + ", ".join(missing)
            )
