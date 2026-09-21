"""Visao do projeto: filtro por tipo + Kanban ou lista geral (Parte 9).

Modo "Todos" tem duas visoes (escolha do usuario):
- "Recentes": tudo misturado, mais recentes (created/updated) no topo.
- "Por tipo e fase": tasks separadas por tipo e ordenadas pela ordem da fase.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import DomainError, to_local
from task_level.presentation.dialogs.task_dialog import TaskDialog
from task_level.presentation.dialogs.task_type_manager_dialog import (
    TaskTypeManagerDialog,
)
from task_level.presentation.widgets.kanban_board import KanbanBoard
from task_level.presentation.widgets.type_badge import (
    make_color_icon,
    normalize_color,
    type_label,
)
from task_level.services import ProjectService, TaskTypeService

VIEW_RECENT = "recent"
VIEW_GROUPED = "grouped"


def _recency_key(task) -> datetime:
    """created/modificado mais recente primeiro (updated > created)."""
    candidates = [t for t in (task.updated_at, task.created_at) if t is not None]
    if candidates:
        return max(candidates)
    return datetime.min.replace(tzinfo=timezone.utc)


def sort_recent(tasks: list) -> list:
    """Tudo misturado, recentes no topo."""
    return sorted(tasks, key=_recency_key, reverse=True)


def group_by_type_and_phase(tasks: list, phases_by_id: dict) -> dict[int, list]:
    """Agrupa por task_type_id; dentro do grupo ordena por ordem da fase.

    Tasks sem fase valida vao para o fim do grupo. Desempate dentro da
    mesma fase: recentes no topo.
    """

    def phase_key(task) -> tuple:
        phase = phases_by_id.get(task.phase_id)
        if phase is None:
            return (1, 10**9, 10**9)
        return (0, phase.order, phase.id or 0)

    grouped: dict[int, list] = {}
    for task in tasks:
        grouped.setdefault(task.task_type_id, []).append(task)
    for type_id, items in grouped.items():
        by_phase: dict[tuple, list] = {}
        for t in items:
            by_phase.setdefault(phase_key(t), []).append(t)
        ordered: list = []
        for pk in sorted(by_phase):
            ordered.extend(sorted(by_phase[pk], key=_recency_key, reverse=True))
        grouped[type_id] = ordered
    return grouped


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
        self._view_mode = QComboBox()
        self._view_mode.addItem("Por tipo e fase", VIEW_GROUPED)
        self._view_mode.addItem("Recentes", VIEW_RECENT)
        self._view_mode.currentIndexChanged.connect(self._mode_changed)
        btn_new = QPushButton("Nova task")
        btn_new.clicked.connect(self._new_task)
        btn_types = QPushButton("Tipos de tarefa...")
        btn_types.clicked.connect(self._manage_types)

        top = QHBoxLayout()
        top.addWidget(btn_back)
        top.addWidget(QLabel("Tipo:"))
        top.addWidget(self._type_filter)
        self._view_label = QLabel("Visão:")
        top.addWidget(self._view_label)
        top.addWidget(self._view_mode)
        top.addWidget(btn_new)
        top.addWidget(btn_types)
        top.addStretch()

        self._all_list = QListWidget()
        self._all_list.itemDoubleClicked.connect(self._open_from_list)
        self._grouped_tree = QTreeWidget()
        self._grouped_tree.setHeaderLabels(["Task", "Fase", "Atualizada"])
        self._grouped_tree.itemDoubleClicked.connect(self._open_from_tree)
        # coluna parte do tamanho do conteudo, mas o usuario pode arrastar
        tree_header = self._grouped_tree.header()
        tree_header.setSectionResizeMode(0, QHeaderView.Interactive)
        tree_header.setSectionResizeMode(1, QHeaderView.Interactive)
        tree_header.setSectionResizeMode(2, QHeaderView.Interactive)
        tree_header.setStretchLastSection(False)

        self._all_stack = QStackedWidget()
        self._all_stack.addWidget(self._all_list)
        self._all_stack.addWidget(self._grouped_tree)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._all_stack)
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
        keep_type_id = self._type_filter.currentData()
        self._type_filter.blockSignals(True)
        self._type_filter.clear()
        self._type_filter.addItem("Todos", None)
        try:
            types = self._types.list_by_project(self.project_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            types = []
        for t in types:
            self._type_filter.addItem(type_label(t.name, t.icon), t.id)
            self._type_filter.setItemIcon(
                self._type_filter.count() - 1, make_color_icon(t.color)
            )
        if keep_type_id is not None:
            idx = self._type_filter.findData(keep_type_id)
            self._type_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self._type_filter.blockSignals(False)
        self._filter_changed()

    def _filter_changed(self) -> None:
        type_id = self._type_filter.currentData()
        show_mode = type_id is None
        self._view_label.setVisible(show_mode)
        self._view_mode.setVisible(show_mode)
        if type_id is None:
            self._load_all()
            self._stack.setCurrentWidget(self._all_stack)
        else:
            self._show_board(type_id)

    def _mode_changed(self) -> None:
        if self._type_filter.currentData() is None:
            self._load_all()

    def _current_mode(self) -> str:
        return self._view_mode.currentData() or VIEW_GROUPED

    # -- lista geral --------------------------------------------------------------

    def _load_all(self) -> None:
        if self._current_mode() == VIEW_RECENT:
            self._load_recent_list()
            self._all_stack.setCurrentWidget(self._all_list)
        else:
            self._load_grouped_tree()
            self._all_stack.setCurrentWidget(self._grouped_tree)

    def _load_recent_list(self) -> None:
        self._all_list.clear()
        if self.project_id is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            types = {t.id: t for t in uow.task_types.list_by_project(self.project_id)}
            phases = {}
            for tid in types:
                for p in uow.phases.list_by_task_type(tid):
                    phases[p.id] = p
            tasks = sort_recent(uow.tasks.list_by_project(self.project_id))
        for t in tasks:
            task_type = types.get(t.task_type_id)
            type_name = task_type.name if task_type else "?"
            type_icon = task_type.icon if task_type else ""
            type_color = task_type.color if task_type else None
            phase_name = phases[t.phase_id].name if t.phase_id in phases else "-"
            item = QListWidgetItem(
                f"[{type_label(type_name, type_icon)}] #{t.id} {t.title}  ({phase_name})"
            )
            item.setData(Qt.UserRole, t.id)
            item.setIcon(make_color_icon(type_color))
            self._all_list.addItem(item)

    def _load_grouped_tree(self) -> None:
        # lembra quais grupos estavam abertos p/ nao fechar ao atualizar
        first_load = self._grouped_tree.topLevelItemCount() == 0
        was_expanded: set[int] = set()
        for i in range(self._grouped_tree.topLevelItemCount()):
            top = self._grouped_tree.topLevelItem(i)
            tid = top.data(0, Qt.UserRole + 1)
            if top.isExpanded() and tid is not None:
                was_expanded.add(tid)
        self._grouped_tree.clear()
        if self.project_id is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            types = {t.id: t for t in uow.task_types.list_by_project(self.project_id)}
            phases = {}
            for tid in types:
                for p in uow.phases.list_by_task_type(tid):
                    phases[p.id] = p
            grouped = group_by_type_and_phase(
                uow.tasks.list_by_project(self.project_id), phases
            )
        for type_id in sorted(grouped, key=lambda i: types[i].name if i in types else "?"):
            task_type = types.get(type_id)
            type_name = task_type.name if task_type else "?"
            type_icon = task_type.icon if task_type else ""
            type_color = task_type.color if task_type else None
            items = grouped[type_id]
            header_text = f"{type_label(type_name, type_icon)} ({len(items)})"
            header = QTreeWidgetItem([header_text, "", ""])
            header.setData(0, Qt.UserRole, None)
            header.setData(0, Qt.UserRole + 1, type_id)
            header.setToolTip(0, header_text)
            header.setIcon(0, make_color_icon(type_color))
            if type_color:
                from PySide6.QtGui import QColor

                c = QColor(normalize_color(type_color))
                c.setAlpha(40)
                from PySide6.QtGui import QBrush

                header.setBackground(0, QBrush(c))
            self._grouped_tree.addTopLevelItem(header)
            # grupos comecam fechados; expansao so pega depois de inserir
            header.setExpanded(False if first_load else type_id in was_expanded)
            for t in items:
                phase_name = phases[t.phase_id].name if t.phase_id in phases else "-"
                updated = _recency_key(t)
                stamp = (
                    to_local(updated).strftime("%d/%m %H:%M")
                    if hasattr(updated, "strftime")
                    else "-"
                )
                full_stamp = (
                    to_local(updated).strftime("%d/%m/%Y %H:%M")
                    if hasattr(updated, "strftime")
                    else "-"
                )
                child_text = f"#{t.id} {t.title}"
                child = QTreeWidgetItem([child_text, phase_name, stamp])
                child.setData(0, Qt.UserRole, t.id)
                child.setToolTip(0, child_text)
                child.setToolTip(1, phase_name)
                child.setToolTip(2, full_stamp)
                header.addChild(child)
        for col in range(3):
            self._grouped_tree.resizeColumnToContents(col)

    def _open_from_list(self, item: QListWidgetItem) -> None:
        if TaskDialog.edit(self, self._db_path, self.project_id, item.data(Qt.UserRole)):
            self._load_all()

    def _open_from_tree(self, item: QTreeWidgetItem) -> None:
        task_id = item.data(0, Qt.UserRole)
        if task_id is None:  # cabecalho do tipo
            return
        if TaskDialog.edit(self, self._db_path, self.project_id, task_id):
            self._load_all()

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
