"""Dialogo de filtros por atributo: escolhe atributo + operador + valor."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import AttributeType
from task_level.services.filters import ops_for


class _FilterRow(QWidget):
    """Uma linha: atributo + operador + valor + remover."""

    def __init__(
        self,
        attributes: list[dict],
        on_remove,
        parent: QWidget | None = None,
    ) -> None:
        """attributes: [{"type_id","type_name","name","label","type","options"}]."""
        super().__init__(parent)
        self._attributes = attributes
        self.attr_combo = QComboBox()
        for a in attributes:
            self.attr_combo.addItem(a["label"], a)
        self.op_combo = QComboBox()
        self.stack = QStackedWidget()
        self.line = QLineEdit()
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd/MM/yyyy")
        self.date.setDate(QDate.currentDate())
        self.combo = QComboBox()
        self.stack.addWidget(self.line)
        self.stack.addWidget(self.date)
        self.stack.addWidget(self.combo)
        remove = QPushButton("X")
        remove.setFixedWidth(32)
        remove.clicked.connect(lambda: on_remove(self))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.attr_combo, stretch=2)
        layout.addWidget(self.op_combo, stretch=2)
        layout.addWidget(self.stack, stretch=2)
        layout.addWidget(remove)

        self.attr_combo.currentIndexChanged.connect(self._reload_ops)
        self.op_combo.currentIndexChanged.connect(self._reload_value)
        self._reload_ops()

    def _current_attr(self) -> dict:
        return self.attr_combo.currentData() or {}

    def _reload_ops(self) -> None:
        attr = self._current_attr()
        self.op_combo.blockSignals(True)
        self.op_combo.clear()
        for op_id, label, needs in ops_for(attr.get("type", "")):
            self.op_combo.addItem(label, (op_id, needs))
        self.op_combo.blockSignals(False)
        self._reload_value()

    def _reload_value(self) -> None:
        data = self.op_combo.currentData() or ("", False)
        op_id, needs = data
        attr = self._current_attr()
        self.stack.setVisible(bool(needs))
        if not needs:
            return
        if attr.get("type") == AttributeType.DATE.value:
            self.stack.setCurrentWidget(self.date)
        elif attr.get("type") == AttributeType.SELECT.value:
            self.combo.blockSignals(True)
            self.combo.clear()
            for option in (attr.get("options") or []):
                self.combo.addItem(option, option)
            self.combo.blockSignals(False)
            self.stack.setCurrentWidget(self.combo)
        else:
            self.line.setPlaceholderText(
                "ex: 1.234,56"
                if attr.get("type") == AttributeType.CURRENCY.value
                else "valor..."
            )
            self.stack.setCurrentWidget(self.line)
        _ = op_id

    def data(self) -> dict | None:
        """Filtro pronto ou None se incompleto."""
        attr = self._current_attr()
        if not attr:
            return None
        op_data = self.op_combo.currentData() or ("", False)
        op_id, needs = op_data
        if not op_id:
            return None
        value = ""
        if needs:
            if self.stack.currentWidget() is self.date:
                value = self.date.date().toString("yyyy-MM-dd")
            elif self.stack.currentWidget() is self.combo:
                value = self.combo.currentData() or ""
            else:
                value = self.line.text().strip()
            if not value:
                return None
        return {
            "type_id": attr["type_id"],
            "attr": attr["name"],
            "op": op_id,
            "value": value,
        }

    def set_data(self, f: dict) -> None:
        for i in range(self.attr_combo.count()):
            a = self.attr_combo.itemData(i)
            if a["type_id"] == f.get("type_id") and a["name"] == f.get("attr"):
                self.attr_combo.setCurrentIndex(i)
                break
        self._reload_ops()
        for i in range(self.op_combo.count()):
            if self.op_combo.itemData(i)[0] == f.get("op"):
                self.op_combo.setCurrentIndex(i)
                break
        self._reload_value()
        value = f.get("value", "")
        if self.stack.currentWidget() is self.date and value:
            self.date.setDate(QDate.fromString(value, "yyyy-MM-dd"))
        elif self.stack.currentWidget() is self.combo and value:
            idx = self.combo.findData(value)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        elif value:
            self.line.setText(value)


class FilterDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        db_path: str | Path,
        project_id: int,
        type_id: int | None = None,
        filters: list[dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filtrar por atributos")
        self.resize(560, 320)
        self._db_path = db_path
        self._project_id = project_id
        self._fixed_type = type_id
        self._attributes: list[dict] = []
        # Guarda filtros por tipo para nao perder outros tipos ao trocar
        # o combo no modo Todos, nem ao editar um tipo de cada vez.
        self._by_type: dict[int, list[dict]] = {}
        for f in filters or []:
            tid = f.get("type_id")
            if isinstance(tid, int):
                self._by_type.setdefault(tid, []).append(dict(f))

        self._rows_box = QVBoxLayout()
        add_btn = QPushButton("Adicionar filtro")
        add_btn.clicked.connect(lambda _=False: self._add_row())
        clear_btn = QPushButton("Limpar filtros")
        clear_btn.setToolTip("Remove todos os filtros aplicados")
        clear_btn.clicked.connect(lambda _=False: self._clear_all())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        self._type_combo: QComboBox | None = None
        if type_id is None:
            from PySide6.QtWidgets import QFormLayout

            self._type_combo = QComboBox()
            for t in self._load_types():
                self._type_combo.addItem(t["name"], t["id"])
            type_form = QFormLayout()
            type_form.addRow("Tipo:", self._type_combo)
            layout.addLayout(type_form)
        from PySide6.QtWidgets import QHBoxLayout as _HBox

        row_btns = _HBox()
        row_btns.addWidget(add_btn)
        row_btns.addWidget(clear_btn)
        row_btns.addStretch()
        layout.addLayout(self._rows_box)
        layout.addLayout(row_btns)
        layout.addStretch()
        layout.addWidget(buttons)

        self._rows: list[_FilterRow] = []
        start = type_id
        if start is None and self._by_type:
            first = (filters or [])[0]
            start = first.get("type_id")
        if self._type_combo is not None:
            self._type_combo.blockSignals(True)
            if start is not None:
                idx = self._type_combo.findData(start)
                if idx >= 0:
                    self._type_combo.setCurrentIndex(idx)
            self._type_combo.blockSignals(False)
            self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._last_scope: int | None = self._current_scope()
        self._reload_scope_from_memory()

    def _load_types(self) -> list[dict]:
        with UnitOfWork.open(self._db_path) as uow:
            return [
                {"id": t.id, "name": t.name}
                for t in uow.task_types.list_by_project(self._project_id)
            ]

    def _current_scope(self) -> int | None:
        if self._fixed_type is not None:
            return self._fixed_type
        if self._type_combo is not None:
            return self._type_combo.currentData()
        return None

    def _stash_current(self) -> None:
        """Salva as linhas visiveis no _by_type do escopo anterior."""
        scope = self._last_scope
        if scope is None:
            return
        cur: list[dict] = []
        for row in self._rows:
            d = row.data()
            if d is not None:
                dd = dict(d)
                dd["type_id"] = scope
                cur.append(dd)
        if cur:
            self._by_type[scope] = cur
        else:
            self._by_type.pop(scope, None)

    def _on_type_changed(self) -> None:
        self._stash_current()
        self._last_scope = self._current_scope()
        self._reload_scope_from_memory()

    def _reload_scope_from_memory(self) -> None:
        scope = self._current_scope()
        self._last_scope = scope
        self._attributes = self._load_attributes(
            self._db_path, self._project_id, scope
        )
        for row in self._rows:
            self._rows_box.removeWidget(row)
            row.deleteLater()
        self._rows = []
        for f in self._by_type.get(scope, []) if scope is not None else []:
            self._add_row(f)
        if not self._rows:
            # sem filtros nesse tipo: mostra uma linha vazia p/ adicionar
            if self._attributes:
                self._add_row()

    # Mantido p/ compat com testes antigos.
    def _reload_scope(self, presets: list[dict]) -> None:
        for f in presets:
            tid = f.get("type_id")
            if isinstance(tid, int):
                self._by_type.setdefault(tid, [])
                if f not in self._by_type[tid]:
                    self._by_type[tid].append(dict(f))
        self._reload_scope_from_memory()

    @staticmethod
    def _load_attributes(
        db_path: str | Path, project_id: int, type_id: int | None
    ) -> list[dict]:
        out = []
        with UnitOfWork.open(db_path) as uow:
            types = uow.task_types.list_by_project(project_id)
            if type_id is not None:
                types = [t for t in types if t.id == type_id]
            for t in types:
                for d in uow.attribute_definitions.list_by_task_type(t.id):
                    out.append(
                        {
                            "type_id": t.id,
                            "type_name": t.name,
                            "name": d.name,
                            "label": d.label,
                            "type": d.type,
                            "options": d.options,
                        }
                    )
        return out

    def _add_row(self, preset: dict | None = None) -> None:
        row = _FilterRow(self._attributes, self._remove_row, self)
        if preset:
            row.set_data(preset)
        self._rows.append(row)
        self._rows_box.addWidget(row)

    def _remove_row(self, row: _FilterRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            self._rows_box.removeWidget(row)
            row.deleteLater()

    def _clear_all(self) -> None:
        """Limpa todos os filtros (todos os tipos) sem precisar remover um por um."""
        self._by_type.clear()
        for row in list(self._rows):
            self._rows_box.removeWidget(row)
            row.deleteLater()
        self._rows = []
        if self._attributes:
            self._add_row()

    def accept(self) -> None:
        # Linhas incompletas (valor vazio) sao ignoradas em vez de bloquear:
        # OK com nada preenchido = sem filtros. Isso permite limpar e permite
        # salvar outros tipos mesmo com a linha vazia do tipo atual.
        self._stash_current()
        super().accept()

    def data(self) -> list[dict]:
        self._stash_current()
        out: list[dict] = []
        for lst in self._by_type.values():
            out.extend(dict(f) for f in lst)
        return out

    @classmethod
    def edit(
        cls,
        parent: QWidget | None,
        db_path: str | Path,
        project_id: int,
        type_id: int | None = None,
        filters: list[dict] | None = None,
    ) -> list[dict] | None:
        dlg = cls(parent, db_path, project_id, type_id, filters)
        return dlg.data() if dlg.exec() else None
