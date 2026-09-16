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
