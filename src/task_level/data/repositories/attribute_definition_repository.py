"""AttributeDefinition repository (Parte 4)."""

from __future__ import annotations

import json
import sqlite3

from task_level.domain import AttributeDefinition, from_iso, to_iso

from .base import b2i, i2b


def _to_model(row: sqlite3.Row) -> AttributeDefinition:
    raw_config = row["reference_config"]
    return AttributeDefinition(
        id=row["id"],
        task_type_id=row["task_type_id"],
        name=row["name"],
        label=row["label"],
        type=row["type"],
        required=i2b(row["required"]) or False,
        default_value=row["default_value"],
        reference_config=json.loads(raw_config) if raw_config else None,
        order=row["order"],
        created_at=from_iso(row["created_at"]),
    )


class AttributeDefinitionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, definition: AttributeDefinition) -> AttributeDefinition:
        definition.validate()
        cur = self._conn.execute(
            'INSERT INTO attribute_definitions (task_type_id, name, label, type, required,'
            ' default_value, reference_config, "order", created_at)'
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                definition.task_type_id,
                definition.name.strip(),
                definition.label.strip(),
                definition.type,
                b2i(definition.required),
                definition.default_value,
                json.dumps(definition.reference_config)
                if definition.reference_config is not None
                else None,
                definition.order,
                to_iso(definition.created_at),
            ),
        )
        definition.id = cur.lastrowid
        return definition

    def get(self, definition_id: int) -> AttributeDefinition | None:
        row = self._conn.execute(
            "SELECT * FROM attribute_definitions WHERE id = ?", (definition_id,)
        ).fetchone()
        return _to_model(row) if row else None

    def get_by_name(self, task_type_id: int, name: str) -> AttributeDefinition | None:
        row = self._conn.execute(
            "SELECT * FROM attribute_definitions WHERE task_type_id = ? AND name = ?",
            (task_type_id, name),
        ).fetchone()
        return _to_model(row) if row else None

    def list_by_task_type(self, task_type_id: int) -> list[AttributeDefinition]:
        rows = self._conn.execute(
            'SELECT * FROM attribute_definitions WHERE task_type_id = ?'
            ' ORDER BY "order", id',
            (task_type_id,),
        ).fetchall()
        return [_to_model(r) for r in rows]

    def update(self, definition: AttributeDefinition) -> None:
        definition.validate()
        if definition.id is None:
            raise ValueError("attribute_definition.id obrigatorio para update")
        self._conn.execute(
            'UPDATE attribute_definitions SET name = ?, label = ?, type = ?,'
            ' required = ?, default_value = ?, reference_config = ?, "order" = ?'
            " WHERE id = ?",
            (
                definition.name.strip(),
                definition.label.strip(),
                definition.type,
                b2i(definition.required),
                definition.default_value,
                json.dumps(definition.reference_config)
                if definition.reference_config is not None
                else None,
                definition.order,
                definition.id,
            ),
        )

    def delete(self, definition_id: int) -> None:
        self._conn.execute(
            "DELETE FROM attribute_definitions WHERE id = ?", (definition_id,)
        )
