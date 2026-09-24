"""TaskType service: tipos + fases + definicoes de atributos (Partes 5 e 8)."""

from __future__ import annotations

import sqlite3
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
            current_max = uow.task_types.max_order(project_id)
            next_order = (current_max + 1) if current_max is not None else 0
            task_type = uow.task_types.add(
                TaskType(
                    project_id=project_id,
                    name=name,
                    description=description,
                    color=color,
                    icon=icon,
                    order=next_order,
                )
            )
            assert task_type.id is not None
            self._create_phases(uow, task_type.id, phases)
            for i, spec in enumerate(attributes or []):
                self._validate_reference_config(uow, project_id, spec)
                uow.attribute_definitions.add(
                    self._spec_to_definition(
                        task_type.id, {**spec, "order": spec.get("order", i)}
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
        finals = [s for s in specs if s.get("is_final")]
        if len(finals) != 1:
            raise ValidationError("task_type precisa de exatamente 1 fase final")
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
                    enter_conditions=spec.get("enter_conditions"),
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

    def update_type(
        self,
        type_id: int,
        name: str,
        description: str = "",
        color: str = "#888888",
        icon: str = "",
    ) -> TaskType:
        with UnitOfWork.open(self._db_path) as uow:
            task_type = uow.task_types.get(type_id)
            if task_type is None:
                raise NotFoundError(f"task_type {type_id} nao encontrado")
            task_type.name = name
            task_type.description = description
            task_type.color = color
            task_type.icon = icon
            uow.task_types.update(task_type)
            return task_type

    def add_phase(self, task_type_id: int, name: str, **kwargs) -> Phase:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.task_types.get(task_type_id) is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            phase = Phase(task_type_id=task_type_id, name=name, **kwargs)
            if phase.is_initial:
                uow.phases.unset_initials(task_type_id)
            if phase.is_final:
                uow.phases.unset_finals(task_type_id)
            return uow.phases.add(phase)

    def save_phases(self, task_type_id: int, specs: list[dict]) -> list[Phase]:
        """Salva o conjunto de fases de uma vez (cria as sem "id", atualiza as demais).

        Valida o estado FINAL (exatamente 1 inicial + 1 final no lote) em vez
        de validar a cada fase: updates sequenciais quebravam ao mover o papel
        inicial/final entre fases (ex: reordenar um tipo de 2 fases dizia
        "tipo precisa manter 1 fase final"). Roda em uma transacao unica.
        Specs com "id" precisam pertencer a este tipo.
        """
        with UnitOfWork.open(self._db_path) as uow:
            if uow.task_types.get(task_type_id) is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            if len([s for s in specs if s.get("is_initial")]) != 1:
                raise ValidationError("tipo precisa de exatamente 1 fase inicial")
            if len([s for s in specs if s.get("is_final")]) != 1:
                raise ValidationError("tipo precisa de exatamente 1 fase final")
            out: list[Phase] = []
            for i, spec in enumerate(specs):
                pid = spec.get("id")
                if pid is None:
                    phase = uow.phases.add(
                        Phase(
                            task_type_id=task_type_id,
                            name=spec.get("name", ""),
                            description=spec.get("description", ""),
                            color=spec.get("color", "#888888"),
                            order=int(spec.get("order", i)),
                            is_initial=bool(spec.get("is_initial", False)),
                            is_final=bool(spec.get("is_final", False)),
                            enter_conditions=spec.get("enter_conditions"),
                        )
                    )
                    if phase.is_initial:
                        uow.phases.unset_initials(task_type_id, except_id=phase.id)
                    if phase.is_final:
                        uow.phases.unset_finals(task_type_id, except_id=phase.id)
                    out.append(phase)
                else:
                    phase = uow.phases.get(pid)
                    if phase is None:
                        raise NotFoundError(f"phase {pid} nao encontrada")
                    if phase.task_type_id != task_type_id:
                        raise ValidationError("phase pertence a outro task_type")
                    phase.name = spec.get("name", phase.name)
                    if "description" in spec:
                        phase.description = spec["description"]
                    if "color" in spec:
                        phase.color = spec["color"]
                    if "order" in spec:
                        phase.order = int(spec["order"])
                    if "is_initial" in spec:
                        phase.is_initial = bool(spec["is_initial"])
                    if "is_final" in spec:
                        phase.is_final = bool(spec["is_final"])
                    if "enter_conditions" in spec:
                        phase.enter_conditions = spec["enter_conditions"]
                    if phase.is_initial:
                        uow.phases.unset_initials(task_type_id, except_id=pid)
                    if phase.is_final:
                        uow.phases.unset_finals(task_type_id, except_id=pid)
                    uow.phases.update(phase)
                    out.append(phase)
            return out

    def update_phase(self, phase_id: int, **fields) -> Phase:
        with UnitOfWork.open(self._db_path) as uow:
            phase = uow.phases.get(phase_id)
            if phase is None:
                raise NotFoundError(f"phase {phase_id} nao encontrada")
            for key, value in fields.items():
                setattr(phase, key, value)
            if phase.is_initial:
                uow.phases.unset_initials(phase.task_type_id, except_id=phase_id)
            else:
                others = [
                    p
                    for p in uow.phases.list_by_task_type(phase.task_type_id)
                    if p.id != phase_id and p.is_initial
                ]
                if not others:
                    raise ValidationError("tipo precisa manter 1 fase inicial")
            if phase.is_final:
                uow.phases.unset_finals(phase.task_type_id, except_id=phase_id)
            else:
                others = [
                    p
                    for p in uow.phases.list_by_task_type(phase.task_type_id)
                    if p.id != phase_id and p.is_final
                ]
                if not others:
                    raise ValidationError("tipo precisa manter 1 fase final")
            uow.phases.update(phase)
            return phase

    def delete_phase(self, phase_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            phase = uow.phases.get(phase_id)
            if phase is None:
                raise NotFoundError(f"phase {phase_id} nao encontrada")
            if phase.is_initial:
                others = [
                    p
                    for p in uow.phases.list_by_task_type(phase.task_type_id)
                    if p.id != phase_id
                ]
                if not any(p.is_initial for p in others):
                    raise ValidationError("nao e possivel excluir a unica fase inicial")
            if phase.is_final:
                others = [
                    p
                    for p in uow.phases.list_by_task_type(phase.task_type_id)
                    if p.id != phase_id
                ]
                if not any(p.is_final for p in others):
                    raise ValidationError("nao e possivel excluir a unica fase final")
            uow.phases.delete(phase_id)

    def add_attribute(self, task_type_id: int, spec: dict) -> AttributeDefinition:
        with UnitOfWork.open(self._db_path) as uow:
            task_type = uow.task_types.get(task_type_id)
            if task_type is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            self._validate_reference_config(uow, task_type.project_id, spec)
            try:
                return uow.attribute_definitions.add(
                    self._spec_to_definition(task_type_id, spec)
                )
            except sqlite3.IntegrityError as e:
                raise ValidationError("nome de atributo duplicado neste tipo") from e

    def update_attribute(self, definition_id: int, spec: dict) -> AttributeDefinition:
        with UnitOfWork.open(self._db_path) as uow:
            current = uow.attribute_definitions.get(definition_id)
            if current is None:
                raise NotFoundError(f"attribute {definition_id} nao encontrado")
            task_type = uow.task_types.get(current.task_type_id)
            project_id = task_type.project_id if task_type else None
            self._validate_reference_config(uow, project_id, spec)
            updated = self._spec_to_definition(current.task_type_id, spec)
            updated.id = definition_id
            updated.created_at = current.created_at
            try:
                uow.attribute_definitions.update(updated)
            except sqlite3.IntegrityError as e:
                raise ValidationError("nome de atributo duplicado neste tipo") from e
            return updated

    def delete_attribute(self, definition_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.attribute_definitions.get(definition_id) is None:
                raise NotFoundError(f"attribute {definition_id} nao encontrado")
            uow.attribute_definitions.delete(definition_id)

    @staticmethod
    def _validate_reference_config(uow, project_id: int | None, spec: dict) -> None:
        """Garante que o tipo alvo da referencia pertence ao mesmo projeto."""
        config = spec.get("reference_config")
        if not config:
            return
        if not isinstance(config, dict):
            raise ValidationError("reference_config deve ser um objeto")
        target_type_id = config.get("target_type_id")
        if target_type_id is None:
            return
        target = uow.task_types.get(int(target_type_id))
        if target is None:
            raise ValidationError("tipo alvo da referencia nao encontrado")
        if project_id is not None and target.project_id != project_id:
            raise ValidationError("tipo alvo da referencia e de outro projeto")

    @staticmethod
    def _spec_to_definition(task_type_id: int, spec: dict) -> AttributeDefinition:
        raw_options = spec.get("options")
        options = None
        if isinstance(raw_options, list):
            options = [str(o).strip() for o in raw_options]
            options = [o for o in options if o]
            if not options:
                options = None
        return AttributeDefinition(
            task_type_id=task_type_id,
            name=spec["name"],
            label=spec.get("label", spec["name"]),
            type=spec["type"],
            required=bool(spec.get("required", False)),
            default_value=spec.get("default_value", ""),
            reference_config=spec.get("reference_config"),
            options=options,
            order=int(spec.get("order", 0)),
        )

    def reorder_types(self, project_id: int, ordered_ids: list[int]) -> None:
        """Persiste a ordem visual dos tipos (posicao na lista = ordem).

        Valida que todos os ids pertencem ao projeto e que nenhum tipo do
        projeto ficou de fora (evita perda silenciosa).
        """
        with UnitOfWork.open(self._db_path) as uow:
            current = uow.task_types.list_by_project(project_id)
            current_ids = {t.id for t in current if t.id is not None}
            wanted = list(ordered_ids)
            if set(wanted) != current_ids or len(wanted) != len(current_ids):
                raise ValidationError("reordenacao invalida: ids nao conferem")
            for pos, tid in enumerate(wanted):
                uow.task_types.set_order(tid, pos)

    def move_type(self, project_id: int, type_id: int, delta: int) -> list[int]:
        """Move um tipo delta posicoes; retorna a nova ordem de ids."""
        with UnitOfWork.open(self._db_path) as uow:
            current = uow.task_types.list_by_project(project_id)
            ids = [t.id for t in current if t.id is not None]
        if type_id not in ids:
            raise NotFoundError(f"task_type {type_id} nao encontrado")
        pos = ids.index(type_id)
        new_pos = max(0, min(len(ids) - 1, pos + delta))
        if new_pos == pos:
            return ids
        ids.insert(new_pos, ids.pop(pos))
        self.reorder_types(project_id, ids)
        return ids

    def delete(self, type_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.task_types.get(type_id) is None:
                raise NotFoundError(f"task_type {type_id} nao encontrado")
            uow.task_types.delete(type_id)
