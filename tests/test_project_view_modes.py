"""Testes da visao Todos: Recentes vs Por tipo e fase (sem Qt + smoke offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from task_level.presentation.views.project_view import (
    VIEW_GROUPED,
    VIEW_RECENT,
    group_by_type_and_phase,
    sort_recent,
)


def _task(tid, type_id, phase_id, updated_hour):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=tid,
        task_type_id=type_id,
        phase_id=phase_id,
        title=f"T{tid}",
        created_at=base,
        updated_at=base + timedelta(hours=updated_hour),
    )


def _phase(pid, order):
    return SimpleNamespace(id=pid, order=order, name=f"P{pid}")


def test_sort_recent_mixed_recentes_no_topo():
    tasks = [_task(1, 1, 1, 1), _task(2, 1, 1, 5), _task(3, 2, 1, 3)]
    assert [t.id for t in sort_recent(tasks)] == [2, 3, 1]


def test_grouped_separa_por_tipo_e_ordena_pela_fase():
    phases = {10: _phase(10, 0), 20: _phase(20, 2)}
    tasks = [
        _task(1, 1, 20, 9),  # fase avancada mas antiga-na-fase? recente
        _task(2, 1, 10, 1),  # fase inicial deve vir antes
        _task(3, 2, 20, 4),
    ]
    grouped = group_by_type_and_phase(tasks, phases)
    assert set(grouped) == {1, 2}
    assert [t.id for t in grouped[1]] == [2, 1]
    assert [t.id for t in grouped[2]] == [3]


def test_grouped_mesma_fase_recentes_primeiro_e_sem_fase_no_fim():
    phases = {10: _phase(10, 0)}
    tasks = [_task(1, 1, 10, 1), _task(2, 1, 10, 7), _task(3, 1, None, 9)]
    grouped = group_by_type_and_phase(tasks, phases)
    assert [t.id for t in grouped[1]] == [2, 1, 3]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_project_view_todos_alterna_modos(tmp_path, qapp):
    from task_level.presentation.views.project_view import ProjectView
    from task_level.services import ProjectService, TaskService, TaskTypeService

    db = tmp_path / "modes.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(pid, "Bug")
    feat = types.create_type(pid, "Feature")
    svc = TaskService(db)
    svc.create_task(pid, bug.id, "B1")
    svc.create_task(pid, feat.id, "F1")

    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        # padrao: agrupado por tipo
        assert view._current_mode() == VIEW_GROUPED
        assert view._grouped_tree.topLevelItemCount() == 2
        assert view._all_stack.currentWidget() is view._grouped_tree

        # alterna para recentes: lista unica misturada
        idx = view._view_mode.findData(VIEW_RECENT)
        view._view_mode.setCurrentIndex(idx)
        assert view._all_list.count() == 2
        assert view._all_stack.currentWidget() is view._all_list
    finally:
        view.close()


def test_grouped_tree_copy_selection_tsv(tmp_path, qapp):
    """Shift/Ctrl+clique + Ctrl+C copia celulas em TSV (cola no Excel)."""
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QApplication

    from task_level.presentation.views.project_view import ProjectView
    from task_level.services import ProjectService, TaskService, TaskTypeService

    db = tmp_path / "copy.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid, "Bug", attributes=[{"name": "sev", "label": "Severidade", "type": "text"}]
    ).id
    TaskService(db).create_task(pid, tid, "B1", values={"sev": "alta"})
    TaskService(db).create_task(pid, tid, "B2", values={"sev": "baixa"})

    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        view._focus = {str(tid): ["sev"]}
        view._load_all()
        tree = view._grouped_tree
        assert tree.columnCount() == 4
        top = tree.topLevelItem(0)
        top.setExpanded(True)
        sm = tree.selectionModel()
        sm.select(
            tree.indexFromItem(top.child(0), 0), QItemSelectionModel.Select
        )
        sm.select(
            tree.indexFromItem(top.child(0), 3), QItemSelectionModel.Select
        )
        sm.select(
            tree.indexFromItem(top.child(1), 0), QItemSelectionModel.Select
        )
        sm.select(
            tree.indexFromItem(top.child(1), 3), QItemSelectionModel.Select
        )
        assert view._copy_tree_selection() is True
        text = QApplication.clipboard().text()
        rows = text.split("\n")
        assert len(rows) == 2
        assert all("\t" in r for r in rows)
        assert "B1" in text and "B2" in text
        tree.clearSelection()
        assert view._copy_tree_selection() is False
    finally:
        view.close()


def test_hide_final_tasks_checkbox(tmp_path, qapp):
    """Ocultar finalizadas: esconde e revela (Todos + Kanban)."""
    from task_level.data import UnitOfWork
    from task_level.presentation.views.project_view import ProjectView
    from task_level.presentation.widgets.kanban_board import KanbanBoard
    from task_level.services import ProjectService, TaskService, TaskTypeService

    db = tmp_path / "hide.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(pid, "Bug").id
    svc = TaskService(db)
    svc.create_task(pid, tid, "Aberta")
    done = svc.create_task(pid, tid, "Fechada")
    phases = sorted(
        UnitOfWork.open(db).phases.list_by_task_type(tid), key=lambda p: p.order
    )
    svc.move_phase(done.id, phases[1].id)
    svc.move_phase(done.id, phases[2].id)
    assert phases[2].is_final

    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        assert view._grouped_tree.topLevelItem(0).childCount() == 2
        view._chk_hide_final.setChecked(True)
        assert view._grouped_tree.topLevelItem(0).childCount() == 1
        idx = view._view_mode.findData(VIEW_RECENT)
        view._view_mode.setCurrentIndex(idx)
        assert view._all_list.count() == 1
        view._chk_hide_final.setChecked(False)
        assert view._all_list.count() == 2
    finally:
        view.close()
    hidden = KanbanBoard(db, pid, tid, hide_final=True)
    try:
        assert sum(lst.count() for _, _, lst in hidden._columns) == 1
    finally:
        hidden.close()
    shown = KanbanBoard(db, pid, tid)
    try:
        assert sum(lst.count() for _, _, lst in shown._columns) == 2
    finally:
        shown.close()


def test_reload_types_keeps_selected_filter(tmp_path, qapp):
    """Gerenciar tipos nao deve derrubar o filtro: continua vendo as tasks."""
    from task_level.presentation.views.project_view import ProjectView
    from task_level.services import ProjectService, TaskService, TaskTypeService

    db = tmp_path / "keep.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(pid, "Bug")
    types.create_type(pid, "Feature")
    TaskService(db).create_task(pid, bug.id, "B1")

    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        idx = view._type_filter.findData(bug.id)
        view._type_filter.setCurrentIndex(idx)  # abre o Kanban do Bug
        assert view._stack.currentWidget() is view._board_host
        view._reload_types()  # simula voltar do "Tipos de tarefa..."
        assert view._type_filter.currentData() == bug.id
        assert view._stack.currentWidget() is view._board_host
    finally:
        view.close()


def test_grouped_tree_keeps_expanded_and_full_names(tmp_path, qapp):
    """Grupos comecam fechados; recarregar preserva; coluna/tooltip completos."""
    from PySide6.QtWidgets import QHeaderView

    from task_level.presentation.views.project_view import ProjectView
    from task_level.services import ProjectService, TaskService, TaskTypeService

    db = tmp_path / "tree.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(pid, "Bug")
    feat = types.create_type(pid, "Feature")
    svc = TaskService(db)
    svc.create_task(pid, bug.id, "Um nome bem longo de task que nao pode cortar")
    svc.create_task(pid, feat.id, "F1")

    view = ProjectView(db, on_back=lambda: None)
    try:
        view.set_project(pid)
        tree = view._grouped_tree
        assert tree.header().sectionResizeMode(0) == QHeaderView.Interactive
        assert tree.topLevelItemCount() == 2
        assert tree.topLevelItem(0).isExpanded() is False  # comecam fechados
        assert tree.topLevelItem(1).isExpanded() is False
        assert tree.columnWidth(0) > 0  # parte do tamanho do conteudo
        first = tree.topLevelItem(0)
        assert first.toolTip(0) == first.text(0)
        assert "Um nome bem longo" in first.child(0).toolTip(0)
        assert first.child(0).toolTip(1) == first.child(0).text(1)
        assert "2026" in first.child(0).toolTip(2)  # tooltip c/ ano completo
        first.setExpanded(True)  # usuario abre um grupo...
        view._load_grouped_tree()  # ...atualiza (ex: editou task)...
        assert tree.topLevelItem(0).isExpanded() is True  # ...continua aberto
        assert tree.topLevelItem(1).isExpanded() is False  # ...e o outro fechado
    finally:
        view.close()
