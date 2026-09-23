"""Dialog de criar/editar task com formulario dinamico (Parte 9).

Campos por tipo de atributo:
- text -> QLineEdit | number -> QLineEdit numerico | boolean -> QCheckBox
- reference_task -> QComboBox de tasks | reference_attribute -> picker dedicado
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import AttributeType, DomainError, task_number
from task_level.presentation.dialogs.reference_attribute_picker import (
    ReferenceAttributePicker,
)


def format_attr_value(
    attr, attr_type: str | None = None, ref_numbers: dict[int, int] | None = None
) -> str:
    """Texto curto do valor de um TaskAttribute (p/ exibir em combos/resumos).

    ref_numbers: task_id -> numero visivel (p/ referencias mostrarem #seq).
    """
    from task_level.domain import AttributeType, format_currency, format_date

    if attr_type == AttributeType.CURRENCY.value and attr.value_number is not None:
        return format_currency(attr.value_number)
    if attr_type == AttributeType.DATE.value and attr.value_text:
        return format_date(attr.value_text)
    if attr_type == AttributeType.FILE.value and attr.value_text:
        from pathlib import Path as _Path

        return _Path(attr.value_text).name
    if attr.value_text is not None:
        text = attr.value_text.strip()
        return text if len(text) <= 40 else text[:39] + "…"
    if attr.value_number is not None:
        number = attr.value_number
        return str(int(number)) if float(number).is_integer() else str(number)
    if attr.value_boolean is not None:
        return "sim" if attr.value_boolean else "nao"
    if attr.value_reference_task_id is not None:
        number = (ref_numbers or {}).get(
            attr.value_reference_task_id, attr.value_reference_task_id
        )
        return f"task #{number}"
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
        self._file_pending: dict[str, str] = {}
        self._file_cleared: set[str] = set()
        self._note_edits: dict[int, QTextEdit] = {}
        self._ordered_phases: list = []

        self.setWindowTitle("Editar task" if task_id else "Nova task")
        self.setSizeGripEnabled(True)

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

        self._notes_tabs = QTabWidget()
        self._notes_tabs.setVisible(task_id is not None)
        notes_label = QLabel("Observacoes por fase:")
        notes_label.setVisible(task_id is not None)
        self._notes_label = notes_label

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Conteudo rolavel: com muitos atributos o dialogo ultrapassava a tela
        # e os botoes ficavam cortados. A rolagem fica no conteudo; os botoes
        # OK/Cancel permanecem fixos no rodape.
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addLayout(form)
        content_layout.addLayout(attr_box)
        content_layout.addWidget(self._notes_label)
        content_layout.addWidget(self._notes_tabs)
        content_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(content)
        self._scroll = scroll

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(buttons)

        # Com muitos atributos o conteudo e maior que a tela: a rolagem fica
        # no conteudo e os botoes OK/Cancel permanecem fixos no rodape.
        # O dialogo nunca abre maior que a area util da tela.
        self._fit_to_screen()
        self.setMinimumSize(420, 300)

        self._load_types()
        if task_id is None:
            self._type_combo.currentIndexChanged.connect(self._rebuild_attributes)
            self._rebuild_attributes()
        else:
            self._load_existing(task_type_id)

    # -- ajuste a tela ----------------------------------------------------------

    def _available_geometry(self):
        """Area util da tela onde o dialogo vai aparecer (sem taskbar)."""
        try:
            screen = self.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                parent = self.parentWidget()
                if parent is not None:
                    screen = parent.screen()
            except Exception:
                screen = None
        if screen is None:
            try:
                screen = QGuiApplication.primaryScreen()
            except Exception:
                screen = None
        if screen is not None:
            try:
                return screen.availableGeometry()
            except Exception:
                return None
        return None

    def _fit_to_screen(self) -> None:
        avail = self._available_geometry()
        if avail is None:
            self.resize(520, 620)
            return
        max_w = max(420, int(avail.width() * 0.95))
        max_h = max(300, int(avail.height() * 0.92))
        self.setMaximumSize(max_w, max_h)
        # Tamanho inicial confortavel, mas sempre dentro da area util.
        self.resize(min(520, max_w), min(620, max_h))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Garante que mesmo apos construir os campos o dialogo caiba na tela:
        # encolhe se preciso e recentraliza na area util.
        avail = self._available_geometry()
        if avail is None:
            return
        w = min(self.width(), avail.width())
        h = min(self.height(), int(avail.height() * 0.92))
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)
        # Recentraliza se estiver (parcialmente) fora da area util.
        geom = self.frameGeometry()
        if not avail.contains(geom):
            geom.moveCenter(avail.center())
            # move() respeita o window manager; garante topo visivel.
            x = max(avail.left(), min(geom.left(), avail.right() - w))
            y = max(avail.top(), min(geom.top(), avail.bottom() - h))
            self.move(x, y)

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
            notes = {
                n.phase_id: n.note for n in uow.phase_notes.list_by_task(task.id)
            }
            self._build_notes_tabs(notes)
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

    def _build_notes_tabs(self, notes: dict[int, str]) -> None:
        """Uma aba de observacao por fase (edit mode)."""
        self._notes_tabs.clear()
        self._note_edits = {}
        self._ordered_phases = list(self._phase_options)
        current_tab = 0
        for i, phase in enumerate(self._ordered_phases):
            editor = QTextEdit()
            editor.setMaximumHeight(80)
            editor.setPlaceholderText(f"Observacao sobre '{phase.name}'...")
            if phase.id is not None and phase.id in notes:
                editor.setPlainText(notes[phase.id])
            assert phase.id is not None
            self._note_edits[phase.id] = editor
            self._notes_tabs.addTab(editor, phase.name)
            if phase.id == self._target_phase_id:
                current_tab = i
        self._notes_tabs.setCurrentIndex(current_tab)
        has_phases = bool(self._ordered_phases)
        self._notes_tabs.setVisible(has_phases)
        self._notes_label.setVisible(has_phases)

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
            prev_id = self._phase_options[pos - 1].id if has_prev else None
            next_id = self._phase_options[pos + 1].id if has_next else None
        else:
            has_prev, has_next, prev_name, next_name = False, bool(ids), "", ""
            prev_id, next_id = None, None
        back_block = self._transition_block(prev_id) if has_prev else None
        fwd_block = self._transition_block(next_id) if has_next else None
        self._btn_phase_back.setEnabled(has_prev)
        self._btn_phase_fwd.setEnabled(has_next)
        self._btn_phase_back.setToolTip(
            back_block
            or (f"Voltar para {prev_name}" if has_prev else "Ja esta na primeira fase")
        )
        self._btn_phase_fwd.setToolTip(
            fwd_block
            or (f"Avancar para {next_name}" if has_next else "Ja esta na ultima fase")
        )

    def _transition_block(self, phase_id: int | None) -> str | None:
        if phase_id is None or self._task_id is None:
            return None
        from task_level.domain import DomainError
        from task_level.services import TaskService

        try:
            TaskService(self._db_path).check_move(self._task_id, phase_id)
        except DomainError as e:
            return str(e)
        return None

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
        self._file_pending = {}
        self._file_cleared = set()

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
            elif d.type == AttributeType.SELECT.value:
                w = QComboBox()
                w.addItem("(nenhuma)", None)
                for option in (d.options or []):
                    w.addItem(option, option)
                if saved and saved.value_text:
                    idx = w.findData(saved.value_text)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
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
                        w.addItem(f"[{tname}] #{task_number(t)} {t.title}", t.id)
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
            elif d.type == AttributeType.FILE.value:
                from task_level.data.files import attachment_label

                key = d.name
                self._file_pending.pop(key, None)
                self._file_cleared.discard(key)
                label = QLabel("")
                if saved and saved.value_text:
                    label.setText(attachment_label(saved.value_text))
                else:
                    label.setText("(nenhum)")
                select = QPushButton("Selecionar...")
                select.clicked.connect(
                    lambda _=False, k=key, lb=label: self._pick_file(k, lb)
                )
                open_btn = QPushButton("Abrir")
                open_btn.clicked.connect(lambda _=False, k=key: self._open_file(k))
                clear = QPushButton("Limpar")
                clear.clicked.connect(
                    lambda _=False, k=key, lb=label: self._clear_file(k, lb)
                )
                row = QHBoxLayout()
                row.addWidget(label, stretch=1)
                row.addWidget(select)
                row.addWidget(open_btn)
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

    def _effective_file(self, key: str) -> str | None:
        """Caminho a abrir: pendente (novo) ou o ja salvo."""
        if key in self._file_pending:
            return self._file_pending[key]
        if key in self._file_cleared:
            return None
        definition_id = next(
            (d.id for d in self._definitions if d.name == key),
            None,
        )
        saved = self._saved_values.get(definition_id) if definition_id else None
        return saved.value_text if saved else None

    def _refresh_file_label(self, key: str, label: QLabel) -> None:
        from task_level.data.files import attachment_label

        effective = self._effective_file(key)
        prefix = "🆕 " if key in self._file_pending else ""
        label.setText(prefix + attachment_label(effective))

    def _pick_file(self, key: str, label: QLabel) -> None:
        from PySide6.QtWidgets import QFileDialog

        chosen, _ = QFileDialog.getOpenFileName(self, "Selecionar arquivo")
        if not chosen:
            return
        self._file_pending[key] = chosen
        self._file_cleared.discard(key)
        self._refresh_file_label(key, label)

    def _open_file(self, key: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        effective = self._effective_file(key)
        if not effective:
            QMessageBox.information(self, "Arquivo", "Nenhum arquivo anexado.")
            return
        if not Path(effective).is_file():
            QMessageBox.warning(self, "Arquivo", "Arquivo nao encontrado no disco.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(effective))

    def _clear_file(self, key: str, label: QLabel) -> None:
        self._file_pending.pop(key, None)
        self._file_cleared.add(key)
        self._refresh_file_label(key, label)

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
            return (
                f"#{task_number(task)} {task.title} - {name} = "
                f"{format_attr_value(attr, dtype)}"
            )

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
                shown = format_attr_value(value, target_def.type)
                eligible.append(
                    (
                        t.id,
                        f"[{tname}] #{task_number(t)} {t.title}"
                        f" — {target_def.label} = {shown}",
                    )
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
            elif d.type == AttributeType.SELECT.value:
                if widget.currentData() is not None:
                    values[name] = widget.currentData()
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
            if not d.required or d.type == "boolean":
                continue
            if d.type == AttributeType.FILE.value:
                has_file = d.name in self._file_pending or (
                    self._effective_file(d.name) is not None
                )
                if not has_file:
                    errors.append(f"'{d.label}' e obrigatorio.")
            elif d.name not in payload_values:
                errors.append(f"'{d.label}' e obrigatorio.")
        if errors:
            QMessageBox.warning(self, "Validacao", "\n".join(errors))
            return
        if self._task_id is not None:
            target = self.payload()["phase_id"]
            if target is not None and target != self._origin_phase_id:
                block = self._transition_block(target)
                if block is not None:
                    QMessageBox.warning(self, "Nao e possivel mudar de fase", block)
                    self._target_phase_id = self._origin_phase_id
                    self._refresh_phase_stepper()
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
                self._apply_files(svc, task.id)
                self._apply_notes(svc, task.id)
                return task.id
            svc.update_details(self._task_id, data["title"], data["description"])
            with UnitOfWork.open(self._db_path) as uow:
                task = uow.tasks.get(self._task_id)
                assert task is not None
                definitions = uow.attribute_definitions.list_by_task_type(
                    task.task_type_id
                )
            for d in definitions:
                if d.type == AttributeType.FILE.value:
                    continue  # anexos tratados em _apply_files
                if d.name in data["values"]:
                    svc.set_attribute(self._task_id, d.name, data["values"][d.name])
                else:
                    svc.clear_attribute(self._task_id, d.name)
            self._apply_files(svc, self._task_id)
            self._apply_notes(svc, self._task_id)
            if data["phase_id"] is not None and data["phase_id"] != task.phase_id:
                svc.move_phase(self._task_id, data["phase_id"])
            return self._task_id
        except DomainError as e:
            QMessageBox.critical(self, "Erro", str(e))
            raise

    def _apply_notes(self, svc, task_id: int) -> None:
        """Salva as observacoes por fase (vazia = apaga)."""
        for phase_id, editor in self._note_edits.items():
            svc.set_phase_note(task_id, phase_id, editor.toPlainText())

    def _apply_files(self, svc, task_id: int) -> None:
        """Copia anexos pendentes e limpa os marcados (sem tocar nos demais)."""
        for name, source in self._file_pending.items():
            svc.set_file_attribute(task_id, name, source)
        for name in self._file_cleared:
            if name not in self._file_pending:
                svc.clear_attribute(task_id, name)

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
