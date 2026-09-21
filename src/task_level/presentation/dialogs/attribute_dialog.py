"""Editor de definicao de atributo (Parte 8).

Para atributos de referencia permite configurar `reference_config`:
- reference_task: {"target_type_id"?} (ausente = qualquer tipo do projeto)
- reference_attribute: {"attribute_name", "target_type_id"?} (fixa qual
  atributo sera referenciado, entao na task basta escolher a task)
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
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
    ("Dinheiro (R$)", AttributeType.CURRENCY.value),
    ("Data", AttributeType.DATE.value),
    ("Verdadeiro/Falso", AttributeType.BOOLEAN.value),
    ("Referencia a task", AttributeType.REFERENCE_TASK.value),
    ("Referencia a atributo", AttributeType.REFERENCE_ATTRIBUTE.value),
]


class AttributeDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        spec: dict | None = None,
        ref_targets: list[dict] | None = None,
    ) -> None:
        """ref_targets: [{"type_id", "type_name", "attrs": [{"name","label"}]}]."""
        super().__init__(parent)
        self.setWindowTitle("Atributo")
        spec = spec or {}
        self._ref_targets: list[dict] = [dict(t) for t in (ref_targets or [])]
        self._pending_config = (
            dict(spec["reference_config"])
            if isinstance(spec.get("reference_config"), dict)
            else {}
        )

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

        # -- secao de referencia (so visivel p/ tipos de referencia) ---------
        self._ref_section = QWidget()
        ref_form = QFormLayout(self._ref_section)
        self._ref_type = QComboBox()
        self._ref_type.currentIndexChanged.connect(self._refresh_ref_attrs)
        self._ref_attr = QComboBox()
        self._ref_hint = QLabel("")
        self._ref_hint.setWordWrap(True)
        ref_form.addRow("Tipo alvo:", self._ref_type)
        ref_form.addRow("Atributo alvo:", self._ref_attr)
        ref_form.addRow("", self._ref_hint)
        self._type.currentIndexChanged.connect(self._refresh_ref_section)

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
        layout.addWidget(self._ref_section)
        layout.addWidget(buttons)
        self._refresh_ref_section()

    # -- secao de referencia --------------------------------------------------

    def _is_ref_task(self) -> bool:
        return self._type.currentData() == AttributeType.REFERENCE_TASK.value

    def _is_ref_attr(self) -> bool:
        return self._type.currentData() == AttributeType.REFERENCE_ATTRIBUTE.value

    def _refresh_ref_section(self) -> None:
        is_ref = self._is_ref_task() or self._is_ref_attr()
        self._ref_section.setVisible(is_ref)
        if not is_ref:
            return
        self._ref_type.blockSignals(True)
        self._ref_type.clear()
        self._ref_type.addItem("Qualquer tipo do projeto", None)
        for t in self._ref_targets:
            self._ref_type.addItem(t["type_name"], t["type_id"])
        wanted_type = self._pending_config.get("target_type_id")
        if wanted_type is not None:
            idx = self._ref_type.findData(wanted_type)
            if idx >= 0:
                self._ref_type.setCurrentIndex(idx)
        self._ref_type.blockSignals(False)
        # linha "Atributo alvo" so faz sentido p/ referencia a atributo
        show_attr = self._is_ref_attr()
        self._ref_attr.setVisible(show_attr)
        label_widget = self._ref_section.layout().labelForField(self._ref_attr)
        if label_widget is not None:
            label_widget.setVisible(show_attr)
        self._refresh_ref_attrs()
        if self._is_ref_task():
            self._ref_hint.setText(
                "Na task, podera referenciar tasks de qualquer tipo do projeto"
                " (ou so do tipo escolhido)."
            )
        self._pending_config = {}

    def _type_attrs(self, type_id: int | None) -> list[tuple[str, str, str]]:
        """[(type_name, name, label)] do tipo escolhido (ou todos se None)."""
        out: list[tuple[str, str, str]] = []
        for t in self._ref_targets:
            if type_id is not None and t["type_id"] != type_id:
                continue
            for a in t.get("attrs", []):
                out.append((t["type_name"], a["name"], a.get("label", a["name"])))
        return out

    def _refresh_ref_attrs(self) -> None:
        if not self._is_ref_attr():
            return
        self._ref_attr.clear()
        if not self._ref_targets:
            self._ref_hint.setText(
                "Projeto ainda sem atributos: na task sera preciso escolher "
                "task + atributo."
            )
            return
        options = self._type_attrs(self._ref_type.currentData())
        seen: set[str] = set()
        for _type_name, name, label in options:
            if name in seen:
                continue  # mesmo nome em varios tipos: uma opcao basta
            seen.add(name)
            self._ref_attr.addItem(f"{label} ({name})", name)
        if self._ref_attr.count() == 0:
            self._ref_hint.setText(
                "Tipo sem atributos: na task sera preciso escolher task + atributo."
                if self._ref_type.currentData() is not None
                else "Projeto ainda sem atributos: na task sera preciso escolher "
                "task + atributo."
            )
            return
        wanted = self._pending_config.get("attribute_name")
        if wanted is not None:
            idx = self._ref_attr.findData(wanted)
            if idx >= 0:
                self._ref_attr.setCurrentIndex(idx)
        self._ref_hint.setText(
            "Na task, bastara escolher a task: o valor vira deste atributo."
        )

    def _reference_config_data(self) -> dict | None:
        if self._is_ref_task():
            target = self._ref_type.currentData()
            return {"target_type_id": target} if target is not None else None
        if self._is_ref_attr():
            if self._ref_attr.count() == 0 or self._ref_attr.currentData() is None:
                return None
            config: dict = {"attribute_name": self._ref_attr.currentData()}
            target = self._ref_type.currentData()
            if target is not None:
                config["target_type_id"] = target
            return config
        return None

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
            "reference_config": self._reference_config_data(),
        }

    @classmethod
    def create(
        cls, parent: QWidget | None = None, ref_targets: list[dict] | None = None
    ) -> dict | None:
        dlg = cls(parent, ref_targets=ref_targets)
        return dlg.data() if dlg.exec() else None

    @classmethod
    def edit(
        cls,
        parent: QWidget | None,
        spec: dict,
        ref_targets: list[dict] | None = None,
    ) -> dict | None:
        dlg = cls(parent, spec, ref_targets=ref_targets)
        return dlg.data() if dlg.exec() else None
