"""Repositories por entidade (Parte 4)."""

from .attribute_definition_repository import AttributeDefinitionRepository
from .phase_repository import PhaseRepository
from .project_repository import ProjectRepository
from .task_attribute_repository import TaskAttributeRepository
from .task_phase_note_repository import TaskPhaseNoteRepository
from .task_repository import TaskRepository
from .task_type_repository import TaskTypeRepository

__all__ = [
    "AttributeDefinitionRepository",
    "PhaseRepository",
    "ProjectRepository",
    "TaskAttributeRepository",
    "TaskPhaseNoteRepository",
    "TaskRepository",
    "TaskTypeRepository",
]
