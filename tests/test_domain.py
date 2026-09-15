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
