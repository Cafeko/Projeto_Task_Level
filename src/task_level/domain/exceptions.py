"""Excecoes de dominio."""

from __future__ import annotations


class DomainError(Exception):
    """Base para erros de dominio."""


class ValidationError(DomainError):
    """Falha de validacao manual de dataclass."""


class NotFoundError(DomainError):
    """Entidade nao encontrada."""


class CircularReferenceError(DomainError):
    """Referencia entre tasks criaria ciclo."""
