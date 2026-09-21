"""Seletor de (task, atributo) para referencias a atributo (Parte 9)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork


class ReferenceAttributePicker(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        db_path: str | Path,
        project_id: int,
        exclude_task_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Referenciar atributo")
        self._db_path = db_path
        self._project_id = project_id
        self._exclude = exclude_task_id

        self._task_combo = QComboBox()
        self._attr_combo = QComboBox()
        self._task_combo.currentIndexChanged.connect(self._load_attributes)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Task:", self._task_combo)
        form.addRow("Atributo:", self._attr_combo)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._load_tasks()

    def _load_tasks(self) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            type_names = {
                t.id: t.name for t in uow.task_types.list_by_project(self._project_id)
            }
            tasks = uow.tasks.list_by_project(self._project_id)
        for t in tasks:
            if t.id == self._exclude:
                continue
            tname = type_names.get(t.task_type_id, "?")
            self._task_combo.addItem(f"[{tname}] #{t.id} {t.title}", t.id)

    def _load_attributes(self) -> None:
        self._attr_combo.clear()
        task_id = self._task_combo.currentData()
        if task_id is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return
            definitions = {
                d.id: d
                for d in uow.attribute_definitions.list_by_task_type(task.task_type_id)
            }
            values = uow.task_attributes.list_by_task(task_id)
        for v in values:
            d = definitions.get(v.attribute_definition_id)
            if d is None or v.id is None:
                continue
            label = f"{d.label} = {self._display(v, d.type)}"
            self._attr_combo.addItem(label, (task_id, v.id))

    @staticmethod
    def _display(attr, attr_type: str | None = None) -> str:
        from task_level.domain import AttributeType, format_currency, format_date

        if attr_type == AttributeType.CURRENCY.value and attr.value_number is not None:
            return format_currency(attr.value_number)
        if attr_type == AttributeType.DATE.value and attr.value_text:
            return format_date(attr.value_text)
        if attr.value_text is not None:
            return attr.value_text
        if attr.value_number is not None:
            return str(attr.value_number)
        if attr.value_boolean is not None:
            return "sim" if attr.value_boolean else "nao"
        if attr.value_reference_task_id is not None:
            return f"task #{attr.value_reference_task_id}"
        return "-"

    def data(self) -> tuple[int, int] | None:
        return self._attr_combo.currentData()

    @classmethod
    def pick(
        cls,
        parent: QWidget | None,
        db_path: str | Path,
        project_id: int,
        exclude_task_id: int | None = None,
    ) -> tuple[int, int] | None:
        dlg = cls(parent, db_path, project_id, exclude_task_id)
        if not dlg.exec():
            return None
        return dlg.data()
