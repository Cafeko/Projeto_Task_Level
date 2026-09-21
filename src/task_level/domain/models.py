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


def parse_currency(text: str) -> float:
    """Aceita 'R$ 1.234,56', '1234,56', '1234.56' -> float. Erro: ValidationError."""
    cleaned = text.strip().replace("R$", "").replace("r$", "").strip()
    if not cleaned:
        raise ValidationError("valor em dinheiro vazio")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError as e:
        raise ValidationError(f"valor em dinheiro invalido: {text!r}") from e


def format_currency(value: float) -> str:
    """1234.5 -> 'R$ 1.234,50' (pt-BR)."""
    grouped = f"{value:,.2f}"  # '1,234.50'
    return "R$ " + grouped.replace(",", "X").replace(".", ",").replace("X", ".")


def parse_date(text: str) -> str:
    """Aceita '20/09/2026' ou '2026-09-20' -> ISO 'YYYY-MM-DD'."""
    from datetime import date as _date

    cleaned = text.strip()
    if not cleaned:
        raise ValidationError("data vazia")
    try:
        if "/" in cleaned:
            day, month, year = (int(p) for p in cleaned.replace("-", "/").split("/"))
            return _date(year, month, day).isoformat()
        return _date.fromisoformat(cleaned).isoformat()
    except ValueError as e:
        raise ValidationError(f"data invalida: {text!r}") from e


def format_date(iso_text: str) -> str:
    """'2026-09-20' -> '20/09/2026' (se invalido, devolve como esta)."""
    try:
        year, month, day = (int(p) for p in iso_text.strip().split("-"))
        from datetime import date as _date

        return _date(year, month, day).strftime("%d/%m/%Y")
    except (ValueError, AttributeError):
        return iso_text


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
    options: list[str] | None = None  # AttributeType.SELECT: valores permitidos
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
        if self.type == AttributeType.SELECT.value:
            if not isinstance(self.options, list) or not [
                o for o in self.options if isinstance(o, str) and o.strip()
            ]:
                raise ValidationError("attribute_definition.options precisa de ao menos 1 opcao")


@dataclass
class Phase:
    task_type_id: int
    name: str
    description: str = ""
    color: str = "#888888"
    order: int = 0
    is_initial: bool = False
    is_final: bool = False
    enter_conditions: list[dict] | None = None  # [{attr, op, value}] p/ entrar
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        if not self.task_type_id or self.task_type_id <= 0:
            raise ValidationError("phase.task_type_id invalido")
        _require_non_empty(self.name, "phase.name")
        if self.enter_conditions is not None:
            if not isinstance(self.enter_conditions, list) or not all(
                isinstance(c, dict)
                and isinstance(c.get("attr"), str)
                and isinstance(c.get("op"), str)
                for c in self.enter_conditions
            ):
                raise ValidationError("phase.enter_conditions invalido")


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
            AttributeType.CURRENCY.value: "value_number",
            AttributeType.DATE.value: "value_text",
            AttributeType.FILE.value: "value_text",
            AttributeType.SELECT.value: "value_text",
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


@dataclass
class TaskPhaseNote:
    """Observacao livre da task em uma fase (ex: o que aconteceu ali)."""

    task_id: int
    phase_id: int
    note: str = ""
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        if not self.task_id or self.task_id <= 0:
            raise ValidationError("task_phase_note.task_id invalido")
        if not self.phase_id or self.phase_id <= 0:
            raise ValidationError("task_phase_note.phase_id invalido")


@dataclass
class ActivityEntry:
    """Uma mudanca registrada (Historico; undo_json p/ desfazer/refazer)."""

    project_id: int
    action: str
    task_id: int | None = None
    task_title: str = ""
    summary: str = ""
    undo_json: str | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=utcnow)

    def validate(self) -> None:
        if not self.project_id or self.project_id <= 0:
            raise ValidationError("activity.project_id invalido")
        _require_non_empty(self.action, "activity.action")


def expected_fields() -> list[str]:    return [
        "value_text",
        "value_number",
        "value_boolean",
        "value_reference_task_id",
        "value_reference_attribute_id",
    ]
