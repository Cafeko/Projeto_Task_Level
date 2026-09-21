"""Phase repository (Parte 4)."""

from __future__ import annotations

import sqlite3

from task_level.domain import Phase, from_iso, to_iso

from .base import b2i, i2b


def _to_model(row: sqlite3.Row) -> Phase:
    return Phase(
        id=row["id"],
        task_type_id=row["task_type_id"],
        name=row["name"],
        description=row["description"],
        color=row["color"],
        order=row["order"],
        is_initial=i2b(row["is_initial"]) or False,
        is_final=i2b(row["is_final"]) or False,
        created_at=from_iso(row["created_at"]),
    )


class PhaseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, phase: Phase) -> Phase:
        phase.validate()
        cur = self._conn.execute(
            'INSERT INTO phases (task_type_id, name, description, color, "order",'
            " is_initial, is_final, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                phase.task_type_id,
                phase.name.strip(),
                phase.description,
                phase.color,
                phase.order,
                b2i(phase.is_initial),
                b2i(phase.is_final),
                to_iso(phase.created_at),
            ),
        )
        phase.id = cur.lastrowid
        return phase

    def get(self, phase_id: int) -> Phase | None:
        row = self._conn.execute(
            "SELECT * FROM phases WHERE id = ?", (phase_id,)
        ).fetchone()
        return _to_model(row) if row else None

    def list_by_task_type(self, task_type_id: int) -> list[Phase]:
        rows = self._conn.execute(
            'SELECT * FROM phases WHERE task_type_id = ? ORDER BY "order", id',
            (task_type_id,),
        ).fetchall()
        return [_to_model(r) for r in rows]

    def initial_of_type(self, task_type_id: int) -> Phase | None:
        row = self._conn.execute(
            "SELECT * FROM phases WHERE task_type_id = ? AND is_initial = 1"
            ' ORDER BY "order", id LIMIT 1',
            (task_type_id,),
        ).fetchone()
        return _to_model(row) if row else None

    def update(self, phase: Phase) -> None:
        phase.validate()
        if phase.id is None:
            raise ValueError("phase.id obrigatorio para update")
        self._conn.execute(
            'UPDATE phases SET name = ?, description = ?, color = ?, "order" = ?,'
            " is_initial = ?, is_final = ? WHERE id = ?",
            (
                phase.name.strip(),
                phase.description,
                phase.color,
                phase.order,
                b2i(phase.is_initial),
                b2i(phase.is_final),
                phase.id,
            ),
        )

    def unset_initials(self, task_type_id: int, except_id: int | None = None) -> None:
        self._conn.execute(
            "UPDATE phases SET is_initial = 0 WHERE task_type_id = ?"
            + ("" if except_id is None else " AND id != ?"),
            (task_type_id,)
            if except_id is None
            else (task_type_id, except_id),
        )

    def unset_finals(self, task_type_id: int, except_id: int | None = None) -> None:
        self._conn.execute(
            "UPDATE phases SET is_final = 0 WHERE task_type_id = ?"
            + ("" if except_id is None else " AND id != ?"),
            (task_type_id,)
            if except_id is None
            else (task_type_id, except_id),
        )

    def delete(self, phase_id: int) -> None:
        self._conn.execute("DELETE FROM phases WHERE id = ?", (phase_id,))
