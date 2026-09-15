"""Visao do projeto: filtro por tipo + Kanban ou lista geral (Parte 9)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import DomainError
from task_level.presentation.dialogs.task_dialog import TaskDialog
from task_level.presentation.dialogs.task_type_manager_dialog import (
    TaskTypeManagerDialog,
)
from task_level.presentation.widgets.kanban_board import KanbanBoard
from task_level.services import ProjectService, TaskTypeService


class ProjectView(QWidget):
    def __init__(
        self,
        db_path: str | Path,
        on_back: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._projects = ProjectService(db_path)
        self._types = TaskTypeService(db_path)
        self._on_back = on_back
        self.project_id: int | None = None

        self._title = QLabel("")
        self._title.setStyleSheet("font-size: 18px; font-weight: bold;")

        btn_back = QPushButton("Voltar")
        btn_back.clicked.connect(self._on_back)
        self._type_filter = QComboBox()
        self._type_filter.currentIndexChanged.connect(self._filter_changed)
        btn_new = QPushButton("Nova task")
        btn_new.clicked.connect(self._new_task)
        btn_types = QPushButton("Tipos de tarefa...")
        btn_types.clicked.connect(self._manage_types)

        top = QHBoxLayout()
        top.addWidget(btn_back)
        top.addWidget(QLabel("Tipo:"))
        top.addWidget(self._type_filter)
        top.addWidget(btn_new)
        top.addWidget(btn_types)
        top.addStretch()

        self._all_list = QListWidget()
        self._all_list.itemDoubleClicked.connect(self._open_from_list)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._all_list)
        self._board_host = QWidget()
        self._board_layout = QVBoxLayout(self._board_host)
        self._stack.addWidget(self._board_host)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._title)
        layout.addWidget(self._stack)

    # -- navegacao --------------------------------------------------------------

    def set_project(self, project_id: int) -> None:
        try:
            project = self._projects.get(project_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.project_id = project_id
        self._title.setText(f"#{project.id} {project.name}")
        self._reload_types()

    def _reload_types(self) -> None:
        self._type_filter.blockSignals(True)
        self._type_filter.clear()
        self._type_filter.addItem("Todos", None)
        try:
            types = self._types.list_by_project(self.project_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            types = []
        for t in types:
            self._type_filter.addItem(t.name, t.id)
        self._type_filter.blockSignals(False)
        self._filter_changed()

    def _filter_changed(self) -> None:
        type_id = self._type_filter.currentData()
        if type_id is None:
            self._load_all_list()
            self._stack.setCurrentWidget(self._all_list)
        else:
            self._show_board(type_id)

    # -- lista geral --------------------------------------------------------------

    def _load_all_list(self) -> None:
        self._all_list.clear()
        if self.project_id is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            types = {t.id: t for t in uow.task_types.list_by_project(self.project_id)}
            phases = {}
            for tid in types:
                for p in uow.phases.list_by_task_type(tid):
                    phases[p.id] = p
            tasks = uow.tasks.list_by_project(self.project_id)
        for t in tasks:
            type_name = types[t.task_type_id].name if t.task_type_id in types else "?"
            phase_name = phases[t.phase_id].name if t.phase_id in phases else "-"
            item = QListWidgetItem(f"[{type_name}] #{t.id} {t.title}  ({phase_name})")
            item.setData(Qt.UserRole, t.id)
            self._all_list.addItem(item)

    def _open_from_list(self, item: QListWidgetItem) -> None:
        if TaskDialog.edit(self, self._db_path, self.project_id, item.data(Qt.UserRole)):
            self._load_all_list()

    # -- kanban ---------------------------------------------------------------------

    def _show_board(self, type_id: int) -> None:
        while self._board_layout.count():
            item = self._board_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        board = KanbanBoard(
            self._db_path, self.project_id, type_id, on_changed=self._board_changed
        )
        self._board_layout.addWidget(board)
        self._stack.setCurrentWidget(self._board_host)

    def _board_changed(self) -> None:
        pass  # contadores ja atualizados no refresh do board

    # -- acoes ------------------------------------------------------------------------

    def _new_task(self) -> None:
        if self.project_id is None:
            return
        type_id = self._type_filter.currentData()
        created = TaskDialog.create(self, self._db_path, self.project_id, type_id)
        if created is not None:
            self._filter_changed()

    def _manage_types(self) -> None:
        if self.project_id is None:
            return
        TaskTypeManagerDialog(self, self._db_path, self.project_id).exec()
        self._reload_types()
