"""Smoke tests da GUI em modo offscreen (Parte 7)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from task_level.presentation.main_window import MainWindow
from task_level.services import ProjectService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_lists_projects(tmp_path, qapp):
    db = tmp_path / "gui.db"
    pid = ProjectService(db).create("P1").id
    win = MainWindow(db)
    try:
        assert win.windowTitle() == "Task Level"
        assert win.list_view.project_list.count() == 1
        win.open_project(pid)
        assert win.stack.currentWidget() is win.project_view
        assert "P1" in win.project_view._title.text()
        win.show_projects()
        assert win.stack.currentWidget() is win.list_view
    finally:
        win.close()
