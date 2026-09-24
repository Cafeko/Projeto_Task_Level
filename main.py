#!/usr/bin/env python3
"""Launcher do Task Level - pode dar duplo-clique ou `python main.py` de qualquer pasta.

- Resolve o diretorio do projeto a partir da localizacao deste arquivo (nao do cwd).
- Coloca `src/` no sys.path (dispensa instalacao / PYTHONPATH).
- Se foi aberto com o Python global (sem PySide6), tenta re-executar com o
  `.venv` do projeto automaticamente, espelhando o modo: `pythonw`/`.pyw`
  (sem console) re-executa com o `pythonw.exe` do `.venv`; `python`/console
  usa o `python.exe` (mantem a saida no terminal).
- Sem console nenhum (duplo-clique no Windows): use o `main.pyw` vizinho
  ou o `task-level.vbs` (o `.bat` normal tambem evita o console via pythonw).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _is_windowless() -> bool:
    """True se rodando sem console (pythonw.exe ou script .pyw)."""
    try:
        exe = Path(sys.executable).name.lower()
    except OSError:
        exe = ""
    if exe.startswith("pythonw"):
        return True
    return bool(sys.argv and str(sys.argv[0]).lower().endswith(".pyw"))


def _venv_python(windowless: bool = False) -> Path | None:
    if os.name == "nt":
        # Sem console: prefere pythonw (nunca abre prompt); com console,
        # fica no python.exe para a saida/erros continuarem no terminal.
        names = ("pythonw.exe", "python.exe") if windowless else ("python.exe",)
        for name in names:
            cand = ROOT / ".venv" / "Scripts" / name
            if cand.is_file():
                return cand
        return None
    cand = ROOT / ".venv" / "bin" / "python"
    return cand if cand.is_file() else None


def _ensure_venv() -> None:
    """Re-executa com o .venv se o interpretador atual nao tem as deps."""
    try:
        import PySide6  # noqa: F401
        return  # deps OK, segue com o interpretador atual
    except ImportError:
        pass
    venv_py = _venv_python(_is_windowless())
    if venv_py is None:
        return  # sem venv: deixa o erro de import aparecer normalmente
    try:
        same = Path(sys.executable).resolve() == venv_py.resolve()
    except OSError:
        same = False
    if same:
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


if __name__ == "__main__":
    _ensure_venv()
    from task_level.main import main

    sys.exit(main())
