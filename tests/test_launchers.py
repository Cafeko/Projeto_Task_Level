"""Cadeia windowless: abrir sem janela de console (Windows).

- `main.pyw` delega ao `main.py` (runpy) para o Windows abrir com pythonw.
- `task-level.bat` usa pythonw (sem prompt); `-debug` mantem console + pause.
- `task-level.vbs` executa oculto (Run ..., 0, ...) com pythonw.
- `main.py` re-executa com o pythonw do .venv quando sem console.
"""

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_main_launcher():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_launcher_main", ROOT / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_launchers_compile():
    for name in ("main.py", "main.pyw"):
        py_compile.compile(str(ROOT / name), doraise=True)


def test_pyw_delegates_to_main_py():
    text = (ROOT / "main.pyw").read_text(encoding="utf-8")
    assert "main.py" in text
    assert "runpy" in text


def test_bat_uses_pythonw_without_console():
    bat = (ROOT / "task-level.bat").read_text(encoding="utf-8")
    assert "pythonw" in bat.lower()
    assert "python.exe" not in bat
    assert "pause" not in bat.lower()


def test_debug_bat_keeps_console_and_pause():
    bat = (ROOT / "task-level-debug.bat").read_text(encoding="utf-8")
    assert "python.exe" in bat
    assert "pause" in bat.lower()


def test_vbs_runs_hidden_with_pythonw():
    vbs = (ROOT / "task-level.vbs").read_text(encoding="utf-8")
    assert "pythonw" in vbs.lower()
    assert ", 0, False" in vbs  # janela oculta


def test_is_windowless_detection(monkeypatch):
    mod = _load_main_launcher()
    monkeypatch.setattr(mod.sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(mod.sys, "argv", ["pytest"])
    assert mod._is_windowless() is False
    monkeypatch.setattr(mod.sys, "executable", r"C:\Python\pythonw.exe")
    assert mod._is_windowless() is True
    monkeypatch.setattr(mod.sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(mod.sys, "argv", ["main.pyw"])
    assert mod._is_windowless() is True


def test_venv_python_prefers_pythonw_when_windowless():
    import os

    mod = _load_main_launcher()
    if os.name != "nt":
        assert mod._venv_python(False).name == "python"
        return
    console = mod._venv_python(False)
    assert console is not None and console.name.lower() == "python.exe"
    windowless = mod._venv_python(True)
    assert windowless is not None
    assert windowless.name.lower() in ("pythonw.exe", "python.exe")
