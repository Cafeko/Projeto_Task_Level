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


def _format_attr_value(attr, attr_type: str | None = None) -> str:
    """Texto curto do valor de um TaskAttribute (p/ exibir em combos/resumos)."""
    from task_level.domain import AttributeType, format_currency, format_date

    if attr_type == AttributeType.CURRENCY.value and attr.value_number is not None:
        return format_currency(attr.value_number)
    if attr_type == AttributeType.DATE.value and attr.value_text:
        return format_date(attr.value_text)
    if attr.value_text is not None:
        text = attr.value_text.strip()
        return text if len(text) <= 40 else text[:39] + "…"
    if attr.value_number is not None:
        number = attr.value_number
        return str(int(number)) if float(number).is_integer() else str(number)
    if attr.value_boolean is not None:
        return "sim" if attr.value_boolean else "nao"
    if attr.value_reference_task_id is not None:
        return f"task #{attr.value_reference_task_id}"
    return "-"


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
        self._ref_fixed: dict[str, tuple[QComboBox, str]] = {}
        self._date_edits: dict[str, QWidget] = {}

        self.setWindowTitle("Editar task" if task_id else "Nova task")
        self.resize(480, 520)

        self._title = QLineEdit()
        self._desc = QTextEdit()
        self._desc.setMaximumHeight(70)
        self._type_combo = QComboBox()
        self._phase_label = QLabel("-")
        self._btn_phase_back = QPushButton("← Voltar")
        self._btn_phase_fwd = QPushButton("Avancar →")
        self._btn_phase_back.clicked.connect(lambda: self._step_phase(-1))
        self._btn_phase_fwd.clicked.connect(lambda: self._step_phase(+1))
        self._phase_options: list = []
        self._origin_phase_id: int | None = None
        self._target_phase_id: int | None = None

        form = QFormLayout()
        if task_id is None:
            form.addRow("Tipo:", self._type_combo)
        else:
            self._type_label = QLabel("")
            form.addRow("Tipo:", self._type_label)
            phase_row = QHBoxLayout()
            phase_row.addWidget(self._phase_label, stretch=1)
            phase_row.addWidget(self._btn_phase_back)
            phase_row.addWidget(self._btn_phase_fwd)
            form.addRow("Fase:", phase_row)
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
            self._phase_options = sorted(
                uow.phases.list_by_task_type(self._type_id), key=lambda p: p.order
            )
            self._origin_phase_id = task.phase_id
            self._target_phase_id = task.phase_id
            self._refresh_phase_stepper()
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

    def _step_phase(self, delta: int) -> None:
        """Move o alvo uma fase (botoes Voltar/Avancar)."""
        ids = [p.id for p in self._phase_options]
        if self._target_phase_id in ids:
            pos = ids.index(self._target_phase_id)
        elif delta > 0 and ids:
            pos = -1
        else:
            return
        new_pos = pos + delta
        if 0 <= new_pos < len(ids):
            self._target_phase_id = ids[new_pos]
            self._refresh_phase_stepper()

    def _refresh_phase_stepper(self) -> None:
        ids = [p.id for p in self._phase_options]
        names = {p.id: p.name for p in self._phase_options}
        current = names.get(self._target_phase_id, "-")
        if self._target_phase_id != self._origin_phase_id:
            current += " (vai mudar ao salvar)"
        self._phase_label.setText(current)
        if self._target_phase_id in ids:
            pos = ids.index(self._target_phase_id)
            has_prev, has_next = pos > 0, pos < len(ids) - 1
            prev_name = self._phase_options[pos - 1].name if has_prev else ""
            next_name = self._phase_options[pos + 1].name if has_next else ""
        else:
            has_prev, has_next, prev_name, next_name = False, bool(ids), "", ""
        self._btn_phase_back.setEnabled(has_prev)
        self._btn_phase_fwd.setEnabled(has_next)
        self._btn_phase_back.setToolTip(
            f"Voltar para {prev_name}" if has_prev else "Ja esta na primeira fase"
        )
        self._btn_phase_fwd.setToolTip(
            f"Avancar para {next_name}" if has_next else "Ja esta na ultima fase"
        )

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
        self._ref_fixed = {}
        self._date_edits = {}

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
            elif d.type == AttributeType.CURRENCY.value:
                from task_level.domain import format_currency

                w = QLineEdit()
                w.setPlaceholderText("ex: 1.234,56")
                if saved and saved.value_number is not None:
                    w.setText(format_currency(saved.value_number))
                widget = w
            elif d.type == AttributeType.DATE.value:
                from PySide6.QtCore import QDate
                from PySide6.QtWidgets import QDateEdit

                date_edit = QDateEdit()
                date_edit.setCalendarPopup(True)
                date_edit.setDisplayFormat("dd/MM/yyyy")
                if saved and saved.value_text:
                    try:
                        from task_level.domain import parse_date

                        iso = parse_date(saved.value_text)
                        date_edit.setDate(QDate.fromString(iso, "yyyy-MM-dd"))
                    except Exception:
                        date_edit.setDate(QDate.currentDate())
                else:
                    date_edit.setDate(QDate.currentDate())
                self._date_edits[d.name] = date_edit
                widget = date_edit
            elif d.type == AttributeType.REFERENCE_TASK.value:
                w = QComboBox()
                w.addItem("(nenhuma)", None)
                allowed_type = (d.reference_config or {}).get("target_type_id")
                with UnitOfWork.open(self._db_path) as uow:
                    type_names = {
                        t.id: t.name
                        for t in uow.task_types.list_by_project(self._project_id)
                    }
                    for t in uow.tasks.list_by_project(self._project_id):
                        if t.id == self._task_id:
                            continue
                        if allowed_type is not None and t.task_type_id != allowed_type:
                            continue
                        tname = type_names.get(t.task_type_id, "?")
                        w.addItem(f"[{tname}] #{t.id} {t.title}", t.id)
                if saved and saved.value_reference_task_id is not None:
                    idx = w.findData(saved.value_reference_task_id)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                widget = w
            elif d.type == AttributeType.REFERENCE_ATTRIBUTE.value:
                fixed_attr = (d.reference_config or {}).get("attribute_name")
                if fixed_attr:
                    w = QComboBox()
                    w.addItem("(nenhuma)", None)
                    for task_id, label in self._eligible_ref_tasks(d):
                        w.addItem(label, task_id)
                    if saved and saved.value_reference_task_id is not None:
                        idx = w.findData(saved.value_reference_task_id)
                        if idx >= 0:
                            w.setCurrentIndex(idx)
                    self._ref_fixed[d.name] = (w, fixed_attr)
                    widget = w
                    suffix = " *" if d.required else ""
                    self._attr_form.addRow(f"{d.label} → {fixed_attr}{suffix}:", widget)
                    self._fields[d.name] = widget
                    continue
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
            dtype = d.type if d else None
            return f"#{task_id} {task.title} - {name} = {_format_attr_value(attr, dtype)}"

    def _eligible_ref_tasks(self, definition) -> list[tuple[int, str]]:
        """Tasks do projeto que ja tem valor no atributo fixo (referenciaveis).

        Vale para tipos diferentes: filtra pelo nome do atributo e,
        se configurado, pelo tipo alvo.
        """
        config = definition.reference_config or {}
        attr_name = config.get("attribute_name")
        allowed_type = config.get("target_type_id")
        eligible: list[tuple[int, str]] = []
        with UnitOfWork.open(self._db_path) as uow:
            type_names = {
                t.id: t.name
                for t in uow.task_types.list_by_project(self._project_id)
            }
            for t in uow.tasks.list_by_project(self._project_id):
                if t.id == self._task_id:
                    continue
                if allowed_type is not None and t.task_type_id != allowed_type:
                    continue
                target_def = uow.attribute_definitions.get_by_name(
                    t.task_type_id, attr_name
                )
                if target_def is None or target_def.id is None:
                    continue
                value = uow.task_attributes.get(t.id, target_def.id)
                if value is None:
                    continue  # sem valor ainda: nada a referenciar
                tname = type_names.get(t.task_type_id, "?")
                shown = _format_attr_value(value, target_def.type)
                eligible.append(
                    (t.id, f"[{tname}] #{t.id} {t.title} — {target_def.label} = {shown}")
                )
        return eligible

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
            elif d.type == AttributeType.CURRENCY.value:
                from task_level.domain import ValidationError, parse_currency

                text = widget.text().strip()
                if text:
                    try:
                        values[name] = parse_currency(text)
                    except ValidationError:
                        pass  # service acusa ao salvar; obrigatorio acusa aqui
            elif d.type == AttributeType.DATE.value:
                date_edit = self._date_edits.get(name)
                if date_edit is not None:
                    values[name] = date_edit.date().toString("yyyy-MM-dd")
            elif d.type == AttributeType.REFERENCE_TASK.value:
                if widget.currentData() is not None:
                    values[name] = widget.currentData()
            elif d.type == AttributeType.REFERENCE_ATTRIBUTE.value:
                if name in self._ref_fixed:
                    combo, attr_name = self._ref_fixed[name]
                    task_id = combo.currentData()
                    if task_id is not None:
                        from task_level.services import TaskService

                        resolved = TaskService(self._db_path).resolve_reference_attribute(
                            task_id, attr_name
                        )
                        if resolved is not None:
                            values[name] = resolved
                elif self._ref_attr_values.get(name) is not None:
                    values[name] = self._ref_attr_values[name]
        return {
            "title": self._title.text().strip(),
            "description": self._desc.toPlainText(),
            "task_type_id": self._current_type_id(),
            "phase_id": self._target_phase_id
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
