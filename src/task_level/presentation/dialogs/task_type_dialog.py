"""Dialog de criar/editar tipo de tarefa com fases e atributos (Parte 8)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from task_level.presentation.dialogs.attribute_dialog import AttributeDialog
from task_level.presentation.dialogs.phase_dialog import PhaseDialog


def validate_type_payload(payload: dict) -> list[str]:
    """Validacao pura (testavel sem Qt). Retorna lista de erros."""
    errors: list[str] = []
    if not payload.get("name", "").strip():
        errors.append("Nome do tipo nao pode ser vazio.")
    phases = payload.get("phases", [])
    if not phases:
        errors.append("Tipo precisa de ao menos 1 fase.")
    initials = [p for p in phases if p.get("is_initial")]
    if len(initials) != 1:
        errors.append("Tipo precisa de exatamente 1 fase inicial.")
    names = [a.get("name", "") for a in payload.get("attributes", [])]
    if len(names) != len(set(names)):
        errors.append("Nomes de atributos duplicados.")
    return errors


class TaskTypeDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, payload: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tipo de tarefa")
        self.resize(560, 480)
        payload = payload or {}

        self._name = QLineEdit(payload.get("name", ""))
        self._desc = QLineEdit(payload.get("description", ""))
        self._color = QLineEdit(payload.get("color", "#888888"))
        pick_color = QPushButton("Escolher...")
        pick_color.clicked.connect(self._pick_color)
        color_row = QHBoxLayout()
        color_row.addWidget(self._color)
        color_row.addWidget(pick_color)
        self._icon = QLineEdit(payload.get("icon", ""))

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Descricao:", self._desc)
        form.addRow("Cor:", color_row)
        form.addRow("Icone:", self._icon)

        self._phases: list[dict] = [dict(p) for p in payload.get("phases", [])]
        self._attrs: list[dict] = [dict(a) for a in payload.get("attributes", [])]

        tabs = QTabWidget()
        tabs.addTab(self._build_phases_tab(), "Fases")
        tabs.addTab(self._build_attrs_tab(), "Atributos")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(tabs)
        layout.addWidget(buttons)
        self._refresh_phases()
        self._refresh_attrs()

    # -- topo ---------------------------------------------------------------

    def _pick_color(self) -> None:
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self._color.text()), self)
        if color.isValid():
            self._color.setText(color.name())

    # -- fases ----------------------------------------------------------------

    def _build_phases_tab(self) -> QWidget:
        self._phase_list = QListWidget()
        self._phase_list.itemDoubleClicked.connect(self._edit_phase)
        add = QPushButton("Adicionar")
        edit = QPushButton("Editar")
        remove = QPushButton("Remover")
        up = QPushButton("Subir")
        down = QPushButton("Descer")
        add.clicked.connect(self._add_phase)
        edit.clicked.connect(self._edit_phase)
        remove.clicked.connect(self._remove_phase)
        up.clicked.connect(lambda: self._move_phase(-1))
        down.clicked.connect(lambda: self._move_phase(1))
        row = QHBoxLayout()
        for b in (add, edit, remove, up, down):
            row.addWidget(b)
        row.addStretch()
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self._phase_list)
        layout.addLayout(row)
        return tab

    def _refresh_phases(self) -> None:
        self._phase_list.clear()
        for i, spec in enumerate(self._phases):
            tags = []
            if spec.get("is_initial"):
                tags.append("inicial")
            if spec.get("is_final"):
                tags.append("final")
            suffix = f" [{', '.join(tags)}]" if tags else ""
            item = QListWidgetItem(f"{i}. {spec.get('name', '')}{suffix}")
            item.setData(Qt.UserRole, i)
            self._phase_list.addItem(item)

    def _add_phase(self) -> None:
        spec = PhaseDialog.create(self)
        if spec is not None:
            self._phases.append(spec)
            self._refresh_phases()

    def _edit_phase(self) -> None:
        row = self._phase_list.currentRow()
        if row < 0:
            return
        spec = PhaseDialog.edit(self, self._phases[row])
        if spec is not None:
            spec["id"] = self._phases[row].get("id")  # preserva vinculo
            self._phases[row] = spec
            self._refresh_phases()

    def _remove_phase(self) -> None:
        row = self._phase_list.currentRow()
        if row < 0:
            return
        del self._phases[row]
        self._refresh_phases()

    def _move_phase(self, delta: int) -> None:
        row = self._phase_list.currentRow()
        other = row + delta
        if row < 0 or not 0 <= other < len(self._phases):
            return
        self._phases[row], self._phases[other] = self._phases[other], self._phases[row]
        for i, spec in enumerate(self._phases):
            spec["order"] = i
        self._refresh_phases()
        self._phase_list.setCurrentRow(other)

    # -- atributos --------------------------------------------------------------

    def _build_attrs_tab(self) -> QWidget:
        self._attr_table = QTableWidget(0, 4)
        self._attr_table.setHorizontalHeaderLabels(["Nome", "Rotulo", "Tipo", "Obrig."])
        self._attr_table.horizontalHeader().setStretchLastSection(True)
        self._attr_table.itemDoubleClicked.connect(self._edit_attr)
        add = QPushButton("Adicionar")
        edit = QPushButton("Editar")
        remove = QPushButton("Remover")
        add.clicked.connect(self._add_attr)
        edit.clicked.connect(self._edit_attr)
        remove.clicked.connect(self._remove_attr)
        row = QHBoxLayout()
        for b in (add, edit, remove):
            row.addWidget(b)
        row.addStretch()
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self._attr_table)
        layout.addLayout(row)
        return tab

    def _refresh_attrs(self) -> None:
        self._attr_table.setRowCount(len(self._attrs))
        for i, spec in enumerate(self._attrs):
            self._attr_table.setItem(i, 0, QTableWidgetItem(spec.get("name", "")))
            self._attr_table.setItem(i, 1, QTableWidgetItem(spec.get("label", "")))
            self._attr_table.setItem(i, 2, QTableWidgetItem(spec.get("type", "")))
            self._attr_table.setItem(
                i, 3, QTableWidgetItem("sim" if spec.get("required") else "nao")
            )

    def _add_attr(self) -> None:
        spec = AttributeDialog.create(self)
        if spec is not None:
            self._attrs.append(spec)
            self._refresh_attrs()

    def _edit_attr(self) -> None:
        row = self._attr_table.currentRow()
        if row < 0:
            return
        spec = AttributeDialog.edit(self, self._attrs[row])
        if spec is not None:
            spec["id"] = self._attrs[row].get("id")
            spec["reference_config"] = self._attrs[row].get("reference_config")
            self._attrs[row] = spec
            self._refresh_attrs()

    def _remove_attr(self) -> None:
        row = self._attr_table.currentRow()
        if row < 0:
            return
        del self._attrs[row]
        self._refresh_attrs()

    # -- payload ------------------------------------------------------------------

    def payload(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._desc.text(),
            "color": self._color.text().strip() or "#888888",
            "icon": self._icon.text().strip(),
            "phases": self._phases,
            "attributes": self._attrs,
        }

    def accept(self) -> None:
        errors = validate_type_payload(self.payload())
        if errors:
            QMessageBox.warning(self, "Validacao", "\n".join(errors))
            return
        super().accept()

    @classmethod
    def create(cls, parent: QWidget | None = None) -> dict | None:
        dlg = cls(parent)
        return dlg.payload() if dlg.exec() else None

    @classmethod
    def edit(cls, parent: QWidget | None, payload: dict) -> dict | None:
        dlg = cls(parent, payload)
        return dlg.payload() if dlg.exec() else None
