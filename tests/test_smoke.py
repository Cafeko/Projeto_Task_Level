"""Smoke test da Parte 1: imports + entry point."""


def test_package_imports():
    import task_level

    assert task_level.__version__ == "0.1.0"


def test_main_returns_zero(capsys):
    from task_level.main import main

    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Parte 1" in out
