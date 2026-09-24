"""Testes Parte 3: database + migrations."""

import sqlite3

import pytest

from task_level.data import database


@pytest.fixture()
def conn(tmp_path):
    c = database.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_migrate_creates_all_tables(conn):
    assert database.migrate(conn) == [1, 2, 3, 4, 5, 6, 7]
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "projects",
        "task_types",
        "attribute_definitions",
        "phases",
        "tasks",
        "task_attributes",
        "task_phase_notes",
        "schema_migrations",
    } <= tables
    cols = [r[1] for r in conn.execute("PRAGMA table_info(attribute_definitions)")]
    assert "options" in cols
    phase_cols = [r[1] for r in conn.execute("PRAGMA table_info(phases)")]
    assert "enter_conditions" in phase_cols
    assert "activity_log" in tables
    task_cols = [r[1] for r in conn.execute("PRAGMA table_info(tasks)")]
    assert "seq" in task_cols
    type_cols = [r[1] for r in conn.execute("PRAGMA table_info(task_types)")]
    assert "order" in type_cols


def test_migrate_idempotent(conn):
    assert database.migrate(conn) == [1, 2, 3, 4, 5, 6, 7]
    assert database.migrate(conn) == []


def test_foreign_keys_enforced(conn):
    database.migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO task_types (project_id, name, created_at) VALUES (999, 'Bug', 'x')"
            )


def test_cascade_project_deletes_types_and_tasks(conn):
    from task_level.domain import to_iso, utcnow

    database.migrate(conn)
    now = to_iso(utcnow())
    with conn:
        cur = conn.execute(
            "INSERT INTO projects (name, description, created_at, updated_at) VALUES (?,?,?,?)",
            ("P", "", now, now),
        )
        pid = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO task_types (project_id, name, created_at) VALUES (?,?,?)",
            (pid, "Bug", now),
        )
        tid = cur.lastrowid
        conn.execute(
            "INSERT INTO tasks (project_id, task_type_id, title, created_at, updated_at)"
            " VALUES (?,?,?, ?, ?)",
            (pid, tid, "T1", now, now),
        )
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
    assert conn.execute("SELECT COUNT(*) FROM task_types").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_unique_task_attribute_per_definition(conn):
    from task_level.domain import to_iso, utcnow

    database.migrate(conn)
    now = to_iso(utcnow())
    with conn:
        pid = conn.execute(
            "INSERT INTO projects (name, description, created_at, updated_at) VALUES (?,?,?,?)",
            ("P", "", now, now),
        ).lastrowid
        tid = conn.execute(
            "INSERT INTO task_types (project_id, name, created_at) VALUES (?,?,?)",
            (pid, "Bug", now),
        ).lastrowid
        ad = conn.execute(
            "INSERT INTO attribute_definitions (task_type_id, name, label, type, created_at)"
            " VALUES (?,?,?,?,?)",
            (tid, "sev", "Severidade", "text", now),
        ).lastrowid
        task = conn.execute(
            "INSERT INTO tasks (project_id, task_type_id, title, created_at, updated_at)"
            " VALUES (?,?,?, ?, ?)",
            (pid, tid, "T1", now, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO task_attributes (task_id, attribute_definition_id, value_text,"
            " created_at, updated_at) VALUES (?,?,?,?,?)",
            (task, ad, "alta", now, now),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO task_attributes (task_id, attribute_definition_id, value_text,"
                " created_at, updated_at) VALUES (?,?,?,?,?)",
                (task, ad, "baixa", now, now),
            )
