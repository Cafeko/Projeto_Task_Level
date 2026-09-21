"""Testes Parte 2: domain."""

import pytest

from task_level.domain import (
    AttributeDefinition,
    AttributeType,
    Phase,
    Project,
    Task,
    TaskAttribute,
    ValidationError,
    from_iso,
    to_iso,
)


def test_attribute_type_values():
    assert set(AttributeType.values()) == {
        "text",
        "number",
        "boolean",
        "currency",
        "date",
        "reference_task",
        "reference_attribute",
    }


def test_project_validate_ok():
    Project(name="Meu projeto").validate()


def test_project_validate_empty_fails():
    with pytest.raises(ValidationError):
        Project(name="  ").validate()


def test_attribute_definition_invalid_type_fails():
    with pytest.raises(ValidationError):
        AttributeDefinition(
            task_type_id=1, name="x", label="X", type="invalido"
        ).validate()


def test_task_attribute_type_match_ok():
    TaskAttribute(task_id=1, attribute_definition_id=1, value_text="oi").validate("text")
    TaskAttribute(task_id=1, attribute_definition_id=1, value_number=3.5).validate("number")
    TaskAttribute(task_id=1, attribute_definition_id=1, value_boolean=True).validate("boolean")
    TaskAttribute(
        task_id=1, attribute_definition_id=1, value_reference_task_id=2
    ).validate("reference_task")


def test_task_attribute_wrong_field_fails():
    with pytest.raises(ValidationError):
        TaskAttribute(task_id=1, attribute_definition_id=1, value_number=1).validate("text")


def test_phase_validate_ok():
    Phase(task_type_id=1, name="Backlog", is_initial=True).validate()


def test_task_validate_ok():
    Task(project_id=1, task_type_id=1, phase_id=1, title="Bug #1").validate()


def test_iso_roundtrip():
    from task_level.domain import utcnow

    dt = utcnow()
    assert from_iso(to_iso(dt)).isoformat() == dt.isoformat()


def test_to_local_keeps_instant_uses_pc_zone():
    from datetime import datetime, timezone

    from task_level.domain import to_local, utcnow

    dt = utcnow()
    local = to_local(dt)
    assert local == dt  # mesmo instante
    assert local.utcoffset() == datetime.now().astimezone().utcoffset()
    naive = datetime(2026, 1, 1, 12, 0, 0)  # sem tz: assume UTC
    assert to_local(naive) == naive.replace(tzinfo=timezone.utc).astimezone()


def test_currency_parse_and_format():
    from task_level.domain import format_currency, parse_currency

    assert parse_currency("R$ 1.234,56") == 1234.56
    assert parse_currency("1234,56") == 1234.56
    assert parse_currency("1234.56") == 1234.56
    assert format_currency(1234.56) == "R$ 1.234,56"
    assert format_currency(10) == "R$ 10,00"


def test_date_parse_and_format():
    from task_level.domain import ValidationError, format_date, parse_date

    assert parse_date("20/09/2026") == "2026-09-20"
    assert parse_date("2026-09-20") == "2026-09-20"
    assert format_date("2026-09-20") == "20/09/2026"
    with pytest.raises(ValidationError):
        parse_date("31/02/2026")
    with pytest.raises(ValidationError):
        parse_date(" batman ")
