"""Conexao SQLite + migration runner manual (Parte 3)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from task_level.domain import to_iso, utcnow

_VERSION_RE = re.compile(r"^V(\d+)__.+\.sql$")


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def default_db_path() -> Path:
    return Path.home() / ".task_level" / "task_level.db"


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Abre conexao com FKs ligadas. Cria diretorio pai se necessario."""
    db_path = Path(db_path)
    if str(db_path) != ":memory:" and db_path.parent != Path("."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_version_table(conn)
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def pending_migrations(conn: sqlite3.Connection) -> list[tuple[int, Path]]:
    applied = applied_versions(conn)
    found: list[tuple[int, Path]] = []
    for sql_file in sorted(migrations_dir().glob("V*.sql")):
        m = _VERSION_RE.match(sql_file.name)
        if not m:
            continue
        version = int(m.group(1))
        if version not in applied:
            found.append((version, sql_file))
    return sorted(found)


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Aplica migrations pendentes em ordem. Retorna versoes aplicadas."""
    _ensure_version_table(conn)
    done: list[int] = []
    for version, sql_file in pending_migrations(conn):
        sql = sql_file.read_text(encoding="utf-8")
        with conn:  # transacao por migration
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, to_iso(utcnow())),
            )
        done.append(version)
    return done
