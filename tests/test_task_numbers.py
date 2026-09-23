"""Numeracao visivel da task: sequencial por tipo (#1, #2... por tipo).

Sem ids antes de projeto/tipo; numero da task e por tipo e estavel
(excluir nao renumera: nova task = MAX+1 do tipo).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from task_level.data import UnitOfWork
from task_level.services import ProjectService, TaskService, TaskTypeService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def setup(tmp_path):
    db = tmp_path / "nums.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(pid, "Bug")
    feat = types.create_type(pid, "Feature")
    return db, pid, bug.id, feat.id


def test_seq_independente_por_tipo(setup):
    db, pid, bug, feat = setup
    svc = TaskService(db)
    b1 = svc.create_task(pid, bug, "B1")
    b2 = svc.create_task(pid, bug, "B2")
    f1 = svc.create_task(pid, feat, "F1")
    assert (b1.seq, b2.seq, f1.seq) == (1, 2, 1)
    assert svc.get(b1.id).seq == 1
    assert svc.get(f1.id).seq == 1


def test_seq_estavel_excluir_nao_renumera(setup):
    db, pid, bug, _feat = setup
    svc = TaskService(db)
    b1 = svc.create_task(pid, bug, "B1")
    svc.create_task(pid, bug, "B2")
    svc.delete(b1.id)
    b3 = svc.create_task(pid, bug, "B3")
    assert b3.seq == 3  # nao reaproveita o 1
    assert sorted(t.seq for t in svc.list_by_project(pid, bug)) == [2, 3]


def test_undo_delete_mantem_seq(setup):
    db, pid, bug, _feat = setup
    svc = TaskService(db)
    b1 = svc.create_task(pid, bug, "B1")
    svc.delete(b1.id)
    svc._undo_manager().undo(svc)
    assert svc.get(b1.id).seq == 1


def test_summary_usa_seq(setup):
    db, pid, bug, _feat = setup
    svc = TaskService(db)
    b1 = svc.create_task(pid, bug, "B1")
    with UnitOfWork.open(db) as uow:
        entries = uow.activity.list_by_project(pid)
    assert entries[0].summary == f"#{b1.seq} B1 criada"


def test_migration_v6_backfill_por_tipo(tmp_path):
    """Banco pre-V6 (sem coluna seq) ganha numeracao por tipo ordenada por id."""
    from task_level.data import database

    db = tmp_path / "old.db"
    conn = database.connect(db)
    database.applied_versions(conn)  # cria schema_migrations
    mig = database.migrations_dir()
    conn.executescript((mig / "V1__init.sql").read_text(encoding="utf-8"))
    for name in (
        "V2__attribute_options.sql",
        "V3__task_phase_notes.sql",
        "V4__phase_conditions.sql",
        "V5__activity_log.sql",
    ):
        conn.executescript((mig / name).read_text(encoding="utf-8"))
    for v in (1, 2, 3, 4, 5):
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (v, "2026-01-01T00:00:00Z"),
        )
    conn.execute(
        "INSERT INTO projects (id, name, description, created_at, updated_at)"
        " VALUES (1, 'P', '', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO task_types (id, project_id, name, description, color, icon,"
        " created_at) VALUES (10, 1, 'A', '', '#888', '', '2026-01-01T00:00:00Z'),"
        " (20, 1, 'B', '', '#888', '', '2026-01-01T00:00:00Z')"
    )
    # intercalados no id global: A=1, B=2, A=3
    conn.execute(
        "INSERT INTO tasks (id, project_id, task_type_id, phase_id, title,"
        " description, created_at, updated_at, completed_at)"
        " VALUES (1, 1, 10, NULL, 'A1', '', '2026-01-01T00:00:00Z',"
        " '2026-01-01T00:00:00Z', NULL),"
        " (2, 1, 20, NULL, 'B1', '', '2026-01-01T00:00:01Z',"
        " '2026-01-01T00:00:01Z', NULL),"
        " (3, 1, 10, NULL, 'A2', '', '2026-01-01T00:00:02Z',"
        " '2026-01-01T00:00:02Z', NULL)"
    )
    conn.commit()
    conn.close()

    conn = database.connect(db)
    try:
        assert 6 in database.migrate(conn)
        rows = {
            r[0]: r[1]
            for r in conn.execute("SELECT id, seq FROM tasks").fetchall()
        }
        assert rows == {1: 1, 2: 1, 3: 2}
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'idx_tasks_type_seq'"
        ).fetchone()
        assert idx is not None
    finally:
        conn.close()


def test_todos_mostra_seq_sem_ids(tmp_path, qapp):
    from task_level.presentation.views.project_view import ProjectView

    db = tmp_path / "view.db"
    pid = ProjectService(db).create("Meu Projeto").id
    types = TaskTypeService(db)
    bug = types.create_type(pid, "Bug").id
    feat = types.create_type(pid, "Feature").id
    svc = TaskService(db)
    svc.create_task(pid, bug, "B1")
    svc.create_task(pid, bug, "B2")
    svc.create_task(pid, feat, "F1")

    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        assert view._title.text() == "Meu Projeto"  # sem #id
        tree = view._grouped_tree
        headers = {tree.topLevelItem(i).text(0) for i in range(2)}
        assert all("#" not in h for h in headers)  # tipo sem #id
        children = set()
        for i in range(tree.topLevelItemCount()):
            header = tree.topLevelItem(i)
            children.update(
                header.child(j).text(0) for j in range(header.childCount())
            )
        assert children == {"#1 B1", "#2 B2", "#1 F1"}  # seq por tipo

        from task_level.presentation.views.project_view import VIEW_RECENT

        view._view_mode.setCurrentIndex(view._view_mode.findData(VIEW_RECENT))
        texts = [view._all_list.item(i).text() for i in range(3)]
        assert any(t.startswith("[Bug] #1 B1") for t in texts)
        assert any(t.startswith("[Bug] #2 B2") for t in texts)
        assert any(t.startswith("[Feature] #1 F1") for t in texts)
    finally:
        view.close()


def test_kanban_e_listas_sem_ids(tmp_path, qapp):
    from task_level.presentation.views.project_list_view import ProjectListView
    from task_level.presentation.widgets.kanban_board import KanbanBoard

    db = tmp_path / "lists.db"
    projects = ProjectService(db)
    pid = projects.create("Meu Projeto").id
    tid = TaskTypeService(db).create_type(pid, "Bug").id
    TaskService(db).create_task(pid, tid, "B1")

    plist = ProjectListView(projects, on_open=lambda _pid: None)
    try:
        plist.refresh()
        assert plist.project_list.item(0).text() == "Meu Projeto"
    finally:
        plist.close()

    board = KanbanBoard(db, pid, tid)
    try:
        first_col = board._columns[0][2]
        assert first_col.item(0).text().startswith("#1 B1")
        assert first_col.item(0).data(Qt.UserRole) is not None  # id segue interno
    finally:
        board.close()


def test_type_manager_sem_id(tmp_path, qapp):
    from task_level.presentation.dialogs.task_type_manager_dialog import (
        TaskTypeManagerDialog,
    )

    db = tmp_path / "types.db"
    pid = ProjectService(db).create("P1").id
    TaskTypeService(db).create_type(pid, "Bug", icon="🐞")
    dlg = TaskTypeManagerDialog(None, db, pid)
    try:
        assert dlg._list.item(0).text() == "🐞 Bug"
    finally:
        dlg.close()
