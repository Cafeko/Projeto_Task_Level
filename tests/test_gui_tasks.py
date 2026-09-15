"""Testes Parte 9: dialog de task + kanban (offscreen) + update_details."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from task_level.presentation.widgets.kanban_board import KanbanBoard
from task_level.services import ProjectService, TaskService, TaskTypeService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def setup(tmp_path):
    db = tmp_path / "tasks.db"
    p = ProjectService(db).create("P1")
    types = TaskTypeService(db)
    t = types.create_type(
        p.id,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text", "required": True},
            {"name": "ativo", "label": "Ativo", "type": "boolean"},
        ],
    )
    return db, p.id, t.id


def test_update_details_and_clear_attribute(setup):
    db, pid, tid = setup
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1", values={"sev": "alta", "ativo": True})
    updated = svc.update_details(task.id, "T1-renamed", "desc")
    assert updated.title == "T1-renamed" and updated.description == "desc"
    svc.clear_attribute(task.id, "sev")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(db) as uow:
        sev_def = uow.attribute_definitions.get_by_name(tid, "sev")
        assert uow.task_attributes.get(task.id, sev_def.id) is None


def test_task_dialog_payload(setup, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db, pid, _tid = setup
    dlg = TaskDialog(None, db, pid)
    try:
        assert dlg._type_combo.count() == 1
        dlg._title.setText("Bug #1")
        sev_widget = dlg._fields["sev"]
        sev_widget.setText("alta")
        payload = dlg.payload()
        assert payload["title"] == "Bug #1"
        assert payload["values"] == {"sev": "alta", "ativo": False}
    finally:
        dlg.close()


def test_kanban_board_columns_and_move(setup, qapp):
    db, pid, tid = setup
    svc = TaskService(db)
    a = svc.create_task(pid, tid, "A", values={"sev": "alta"})
    board = KanbanBoard(db, pid, tid)
    try:
        assert len(board._columns) == 3
        first_col_tasks = board._columns[0][2].count()
        assert first_col_tasks == 1
        from task_level.data import UnitOfWork

        with UnitOfWork.open(db) as uow:
            final = [p for p in uow.phases.list_by_task_type(tid) if p.is_final][0]
        svc.set_attribute(a.id, "sev", "alta")
        board._move_task(a.id, final.id)
        counts = [lst.count() for _, _, lst in board._columns]
        assert sum(counts) == 1 and counts[-1] == 1
    finally:
        board.close()
