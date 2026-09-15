"""Project repository (Parte 4)."""

from __future__ import annotations

import sqlite3

from task_level.domain import Project, from_iso, to_iso


def _to_model(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=from_iso(row["created_at"]),
        updated_at=from_iso(row["updated_at"]),
    )


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, project: Project) -> Project:
        project.validate()
        cur = self._conn.execute(
            "INSERT INTO projects (name, description, created_at, updated_at)"
            " VALUES (?, ?, ?, ?)",
            (
                project.name.strip(),
                project.description,
                to_iso(project.created_at),
                to_iso(project.updated_at),
            ),
        )
        project.id = cur.lastrowid
        return project

    def get(self, project_id: int) -> Project | None:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return _to_model(row) if row else None

    def list(self) -> list[Project]:
        rows = self._conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [_to_model(r) for r in rows]

    def update(self, project: Project) -> None:
        project.validate()
        if project.id is None:
            raise ValueError("project.id obrigatorio para update")
        self._conn.execute(
            "UPDATE projects SET name = ?, description = ?, updated_at = ? WHERE id = ?",
            (
                project.name.strip(),
                project.description,
                to_iso(project.updated_at),
                project.id,
            ),
        )

    def delete(self, project_id: int) -> None:
        self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
