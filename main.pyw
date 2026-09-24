#!/usr/bin/env python3
"""Launcher sem console do Task Level (Windows: duplo-clique nao abre prompt).

O Windows associa `.pyw` ao `pythonw.exe` (sem console). Este arquivo so
encaminha para o `main.py` vizinho, que resolve o `.venv` e abre a GUI —
espelhando o modo windowless (re-executa com o `pythonw.exe` do `.venv`,
nunca com o `python.exe` com console).
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.argv[0] = str(ROOT / "main.py")
runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
