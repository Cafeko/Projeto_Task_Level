"""Enums de dominio."""

from __future__ import annotations

from enum import Enum


class AttributeType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CURRENCY = "currency"
    DATE = "date"
    REFERENCE_TASK = "reference_task"
    REFERENCE_ATTRIBUTE = "reference_attribute"

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]

    @classmethod
    def has(cls, value: str) -> bool:
        return value in cls.values()
