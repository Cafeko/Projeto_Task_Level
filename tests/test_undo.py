"""Testes do log de mudancas + desfazer/refazer."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from task_level.data import UnitOfWork
from task_level.domain import NotFoundError
from task_level.services import ProjectService, TaskService, TaskTypeService
from task_level.services.undo import EmptyHistory, UndoManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def setup(tmp_path):
    db = tmp_path / "undo.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid,
        "Bug",
        attributes=[{"name": "sev", "label": "Severidade", "type": "text"}],
    ).id
    svc = TaskService(db)
    return db, pid, tid, svc


def _actions(db, pid):
    with UnitOfWork.open(db) as uow:
        return [e.action for e in uow.activity.list_by_project(pid)]


def test_mutations_are_logged(setup):
    db, pid, tid, svc = setup
    t = svc.create_task(pid, tid, "B1", values={"sev": "alta"})
    svc.update_details(t.id, "B1b")
    svc.move_phase(t.id, svc.neighbors(t.id)[1].id)
    actions = _actions(db, pid)
    assert actions == ["moved", "updated", "created"]  # recentes primeiro


def test_undo_redo_details(setup):
    _db, _pid, _tid, svc = setup
    t = svc.create_task(_pid, _tid, "B1")
    mgr = UndoManager.for_db(svc._db_path)
    svc.update_details(t.id, "B2")
    assert svc.get(t.id).title == "B2"
    assert mgr.undo(svc) == "editar 'B2'"
    assert svc.get(t.id).title == "B1"
    assert mgr.redo(svc) == "editar 'B2'"
    assert svc.get(t.id).title == "B2"


def test_undo_redo_attribute(setup):
    _db, _pid, _tid, svc = setup
    t = svc.create_task(_pid, _tid, "B1", values={"sev": "alta"})
    mgr = UndoManager.for_db(svc._db_path)
    svc.set_attribute(t.id, "sev", "baixa")
    svc.clear_attribute(t.id, "sev")
    mgr.undo(svc)  # desfaz o limpar -> volta "baixa"
    _d, raw = svc._read_attr_raw(t.id, "sev")
    assert raw == "baixa"
    mgr.undo(svc)  # desfaz o set -> volta "alta"
    _d, raw = svc._read_attr_raw(t.id, "sev")
    assert raw == "alta"
    mgr.redo(svc)  # refaz o set -> "baixa"
    _d, raw = svc._read_attr_raw(t.id, "sev")
    assert raw == "baixa"


def test_undo_redo_move(setup):
    _db, _pid, _tid, svc = setup
    t = svc.create_task(_pid, _tid, "B1")
    mgr = UndoManager.for_db(svc._db_path)
    nxt = svc.neighbors(t.id)[1]
    svc.move_phase(t.id, nxt.id)
    assert svc.get(t.id).phase_id == nxt.id
    mgr.undo(svc)
    assert svc.get(t.id).phase_id == t.phase_id
    mgr.redo(svc)
    assert svc.get(t.id).phase_id == nxt.id


def test_undo_create_deletes_redo_restores_same_id(setup):
    _db, _pid, _tid, svc = setup
    t = svc.create_task(_pid, _tid, "B1")
    mgr = UndoManager.for_db(svc._db_path)
    mgr.undo(svc)  # desfaz criacao -> apaga
    with pytest.raises(NotFoundError):
        svc.get(t.id)
    mgr.redo(svc)  # refaz -> volta com mesmo id
    assert svc.get(t.id).title == "B1"


def test_undo_delete_restores_with_values(setup):
    _db, _pid, _tid, svc = setup
    t = svc.create_task(_pid, _tid, "B1", values={"sev": "alta"})
    mgr = UndoManager.for_db(svc._db_path)
    svc.delete(t.id)
    mgr.undo(svc)
    restored = svc.get(t.id)
    assert restored.title == "B1"
    _d, raw = svc._read_attr_raw(t.id, "sev")
    assert raw == "alta"
    mgr.redo(svc)
    with pytest.raises(NotFoundError):
        svc.get(t.id)


def test_redo_cleared_on_new_action(setup):
    _db, _pid, _tid, svc = setup
    t = svc.create_task(_pid, _tid, "B1")
    mgr = UndoManager.for_db(svc._db_path)
    svc.update_details(t.id, "B2")
    mgr.undo(svc)
    assert mgr.can_redo()
    svc.update_details(t.id, "B3")  # nova acao limpa redo
    assert not mgr.can_redo()
    assert svc.get(t.id).title == "B3"


def test_undo_does_not_spam_log(setup):
    db, pid, tid, svc = setup
    svc.create_task(pid, tid, "B1")
    before = len(_actions(db, pid))
    UndoManager.for_db(svc._db_path).undo(svc)
    UndoManager.for_db(svc._db_path).redo(svc)
    assert len(_actions(db, pid)) == before


def test_empty_history_raises(tmp_path):
    mgr = UndoManager.for_db(tmp_path / "fresh.db")
    svc = TaskService(tmp_path / "fresh.db")
    with pytest.raises(EmptyHistory):
        mgr.undo(svc)
    with pytest.raises(EmptyHistory):
        mgr.redo(svc)


def test_file_undo_restores_content(tmp_path):
    from task_level.data.files import attachments_root

    db = tmp_path / "uf.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid, "T", attributes=[{"name": "doc", "label": "Doc", "type": "file"}]
    ).id
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1")
    src = tmp_path / "a.txt"
    src.write_text("v1", encoding="utf-8")
    svc.set_file_attribute(task.id, "doc", src)
    mgr = UndoManager.for_db(db)
    _d, raw = svc._read_attr_raw(task.id, "doc")
    assert raw is not None and Path(raw).is_file()
    mgr.undo(svc)  # desfaz anexo -> sem valor, arquivo na lixeira
    _d, raw = svc._read_attr_raw(task.id, "doc")
    assert raw is None
    assert not any(
        p.is_file() for p in attachments_root(db).rglob("*") if ".trash" not in p.parts
    )
    mgr.redo(svc)  # refaz -> arquivo de volta com conteudo
    _d, raw = svc._read_attr_raw(task.id, "doc")
    assert raw is not None and Path(raw).read_text(encoding="utf-8") == "v1"


def test_history_dialog_lists_entries(setup, qapp):
    from task_level.presentation.dialogs.history_dialog import HistoryDialog

    db, pid, tid, svc = setup
    svc.create_task(pid, tid, "B1")
    dlg = HistoryDialog(None, db, pid)
    try:
        assert dlg._list.count() >= 1
        assert "criada" in dlg._list.item(0).text()
        dlg._search.setText("B1")
        assert dlg._list.count() >= 1
        dlg._search.setText("zzz-nada")
        assert dlg._list.count() == 0
    finally:
        dlg.close()
