"""TaskType repository (Parte 4)."""

from __future__ import annotations

import sqlite3

from task_level.domain import TaskType, from_iso, to_iso


def _to_model(row: sqlite3.Row) -> TaskType:
    try:
        order = int(row["order"])
    except (KeyError, IndexError, TypeError, ValueError):
        order = 0
    return TaskType(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        color=row["color"],
        icon=row["icon"],
        order=order,
        created_at=from_iso(row["created_at"]),
    )


class TaskTypeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, task_type: TaskType) -> TaskType:
        task_type.validate()
        cur = self._conn.execute(
            "INSERT INTO task_types (project_id, name, description, color, icon,"
            ' "order", created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                task_type.project_id,
                task_type.name.strip(),
                task_type.description,
                task_type.color,
                task_type.icon,
                int(task_type.order),
                to_iso(task_type.created_at),
            ),
        )
        task_type.id = cur.lastrowid
        return task_type

    def get(self, type_id: int) -> TaskType | None:
        row = self._conn.execute(
            "SELECT * FROM task_types WHERE id = ?", (type_id,)
        ).fetchone()
        return _to_model(row) if row else None

    def list_by_project(self, project_id: int) -> list[TaskType]:
        rows = self._conn.execute(
            "SELECT * FROM task_types WHERE project_id = ? ORDER BY \"order\", id",
            (project_id,),
        ).fetchall()
        return [_to_model(r) for r in rows]

    def max_order(self, project_id: int) -> int | None:
        row = self._conn.execute(
            "SELECT MAX(\"order\") FROM task_types WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None

    def update(self, task_type: TaskType) -> None:
        task_type.validate()
        if task_type.id is None:
            raise ValueError("task_type.id obrigatorio para update")
        self._conn.execute(
            "UPDATE task_types SET name = ?, description = ?, color = ?, icon = ?, \"order\" = ?"
            " WHERE id = ?",
            (
                task_type.name.strip(),
                task_type.description,
                task_type.color,
                task_type.icon,
                int(task_type.order),
                task_type.id,
            ),
        )

    def set_order(self, type_id: int, order: int) -> None:
        self._conn.execute(
            "UPDATE task_types SET \"order\" = ? WHERE id = ?",
            (int(order), type_id),
        )

    def delete(self, type_id: int) -> None:
        self._conn.execute("DELETE FROM task_types WHERE id = ?", (type_id,))
