"""ActivityLog repository (historico de mudancas das tasks)."""

from __future__ import annotations

import sqlite3

from task_level.domain import ActivityEntry, from_iso, to_iso, utcnow


def _to_model(row: sqlite3.Row) -> ActivityEntry:
    return ActivityEntry(
        id=row["id"],
        project_id=row["project_id"],
        task_id=row["task_id"],
        task_title=row["task_title"],
        action=row["action"],
        summary=row["summary"],
        undo_json=row["undo_json"],
        created_at=from_iso(row["created_at"]),
    )


class ActivityLogRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, entry: ActivityEntry) -> ActivityEntry:
        entry.validate()
        cur = self._conn.execute(
            "INSERT INTO activity_log (project_id, task_id, task_title, action,"
            " summary, undo_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.project_id,
                entry.task_id,
                entry.task_title,
                entry.action,
                entry.summary,
                entry.undo_json,
                to_iso(utcnow()),
            ),
        )
        entry.id = cur.lastrowid
        return entry

    def list_by_project(self, project_id: int, limit: int = 200) -> list[ActivityEntry]:
        rows = self._conn.execute(
            "SELECT * FROM activity_log WHERE project_id = ?"
            " ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
        return [_to_model(r) for r in rows]

    def clear_project(self, project_id: int) -> None:
        self._conn.execute(
            "DELETE FROM activity_log WHERE project_id = ?", (project_id,)
        )
