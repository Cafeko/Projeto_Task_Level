"""Testes Parte 8: edicao de tipos + dialogs (offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from task_level.domain import ValidationError
from task_level.presentation.dialogs.task_type_dialog import validate_type_payload
from task_level.services import ProjectService, TaskTypeService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def types(tmp_path):
    db = tmp_path / "types.db"
    p = ProjectService(db).create("P1")
    return TaskTypeService(db), p.id


def test_validate_type_payload_pure():
    assert validate_type_payload({"name": "", "phases": [], "attributes": []}) != []
    ok = {
        "name": "Bug",
        "phases": [{"name": "Novo", "is_initial": True}],
        "attributes": [{"name": "a"}, {"name": "b"}],
    }
    assert validate_type_payload(ok) == []
    two_initial = {
        "name": "Bug",
        "phases": [
            {"name": "A", "is_initial": True},
            {"name": "B", "is_initial": True},
        ],
        "attributes": [],
    }
    assert validate_type_payload(two_initial) != []
    dup_attr = {
        "name": "Bug",
        "phases": [{"name": "A", "is_initial": True}],
        "attributes": [{"name": "x"}, {"name": "x"}],
    }
    assert validate_type_payload(dup_attr) != []


def test_update_type_and_phase_flow(types):
    svc, pid = types
    t = svc.create_type(pid, "Bug")
    updated = svc.update_type(t.id, "Bugfix", color="#ff0000")
    assert updated.name == "Bugfix" and updated.color == "#ff0000"

    phases_before = svc.get(t.id)
    assert phases_before is not None
    from task_level.data import UnitOfWork

    with UnitOfWork.open(svc._db_path) as uow:
        initial = uow.phases.initial_of_type(t.id)
    renamed = svc.update_phase(initial.id, name="Triagem")
    assert renamed.name == "Triagem" and renamed.is_initial

    with pytest.raises(ValidationError):
        svc.delete_phase(initial.id)  # unica inicial


def test_update_attribute_duplicate_name(types):
    svc, pid = types
    t = svc.create_type(
        pid,
        "T",
        attributes=[
            {"name": "a", "label": "A", "type": "text"},
            {"name": "b", "label": "B", "type": "text"},
        ],
    )
    from task_level.data import UnitOfWork

    with UnitOfWork.open(svc._db_path) as uow:
        b = uow.attribute_definitions.get_by_name(t.id, "b")
    with pytest.raises(ValidationError):
        svc.update_attribute(
            b.id, {"name": "a", "label": "A2", "type": "text", "order": 1}
        )


def test_task_type_dialog_payload_roundtrip(tmp_path, qapp):
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog()
    try:
        assert validate_type_payload(dlg.payload()) != []
        dlg._name.setText("Bug")
        dlg._phases.append({"name": "Novo", "is_initial": True, "is_final": False})
        payload = dlg.payload()
        assert validate_type_payload(payload) == []
        assert payload["name"] == "Bug"
    finally:
        dlg.close()


def test_manager_dialog_lists_types(tmp_path, qapp):
    from task_level.presentation.dialogs.task_type_manager_dialog import (
        TaskTypeManagerDialog,
    )

    db = tmp_path / "mgr.db"
    pid = ProjectService(db).create("P1").id
    TaskTypeService(db).create_type(pid, "Bug")
    dlg = TaskTypeManagerDialog(None, db, pid)
    try:
        assert dlg._list.count() == 1
    finally:
        dlg.close()
