"""Historico de mudancas do projeto (log de atividade, recentes primeiro)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from task_level.data import UnitOfWork
from task_level.domain import to_local

ACTION_LABELS = {
    "created": "criada",
    "updated": "editada",
    "deleted": "excluida",
    "moved": "fase",
    "attribute": "atributo",
    "note": "observacao",
}


class HistoryDialog(QDialog):
    def __init__(
        self, parent: QWidget | None, db_path: str | Path, project_id: int
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historico de mudancas")
        self.resize(620, 420)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrar por task ou texto...")
        self._search.textChanged.connect(self._apply_filter)
        self._list = QListWidget()

        top = QHBoxLayout()
        top.addWidget(QLabel("Buscar:"))
        top.addWidget(self._search)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._list)
        self._entries: list[str] = []
        self._load(project_id, db_path)

    def _load(self, project_id: int, db_path: str | Path) -> None:
        with UnitOfWork.open(db_path) as uow:
            entries = uow.activity.list_by_project(project_id)
        self._entries = []
        for e in entries:
            stamp = to_local(e.created_at).strftime("%d/%m %H:%M")
            action = ACTION_LABELS.get(e.action, e.action)
            self._entries.append(f"{stamp}  [{action}] {e.summary}")
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self._search.text().strip().lower()
        self._list.clear()
        for text in self._entries:
            if needle and needle not in text.lower():
                continue
            self._list.addItem(QListWidgetItem(text))

    @classmethod
    def show(cls, parent: QWidget | None, db_path: str | Path, project_id: int) -> None:
        dlg = cls(parent, db_path, project_id)
        dlg.exec()
