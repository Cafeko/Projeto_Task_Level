"""Janela principal com navegacao por pilha (Parte 7)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QStackedWidget

from task_level.presentation.views.project_list_view import ProjectListView
from task_level.presentation.views.project_view import ProjectView
from task_level.services import ProjectService, TaskService, TaskTypeService


class MainWindow(QMainWindow):
    def __init__(self, db_path: str | Path) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.projects = ProjectService(self.db_path)
        self.task_types = TaskTypeService(self.db_path)
        self.tasks = TaskService(self.db_path)

        self.setWindowTitle("Task Level")
        self.resize(1000, 700)

        self.list_view = ProjectListView(self.projects, self.open_project)
        self.project_view = ProjectView(self.db_path, self.show_projects)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.list_view)
        self.stack.addWidget(self.project_view)
        self.setCentralWidget(self.stack)

        self.show_projects()
        self.statusBar().showMessage(f"Banco: {self.db_path}")

    def show_projects(self) -> None:
        self.list_view.refresh()
        self.stack.setCurrentWidget(self.list_view)

    def open_project(self, project_id: int) -> None:
        self.project_view.set_project(project_id)
        self.stack.setCurrentWidget(self.project_view)
