"""Helpers de conversao SQLite <-> dominio (Parte 4)."""

from __future__ import annotations


def b2i(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def i2b(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)
