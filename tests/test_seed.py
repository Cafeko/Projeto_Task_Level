"""Testes Parte 6: seed + integracao fim-a-fim."""

from task_level.data import UnitOfWork
from task_level.seed import seed_demo
from task_level.services import TaskService


def test_seed_demo_creates_linked_data(tmp_path):
    db = tmp_path / "seed.db"
    result = seed_demo(db)

    with UnitOfWork.open(db) as uow:
        assert len(uow.projects.list()) == 1
        types = uow.task_types.list_by_project(result["project_id"])
        assert len(types) == 2
        for t in types:
            assert len(uow.phases.list_by_task_type(t.id)) == 3

        b1_id, b2_id, f1_id = result["task_ids"]
        bug_id, feature_id = result["type_ids"]

        rel_def = uow.attribute_definitions.get_by_name(bug_id, "bloqueado_por")
        rel = uow.task_attributes.get(b2_id, rel_def.id)
        assert rel.value_reference_task_id == b1_id

        esp_def = uow.attribute_definitions.get_by_name(feature_id, "bug_origem")
        esp = uow.task_attributes.get(f1_id, esp_def.id)
        assert esp.value_reference_task_id == b1_id
        sev_def = uow.attribute_definitions.get_by_name(bug_id, "sev")
        sev = uow.task_attributes.get(b1_id, sev_def.id)
        assert esp.value_reference_attribute_id == sev.id
        assert sev.value_text == "critica"

        b1 = uow.tasks.get(b1_id)
        assert b1.completed_at is not None  # movida para fase final no seed


def test_seed_twice_creates_two_projects(tmp_path):
    db = tmp_path / "seed2.db"
    seed_demo(db)
    seed_demo(db)
    with UnitOfWork.open(db) as uow:
        assert len(uow.projects.list()) == 2
    assert len(TaskService(db).list_by_project(1)) == 3
