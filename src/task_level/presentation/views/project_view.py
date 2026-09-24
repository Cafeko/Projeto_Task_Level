"""Visao do projeto: filtro por tipo + Kanban ou lista geral (Parte 9).

Modo "Todos" tem duas visoes (escolha do usuario):
- "Recentes": tudo misturado, mais recentes (created/updated) no topo.
- "Por tipo e fase": tasks separadas por tipo e ordenadas pela ordem da fase.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import DomainError, task_number, to_local
from task_level.presentation.dialogs.filter_dialog import FilterDialog
from task_level.presentation.dialogs.focus_dialog import FocusDialog
from task_level.presentation.dialogs.history_dialog import HistoryDialog
from task_level.presentation.dialogs.task_dialog import TaskDialog, format_attr_value
from task_level.presentation.dialogs.task_type_manager_dialog import (
    TaskTypeManagerDialog,
)
from task_level.presentation.widgets.kanban_board import KanbanBoard
from task_level.presentation.widgets.type_badge import (
    make_color_icon,
    normalize_color,
    type_label,
)
from task_level.services import ProjectService, TaskService, TaskTypeService

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
        self._type_filter.currentIndexChanged.connect(self._on_user_type_changed)
        self._filters: list[dict] = []
        self._btn_filters = QPushButton("Filtros...")
        self._btn_filters.clicked.connect(self._open_filters)
        self._focus: dict[str, list[str]] = {}
        self._btn_focus = QPushButton("Foco...")
        self._btn_focus.clicked.connect(self._open_focus)
        self._view_mode = QComboBox()
        self._view_mode.addItem("Por tipo e fase", VIEW_GROUPED)
        self._view_mode.addItem("Recentes", VIEW_RECENT)
        self._view_mode.currentIndexChanged.connect(self._mode_changed)
        btn_new = QPushButton("Nova task")
        btn_new.clicked.connect(self._new_task)
        btn_types = QPushButton("Tipos de tarefa...")
        btn_types.clicked.connect(self._manage_types)
        self._btn_undo = QPushButton("← Desfazer")
        self._btn_undo.clicked.connect(self._do_undo)
        self._btn_redo = QPushButton("Refazer →")
        self._btn_redo.clicked.connect(self._do_redo)
        self._btn_history = QPushButton("Historico...")
        self._btn_history.clicked.connect(self._open_history)
        sc_undo = QShortcut(QKeySequence.StandardKey.Undo, self)
        sc_undo.setContext(Qt.WindowShortcut)
        sc_undo.activated.connect(self._do_undo)
        sc_redo = QShortcut(QKeySequence.StandardKey.Redo, self)
        sc_redo.setContext(Qt.WindowShortcut)
        sc_redo.activated.connect(self._do_redo)

        top = QHBoxLayout()
        top.addWidget(btn_back)
        top.addWidget(QLabel("Tipo:"))
        top.addWidget(self._type_filter)
        top.addWidget(self._btn_filters)
        top.addWidget(self._btn_focus)
        self._view_label = QLabel("Visão:")
        top.addWidget(self._view_label)
        top.addWidget(self._view_mode)
        top.addWidget(btn_new)
        top.addWidget(btn_types)
        top.addWidget(self._btn_undo)
        top.addWidget(self._btn_redo)
        top.addWidget(self._btn_history)
        top.addStretch()

        self._all_list = QListWidget()
        self._all_list.itemDoubleClicked.connect(self._open_from_list)
        self._all_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._all_list.customContextMenuRequested.connect(self._menu_from_list)
        self._grouped_tree = QTreeWidget()
        self._grouped_tree.setHeaderLabels(["Task", "Fase", "Atualizada"])
        self._grouped_tree.itemDoubleClicked.connect(self._open_from_tree)
        self._grouped_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._grouped_tree.customContextMenuRequested.connect(self._menu_from_tree)
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
        self._title.setText(project.name)
        self._load_focus()
        self._update_focus_button()
        self._refresh_undo_buttons()
        self._reload_types()

    def _focus_settings_key(self) -> str:
        return f"focus/project_{self.project_id}"

    def _load_focus(self) -> None:
        self._focus = {}
        try:
            raw = QSettings("TaskLevel", "task-level").value(
                self._focus_settings_key(), "{}"
            )
            data = json.loads(raw) if isinstance(raw, str) else {}
            if isinstance(data, dict):
                self._focus = {
                    str(k): [str(n) for n in v]
                    for k, v in data.items()
                    if isinstance(v, list)
                }
        except Exception:
            self._focus = {}

    def _save_focus(self) -> None:
        QSettings("TaskLevel", "task-level").setValue(
            self._focus_settings_key(), json.dumps(self._focus)
        )

    def _update_focus_button(self) -> None:
        total = sum(len(v) for v in self._focus.values())
        self._btn_focus.setText(f"Foco ({total})" if total else "Foco...")

    def _open_focus(self) -> None:
        if self.project_id is None:
            return
        scope = self._type_filter.currentData()
        if scope is None:
            # Modo Todos: edita todos os tipos de uma vez, ja mostrando
            # os focos aplicados e permitindo limpar sem desmarcar um por um.
            result = FocusDialog.edit(
                self, self._db_path, self.project_id, None, dict(self._focus)
            )
            if result is None:
                return
            if isinstance(result, dict):
                self._focus = {
                    str(k): [str(n) for n in v]
                    for k, v in result.items()
                    if v
                }
            else:  # compat: (scope_id, names)
                scope_id, names = result
                if scope_id is None:
                    return
                if names:
                    self._focus[str(scope_id)] = names
                else:
                    self._focus.pop(str(scope_id), None)
        else:
            selected = self._focus.get(str(scope), [])
            result = FocusDialog.edit(
                self, self._db_path, self.project_id, scope, selected
            )
            if result is None:
                return
            if isinstance(result, dict):
                # dialogo retornou tudo (quando tipos mudaram no meio):
                # mescla preservando outros tipos ja salvos
                for k, v in result.items():
                    if v:
                        self._focus[str(k)] = [str(n) for n in v]
                    else:
                        self._focus.pop(str(k), None)
                # remove o escopo atual se foi limpo e nao veio no dict
                if str(scope) not in result:
                    self._focus.pop(str(scope), None)
            else:
                scope_id, names = result
                if scope_id is None:
                    return
                if names:
                    self._focus[str(scope_id)] = names
                else:
                    self._focus.pop(str(scope_id), None)
        self._save_focus()
        self._update_focus_button()
        self._filter_changed()

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

    def _on_user_type_changed(self) -> None:
        # trocar de tipo invalida filtros do tipo anterior
        self._filters = []
        self._update_filter_button()
        self._filter_changed()

    def _undo_manager(self):
        from task_level.services.undo import UndoManager

        return UndoManager.for_db(self._db_path)

    def _refresh_undo_buttons(self) -> None:
        manager = self._undo_manager()
        self._btn_undo.setEnabled(manager.can_undo())
        self._btn_redo.setEnabled(manager.can_redo())
        self._btn_undo.setToolTip(
            f"Desfazer: {manager.undo_label()} (Ctrl+Z)"
            if manager.can_undo()
            else "Nada a desfazer (Ctrl+Z)"
        )
        self._btn_redo.setToolTip(
            f"Refazer: {manager.redo_label()} (Ctrl+Y)"
            if manager.can_redo()
            else "Nada a refazer (Ctrl+Y)"
        )

    def _do_undo(self) -> None:
        from task_level.services.undo import EmptyHistory

        try:
            self._undo_manager().undo(TaskService(self._db_path))
        except EmptyHistory:
            return
        except DomainError as e:
            QMessageBox.critical(self, "Desfazer", str(e))
        self._filter_changed()
        self._refresh_undo_buttons()

    def _do_redo(self) -> None:
        from task_level.services.undo import EmptyHistory

        try:
            self._undo_manager().redo(TaskService(self._db_path))
        except EmptyHistory:
            return
        except DomainError as e:
            QMessageBox.critical(self, "Refazer", str(e))
        self._filter_changed()
        self._refresh_undo_buttons()

    def _open_history(self) -> None:
        if self.project_id is None:
            return
        HistoryDialog.show(self, self._db_path, self.project_id)

    def _update_filter_button(self) -> None:
        self._btn_filters.setText(
            f"Filtros ({len(self._filters)})" if self._filters else "Filtros..."
        )

    def _open_filters(self) -> None:
        if self.project_id is None:
            return
        result = FilterDialog.edit(
            self,
            self._db_path,
            self.project_id,
            self._type_filter.currentData(),
            self._filters,
        )
        if result is None:
            return
        self._filters = result
        self._update_filter_button()
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
        self._refresh_undo_buttons()

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
        self._refresh_undo_buttons()

    def _focus_data(self, uow, tasks):
        """Defs focadas por tipo + valores: ({tid: {name: def}}, {(task, def): val})."""
        wanted = {t.task_type_id for t in tasks if str(t.task_type_id) in self._focus}
        defs: dict = {}
        for tid in wanted:
            defs[tid] = {
                d.name: d
                for d in uow.attribute_definitions.list_by_task_type(tid)
                if d.name in self._focus.get(str(tid), [])
            }
        vals: dict = {}
        for t in tasks:
            for v in uow.task_attributes.list_by_task(t.id):
                vals[(t.id, v.attribute_definition_id)] = v
        return defs, vals

    def _focus_parts(
        self, task, defs, vals, ref_numbers: dict[int, int] | None = None
    ) -> list[str]:
        """['Rotulo: valor', ...] dos atributos em foco (vazios pulados)."""
        parts = []
        for name in self._focus.get(str(task.task_type_id), []):
            d = defs.get(task.task_type_id, {}).get(name)
            if d is None or d.id is None:
                continue
            v = vals.get((task.id, d.id))
            if v is None:
                continue
            text = format_attr_value(v, d.type, ref_numbers)
            if text:
                parts.append(f"{d.label}: {text}")
        return parts

    @staticmethod
    def _ref_numbers(tasks) -> dict[int, int]:
        """task_id -> numero visivel (p/ exibir referencias como #seq)."""
        return {
            t.id: task_number(t) for t in tasks if t.id is not None
        }

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
            tasks = sort_recent(
                TaskService(self._db_path).list_filtered(
                    self.project_id, None, self._filters
                )
            )
            focus_defs, focus_vals = self._focus_data(uow, tasks)
        ref_numbers = self._ref_numbers(tasks)
        for t in tasks:
            task_type = types.get(t.task_type_id)
            type_name = task_type.name if task_type else "?"
            type_icon = task_type.icon if task_type else ""
            type_color = task_type.color if task_type else None
            phase_name = phases[t.phase_id].name if t.phase_id in phases else "-"
            text = (
                f"[{type_label(type_name, type_icon)}] #{task_number(t)}"
                f" {t.title}  ({phase_name})"
            )
            parts = self._focus_parts(t, focus_defs, focus_vals, ref_numbers)
            if parts:
                text += "  |  " + "  |  ".join(parts)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, t.id)
            item.setIcon(make_color_icon(type_color))
            item.setToolTip(text)
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
            tasks_all = TaskService(self._db_path).list_filtered(
                self.project_id, None, self._filters
            )
            grouped = group_by_type_and_phase(tasks_all, phases)
            focus_defs, focus_vals = self._focus_data(uow, tasks_all)
            ref_numbers = self._ref_numbers(tasks_all)
        type_order = sorted(
            grouped, key=lambda i: types[i].name if i in types else "?"
        )
        # colunas extras = atributos em foco (por tipo, na ordem das definicoes)
        focus_cols: list = []
        for tid in type_order:
            for name in self._focus.get(str(tid), []):
                d = focus_defs.get(tid, {}).get(name)
                if d is not None:
                    focus_cols.append((tid, d))
        labels = [d.label for _, d in focus_cols]
        headers = ["Task", "Fase", "Atualizada"] + [
            label if labels.count(label) == 1 else f"{types[tid].name} / {label}"
            for tid, d in focus_cols
            for label in [d.label]
        ]
        # setHeaderLabels sozinho nao encolhe colunas antigas (foco removido
        # deixava a coluna fantasma); forca a contagem antes.
        self._grouped_tree.setColumnCount(len(headers))
        self._grouped_tree.setHeaderLabels(headers)
        tree_header = self._grouped_tree.header()
        for col in range(len(headers)):
            tree_header.setSectionResizeMode(col, QHeaderView.Interactive)
        for type_id in type_order:
            task_type = types.get(type_id)
            type_name = task_type.name if task_type else "?"
            type_icon = task_type.icon if task_type else ""
            type_color = task_type.color if task_type else None
            items = grouped[type_id]
            header_text = f"{type_label(type_name, type_icon)} ({len(items)})"
            header = QTreeWidgetItem([header_text] + [""] * (len(headers) - 1))
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
                child_text = f"#{task_number(t)} {t.title}"
                cells = [child_text, phase_name, stamp]
                for tid, d in focus_cols:
                    cell = ""
                    if tid == t.task_type_id and d.id is not None:
                        v = focus_vals.get((t.id, d.id))
                        if v is not None:
                            cell = format_attr_value(v, d.type, ref_numbers)
                    cells.append(cell)
                child = QTreeWidgetItem(cells)
                child.setData(0, Qt.UserRole, t.id)
                child.setToolTip(0, child_text)
                child.setToolTip(1, phase_name)
                child.setToolTip(2, full_stamp)
                for col in range(3, len(cells)):
                    if cells[col]:
                        child.setToolTip(col, cells[col])
                header.addChild(child)
        for col in range(len(headers)):
            self._grouped_tree.resizeColumnToContents(col)

    def _open_from_list(self, item: QListWidgetItem) -> None:
        self._open_task_id(item.data(Qt.UserRole))

    def _open_from_tree(self, item: QTreeWidgetItem) -> None:
        task_id = item.data(0, Qt.UserRole)
        if task_id is None:  # cabecalho do tipo
            return
        self._open_task_id(task_id)

    def _menu_from_list(self, pos) -> None:
        item = self._all_list.itemAt(pos)
        if item is None:
            return
        self._all_list.setCurrentItem(item)
        self._task_menu(item.data(Qt.UserRole), self._all_list.viewport().mapToGlobal(pos))

    def _menu_from_tree(self, pos) -> None:
        item = self._grouped_tree.itemAt(pos)
        if item is None:
            return
        task_id = item.data(0, Qt.UserRole)
        if task_id is None:  # cabecalho do tipo: sem menu
            return
        self._grouped_tree.setCurrentItem(item)
        self._task_menu(task_id, self._grouped_tree.viewport().mapToGlobal(pos))

    def _task_menu(self, task_id: int, global_pos) -> None:
        menu = QMenu(self)
        act_open = menu.addAction("Abrir")
        act_delete = menu.addAction("Excluir")
        chosen = menu.exec(global_pos)
        if chosen == act_open:
            self._open_task_id(task_id)
        elif chosen == act_delete:
            self._delete_task_id(task_id)

    def _open_task_id(self, task_id: int) -> None:
        if self.project_id is None:
            return
        if TaskDialog.edit(self, self._db_path, self.project_id, task_id):
            self._load_all()

    def _delete_task_id(self, task_id: int) -> None:
        if self.project_id is None:
            return
        answer = QMessageBox.question(self, "Excluir task", "Excluir esta task?")
        if answer != QMessageBox.Yes:
            return
        try:
            TaskService(self._db_path).delete(task_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self._load_all()

    # -- kanban ---------------------------------------------------------------------

    def _show_board(self, type_id: int) -> None:
        while self._board_layout.count():
            item = self._board_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        board = KanbanBoard(
            self._db_path,
            self.project_id,
            type_id,
            on_changed=self._board_changed,
            filters=self._filters,
            focus=self._focus.get(str(type_id), []),
        )
        self._board_layout.addWidget(board)
        self._stack.setCurrentWidget(self._board_host)

    def _board_changed(self) -> None:
        self._refresh_undo_buttons()

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
