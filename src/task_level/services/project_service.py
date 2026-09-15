"""Project service (Parte 5)."""

from __future__ import annotations

from pathlib import Path

from task_level.data import UnitOfWork
from task_level.domain import NotFoundError, Project, utcnow


class ProjectService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    def create(self, name: str, description: str = "") -> Project:
        with UnitOfWork.open(self._db_path) as uow:
            return uow.projects.add(Project(name=name, description=description))

    def list(self) -> list[Project]:
        with UnitOfWork.open(self._db_path) as uow:
            return uow.projects.list()

    def get(self, project_id: int) -> Project:
        with UnitOfWork.open(self._db_path) as uow:
            project = uow.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"project {project_id} nao encontrado")
        return project

    def rename(self, project_id: int, name: str, description: str | None = None) -> Project:
        with UnitOfWork.open(self._db_path) as uow:
            project = uow.projects.get(project_id)
            if project is None:
                raise NotFoundError(f"project {project_id} nao encontrado")
            project.name = name
            if description is not None:
                project.description = description
            project.updated_at = utcnow()
            uow.projects.update(project)
            return project

    def delete(self, project_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            if uow.projects.get(project_id) is None:
                raise NotFoundError(f"project {project_id} nao encontrado")
            uow.projects.delete(project_id)
