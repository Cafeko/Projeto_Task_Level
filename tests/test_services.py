"""Testes Parte 5: services (fluxo completo + ciclos + fases)."""

import pytest

from task_level.domain import CircularReferenceError, NotFoundError, ValidationError
from task_level.services import ProjectService, TaskService, TaskTypeService


@pytest.fixture()
def services(tmp_path):
    db = tmp_path / "svc.db"
    return (
        ProjectService(db),
        TaskTypeService(db),
        TaskService(db),
    )


def _bug_type(task_types, project_id):
    return task_types.create_type(
        project_id,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text", "required": True},
            {"name": "rel", "label": "Relacionada", "type": "reference_task"},
        ],
    )


def test_full_flow_create_move_final(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = _bug_type(task_types, p.id)
    task = tasks.create_task(p.id, t.id, "Bug #1")
    assert task.phase_id is not None and task.completed_at is None

    # mover para fase final sem required -> falha
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        final = [ph for ph in uow.phases.list_by_task_type(t.id) if ph.is_final][0]
    with pytest.raises(ValidationError):
        tasks.move_phase(task.id, final.id)
    # preenche required e move -> ok + completed_at setado
    tasks.set_attribute(task.id, "sev", "alta")
    moved = tasks.move_phase(task.id, final.id)
    assert moved.phase_id == final.id and moved.completed_at is not None


def test_reference_and_cycle_rejected(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = _bug_type(task_types, p.id)
    a = tasks.create_task(p.id, t.id, "A", values={"sev": "alta"})
    b = tasks.create_task(p.id, t.id, "B", values={"sev": "baixa"})
    tasks.set_attribute(a.id, "rel", b.id)  # A -> B ok
    with pytest.raises(CircularReferenceError):
        tasks.set_attribute(b.id, "rel", a.id)  # B -> A fecharia ciclo
    with pytest.raises(CircularReferenceError):
        tasks.set_attribute(a.id, "rel", a.id)  # auto-referencia


def test_reference_attribute_points_to_other_task_attr(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id,
        "T",
        attributes=[
            {"name": "nota", "label": "Nota", "type": "number"},
            {"name": "espelho", "label": "Espelho", "type": "reference_attribute"},
        ],
    )
    a = tasks.create_task(p.id, t.id, "A", values={"nota": 42})
    b = tasks.create_task(p.id, t.id, "B")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        nota_def = uow.attribute_definitions.get_by_name(t.id, "nota")
        nota_attr = uow.task_attributes.get(a.id, nota_def.id)
    tasks.set_attribute(b.id, "espelho", (a.id, nota_attr.id))
    with pytest.raises(NotFoundError):
        tasks.set_attribute(b.id, "espelho", (a.id, 999999))


def test_wrong_type_value_rejected(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id, "T", attributes=[{"name": "n", "label": "N", "type": "number"}]
    )
    task = tasks.create_task(p.id, t.id, "T1")
    with pytest.raises(ValidationError):
        tasks.set_attribute(task.id, "n", "nao-numerico")
    with pytest.raises(NotFoundError):
        tasks.set_attribute(task.id, "inexistente", "x")


def test_type_requires_single_initial_phase(services):
    projects, task_types, _tasks = services
    p = projects.create("P1")
    with pytest.raises(ValidationError):
        task_types.create_type(
            p.id, "Ruim", phases=[{"name": "A"}, {"name": "B"}]
        )
