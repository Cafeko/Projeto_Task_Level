"""Dialogo de Foco: escolhe quais atributos aparecem inline nas listas."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class FocusDialog(QDialog):
    def __init__(
        self,
        parent,
        db_path: str | Path,
        project_id: int,
        type_id: int | None = None,
        selected: list[str] | dict | None = None,
    ) -> None:
        from task_level.data import UnitOfWork

        super().__init__(parent)
        self.setWindowTitle("Foco: atributos visiveis")
        self.resize(380, 360)
        self._db_path = db_path
        self._project_id = project_id
        self._fixed_type = type_id
        # selecoes por tipo: {"12": {"sev", "preco"}} — preserva ao trocar de tipo
        self._selections: dict[str, set[str]] = {}
        pending_single: set[str] | None = None
        if isinstance(selected, dict):
            for k, v in selected.items():
                if isinstance(v, (list, tuple, set)):
                    names = {str(n) for n in v if str(n)}
                    if names:
                        self._selections[str(k)] = names
        elif isinstance(selected, (list, tuple, set)):
            pending_single = {str(n) for n in selected if str(n)}

        layout = QVBoxLayout(self)
        self._type_combo: QComboBox | None = None
        if type_id is None:
            type_form = QFormLayout()
            self._type_combo = QComboBox()
            with UnitOfWork.open(db_path) as uow:
                for t in uow.task_types.list_by_project(project_id):
                    self._type_combo.addItem(t.name, t.id)
            # Se ja ha foco aplicado, abre mostrando um tipo que tem foco
            # para o usuario ver marcado de cara.
            if self._selections and self._type_combo.count():
                for i in range(self._type_combo.count()):
                    tid = self._type_combo.itemData(i)
                    if str(tid) in self._selections:
                        self._type_combo.blockSignals(True)
                        self._type_combo.setCurrentIndex(i)
                        self._type_combo.blockSignals(False)
                        break
            type_form.addRow("Tipo:", self._type_combo)
            layout.addLayout(type_form)
        else:
            if pending_single:
                self._selections[str(type_id)] = set(pending_single)
                pending_single = None
        # lista legada no modo Todos: aplica no tipo inicial visivel
        self._pending_single = pending_single

        self._list = QListWidget()
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("Todos")
        btn_all.setToolTip("Marca todos os atributos do tipo atual")
        btn_all.clicked.connect(self._check_all_current)
        btn_none = QPushButton("Limpar")
        btn_none.setToolTip("Desmarca os atributos do tipo atual")
        btn_none.clicked.connect(self._clear_current)
        btn_all_types = QPushButton("Limpar tudo")
        btn_all_types.setToolTip("Remove o foco de todos os tipos")
        btn_all_types.clicked.connect(self._clear_all_scopes)
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addWidget(btn_all_types)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._type_combo is not None:
            self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._last_scope: int | None = self._current_scope()
        # aplica pendencia legada (Todos + lista simples) no escopo inicial
        if self._pending_single and self._last_scope is not None:
            self._selections.setdefault(str(self._last_scope), set()).update(
                self._pending_single
            )
            self._pending_single = None
        self._reload_attrs()

    def _current_scope(self) -> int | None:
        if self._fixed_type is not None:
            return self._fixed_type
        if self._type_combo is not None:
            return self._type_combo.currentData()
        return None

    def _collect_current(self) -> list[str]:
        names = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.checkState() == Qt.Checked:
                names.append(item.data(Qt.UserRole))
        return names

    def _stash_current(self) -> None:
        scope = self._last_scope
        if scope is None:
            # fallback: usa o escopo visivel (ex: antes do accept)
            scope = self._current_scope()
            if scope is None:
                return
        names = set(self._collect_current())
        if names:
            self._selections[str(scope)] = names
        else:
            self._selections.pop(str(scope), None)

    def _on_type_changed(self) -> None:
        self._stash_current()
        self._last_scope = self._current_scope()
        self._reload_attrs()

    def _reload_attrs(self) -> None:
        from task_level.data import UnitOfWork

        self._list.clear()
        scope = self._current_scope()
        self._last_scope = scope
        if scope is None:
            return
        with UnitOfWork.open(self._db_path) as uow:
            definitions = uow.attribute_definitions.list_by_task_type(scope)
        checked = self._selections.get(str(scope), set())
        for d in definitions:
            item = QListWidgetItem(d.label)
            item.setData(Qt.UserRole, d.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if d.name in checked else Qt.Unchecked
            )
            self._list.addItem(item)

    def _check_all_current(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Checked)

    def _clear_current(self) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(Qt.Unchecked)

    def _clear_all_scopes(self) -> None:
        self._selections.clear()
        self._clear_current()

    def accept(self) -> None:
        self._stash_current()
        super().accept()

    def data(self) -> tuple[int | None, list[str]]:
        """Compat: (escopo, nomes) do tipo visivel (usado no Kanban/tipo fixo)."""
        self._stash_current()
        scope = self._current_scope()
        names = list(self._selections.get(str(scope), set())) if scope is not None else []
        # preserva a ordem da lista visivel
        order = [self._list.item(i).data(Qt.UserRole) for i in range(self._list.count())]
        names = [n for n in order if n in set(names)]
        return (scope, names)

    def data_all(self) -> dict[str, list[str]]:
        """Todas as selecoes por tipo (usado no modo Todos)."""
        self._stash_current()
        out: dict[str, list[str]] = {}
        for k, v in self._selections.items():
            if v:
                out[str(k)] = sorted(v)
        return out

    @classmethod
    def edit(
        cls,
        parent,
        db_path: str | Path,
        project_id: int,
        type_id: int | None = None,
        selected: list[str] | dict | None = None,
    ) -> tuple[int | None, list[str]] | dict[str, list[str]] | None:
        dlg = cls(parent, db_path, project_id, type_id, selected)
        if not dlg.exec():
            return None
        if type_id is None:
            return dlg.data_all()
        return dlg.data()
