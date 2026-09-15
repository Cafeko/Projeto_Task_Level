"""TaskAttribute repository (Parte 4)."""

from __future__ import annotations

import sqlite3

from task_level.domain import TaskAttribute, from_iso, to_iso

from .base import b2i, i2b


def _to_model(row: sqlite3.Row) -> TaskAttribute:
    return TaskAttribute(
        id=row["id"],
        task_id=row["task_id"],
        attribute_definition_id=row["attribute_definition_id"],
        value_text=row["value_text"],
        value_number=row["value_number"],
        value_boolean=i2b(row["value_boolean"]),
        value_reference_task_id=row["value_reference_task_id"],
        value_reference_attribute_id=row["value_reference_attribute_id"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


class TaskAttributeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, attr: TaskAttribute, attr_type: str) -> TaskAttribute:
        """Insert ou update (UPSERT por task_id + attribute_definition_id)."""
        attr.validate(attr_type)
        self._conn.execute(
            "INSERT INTO task_attributes (task_id, attribute_definition_id, value_text,"
            " value_number, value_boolean, value_reference_task_id,"
            " value_reference_attribute_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(task_id, attribute_definition_id) DO UPDATE SET"
            " value_text = excluded.value_text,"
            " value_number = excluded.value_number,"
            " value_boolean = excluded.value_boolean,"
            " value_reference_task_id = excluded.value_reference_task_id,"
            " value_reference_attribute_id = excluded.value_reference_attribute_id,"
            " updated_at = excluded.updated_at",
            (
                attr.task_id,
                attr.attribute_definition_id,
                attr.value_text,
                attr.value_number,
                b2i(attr.value_boolean),
                attr.value_reference_task_id,
                attr.value_reference_attribute_id,
                to_iso(attr.created_at),
                to_iso(attr.updated_at),
            ),
        )
        row = self._conn.execute(
            "SELECT * FROM task_attributes WHERE task_id = ? AND attribute_definition_id = ?",
            (attr.task_id, attr.attribute_definition_id),
        ).fetchone()
        assert row is not None
        return _to_model(row)

    def get(self, task_id: int, attribute_definition_id: int) -> TaskAttribute | None:
        row = self._conn.execute(
            "SELECT * FROM task_attributes WHERE task_id = ? AND attribute_definition_id = ?",
            (task_id, attribute_definition_id),
        ).fetchone()
        return _to_model(row) if row else None

    def get_by_id(self, attribute_id: int) -> TaskAttribute | None:
        row = self._conn.execute(
            "SELECT * FROM task_attributes WHERE id = ?", (attribute_id,)
        ).fetchone()
        return _to_model(row) if row else None

    def list_by_task(self, task_id: int) -> list[TaskAttribute]:
        rows = self._conn.execute(
            "SELECT * FROM task_attributes WHERE task_id = ? ORDER BY id", (task_id,)
        ).fetchall()
        return [_to_model(r) for r in rows]

    def referenced_task_ids(self, task_id: int) -> set[int]:
        """IDs de tasks alcancadas por referencia direta (usado no ciclo - Parte 5)."""
        rows = self._conn.execute(
            "SELECT value_reference_task_id, value_reference_attribute_id"
            " FROM task_attributes WHERE task_id = ?",
            (task_id,),
        ).fetchall()
        ids: set[int] = set()
        attr_refs: list[int] = []
        for row in rows:
            if row[0] is not None:
                ids.add(row[0])
            if row[1] is not None:
                attr_refs.append(row[1])
        for ref_id in attr_refs:
            target = self._conn.execute(
                "SELECT task_id FROM task_attributes WHERE id = ?", (ref_id,)
            ).fetchone()
            if target is not None:
                ids.add(target[0])
        return ids

    def delete(self, task_id: int, attribute_definition_id: int) -> None:
        self._conn.execute(
            "DELETE FROM task_attributes WHERE task_id = ? AND attribute_definition_id = ?",
            (task_id, attribute_definition_id),
        )
