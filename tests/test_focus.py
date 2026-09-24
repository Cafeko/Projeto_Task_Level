"""Testes do Foco: atributos visiveis inline (offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from task_level.presentation.views.project_view import ProjectView
from task_level.presentation.widgets.kanban_board import KanbanBoard
from task_level.services import ProjectService, TaskService, TaskTypeService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def setup(tmp_path):
    db = tmp_path / "focus.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(
        pid,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text"},
            {"name": "preco", "label": "Preco", "type": "currency"},
        ],
    )
    svc = TaskService(db)
    svc.create_task(pid, bug.id, "B1", values={"sev": "alta", "preco": 10})
    svc.create_task(pid, bug.id, "B2", values={"sev": "baixa"})
    return db, pid, bug.id


def test_focus_dialog_roundtrip(tmp_path, qapp):
    from task_level.presentation.dialogs.focus_dialog import FocusDialog

    db = tmp_path / "fd.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid, "T", attributes=[{"name": "a", "label": "A", "type": "text"}]
    ).id
    dlg = FocusDialog(None, db, pid, tid, ["a"])
    try:
        assert dlg._list.count() == 1
        assert dlg._list.item(0).checkState().name == "Checked"
        assert dlg.data() == (tid, ["a"])
    finally:
        dlg.close()


def test_recent_list_shows_focus_values(setup, qapp):
    db, pid, _tid = setup
    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        idx = view._view_mode.findData("recent")
        view._view_mode.setCurrentIndex(idx)
        assert "Severidade" not in view._all_list.item(0).text()
        view._focus = {str(view._type_filter.itemData(1)): ["sev", "preco"]}
        view._load_all()
        texts = [view._all_list.item(i).text() for i in range(view._all_list.count())]
        assert any("Severidade: alta" in t for t in texts)
        assert any("Preco: R$ 10,00" in t for t in texts)
    finally:
        view.close()


def test_grouped_tree_focus_columns(setup, qapp):
    db, pid, _tid = setup
    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        tree = view._grouped_tree
        assert tree.columnCount() == 3
        view._focus = {str(view._type_filter.itemData(1)): ["sev"]}
        view._load_all()
        assert tree.columnCount() == 4
        assert tree.headerItem().text(3) == "Severidade"
        header = tree.topLevelItem(0)
        cells = {header.child(i).text(3) for i in range(header.childCount())}
        assert cells == {"alta", "baixa"}
    finally:
        view.close()


def test_kanban_cards_show_focus(setup, qapp):
    db, pid, tid = setup
    board = KanbanBoard(db, pid, tid, focus=["sev"])
    try:
        _, _, lst = board._columns[0]
        assert lst.count() == 2
        assert "Severidade: alta" in lst.item(0).text()
    finally:
        board.close()


def test_focus_reference_shows_value_not_pointer(tmp_path, qapp):
    """Foco em referencia mostra o valor (#N Titulo / atributo alvo)."""
    db = tmp_path / "ref.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(
        pid, "Bug", attributes=[{"name": "sev", "label": "Severidade", "type": "text"}]
    )
    feat = types.create_type(
        pid,
        "Feature",
        attributes=[
            {"name": "bloq", "label": "Bloqueado por", "type": "reference_task"},
            {
                "name": "orig",
                "label": "Sev origem",
                "type": "reference_attribute",
                "reference_config": {"attribute_name": "sev"},
            },
        ],
    )
    svc = TaskService(db)
    b1 = svc.create_task(pid, bug.id, "Crash critico", values={"sev": "critica"})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(db) as uow:
        sev_def = uow.attribute_definitions.get_by_name(bug.id, "sev")
        sev_attr = uow.task_attributes.get(b1.id, sev_def.id)
    svc.create_task(
        pid, feat.id, "F1", values={"bloq": b1.id, "orig": (b1.id, sev_attr.id)}
    )
    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        view._focus = {str(feat.id): ["bloq", "orig"]}
        idx = view._view_mode.findData("recent")
        view._view_mode.setCurrentIndex(idx)
        texts = [view._all_list.item(i).text() for i in range(view._all_list.count())]
        feat_text = next(t for t in texts if "F1" in t)
        assert "Bloqueado por: #1 Crash critico" in feat_text
        assert "Sev origem: critica" in feat_text
        assert "task #1" not in feat_text.split("Bloqueado por:")[1].split("|")[0]
    finally:
        view.close()
    board = KanbanBoard(db, pid, feat.id, focus=["bloq", "orig"])
    try:
        _, _, lst = board._columns[0]
        assert "Bloqueado por: #1 Crash critico" in lst.item(0).text()
        assert "Sev origem: critica" in lst.item(0).text()
    finally:
        board.close()


def test_focus_composes_with_filters(setup, qapp):
    db, pid, tid = setup
    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        view._focus = {str(tid): ["sev"]}
        view._filters = [{"type_id": tid, "attr": "sev", "op": "eq", "value": "alta"}]
        idx = view._view_mode.findData("recent")
        view._view_mode.setCurrentIndex(idx)
        assert view._all_list.count() == 1
        assert "Severidade: alta" in view._all_list.item(0).text()
    finally:
        view.close()
