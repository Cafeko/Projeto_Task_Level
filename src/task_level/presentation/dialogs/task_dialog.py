"""Dialog de criar/editar task com formulario dinamico (Parte 9).

Campos por tipo de atributo:
- text -> QLineEdit | number -> QLineEdit numerico | boolean -> QCheckBox
- reference_task -> QComboBox de tasks | reference_attribute -> picker dedicado
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import AttributeType, DomainError
from task_level.presentation.dialogs.reference_attribute_picker import (
    ReferenceAttributePicker,
)


class TaskDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        db_path: str | Path,
        project_id: int,
        task_id: int | None = None,
        task_type_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._project_id = project_id
        self._task_id = task_id
        self._definitions: list = []
        self._fields: dict[str, QWidget] = {}
        self._ref_attr_values: dict[str, tuple[int, int] | None] = {}

        self.setWindowTitle("Editar task" if task_id else "Nova task")
        self.resize(480, 520)

        self._title = QLineEdit()
        self._desc = QTextEdit()
        self._desc.setMaximumHeight(70)
        self._type_combo = QComboBox()
        self._phase_combo = QComboBox()

        form = QFormLayout()
        if task_id is None:
            form.addRow("Tipo:", self._type_combo)
        else:
            self._type_label = QLabel("")
            form.addRow("Tipo:", self._type_label)
            form.addRow("Fase:", self._phase_combo)
        form.addRow("Titulo:", self._title)
        form.addRow("Descricao:", self._desc)

        self._attr_form = QFormLayout()
        attr_box = QVBoxLayout()
        attr_box.addLayout(self._attr_form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(attr_box)
        layout.addStretch()
        layout.addWidget(buttons)

        self._load_types()
        if task_id is None:
            self._type_combo.currentIndexChanged.connect(self._rebuild_attributes)
            self._rebuild_attributes()
        else:
            self._load_existing(task_type_id)

    # -- carregamento ---------------------------------------------------------

    def _load_types(self) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            types = uow.task_types.list_by_project(self._project_id)
        for t in types:
            self._type_combo.addItem(t.name, t.id)

    def _current_type_id(self) -> int | None:
        if self._task_id is not None:
            return self._type_id
        return self._type_combo.currentData()

    def _load_existing(self, task_type_id: int | None) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(self._task_id)
            if task is None:
                raise ValueError(f"task {self._task_id} nao encontrada")
            self._type_id = task.task_type_id if task_type_id is None else task_type_id
            type_names = {
                t.id: t.name
                for t in uow.task_types.list_by_project(self._project_id)
            }
            self._type_label.setText(type_names.get(self._type_id, "?"))
            phases = uow.phases.list_by_task_type(self._type_id)
            for p in phases:
                self._phase_combo.addItem(p.name, p.id)
            idx = self._phase_combo.findData(task.phase_id)
            if idx >= 0:
                self._phase_combo.setCurrentIndex(idx)
            self._title.setText(task.title)
            self._desc.setPlainText(task.description)
            self._definitions = uow.attribute_definitions.list_by_task_type(
                self._type_id
            )
            saved = {
                v.attribute_definition_id: v
                for v in uow.task_attributes.list_by_task(task.id)
            }
            self._saved_values = saved
        self._build_fields(prefill=True)

    def _rebuild_attributes(self) -> None:
        type_id = self._current_type_id()
        if type_id is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            self._definitions = uow.attribute_definitions.list_by_task_type(type_id)
        self._saved_values = {}
        self._build_fields(prefill=False)

    # -- form dinamico ----------------------------------------------------------

    def _clear_attr_form(self) -> None:
        while self._attr_form.count():
            item = self._attr_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._fields = {}

    def _build_fields(self, prefill: bool) -> None:
        self._clear_attr_form()
        for d in self._definitions:
            saved = self._saved_values.get(d.id) if prefill else None
            widget: QWidget
            if d.type == AttributeType.TEXT.value:
                w = QLineEdit(saved.value_text if saved and saved.value_text else "")
                widget = w
            elif d.type == AttributeType.NUMBER.value:
                w = QLineEdit()
                w.setValidator(QDoubleValidator())
                w.setPlaceholderText("ex: 1.5")
                if saved and saved.value_number is not None:
                    w.setText(str(saved.value_number))
                widget = w
            elif d.type == AttributeType.BOOLEAN.value:
                w = QCheckBox()
                if saved and saved.value_boolean is not None:
                    w.setChecked(saved.value_boolean)
                widget = w
            elif d.type == AttributeType.REFERENCE_TASK.value:
                w = QComboBox()
                w.addItem("(nenhuma)", None)
                with UnitOfWork.open(self._db_path) as uow:
                    for t in uow.tasks.list_by_project(self._project_id):
                        if t.id == self._task_id:
                            continue
                        w.addItem(f"#{t.id} {t.title}", t.id)
                if saved and saved.value_reference_task_id is not None:
                    idx = w.findData(saved.value_reference_task_id)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                widget = w
            elif d.type == AttributeType.REFERENCE_ATTRIBUTE.value:
                label = QLabel("(nenhuma)")
                key = d.name
                if saved and saved.value_reference_attribute_id is not None:
                    self._ref_attr_values[key] = (
                        saved.value_reference_task_id,
                        saved.value_reference_attribute_id,
                    )
                    label.setText(self._describe_ref_attr(*self._ref_attr_values[key]))
                else:
                    self._ref_attr_values[key] = None
                pick = QPushButton("Selecionar...")
                pick.clicked.connect(
                    lambda _=False, k=key, lb=label: self._pick_ref_attr(k, lb)
                )
                clear = QPushButton("Limpar")
                clear.clicked.connect(
                    lambda _=False, k=key, lb=label: self._clear_ref_attr(k, lb)
                )
                row = QHBoxLayout()
                row.addWidget(label, stretch=1)
                row.addWidget(pick)
                row.addWidget(clear)
                container = QWidget()
                container.setLayout(row)
                widget = container
            else:
                continue
            suffix = " *" if d.required else ""
            self._attr_form.addRow(f"{d.label}{suffix}:", widget)
            self._fields[d.name] = widget

    def _pick_ref_attr(self, key: str, label: QLabel) -> None:
        picked = ReferenceAttributePicker.pick(
            self, self._db_path, self._project_id, exclude_task_id=self._task_id
        )
        if picked is not None:
            self._ref_attr_values[key] = picked
            label.setText(self._describe_ref_attr(*picked))

    def _clear_ref_attr(self, key: str, label: QLabel) -> None:
        self._ref_attr_values[key] = None
        label.setText("(nenhuma)")

    def _describe_ref_attr(self, task_id: int, attr_id: int) -> str:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            attr = uow.task_attributes.get_by_id(attr_id)
            if task is None or attr is None:
                return "(invalida)"
            definitions = {
                d.id: d
                for d in uow.attribute_definitions.list_by_task_type(task.task_type_id)
            }
            d = definitions.get(attr.attribute_definition_id)
            name = d.label if d else f"#{attr_id}"
            return f"#{task_id} {task.title} - {name}"

    # -- payload ------------------------------------------------------------------

    def payload(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        by_name = {d.name: d for d in self._definitions}
        for name, widget in self._fields.items():
            d = by_name[name]
            if d.type == AttributeType.TEXT.value:
                text = widget.text().strip()
                if text:
                    values[name] = text
            elif d.type == AttributeType.NUMBER.value:
                text = widget.text().strip()
                if text:
                    values[name] = float(text.replace(",", "."))
            elif d.type == AttributeType.BOOLEAN.value:
                values[name] = widget.isChecked()
            elif d.type == AttributeType.REFERENCE_TASK.value:
                if widget.currentData() is not None:
                    values[name] = widget.currentData()
            elif d.type == AttributeType.REFERENCE_ATTRIBUTE.value:
                if self._ref_attr_values.get(name) is not None:
                    values[name] = self._ref_attr_values[name]
        return {
            "title": self._title.text().strip(),
            "description": self._desc.toPlainText(),
            "task_type_id": self._current_type_id(),
            "phase_id": self._phase_combo.currentData()
            if self._task_id is not None
            else None,
            "values": values,
        }

    def accept(self) -> None:
        errors: list[str] = []
        if not self._title.text().strip():
            errors.append("Titulo nao pode ser vazio.")
        if self._task_id is None and self._current_type_id() is None:
            errors.append("Selecione o tipo da task.")
        payload_values = self.payload()["values"]
        for d in self._definitions:
            if d.required and d.name not in payload_values and d.type != "boolean":
                errors.append(f"'{d.label}' e obrigatorio.")
        if errors:
            QMessageBox.warning(self, "Validacao", "\n".join(errors))
            return
        super().accept()

    # -- aplicacao via services -----------------------------------------------------

    def apply(self) -> int:
        """Cria ou atualiza a task conforme payload. Retorna o task_id."""
        from task_level.services import TaskService

        svc = TaskService(self._db_path)
        data = self.payload()
        try:
            if self._task_id is None:
                assert data["task_type_id"] is not None
                task = svc.create_task(
                    self._project_id,
                    data["task_type_id"],
                    data["title"],
                    description=data["description"],
                    values=data["values"],
                )
                assert task.id is not None
                return task.id
            svc.update_details(self._task_id, data["title"], data["description"])
            with UnitOfWork.open(self._db_path) as uow:
                task = uow.tasks.get(self._task_id)
                assert task is not None
                definitions = uow.attribute_definitions.list_by_task_type(
                    task.task_type_id
                )
            for d in definitions:
                if d.name in data["values"]:
                    svc.set_attribute(self._task_id, d.name, data["values"][d.name])
                else:
                    svc.clear_attribute(self._task_id, d.name)
            if data["phase_id"] is not None and data["phase_id"] != task.phase_id:
                svc.move_phase(self._task_id, data["phase_id"])
            return self._task_id
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            raise

    @classmethod
    def create(
        cls,
        parent: QWidget | None,
        db_path: str | Path,
        project_id: int,
        task_type_id: int | None = None,
    ) -> int | None:
        dlg = cls(parent, db_path, project_id, task_type_id=task_type_id)
        if task_type_id is not None:
            idx = dlg._type_combo.findData(task_type_id)
            if idx >= 0:
                dlg._type_combo.setCurrentIndex(idx)
                dlg._rebuild_attributes()
        if not dlg.exec():
            return None
        try:
            return dlg.apply()
        except DomainError:
            return None

    @classmethod
    def edit(
        cls, parent: QWidget | None, db_path: str | Path, project_id: int, task_id: int
    ) -> bool:
        dlg = cls(parent, db_path, project_id, task_id=task_id)
        if not dlg.exec():
            return False
        try:
            dlg.apply()
            return True
        except DomainError:
            return False
