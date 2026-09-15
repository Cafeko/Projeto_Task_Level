"""Visao do projeto (placeholder: tasks entram na Parte 9)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from task_level.domain import DomainError
from task_level.services import ProjectService


class ProjectView(QWidget):
    def __init__(
        self,
        db_path: str | Path,
        on_back: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._projects = ProjectService(db_path)
        self._on_back = on_back
        self.project_id: int | None = None

        self._title = QLabel("")
        self._title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._info = QLabel("Gestao de tasks entra na Parte 9.")
        self._info.setStyleSheet("color: gray;")

        btn_back = QPushButton("Voltar")
        btn_back.clicked.connect(self._on_back)
        top = QHBoxLayout()
        top.addWidget(btn_back)
        top.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._title)
        layout.addWidget(self._info)
        layout.addStretch()

    def set_project(self, project_id: int) -> None:
        try:
            project = self._projects.get(project_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.project_id = project_id
        self._title.setText(f"#{project.id} {project.name}")
