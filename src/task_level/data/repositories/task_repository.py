"""Task repository (Parte 4)."""

from __future__ import annotations

import sqlite3

from task_level.domain import Task, from_iso, to_iso


def _to_model(row: sqlite3.Row) -> Task:
    completed = row["completed_at"]
    keys = row.keys()
    return Task(
        id=row["id"],
        project_id=row["project_id"],
        task_type_id=row["task_type_id"],
        phase_id=row["phase_id"],
        title=row["title"],
        description=row["description"],
        seq=row["seq"] if "seq" in keys else None,
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
        completed_at=from_iso(completed) if completed else None,
    )


class TaskRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def next_seq(self, task_type_id: int) -> int:
        """Proximo numero visivel do tipo (estavel: excluir nao renumera)."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM tasks WHERE task_type_id = ?",
            (task_type_id,),
        ).fetchone()
        return int(row[0]) + 1

    def add(self, task: Task) -> Task:
        task.validate()
        if task.seq is None:
            task.seq = self.next_seq(task.task_type_id)
        cur = self._conn.execute(
            "INSERT INTO tasks (project_id, task_type_id, phase_id, title, description,"
            " created_at, updated_at, completed_at, seq)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.project_id,
                task.task_type_id,
                task.phase_id,
                task.title.strip(),
                task.description,
                to_iso(task.created_at),
                to_iso(task.updated_at),
                to_iso(task.completed_at) if task.completed_at else None,
                task.seq,
            ),
        )
        task.id = cur.lastrowid
        return task

    def get(self, task_id: int) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return _to_model(row) if row else None

    def list_by_project(
        self,
        project_id: int,
        task_type_id: int | None = None,
        phase_id: int | None = None,
    ) -> list[Task]:
        sql = "SELECT * FROM tasks WHERE project_id = ?"
        params: list = [project_id]
        if task_type_id is not None:
            sql += " AND task_type_id = ?"
            params.append(task_type_id)
        if phase_id is not None:
            sql += " AND phase_id = ?"
            params.append(phase_id)
        sql += " ORDER BY id"
        return [_to_model(r) for r in self._conn.execute(sql, params).fetchall()]

    def update(self, task: Task) -> None:
        task.validate()
        if task.id is None:
            raise ValueError("task.id obrigatorio para update")
        self._conn.execute(
            "UPDATE tasks SET phase_id = ?, title = ?, description = ?,"
            " updated_at = ?, completed_at = ? WHERE id = ?",
            (
                task.phase_id,
                task.title.strip(),
                task.description,
                to_iso(task.updated_at),
                to_iso(task.completed_at) if task.completed_at else None,
                task.id,
            ),
        )

    def delete(self, task_id: int) -> None:
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
