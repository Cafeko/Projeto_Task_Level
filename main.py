#!/usr/bin/env python3
"""Launcher do Task Level - pode dar duplo-clique ou `python main.py` de qualquer pasta.

- Resolve o diretorio do projeto a partir da localizacao deste arquivo (nao do cwd).
- Coloca `src/` no sys.path (dispensa instalacao / PYTHONPATH).
- Se foi aberto com o Python global (sem PySide6), tenta re-executar com o
  `.venv` do projeto automaticamente.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _venv_python() -> Path | None:
    if os.name == "nt":
        cand = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        cand = ROOT / ".venv" / "bin" / "python"
    return cand if cand.is_file() else None


def _ensure_venv() -> None:
    """Re-executa com o .venv se o interpretador atual nao tem as deps."""
    try:
        import PySide6  # noqa: F401
        return  # deps OK, segue com o interpretador atual
    except ImportError:
        pass
    venv_py = _venv_python()
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
