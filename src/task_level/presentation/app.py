"""Bootstrap da GUI PySide6 (Parte 7)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from task_level.presentation.main_window import MainWindow


def run(db_path: str | Path) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(db_path)
    window.show()
    return app.exec()
