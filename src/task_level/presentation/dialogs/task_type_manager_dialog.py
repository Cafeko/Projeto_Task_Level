"""Gerenciador de tipos de tarefa do projeto (Parte 8)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import DomainError
from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog
from task_level.presentation.widgets.type_badge import make_color_icon, type_label
from task_level.services import TaskTypeService


class TaskTypeManagerDialog(QDialog):
    def __init__(
        self, parent: QWidget | None, db_path: str | Path, project_id: int
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tipos de tarefa")
        self.resize(420, 360)
        self._service = TaskTypeService(db_path)
        self._db_path = db_path
        self._project_id = project_id

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._edit)
        # Reordenar por arrasto: desligado por padrao (evita troca por engano,
        # mesmo padrao das fases/atributos).
        from PySide6.QtWidgets import QAbstractItemView

        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(Qt.MoveAction)
        self._list.model().rowsMoved.connect(self._types_dropped)

        btn_new = QPushButton("Novo")
        btn_edit = QPushButton("Editar")
        btn_delete = QPushButton("Excluir")
        btn_close = QPushButton("Fechar")
        btn_new.clicked.connect(self._create)
        btn_edit.clicked.connect(self._edit)
        btn_delete.clicked.connect(self._delete)
        btn_close.clicked.connect(self.accept)

        row = QHBoxLayout()
        for b in (btn_new, btn_edit, btn_delete, btn_close):
            row.addWidget(b)

        btn_up = QPushButton("↑ Subir")
        btn_up.setToolTip("Move o tipo selecionado uma posicao para cima")
        btn_up.clicked.connect(lambda: self._move_selected(-1))
        btn_down = QPushButton("↓ Descer")
        btn_down.setToolTip("Move o tipo selecionado uma posicao para baixo")
        btn_down.clicked.connect(lambda: self._move_selected(+1))
        self._drag_toggle = QPushButton()
        self._drag_toggle.setCheckable(True)
        self._drag_toggle.setChecked(False)
        self._drag_toggle.toggled.connect(self._set_drag_enabled)

        order_row = QHBoxLayout()
        order_row.addWidget(btn_up)
        order_row.addWidget(btn_down)
        order_row.addWidget(self._drag_toggle)
        order_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tipos deste projeto:"))
        layout.addWidget(self._list)
        layout.addLayout(order_row)
        layout.addLayout(row)
        self._drag_hint = QLabel("")
        self._drag_hint.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self._drag_hint)
        self._set_drag_enabled(False)
        self.refresh()

    def _set_drag_enabled(self, enabled: bool) -> None:
        self._list.setDragEnabled(enabled)
        self._list.setAcceptDrops(enabled)
        self._drag_toggle.setText(
            "🔓 Reordenar: ligado" if enabled else "🔒 Reordenar: desligado"
        )
        self._drag_hint.setText(
            "Arraste os tipos para reordenar (vale no Todos e nos combos)."
            if enabled
            else "A ordem aqui vale no Todos e nos combos. Ligue Reordenar para arrastar."
        )

    def refresh(self, keep_selected: int | None = None) -> None:
        selected = keep_selected if keep_selected is not None else self._selected_id()
        self._list.blockSignals(True)
        self._list.clear()
        try:
            types = self._service.list_by_project(self._project_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            self._list.blockSignals(False)
            return
        for pos, t in enumerate(types):
            item = QListWidgetItem(f"{pos + 1}. {type_label(t.name, t.icon)}")
            item.setData(Qt.UserRole, t.id)
            item.setIcon(make_color_icon(t.color))
            self._list.addItem(item)
            if t.id == selected:
                self._list.setCurrentRow(pos)
        self._list.blockSignals(False)

    def _visual_ids(self) -> list[int]:
        ids = []
        for row in range(self._list.count()):
            tid = self._list.item(row).data(Qt.UserRole)
            if isinstance(tid, int):
                ids.append(tid)
        return ids

    def _persist_visual_order(self) -> None:
        try:
            self._service.reorder_types(self._project_id, self._visual_ids())
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            self.refresh()
            return
        self.refresh(keep_selected=self._selected_id())

    def _types_dropped(self, *_args) -> None:
        """Apos arrastar: a ordem passa a ser a posicao na lista."""
        self._persist_visual_order()

    def _move_selected(self, delta: int) -> None:
        type_id = self._selected_id()
        if type_id is None:
            return
        try:
            self._service.move_type(self._project_id, type_id, delta)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh(keep_selected=type_id)

    def _selected_id(self) -> int | None:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _ref_targets(self) -> list[dict]:
        """Tipos + atributos do projeto (para configurar referencias)."""
        with UnitOfWork.open(self._db_path) as uow:
            targets = []
            for t in uow.task_types.list_by_project(self._project_id):
                defs = uow.attribute_definitions.list_by_task_type(t.id)
                targets.append(
                    {
                        "type_id": t.id,
                        "type_name": t.name,
                        "attrs": [
                            {"name": d.name, "label": d.label} for d in defs
                        ],
                    }
                )
        return targets

    def _create(self) -> None:
        payload = TaskTypeDialog.create(self, ref_targets=self._ref_targets())
        if payload is None:
            return
        try:
            self._service.create_type(
                self._project_id,
                payload["name"],
                description=payload["description"],
                color=payload["color"],
                icon=payload["icon"],
                phases=payload["phases"],
                attributes=payload["attributes"],
            )
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()

    def _load_payload(self, type_id: int) -> dict:
        task_type = self._service.get(type_id)
        with UnitOfWork.open(self._db_path) as uow:
            phases = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "color": p.color,
                    "order": p.order,
                    "is_initial": p.is_initial,
                    "is_final": p.is_final,
                    "enter_conditions": p.enter_conditions,
                }
                for p in uow.phases.list_by_task_type(type_id)
            ]
            attrs = [
                {
                    "id": a.id,
                    "name": a.name,
                    "label": a.label,
                    "type": a.type,
                    "required": a.required,
                    "default_value": a.default_value,
                    "reference_config": a.reference_config,
                    "options": a.options,
                    "order": a.order,
                }
                for a in uow.attribute_definitions.list_by_task_type(type_id)
            ]
        return {
            "name": task_type.name,
            "description": task_type.description,
            "color": task_type.color,
            "icon": task_type.icon,
            "phases": phases,
            "attributes": attrs,
        }

    def _edit(self) -> None:
        type_id = self._selected_id()
        if type_id is None:
            return
        try:
            payload = TaskTypeDialog.edit(
                self, self._load_payload(type_id), ref_targets=self._ref_targets()
            )
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        if payload is None:
            return
        try:
            self._apply_edit(type_id, payload)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()

    def _apply_edit(self, type_id: int, payload: dict) -> None:
        self._service.update_type(
            type_id,
            payload["name"],
            description=payload["description"],
            color=payload["color"],
            icon=payload["icon"],
        )
        old = self._load_payload(type_id)
        old_phase_ids = {p["id"] for p in old["phases"] if p.get("id")}
        new_phase_ids = {p.get("id") for p in payload["phases"] if p.get("id")}
        # Lote unico: reordenar (que troca inicio/fim de lugar) nao pode validar
        # o estado intermediario de cada fase (era o erro "precisa manter 1 fase
        # final" em tipos de 2 fases). save_phases valida so o estado final.
        self._service.save_phases(type_id, payload["phases"])
        for pid in old_phase_ids - new_phase_ids:
            self._service.delete_phase(pid)
        old_attr_ids = {a["id"] for a in old["attributes"] if a.get("id")}
        new_attr_ids = {a.get("id") for a in payload["attributes"] if a.get("id")}
        # ordem e sempre a posicao na lista (como nas fases)
        for i, spec in enumerate(payload["attributes"]):
            spec["order"] = i
            if spec.get("id") is None:
                self._service.add_attribute(type_id, spec)
            else:
                self._service.update_attribute(spec["id"], spec)
        for aid in old_attr_ids - new_attr_ids:
            self._service.delete_attribute(aid)

    def _delete(self) -> None:
        type_id = self._selected_id()
        if type_id is None:
            return
        answer = QMessageBox.question(
            self,
            "Excluir tipo",
            "Excluir o tipo e TODAS as suas tasks? Essa acao nao tem volta.",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self._service.delete(type_id)
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            return
        self.refresh()
