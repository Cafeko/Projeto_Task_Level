"""Janela principal com navegacao, backup e export (Partes 7 e 10)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
)

from task_level.data.backup import backup_db, export_project_json, restore_db, write_export
from task_level.domain import DomainError
from task_level.presentation.views.project_list_view import ProjectListView
from task_level.presentation.views.project_view import ProjectView
from task_level.services import ProjectService, TaskService, TaskTypeService


class MainWindow(QMainWindow):
    def __init__(self, db_path: str | Path) -> None:
        super().__init__()
        self.db_path = Path(db_path)
        self.projects = ProjectService(self.db_path)
        self.task_types = TaskTypeService(self.db_path)
        self.tasks = TaskService(self.db_path)
        self._settings = QSettings("TaskLevel", "task-level")

        self.setWindowTitle("Task Level")
        self.resize(1000, 700)
        geometry = self._settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        self.list_view = ProjectListView(self.projects, self.open_project)
        self.project_view = ProjectView(self.db_path, self.show_projects)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.list_view)
        self.stack.addWidget(self.project_view)
        self.setCentralWidget(self.stack)

        self._build_menu()
        self.show_projects()
        self.statusBar().showMessage(f"Banco: {self.db_path}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    # -- menu ---------------------------------------------------------------------

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("Arquivo")
        act_backup = QAction("Fazer backup agora", self)
        act_backup.triggered.connect(self._do_backup)
        act_restore = QAction("Restaurar backup...", self)
        act_restore.triggered.connect(self._do_restore)
        act_export = QAction("Exportar projeto (JSON)...", self)
        act_export.triggered.connect(self._do_export)
        act_quit = QAction("Sair", self)
        act_quit.triggered.connect(self.close)
        for act in (act_backup, act_restore, act_export, None, act_quit):
            if act is None:
                file_menu.addSeparator()
            else:
                file_menu.addAction(act)

    def _do_backup(self) -> None:
        try:
            target = backup_db(self.db_path)
        except OSError as e:
            QMessageBox.critical(self, "Backup", f"Falha no backup: {e}")
            return
        QMessageBox.information(self, "Backup", f"Backup salvo em:\n{target}")
        self.statusBar().showMessage(f"Backup: {target}", 8000)

    def _do_restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Restaurar backup", str(self.db_path.parent), "SQLite (*.db)"
        )
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "Restaurar backup",
            "Substituir o banco atual pelo backup? O estado atual sera perdido.",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            restore_db(self.db_path, path)
        except OSError as e:
            QMessageBox.critical(self, "Restaurar", f"Falha ao restaurar: {e}")
            return
        self.show_projects()
        QMessageBox.information(self, "Restaurar", "Backup restaurado com sucesso.")

    def _do_export(self) -> None:
        project_id = self.project_view.project_id
        if project_id is None:
            QMessageBox.information(
                self, "Exportar", "Abra um projeto antes de exportar."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar projeto", f"projeto_{project_id}.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            data = export_project_json(self.db_path, project_id)
            write_export(path, data)
        except (DomainError, ValueError, OSError) as e:
            QMessageBox.critical(self, "Exportar", f"Falha ao exportar: {e}")
            return
        QMessageBox.information(self, "Exportar", f"Projeto exportado em:\n{path}")

    # -- navegacao ------------------------------------------------------------------

    def show_projects(self) -> None:
        self.list_view.refresh()
        self.stack.setCurrentWidget(self.list_view)

    def open_project(self, project_id: int) -> None:
        self.project_view.set_project(project_id)
        self.stack.setCurrentWidget(self.project_view)
