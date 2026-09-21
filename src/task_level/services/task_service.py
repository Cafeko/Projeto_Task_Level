"""Task service: CRUD + atributos + fases + validacao de ciclos (Parte 5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from task_level.data import UnitOfWork
from task_level.domain import (
    AttributeType,
    CircularReferenceError,
    NotFoundError,
    Phase,
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

    def resolve_reference_attribute(
        self, task_id: int, attribute_name: str
    ) -> tuple[int, int] | None:
        """Resolve (task_id, attribute_id-valor) para o atributo `attribute_name`.

        Retorna None se a task nao tem definicao com esse nome ou se ainda
        nao ha valor preenchido. Usado pelo modo "atributo fixo" do form.
        """
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return None
            definition = uow.attribute_definitions.get_by_name(
                task.task_type_id, attribute_name
            )
            if definition is None or definition.id is None:
                return None
            value = uow.task_attributes.get(task_id, definition.id)
            if value is None or value.id is None:
                return None
            return (task_id, value.id)

    def update_details(self, task_id: int, title: str, description: str = "") -> Task:
        """Atualiza titulo/descricao (usado pelo dialog de edicao - Parte 9)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            task.title = title
            task.description = description
            task.updated_at = utcnow()
            uow.tasks.update(task)
            return task

    def clear_attribute(self, task_id: int, attr_name: str) -> None:
        """Remove o valor de um atributo (campo esvaziado no form - Parte 9)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            definition = uow.attribute_definitions.get_by_name(
                task.task_type_id, attr_name
            )
            if definition is None:
                raise NotFoundError(f"atributo '{attr_name}' nao existe neste tipo")
            assert definition.id is not None
            uow.task_attributes.delete(task_id, definition.id)

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
            origin = uow.tasks.get(task_id)
            target = uow.tasks.get(ref_id)
            if target is None:
                raise NotFoundError(f"task referenciada {ref_id} nao encontrada")
            if origin is not None and target.project_id != origin.project_id:
                raise ValidationError("referencia deve ser para task do mesmo projeto")
            self._check_ref_task_config(uow, definition_id, target)
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
            origin = uow.tasks.get(task_id)
            target_task = uow.tasks.get(ref_task_id)
            if target_task is None:
                raise NotFoundError(f"task referenciada {ref_task_id} nao encontrada")
            if origin is not None and target_task.project_id != origin.project_id:
                raise ValidationError("referencia deve ser para task do mesmo projeto")
            self._check_ref_attr_config(uow, definition_id, target_task, target)
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

    @staticmethod
    def _field_config(uow: UnitOfWork, definition_id: int) -> dict:
        definition = uow.attribute_definitions.get(definition_id)
        if definition is None or not isinstance(definition.reference_config, dict):
            return {}
        return definition.reference_config

    @staticmethod
    def _check_ref_task_config(uow: UnitOfWork, definition_id: int, target) -> None:
        """reference_task aceita qualquer tipo do projeto, salvo filtro configurado."""
        allowed = TaskService._field_config(uow, definition_id).get("target_type_id")
        if allowed is not None and target.task_type_id != allowed:
            raise ValidationError("referencia fora do tipo permitido neste atributo")

    @staticmethod
    def _check_ref_attr_config(
        uow: UnitOfWork, definition_id: int, target_task, target_value
    ) -> None:
        """reference_attribute com atributo fixo: o alvo tem que ser aquele atributo."""
        config = TaskService._field_config(uow, definition_id)
        wanted = config.get("attribute_name")
        if wanted:
            target_def = uow.attribute_definitions.get(
                target_value.attribute_definition_id
            )
            if target_def is None or target_def.name != wanted:
                raise ValidationError(
                    f"este atributo so referencia '{wanted}' (alvo e outro atributo)"
                )
        allowed = config.get("target_type_id")
        if allowed is not None and target_task.task_type_id != allowed:
            raise ValidationError("referencia fora do tipo permitido neste atributo")

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

    # -- transicoes de fase (PONTO UNICO) ---------------------------------------
    #
    # Toda mudanca de fase passa por `check_move` + `move_phase`, e toda UI
    # consulta `neighbors`. Quando existir o sistema de condicoes
    # (ex: expressoes booleanas sobre atributos por fase), ele entra em
    # `_check_conditions`, sem tocar UI nem `move_phase`:
    #   - `neighbors` passa a ocultar/bloquear o destino com condicao falsa
    #     (motivo em `blocked_reason`);
    #   - `check_move` rejeita com o motivo da condicao.

    def neighbors(self, task_id: int) -> tuple[Phase | None, Phase | None]:
        """(fase anterior, proxima fase) na ordem das fases. None nas pontas."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            ordered = sorted(
                uow.phases.list_by_task_type(task.task_type_id), key=lambda p: p.order
            )
            ids = [p.id for p in ordered]
            if task.phase_id not in ids:
                return (None, None)
            pos = ids.index(task.phase_id)
            prev = ordered[pos - 1] if pos > 0 else None
            nxt = ordered[pos + 1] if pos < len(ordered) - 1 else None
            return (prev, nxt)

    def check_move(self, task_id: int, phase_id: int) -> None:
        """Valida uma transicao (levanta com o motivo se bloqueada)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            phase = uow.phases.get(phase_id)
            if phase is None:
                raise NotFoundError(f"phase {phase_id} nao encontrada")
            if phase.task_type_id != task.task_type_id:
                raise ValidationError("phase pertence a outro task_type")
            if phase_id == task.phase_id:
                return
            self._require_neighbor(uow, task, phase_id)
            self._check_conditions(uow, task, phase)

    @staticmethod
    def _check_conditions(uow: UnitOfWork, task: Task, phase: Phase) -> None:
        """Hook p/ condicoes de transicao (FUTURO: expressoes sobre atributos).

        Hoje sempre permite. Quando implementado, deve levantar
        ValidationError com o motivo (ex: "requer 'sev' preenchida").
        """
        _ = (uow, task, phase)

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
            if phase_id == task.phase_id:
                return task  # ja esta nela: nada a fazer
            self._require_neighbor(uow, task, phase_id)
            self._check_conditions(uow, task, phase)
            if phase.is_final:
                self._require_required_attributes(uow, task)
                task.completed_at = utcnow()
            else:
                task.completed_at = None
            task.phase_id = phase_id
            task.updated_at = utcnow()
            uow.tasks.update(task)
            return task

    @staticmethod
    def _require_neighbor(uow: UnitOfWork, task: Task, phase_id: int) -> None:
        """So permite avancar ou voltar uma fase por vez (pela ordem das fases)."""
        ordered = sorted(
            uow.phases.list_by_task_type(task.task_type_id), key=lambda p: p.order
        )
        ids = [p.id for p in ordered]
        if task.phase_id not in ids or phase_id not in ids:
            return  # sem fase atual conhecida: permite posicionar
        if abs(ids.index(phase_id) - ids.index(task.phase_id)) != 1:
            raise ValidationError("so e possivel avancar ou voltar uma fase por vez")

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
