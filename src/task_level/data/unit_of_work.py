"""UnitOfWork: transacao unica sobre todos os repositories (Parte 4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from . import database
from .repositories.activity_log_repository import ActivityLogRepository
from .repositories.attribute_definition_repository import AttributeDefinitionRepository
from .repositories.phase_repository import PhaseRepository
from .repositories.project_repository import ProjectRepository
from .repositories.task_attribute_repository import TaskAttributeRepository
from .repositories.task_phase_note_repository import TaskPhaseNoteRepository
from .repositories.task_repository import TaskRepository
from .repositories.task_type_repository import TaskTypeRepository


class UnitOfWork:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.projects = ProjectRepository(conn)
        self.task_types = TaskTypeRepository(conn)
        self.attribute_definitions = AttributeDefinitionRepository(conn)
        self.phases = PhaseRepository(conn)
        self.tasks = TaskRepository(conn)
        self.task_attributes = TaskAttributeRepository(conn)
        self.phase_notes = TaskPhaseNoteRepository(conn)
        self.activity = ActivityLogRepository(conn)

    @classmethod
    def open(cls, db_path: str | Path) -> UnitOfWork:
        conn = database.connect(db_path)
        database.migrate(conn)
        return cls(conn)

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    def close(self) -> None:
        self.conn.close()
