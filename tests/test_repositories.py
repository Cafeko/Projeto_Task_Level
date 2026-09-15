"""Testes Parte 4: repositories + UnitOfWork."""

import pytest

from task_level.data import UnitOfWork
from task_level.domain import (
    AttributeDefinition,
    Phase,
    Project,
    Task,
    TaskAttribute,
)


@pytest.fixture()
def uow(tmp_path):
    u = UnitOfWork.open(tmp_path / "repo.db")
    yield u
    u.close()


def _project(uow: UnitOfWork) -> Project:
    with uow:
        return uow.projects.add(Project(name="P1"))


def _full_setup(uow: UnitOfWork):
    """Projeto + tipo + fase inicial + definicao texto. Retorna ids."""
    from task_level.domain import TaskType

    with uow:
        p = uow.projects.add(Project(name="P1"))
        t = uow.task_types.add(TaskType(project_id=p.id, name="Bug"))
        ph = uow.phases.add(Phase(task_type_id=t.id, name="Backlog", is_initial=True))
        ad = uow.attribute_definitions.add(
            AttributeDefinition(
                task_type_id=t.id, name="sev", label="Severidade", type="text"
            )
        )
    assert p.id is not None and t.id is not None
    assert ph.id is not None and ad.id is not None
    return p, t, ph, ad


def test_project_crud(uow):
    p = _project(uow)
    assert p.id is not None
    assert uow.projects.get(p.id).name == "P1"
    assert len(uow.projects.list()) == 1
    p.name = "P1-renamed"
    with uow:
        uow.projects.update(p)
    assert uow.projects.get(p.id).name == "P1-renamed"
    with uow:
        uow.projects.delete(p.id)
    assert uow.projects.get(p.id) is None


def test_task_type_and_phase_flow(uow):
    p, t, ph, _ad = _full_setup(uow)
    assert uow.task_types.list_by_project(p.id) != []
    assert uow.phases.initial_of_type(t.id).id == ph.id


def test_attribute_definition_json_config(uow):
    _p, t, _ph, _ad = _full_setup(uow)
    with uow:
        ref = uow.attribute_definitions.add(
            AttributeDefinition(
                task_type_id=t.id,
                name="bloqueado_por",
                label="Bloqueado por",
                type="reference_task",
                reference_config={"scope": "project"},
            )
        )
    got = uow.attribute_definitions.get_by_name(t.id, "bloqueado_por")
    assert got is not None and got.reference_config == {"scope": "project"}
    assert ref.id == got.id


def test_task_and_attribute_upsert(uow):
    p, t, ph, ad = _full_setup(uow)
    with uow:
        task = uow.tasks.add(
            Task(project_id=p.id, task_type_id=t.id, phase_id=ph.id, title="Bug #1")
        )
        uow.task_attributes.set(
            TaskAttribute(
                task_id=task.id, attribute_definition_id=ad.id, value_text="alta"
            ),
            "text",
        )
        uow.task_attributes.set(
            TaskAttribute(
                task_id=task.id, attribute_definition_id=ad.id, value_text="baixa"
            ),
            "text",
        )
    rows = uow.task_attributes.list_by_task(task.id)
    assert len(rows) == 1 and rows[0].value_text == "baixa"


def test_referenced_task_ids(uow):
    p, t, ph, _ad = _full_setup(uow)
    with uow:
        a = uow.tasks.add(
            Task(project_id=p.id, task_type_id=t.id, phase_id=ph.id, title="A")
        )
        b = uow.tasks.add(
            Task(project_id=p.id, task_type_id=t.id, phase_id=ph.id, title="B")
        )
        ref_def = uow.attribute_definitions.add(
            AttributeDefinition(
                task_type_id=t.id,
                name="rel",
                label="Rel",
                type="reference_task",
            )
        )
        uow.task_attributes.set(
            TaskAttribute(
                task_id=a.id,
                attribute_definition_id=ref_def.id,
                value_reference_task_id=b.id,
            ),
            "reference_task",
        )
    assert uow.task_attributes.referenced_task_ids(a.id) == {b.id}
    assert uow.task_attributes.referenced_task_ids(b.id) == set()


def test_uow_rollback_on_error(uow):
    _project(uow)
    with pytest.raises(RuntimeError):
        with uow:
            uow.projects.add(Project(name="P2"))
            raise RuntimeError("boom")
    assert len(uow.projects.list()) == 1
