"""Lista de projetos: criar, renomear, excluir, abrir (Parte 7)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from task_level.domain import DomainError
from task_level.presentation.dialogs.project_dialog import ProjectDialog
from task_level.services import ProjectService


class ProjectListView(QWidget):
    def __init__(
        self,
        projects: ProjectService,
        on_open: Callable[[int], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._projects = projects
        self._on_open = on_open

        title = QLabel("Projetos")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.project_list = QListWidget()
        self.project_list.itemDoubleClicked.connect(self._open_selected)

        btn_new = QPushButton("Novo")
        btn_rename = QPushButton("Renomear")
        btn_delete = QPushButton("Excluir")
        btn_open = QPushButton("Abrir")
        btn_new.clicked.connect(self._create)
        btn_rename.clicked.connect(self._rename)
        btn_delete.clicked.connect(self._delete)
        btn_open.clicked.connect(self._open_selected)

        buttons = QHBoxLayout()
        for b in (btn_new, btn_rename, btn_delete, btn_open):
            buttons.addWidget(b)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.project_list)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        self.project_list.clear()
        try:
            items = self._projects.list()
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        for p in items:
            item = QListWidgetItem(p.name)
            item.setData(Qt.UserRole, p.id)
            self.project_list.addItem(item)

    def _selected_id(self) -> int | None:
        item = self.project_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _create(self) -> None:
        result = ProjectDialog.create(self)
        if result is None:
            return
        try:
            self._projects.create(*result)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()

    def _rename(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        try:
            project = self._projects.get(pid)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        result = ProjectDialog.edit(self, project)
        if result is None:
            return
        try:
            self._projects.rename(pid, *result)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()

    def _delete(self) -> None:
        pid = self._selected_id()
        if pid is None:
            return
        answer = QMessageBox.question(
            self,
            "Excluir projeto",
            "Excluir o projeto e TODOS os seus tipos e tasks? Essa acao nao tem volta.",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self._projects.delete(pid)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()

    def _open_selected(self) -> None:
        pid = self._selected_id()
        if pid is not None:
            self._on_open(pid)
