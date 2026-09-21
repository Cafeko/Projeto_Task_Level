"""Quadro Kanban por fase de um tipo de tarefa (Parte 9)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import DomainError
from task_level.presentation.dialogs.task_dialog import TaskDialog
from task_level.presentation.widgets.type_badge import normalize_color
from task_level.services import TaskService


class KanbanBoard(QWidget):
    def __init__(
        self,
        db_path: str | Path,
        project_id: int,
        task_type_id: int,
        on_changed: Callable[[], None] | None = None,
        filters: list[dict] | None = None,
        focus: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._project_id = project_id
        self._task_type_id = task_type_id
        self._on_changed = on_changed
        self._filters: list[dict] = list(filters or [])
        self._focus: list[str] = list(focus or [])
        self._columns: list[tuple[int, QLabel, QListWidget]] = []

        self._inner = QWidget()
        self._cols_layout = QHBoxLayout(self._inner)
        self._cols_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._inner)
        self._btn_back = QPushButton("← Voltar")
        self._btn_fwd = QPushButton("Avancar →")
        self._btn_back.clicked.connect(lambda: self._step(-1))
        self._btn_fwd.clicked.connect(lambda: self._step(+1))
        nav = QHBoxLayout()
        nav.addWidget(self._btn_back)
        nav.addWidget(self._btn_fwd)
        nav.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(nav)
        layout.addWidget(scroll)
        self.refresh()

    def _notify(self) -> None:
        if self._on_changed:
            self._on_changed()

    def refresh(self) -> None:
        for _, _, lst in self._columns:
            lst.deleteLater()
        while self._cols_layout.count():
            item = self._cols_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_layout(item.layout())
        self._columns = []

        with UnitOfWork.open(self._db_path) as uow:
            phases = uow.phases.list_by_task_type(self._task_type_id)
            focus_defs = {
                d.name: d
                for d in uow.attribute_definitions.list_by_task_type(
                    self._task_type_id
                )
                if d.name in self._focus
            }
            focus_vals: dict = {}
            tasks = TaskService(self._db_path).list_filtered(
                self._project_id, self._task_type_id, self._filters
            )
            for t in tasks:
                for v in uow.task_attributes.list_by_task(t.id):
                    focus_vals[(t.id, v.attribute_definition_id)] = v
        by_phase: dict[int | None, list] = {}
        for t in tasks:
            by_phase.setdefault(t.phase_id, []).append(t)

        from task_level.presentation.dialogs.task_dialog import format_attr_value

        for phase in phases:
            header = QLabel("")
            header.setStyleSheet(
                f"font-weight: bold; padding: 4px; border-radius: 4px; "
                f"background: {normalize_color(phase.color)}22; "
                f"border: 1px solid {normalize_color(phase.color)};"
            )
            header.setToolTip(phase.description or phase.name)
            lst = QListWidget()
            lst.setMinimumWidth(220)
            lst.setContextMenuPolicy(Qt.CustomContextMenu)
            lst.customContextMenuRequested.connect(
                lambda _pos, w=lst: self._menu(w)
            )
            lst.itemDoubleClicked.connect(self._open_task)
            lst.currentItemChanged.connect(
                lambda _cur, _prev, w=lst: self._on_select(w)
            )
            col = QWidget()
            col_layout = QVBoxLayout(col)
            col_layout.addWidget(header)
            col_layout.addWidget(lst)
            self._cols_layout.addWidget(col)
            assert phase.id is not None
            items = by_phase.get(phase.id, [])
            header.setText(f"{phase.name} ({len(items)})")
            for t in items:
                lines = [f"#{t.id} {t.title}"]
                for name in self._focus:
                    d = focus_defs.get(name)
                    if d is None or d.id is None:
                        continue
                    v = focus_vals.get((t.id, d.id))
                    if v is None:
                        continue
                    text = format_attr_value(v, d.type)
                    if text:
                        lines.append(f"{d.label}: {text}")
                item = QListWidgetItem("\n".join(lines))
                item.setData(Qt.UserRole, t.id)
                item.setToolTip("\n".join(lines))
                lst.addItem(item)
            self._columns.append((phase.id, header, lst))
        self._refresh_nav()

    def _selected_task_id(self) -> int | None:
        for _, _, lst in self._columns:
            item = lst.currentItem()
            if item is not None:
                return item.data(Qt.UserRole)
        return None

    def _on_select(self, source: QListWidget) -> None:
        for _, _, other in self._columns:
            if other is not source and other.currentItem() is not None:
                other.blockSignals(True)
                other.setCurrentRow(-1)
                other.blockSignals(False)
        self._refresh_nav()

    def _refresh_nav(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self._btn_back.setEnabled(False)
            self._btn_fwd.setEnabled(False)
            self._btn_back.setToolTip("Selecione uma task")
            self._btn_fwd.setToolTip("Selecione uma task")
            return
        try:
            svc = TaskService(self._db_path)
            prev, nxt = svc.neighbors(task_id)
            back_block = (
                svc.transition_block(task_id, prev.id)
                if prev is not None and prev.id is not None
                else None
            )
            fwd_block = (
                svc.transition_block(task_id, nxt.id)
                if nxt is not None and nxt.id is not None
                else None
            )
        except DomainError:
            self._btn_back.setEnabled(False)
            self._btn_fwd.setEnabled(False)
            return
        self._btn_back.setEnabled(prev is not None)
        self._btn_fwd.setEnabled(nxt is not None)
        self._btn_back.setToolTip(
            back_block
            or (f"Voltar para {prev.name}" if prev else "Ja esta na primeira fase")
        )
        self._btn_fwd.setToolTip(
            fwd_block
            or (f"Avancar para {nxt.name}" if nxt else "Ja esta na ultima fase")
        )

    def _step(self, delta: int) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            return
        try:
            prev, nxt = TaskService(self._db_path).neighbors(task_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        target = prev if delta < 0 else nxt
        if target is None or target.id is None:
            return
        try:
            TaskService(self._db_path).move_phase(task_id, target.id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()
        self._reselect(task_id)
        self._refresh_nav()
        self._notify()

    def _reselect(self, task_id: int) -> None:
        for _, _, lst in self._columns:
            for row in range(lst.count()):
                if lst.item(row).data(Qt.UserRole) == task_id:
                    lst.setCurrentRow(row)
                    return

    def _selected(self, lst: QListWidget) -> int | None:
        item = lst.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _menu(self, lst: QListWidget) -> None:
        task_id = self._selected(lst)
        if task_id is None:
            return
        menu = QMenu(self)
        act_open = menu.addAction("Abrir")
        move_menu = menu.addMenu("Mover para")
        with UnitOfWork.open(self._db_path) as uow:
            phases = sorted(
                uow.phases.list_by_task_type(self._task_type_id), key=lambda p: p.order
            )
            current = uow.tasks.get(task_id)
        current_phase = current.phase_id if current else None
        neighbors: list = []
        ids = [p.id for p in phases]
        if current_phase in ids:
            pos = ids.index(current_phase)
            if pos > 0:
                neighbors.append(("← Voltar para ", phases[pos - 1]))
            if pos < len(phases) - 1:
                neighbors.append(("Avancar para ", phases[pos + 1]))
        else:
            neighbors = [("", p) for p in phases]
        for prefix, p in neighbors:
            act = move_menu.addAction(f"{prefix}{p.name}")
            act.setData(p.id)
        act_delete = menu.addAction("Excluir")
        chosen = menu.exec(lst.mapToGlobal(lst.rect().center()))
        if chosen is None:
            return
        if chosen == act_open:
            self._open_task_id(task_id)
        elif chosen == act_delete:
            self._delete_task(task_id)
        elif chosen.data() is not None:
            self._move_task(task_id, chosen.data())

    def _open_task(self, item: QListWidgetItem) -> None:
        self._open_task_id(item.data(Qt.UserRole))

    def _open_task_id(self, task_id: int) -> None:
        if TaskDialog.edit(self, self._db_path, self._project_id, task_id):
            self.refresh()
            self._notify()

    def _move_task(self, task_id: int, phase_id: int) -> None:
        try:
            TaskService(self._db_path).move_phase(task_id, phase_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()
        self._notify()

    def _delete_task(self, task_id: int) -> None:
        answer = QMessageBox.question(self, "Excluir task", "Excluir esta task?")
        if answer != QMessageBox.Yes:
            return
        try:
            TaskService(self._db_path).delete(task_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()
        self._notify()


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())
