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
    finals = [p for p in phases if p.get("is_final")]
    if len(finals) != 1:
        errors.append("Tipo precisa de exatamente 1 fase final.")
    names = [a.get("name", "") for a in payload.get("attributes", [])]
    if len(names) != len(set(names)):
        errors.append("Nomes de atributos duplicados.")
    return errors


class TaskTypeDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        payload: dict | None = None,
        ref_targets: list[dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tipo de tarefa")
        self.resize(560, 480)
        payload = payload or {}
        self._ref_targets: list[dict] = [dict(t) for t in (ref_targets or [])]

        self._name = QLineEdit(payload.get("name", ""))
        self._desc = QLineEdit(payload.get("description", ""))
        self._color = QLineEdit(payload.get("color", "#888888"))
        pick_color = QPushButton("Escolher...")
        pick_color.clicked.connect(self._pick_color)
        from PySide6.QtWidgets import QLabel

        self._color_preview = QLabel("   ")
        self._color_preview.setFixedWidth(28)
        self._icon_preview = QLabel("")
        self._icon = QLineEdit(payload.get("icon", ""))
        self._icon.setPlaceholderText("ex: 🐞  (emoji ou texto)")
        self._color.textChanged.connect(lambda _t: self._refresh_preview())
        self._icon.textChanged.connect(lambda _t: self._refresh_preview())
        self._name.textChanged.connect(lambda _t: self._refresh_preview())
        color_row = QHBoxLayout()
        color_row.addWidget(self._color)
        color_row.addWidget(pick_color)
        color_row.addWidget(self._color_preview)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self._icon)
        icon_row.addWidget(self._icon_preview)

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Descricao:", self._desc)
        form.addRow("Cor:", color_row)
        form.addRow("Icone:", icon_row)

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
        self._refresh_preview()

    # -- topo ---------------------------------------------------------------

    def _pick_color(self) -> None:
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self._color.text()), self)
        if color.isValid():
            self._color.setText(color.name())
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        from task_level.presentation.widgets.type_badge import (
            normalize_color,
            type_label,
        )

        color = normalize_color(self._color.text())
        self._color_preview.setStyleSheet(
            f"background: {color}; border: 1px solid #555; border-radius: 4px;"
        )
        self._color_preview.setToolTip(color)
        icon = self._icon.text().strip()
        name = self._name.text().strip() or "Nome"
        self._icon_preview.setText(type_label(name, icon))

    # -- fases ----------------------------------------------------------------

    def _build_phases_tab(self) -> QWidget:
        from PySide6.QtWidgets import QAbstractItemView, QLabel

        self._phase_list = QListWidget()
        self._phase_list.itemDoubleClicked.connect(self._edit_phase)
        # arrasto desligado por padrao (evita troca por engano)
        self._phase_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._phase_list.setDefaultDropAction(Qt.MoveAction)
        self._phase_list.model().rowsMoved.connect(self._phases_dropped)
        add = QPushButton("Adicionar")
        edit = QPushButton("Editar")
        remove = QPushButton("Remover")
        self._drag_toggle = QPushButton()
        self._drag_toggle.setCheckable(True)
        self._drag_toggle.setChecked(False)
        self._drag_toggle.toggled.connect(self._set_drag_enabled)
        add.clicked.connect(self._add_phase)
        edit.clicked.connect(self._edit_phase)
        remove.clicked.connect(self._remove_phase)
        row = QHBoxLayout()
        for b in (add, edit, remove, self._drag_toggle):
            row.addWidget(b)
        row.addStretch()
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._drag_hint = QLabel("")
        self._drag_hint.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self._drag_hint)
        layout.addWidget(self._phase_list)
        layout.addLayout(row)
        self._set_drag_enabled(False)
        return tab

    def _set_drag_enabled(self, enabled: bool) -> None:
        self._phase_list.setDragEnabled(enabled)
        self._phase_list.setAcceptDrops(enabled)
        self._drag_toggle.setText(
            "🔓 Reordenar: ligado" if enabled else "🔒 Reordenar: desligado"
        )
        self._drag_hint.setText(
            "Arraste as fases para reordenar."
            if enabled
            else "Primeira = inicio, ultima = fim. Ligue Reordenar para arrastar."
        )

    def _refresh_phases(self) -> None:
        from task_level.presentation.widgets.type_badge import make_color_icon

        self._phase_list.clear()
        last = len(self._phases) - 1
        for i, spec in enumerate(self._phases):
            tags = []
            if i == 0:
                tags.append("inicio")
            if i == last:
                tags.append("fim")
            raw_conds = spec.get("enter_conditions")
            try:
                from task_level.services.filters import count_conditions as _count

                _n_conds, _n_groups = _count(raw_conds)
            except Exception:
                _n_conds = len(raw_conds) if isinstance(raw_conds, list) else 0
                _n_groups = 1
            if _n_conds:
                extra = f" em {_n_groups} grupos" if _n_groups > 1 else ""
                tags.append(f"{_n_conds} condicao(oes){extra}")
            suffix = f" [{', '.join(tags)}]" if tags else ""
            item = QListWidgetItem(f"{i}. {spec.get('name', '')}{suffix}")
            item.setData(Qt.UserRole, i)
            item.setIcon(make_color_icon(spec.get("color", "#888888")))
            self._phase_list.addItem(item)

    def _type_attrs_for_conditions(self) -> list[dict]:
        """Atributos do tipo em edicao (p/ condicoes de fase, por nome)."""
        return [
            {
                "type_id": 0,
                "type_name": "",
                "name": a.get("name", ""),
                "label": a.get("label", a.get("name", "")),
                "type": a.get("type", "text"),
                "options": a.get("options"),
            }
            for a in self._attrs
        ]

    def _add_phase(self) -> None:
        spec = PhaseDialog.create(self, type_attrs=self._type_attrs_for_conditions())
        if spec is not None:
            spec["order"] = len(self._phases)  # fim da fila, automatico
            self._phases.append(spec)
            self._refresh_phases()

    def _edit_phase(self) -> None:
        row = self._phase_list.currentRow()
        if row < 0:
            return
        spec = PhaseDialog.edit(
            self, self._phases[row], type_attrs=self._type_attrs_for_conditions()
        )
        if spec is not None:
            spec["id"] = self._phases[row].get("id")  # preserva vinculo
            spec["order"] = row  # ordem e sempre a posicao
            self._phases[row] = spec
            self._refresh_phases()

    def _remove_phase(self) -> None:
        row = self._phase_list.currentRow()
        if row < 0:
            return
        del self._phases[row]
        self._renumber_phases()
        self._refresh_phases()

    def _phases_dropped(self, *_args) -> None:
        """Apos arrastar: a ordem passa a ser a posicao na lista."""
        self._sync_order_from_list()
        self._refresh_phases()

    def _sync_order_from_list(self) -> None:
        """Reconstroi self._phases na ordem visual e renumera."""
        ordered = []
        for row in range(self._phase_list.count()):
            ordered.append(self._phases[self._phase_list.item(row).data(Qt.UserRole)])
        self._phases = ordered
        self._renumber_phases()

    def _renumber_phases(self) -> None:
        for i, spec in enumerate(self._phases):
            spec["order"] = i

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
        spec = AttributeDialog.create(self, ref_targets=self._ref_targets)
        if spec is not None:
            self._attrs.append(spec)
            self._refresh_attrs()

    def _edit_attr(self) -> None:
        row = self._attr_table.currentRow()
        if row < 0:
            return
        spec = AttributeDialog.edit(self, self._attrs[row], ref_targets=self._ref_targets)
        if spec is not None:
            spec["id"] = self._attrs[row].get("id")
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
        # primeira = inicio, ultima = fim (sempre; sem opcao manual)
        phases = []
        for i, spec in enumerate(self._phases):
            p = dict(spec)
            p["is_initial"] = (i == 0)
            p["is_final"] = (i == len(self._phases) - 1)
            phases.append(p)
        return {
            "name": self._name.text().strip(),
            "description": self._desc.text(),
            "color": self._color.text().strip() or "#888888",
            "icon": self._icon.text().strip(),
            "phases": phases,
            "attributes": self._attrs,
        }

    def accept(self) -> None:
        errors = validate_type_payload(self.payload())
        if errors:
            QMessageBox.warning(self, "Validacao", "\n".join(errors))
            return
        super().accept()

    @classmethod
    def create(
        cls, parent: QWidget | None = None, ref_targets: list[dict] | None = None
    ) -> dict | None:
        dlg = cls(parent, ref_targets=ref_targets)
        return dlg.payload() if dlg.exec() else None

    @classmethod
    def edit(
        cls,
        parent: QWidget | None,
        payload: dict,
        ref_targets: list[dict] | None = None,
    ) -> dict | None:
        dlg = cls(parent, payload, ref_targets=ref_targets)
        return dlg.payload() if dlg.exec() else None
