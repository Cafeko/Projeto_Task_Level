"""Editor de fase (ordem/inicio/fim sao automaticos: posicao na lista)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QColorDialog,
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


class PhaseDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        spec: dict | None = None,
        type_attrs: list[dict] | None = None,
    ) -> None:
        """type_attrs: [{"type_id","type_name","name","label","type","options"}]."""
        super().__init__(parent)
        self.setWindowTitle("Fase")
        spec = spec or {}
        self._name = QLineEdit(spec.get("name", ""))
        self._desc = QTextEdit(spec.get("description", ""))
        self._desc.setMaximumHeight(60)
        self._color = QLineEdit(spec.get("color", "#888888"))
        btn_color = QHBoxLayout()
        btn_color.addWidget(self._color)

        pick = QPushButton("Escolher...")
        pick.clicked.connect(self._pick_color)
        btn_color.addWidget(pick)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Descricao:", self._desc)
        form.addRow("Cor:", btn_color)
        layout = QVBoxLayout(self)
        layout.addLayout(form)

        # -- condicoes de entrada (todas precisam valer) ----------------------
        self._type_attrs: list[dict] = list(type_attrs or [])
        cond_label = QLabel("Condicoes para entrar (todas precisam valer):")
        layout.addWidget(cond_label)
        self._conds_box = QVBoxLayout()
        layout.addLayout(self._conds_box)
        add_cond = QPushButton("Adicionar condicao")
        add_cond.clicked.connect(lambda _=False: self._add_cond_row())
        layout.addWidget(add_cond)
        layout.addWidget(buttons)

        self._cond_rows: list = []
        existing = spec.get("enter_conditions")
        if isinstance(existing, list):
            for cond in existing:
                if isinstance(cond, dict) and cond.get("attr"):
                    self._add_cond_row(cond)

    def _add_cond_row(self, preset: dict | None = None) -> None:
        from task_level.presentation.dialogs.filter_dialog import _FilterRow

        row = _FilterRow(self._type_attrs, self._remove_cond_row, self)
        if preset:
            row.set_data(
                {"type_id": 0, "attr": preset.get("attr"), "op": preset.get("op"),
                 "value": preset.get("value", "")}
            )
        self._cond_rows.append(row)
        self._conds_box.addWidget(row)

    def _remove_cond_row(self, row) -> None:
        self._cond_rows.remove(row)
        row.deleteLater()

    def _pick_color(self) -> None:
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self._color.text()), self)
        if color.isValid():
            self._color.setText(color.name())

    def accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validacao", "Nome da fase nao pode ser vazio.")
            return
        for row in self._cond_rows:
            if row.data() is None:
                QMessageBox.warning(self, "Validacao", "Ha condicao incompleta.")
                return
        super().accept()

    def data(self) -> dict:
        conds = []
        for row in self._cond_rows:
            f = row.data()
            if f is not None:
                conds.append({"attr": f["attr"], "op": f["op"], "value": f["value"]})
        return {
            "name": self._name.text().strip(),
            "description": self._desc.toPlainText(),
            "color": self._color.text().strip() or "#888888",
            "enter_conditions": conds or None,
        }

    @classmethod
    def create(
        cls, parent: QWidget | None = None, type_attrs: list[dict] | None = None
    ) -> dict | None:
        dlg = cls(parent, type_attrs=type_attrs)
        return dlg.data() if dlg.exec() else None

    @classmethod
    def edit(
        cls,
        parent: QWidget | None,
        spec: dict,
        type_attrs: list[dict] | None = None,
    ) -> dict | None:
        dlg = cls(parent, spec, type_attrs=type_attrs)
        return dlg.data() if dlg.exec() else None
