"""Smoke tests: imports + entry point (GUI mockada)."""


def test_package_imports():
    import task_level

    assert task_level.__version__ == "0.1.0"


def test_main_runs_seed_and_gui(tmp_path, monkeypatch, capsys):
    import task_level.presentation.app as app_mod
    from task_level.main import main

    monkeypatch.setattr(app_mod, "run", lambda db: 0)
    db = tmp_path / "smoke.db"
    assert main(["--db", str(db), "--seed"]) == 0
    out = capsys.readouterr().out
    assert "Seed OK" in out
    assert db.exists()
