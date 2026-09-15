"""Dialog de criar/renomear projeto (Parte 7)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from task_level.domain import Project


class ProjectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        name: str = "",
        description: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Projeto")
        self._name = QLineEdit(name)
        self._desc = QTextEdit(description)
        self._desc.setMaximumHeight(80)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Descricao:", self._desc)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validacao", "Nome nao pode ser vazio.")
            return
        super().accept()

    def data(self) -> tuple[str, str]:
        return self._name.text().strip(), self._desc.toPlainText()

    @classmethod
    def create(cls, parent: QWidget | None = None) -> tuple[str, str] | None:
        dlg = cls(parent)
        return dlg.data() if dlg.exec() else None

    @classmethod
    def edit(cls, parent: QWidget | None, project: Project) -> tuple[str, str] | None:
        dlg = cls(parent, project.name, project.description)
        return dlg.data() if dlg.exec() else None
