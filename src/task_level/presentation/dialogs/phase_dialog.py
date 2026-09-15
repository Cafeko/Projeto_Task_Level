"""Editor de fase (Parte 8)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PhaseDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, spec: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fase")
        spec = spec or {}
        self._name = QLineEdit(spec.get("name", ""))
        self._desc = QTextEdit(spec.get("description", ""))
        self._desc.setMaximumHeight(60)
        self._color = QLineEdit(spec.get("color", "#888888"))
        btn_color = QHBoxLayout()
        btn_color.addWidget(self._color)
        from PySide6.QtWidgets import QPushButton

        pick = QPushButton("Escolher...")
        pick.clicked.connect(self._pick_color)
        btn_color.addWidget(pick)
        self._order = QSpinBox()
        self._order.setRange(0, 999)
        self._order.setValue(int(spec.get("order", 0)))
        self._initial = QCheckBox("Fase inicial")
        self._initial.setChecked(bool(spec.get("is_initial", False)))
        self._final = QCheckBox("Fase final")
        self._final.setChecked(bool(spec.get("is_final", False)))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Descricao:", self._desc)
        form.addRow("Cor:", btn_color)
        form.addRow("Ordem:", self._order)
        form.addRow("", self._initial)
        form.addRow("", self._final)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _pick_color(self) -> None:
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self._color.text()), self)
        if color.isValid():
            self._color.setText(color.name())

    def accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validacao", "Nome da fase nao pode ser vazio.")
            return
        super().accept()

    def data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._desc.toPlainText(),
            "color": self._color.text().strip() or "#888888",
            "order": self._order.value(),
            "is_initial": self._initial.isChecked(),
            "is_final": self._final.isChecked(),
        }

    @classmethod
    def create(cls, parent: QWidget | None = None) -> dict | None:
        dlg = cls(parent)
        return dlg.data() if dlg.exec() else None

    @classmethod
    def edit(cls, parent: QWidget | None, spec: dict) -> dict | None:
        dlg = cls(parent, spec)
        return dlg.data() if dlg.exec() else None
