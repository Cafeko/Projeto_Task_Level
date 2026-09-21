"""Dialogo de Foco: escolhe quais atributos aparecem inline nas listas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class FocusDialog(QDialog):
    def __init__(
        self,
        parent,
        db_path: str | Path,
        project_id: int,
        type_id: int | None = None,
        selected: list[str] | None = None,
    ) -> None:
        from task_level.data import UnitOfWork

        super().__init__(parent)
        self.setWindowTitle("Foco: atributos visiveis")
        self.resize(380, 320)
        self._db_path = db_path
        self._project_id = project_id
        self._fixed_type = type_id
        self._selected = set(selected or [])

        layout = QVBoxLayout(self)
        self._type_combo: QComboBox | None = None
        if type_id is None:
            type_form = QFormLayout()
            self._type_combo = QComboBox()
            with UnitOfWork.open(db_path) as uow:
                for t in uow.task_types.list_by_project(project_id):
                    self._type_combo.addItem(t.name, t.id)
            self._type_combo.currentIndexChanged.connect(self._reload_attrs)
            type_form.addRow("Tipo:", self._type_combo)
            layout.addLayout(type_form)

        self._list = QListWidget()
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._reload_attrs()

    def _current_scope(self) -> int | None:
        if self._fixed_type is not None:
            return self._fixed_type
        if self._type_combo is not None:
            return self._type_combo.currentData()
        return None

    def _reload_attrs(self) -> None:
        from task_level.data import UnitOfWork

        self._list.clear()
        scope = self._current_scope()
        if scope is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            definitions = uow.attribute_definitions.list_by_task_type(scope)
        for d in definitions:
            item = QListWidgetItem(d.label)
            item.setData(Qt.UserRole, d.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if d.name in self._selected else Qt.Unchecked
            )
            self._list.addItem(item)

    def data(self) -> tuple[int | None, list[str]]:
        names = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                names.append(item.data(Qt.UserRole))
        return (self._current_scope(), names)

    @classmethod
    def edit(
        cls,
        parent,
        db_path: str | Path,
        project_id: int,
        type_id: int | None = None,
        selected: list[str] | None = None,
    ) -> tuple[int | None, list[str]] | None:
        dlg = cls(parent, db_path, project_id, type_id, selected)
        return dlg.data() if dlg.exec() else None
