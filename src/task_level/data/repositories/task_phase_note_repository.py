"""TaskPhaseNote repository (observacoes da task por fase)."""

from __future__ import annotations

import sqlite3

from task_level.domain import TaskPhaseNote, from_iso, to_iso, utcnow


def _to_model(row: sqlite3.Row) -> TaskPhaseNote:
    return TaskPhaseNote(
        id=row["id"],
        task_id=row["task_id"],
        phase_id=row["phase_id"],
        note=row["note"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


class TaskPhaseNoteRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, note: TaskPhaseNote) -> TaskPhaseNote:
        """Insert ou update (UPSERT por task_id + phase_id)."""
        note.validate()
        now = to_iso(utcnow())
        self._conn.execute(
            "INSERT INTO task_phase_notes (task_id, phase_id, note, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(task_id, phase_id) DO UPDATE SET"
            " note = excluded.note, updated_at = excluded.updated_at",
            (note.task_id, note.phase_id, note.note, now, now),
        )
        row = self._conn.execute(
            "SELECT * FROM task_phase_notes WHERE task_id = ? AND phase_id = ?",
            (note.task_id, note.phase_id),
        ).fetchone()
        assert row is not None
        return _to_model(row)

    def get(self, task_id: int, phase_id: int) -> TaskPhaseNote | None:
        row = self._conn.execute(
            "SELECT * FROM task_phase_notes WHERE task_id = ? AND phase_id = ?",
            (task_id, phase_id),
        ).fetchone()
        return _to_model(row) if row else None

    def list_by_task(self, task_id: int) -> list[TaskPhaseNote]:
        rows = self._conn.execute(
            "SELECT * FROM task_phase_notes WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [_to_model(r) for r in rows]

    def delete(self, task_id: int, phase_id: int) -> None:
        self._conn.execute(
            "DELETE FROM task_phase_notes WHERE task_id = ? AND phase_id = ?",
            (task_id, phase_id),
        )
