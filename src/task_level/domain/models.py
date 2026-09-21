"""Dataclasses de dominio + validacao manual.

Regras:
- id None antes de persistir, INTEGER apos persistir.
- Datas sempre datetime timezone-aware (UTC). DB serializa ISO8601.
- AttributeDefinition.type define qual campo de TaskAttribute e valido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .enums import AttributeType
from .exceptions import ValidationError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def from_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_local(dt: datetime) -> datetime:
    """Converte para o fuso horario do PC (apenas p/ exibicao).

    O banco continua em UTC; naive = assume UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValidationError(f"{field_name} nao pode ser vazio")


@dataclass
class Project:
    name: str
    description: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        _require_non_empty(self.name, "project.name")
        if len(self.name) > 200:
            raise ValidationError("project.name max 200 chars")


@dataclass
class TaskType:
    project_id: int
    name: str
    description: str = ""
    color: str = "#888888"
    icon: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        if not self.project_id or self.project_id <= 0:
            raise ValidationError("task_type.project_id invalido")
        _require_non_empty(self.name, "task_type.name")


@dataclass
class AttributeDefinition:
    task_type_id: int
    name: str  # slug, ex: severity
    label: str  # ex: Severidade
    type: str  # AttributeType value
    required: bool = False
    default_value: str = ""
    reference_config: dict | None = None
    order: int = 0
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        if not self.task_type_id or self.task_type_id <= 0:
            raise ValidationError("attribute_definition.task_type_id invalido")
        _require_non_empty(self.name, "attribute_definition.name")
        _require_non_empty(self.label, "attribute_definition.label")
        if not AttributeType.has(self.type):
            raise ValidationError(f"attribute_definition.type invalido: {self.type}")
        ref_types = (
            AttributeType.REFERENCE_TASK.value,
            AttributeType.REFERENCE_ATTRIBUTE.value,
        )
        if self.type in ref_types:
            if self.reference_config is not None and not isinstance(self.reference_config, dict):
                raise ValidationError("attribute_definition.reference_config deve ser dict/None")


@dataclass
class Phase:
    task_type_id: int
    name: str
    description: str = ""
    color: str = "#888888"
    order: int = 0
    is_initial: bool = False
    is_final: bool = False
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        if not self.task_type_id or self.task_type_id <= 0:
            raise ValidationError("phase.task_type_id invalido")
        _require_non_empty(self.name, "phase.name")


@dataclass
class Task:
    project_id: int
    task_type_id: int
    phase_id: int | None
    title: str
    description: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None

    def validate(self) -> None:
        if not self.project_id or self.project_id <= 0:
            raise ValidationError("task.project_id invalido")
        if not self.task_type_id or self.task_type_id <= 0:
            raise ValidationError("task.task_type_id invalido")
        _require_non_empty(self.title, "task.title")


@dataclass
class TaskAttribute:
    task_id: int
    attribute_definition_id: int
    value_text: str | None = None
    value_number: float | None = None
    value_boolean: bool | None = None
    value_reference_task_id: int | None = None
    value_reference_attribute_id: int | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def validate(self, attr_type: str) -> None:
        """Valida que apenas o campo compativel com attr_type esta preenchido."""
        if not self.task_id or self.task_id <= 0:
            raise ValidationError("task_attribute.task_id invalido")
        if not self.attribute_definition_id or self.attribute_definition_id <= 0:
            raise ValidationError("task_attribute.attribute_definition_id invalido")
        if not AttributeType.has(attr_type):
            raise ValidationError(f"task_attribute tipo invalido: {attr_type}")

        expected = {
            AttributeType.TEXT.value: "value_text",
            AttributeType.NUMBER.value: "value_number",
            AttributeType.BOOLEAN.value: "value_boolean",
            AttributeType.REFERENCE_TASK.value: "value_reference_task_id",
            AttributeType.REFERENCE_ATTRIBUTE.value: "value_reference_attribute_id",
        }[attr_type]

        # REFERENCE_ATTRIBUTE usa dois campos (task + attribute ids)
        if attr_type == AttributeType.REFERENCE_ATTRIBUTE.value:
            has_ref = (
                self.value_reference_task_id is not None
                or self.value_reference_attribute_id is not None
            )
            others = [
                self.value_text is not None,
                self.value_number is not None,
                self.value_boolean is not None,
            ]
            if any(others):
                raise ValidationError(f"task_attribute: tipo {attr_type} nao usa texto/numero/bool")
            _ = has_ref  # None permitido = atributo opcional vazio
            _ = expected
            return

        value = getattr(self, expected)
        others = [f for f in expected_fields() if f != expected and getattr(self, f) is not None]
        if others:
            raise ValidationError(
                f"task_attribute: tipo {attr_type} usa {expected}, mas {others} preenchidos"
            )
        _ = value  # None permitido = atributo opcional vazio


def expected_fields() -> list[str]:
    return [
        "value_text",
        "value_number",
        "value_boolean",
        "value_reference_task_id",
        "value_reference_attribute_id",
    ]
