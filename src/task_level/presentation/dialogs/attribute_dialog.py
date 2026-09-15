"""Editor de definicao de atributo (Parte 8)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from task_level.domain import AttributeType

TYPE_LABELS: list[tuple[str, str]] = [
    ("Texto", AttributeType.TEXT.value),
    ("Numero", AttributeType.NUMBER.value),
    ("Verdadeiro/Falso", AttributeType.BOOLEAN.value),
    ("Referencia a task", AttributeType.REFERENCE_TASK.value),
    ("Referencia a atributo", AttributeType.REFERENCE_ATTRIBUTE.value),
]


class AttributeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, spec: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Atributo")
        spec = spec or {}
        self._name = QLineEdit(spec.get("name", ""))
        self._name.setPlaceholderText("ex: severidade (sem espacos)")
        self._label = QLineEdit(spec.get("label", ""))
        self._type = QComboBox()
        for label, value in TYPE_LABELS:
            self._type.addItem(label, value)
        current = spec.get("type", AttributeType.TEXT.value)
        idx = self._type.findData(current)
        if idx >= 0:
            self._type.setCurrentIndex(idx)
        self._required = QCheckBox("Obrigatorio")
        self._required.setChecked(bool(spec.get("required", False)))
        self._default = QLineEdit(spec.get("default_value", ""))
        self._order = QSpinBox()
        self._order.setRange(0, 999)
        self._order.setValue(int(spec.get("order", 0)))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Rotulo:", self._label)
        form.addRow("Tipo:", self._type)
        form.addRow("", self._required)
        form.addRow("Padrao:", self._default)
        form.addRow("Ordem:", self._order)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validacao", "Nome nao pode ser vazio.")
            return
        if any(c.isspace() for c in name):
            QMessageBox.warning(self, "Validacao", "Nome nao pode conter espacos.")
            return
        if not self._label.text().strip():
            QMessageBox.warning(self, "Validacao", "Rotulo nao pode ser vazio.")
            return
        super().accept()

    def data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "label": self._label.text().strip(),
            "type": self._type.currentData(),
            "required": self._required.isChecked(),
            "default_value": self._default.text(),
            "order": self._order.value(),
        }

    @classmethod
    def create(cls, parent: QWidget | None = None) -> dict | None:
        dlg = cls(parent)
        return dlg.data() if dlg.exec() else None

    @classmethod
    def edit(cls, parent: QWidget | None, spec: dict) -> dict | None:
        dlg = cls(parent, spec)
        return dlg.data() if dlg.exec() else None
