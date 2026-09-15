"""TaskType service: tipos + fases + definicoes de atributos (Parte 5)."""

from __future__ import annotations

from pathlib import Path

from task_level.data import UnitOfWork
from task_level.domain import (
    AttributeDefinition,
    NotFoundError,
    Phase,
    TaskType,
    ValidationError,
)

DEFAULT_PHASES: list[tuple[str, bool, bool]] = [
    ("Novo", True, False),
    ("Em andamento", False, False),
    ("Concluido", False, True),
]


class TaskTypeService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    def create_type(
        self,
        project_id: int,
        name: str,
        description: str = "",
        color: str = "#888888",
        icon: str = "",
        phases: list[dict] | None = None,
        attributes: list[dict] | None = None,
    ) -> TaskType:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError(f"project {project_id} nao encontrado")
            task_type = uow.task_types.add(
                TaskType(
                    project_id=project_id,
                    name=name,
                    description=description,
                    color=color,
                    icon=icon,
                )
            )
            assert task_type.id is not None
            self._create_phases(uow, task_type.id, phases)
            for i, spec in enumerate(attributes or []):
                uow.attribute_definitions.add(
                    AttributeDefinition(
                        task_type_id=task_type.id,
                        name=spec["name"],
                        label=spec.get("label", spec["name"]),
                        type=spec["type"],
                        required=bool(spec.get("required", False)),
                        default_value=spec.get("default_value", ""),
                        reference_config=spec.get("reference_config"),
                        order=int(spec.get("order", i)),
                    )
                )
            return task_type

    def _create_phases(
        self, uow: UnitOfWork, task_type_id: int, phases: list[dict] | None
    ) -> None:
        specs = phases
        if specs is None:
            specs = [
                {"name": n, "is_initial": ini, "is_final": fin}
                for n, ini, fin in DEFAULT_PHASES
            ]
        initials = [s for s in specs if s.get("is_initial")]
        if len(initials) != 1:
            raise ValidationError("task_type precisa de exatamente 1 fase inicial")
        for i, spec in enumerate(specs):
            uow.phases.add(
                Phase(
                    task_type_id=task_type_id,
                    name=spec["name"],
                    description=spec.get("description", ""),
                    color=spec.get("color", "#888888"),
                    order=int(spec.get("order", i)),
                    is_initial=bool(spec.get("is_initial", False)),
                    is_final=bool(spec.get("is_final", False)),
                )
            )

    def list_by_project(self, project_id: int) -> list[TaskType]:
        with UnitOfWork.open(self._db_path) as uow:
            return uow.task_types.list_by_project(project_id)

    def get(self, type_id: int) -> TaskType:
        with UnitOfWork.open(self._db_path) as uow:
            task_type = uow.task_types.get(type_id)
        if task_type is None:
            raise NotFoundError(f"task_type {type_id} nao encontrado")
        return task_type

    def add_phase(self, task_type_id: int, name: str, **kwargs) -> Phase:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.task_types.get(task_type_id) is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            return uow.phases.add(Phase(task_type_id=task_type_id, name=name, **kwargs))

    def add_attribute(self, task_type_id: int, spec: dict) -> AttributeDefinition:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.task_types.get(task_type_id) is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            return uow.attribute_definitions.add(
                AttributeDefinition(
                    task_type_id=task_type_id,
                    name=spec["name"],
                    label=spec.get("label", spec["name"]),
                    type=spec["type"],
                    required=bool(spec.get("required", False)),
                    default_value=spec.get("default_value", ""),
                    reference_config=spec.get("reference_config"),
                    order=int(spec.get("order", 0)),
                )
            )

    def delete(self, type_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.task_types.get(type_id) is None:
                raise NotFoundError(f"task_type {type_id} nao encontrado")
            uow.task_types.delete(type_id)
