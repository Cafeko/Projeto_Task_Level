"""Filtros de tasks por valor de atributo (motor puro, testavel sem Qt).

Um filtro e um dict: {"type_id": int, "attr": str, "op": str, "value": str}.
A task passa se TODOS os filtros casarem (AND).
"""

from __future__ import annotations

from task_level.domain import AttributeType, ValidationError, parse_currency, parse_date

# operadores por tipo: [(id, rotulo, precisa_valor)]
FILTER_OPS: dict[str, list[tuple[str, str, bool]]] = {
    AttributeType.TEXT.value: [
        ("contains", "contem", True),
        ("eq", "igual a", True),
        ("empty", "vazio", False),
        ("filled", "preenchido", False),
    ],
    AttributeType.NUMBER.value: [
        ("eq", "igual a", True),
        ("ne", "diferente de", True),
        ("gt", "maior que", True),
        ("lt", "menor que", True),
        ("gte", "maior ou igual", True),
        ("lte", "menor ou igual", True),
        ("empty", "vazio", False),
        ("filled", "preenchido", False),
    ],
    AttributeType.CURRENCY.value: [
        ("eq", "igual a", True),
        ("ne", "diferente de", True),
        ("gt", "maior que", True),
        ("lt", "menor que", True),
        ("gte", "maior ou igual", True),
        ("lte", "menor ou igual", True),
        ("empty", "vazio", False),
        ("filled", "preenchido", False),
    ],
    AttributeType.BOOLEAN.value: [
        ("is_true", "e sim", False),
        ("is_false", "e nao", False),
    ],
    AttributeType.DATE.value: [
        ("eq", "igual a", True),
        ("lt", "antes de", True),
        ("gt", "depois de", True),
        ("empty", "vazio", False),
        ("filled", "preenchido", False),
    ],
    AttributeType.FILE.value: [
        ("filled", "com anexo", False),
        ("empty", "sem anexo", False),
    ],
    AttributeType.SELECT.value: [
        ("eq", "e", True),
        ("ne", "diferente de", True),
        ("empty", "vazio", False),
        ("filled", "preenchido", False),
    ],
    AttributeType.REFERENCE_TASK.value: [
        ("filled", "com valor", False),
        ("empty", "sem valor", False),
    ],
    AttributeType.REFERENCE_ATTRIBUTE.value: [
        ("filled", "com valor", False),
        ("empty", "sem valor", False),
    ],
}


def ops_for(attr_type: str) -> list[tuple[str, str, bool]]:
    return FILTER_OPS.get(attr_type, [])


def _text_of(definition, value_row) -> str | None:
    if value_row is None:
        return None
    return value_row.value_text


def _number_of(value_row) -> float | None:
    if value_row is None:
        return None
    return value_row.value_number


def matches_attr(definition, value_row, op: str, raw_value: str) -> bool:
    """Um filtro casa com o valor (ou ausencia) do atributo?"""
    attr_type = definition.type
    if attr_type == AttributeType.TEXT.value:
        current = _text_of(definition, value_row)
        if op == "empty":
            return not current
        if op == "filled":
            return bool(current)
        current = current or ""
        if op == "contains":
            return raw_value.lower() in current.lower()
        if op == "eq":
            return current == raw_value
    elif attr_type in (AttributeType.NUMBER.value, AttributeType.CURRENCY.value):
        current = _number_of(value_row)
        if op == "empty":
            return current is None
        if op == "filled":
            return current is not None
        try:
            wanted = (
                parse_currency(raw_value)
                if attr_type == AttributeType.CURRENCY.value
                else float(raw_value.replace(",", "."))
            )
        except (ValueError, TypeError, ValidationError):
            return False
        if current is None:
            return False
        if op == "eq":
            return current == wanted
        if op == "ne":
            return current != wanted
        if op == "gt":
            return current > wanted
        if op == "lt":
            return current < wanted
        if op == "gte":
            return current >= wanted
        if op == "lte":
            return current <= wanted
    elif attr_type == AttributeType.BOOLEAN.value:
        current = value_row.value_boolean if value_row else None
        if op == "is_true":
            return current is True
        if op == "is_false":
            return current is not True
    elif attr_type == AttributeType.DATE.value:
        current = _text_of(definition, value_row)
        if op == "empty":
            return not current
        if op == "filled":
            return bool(current)
        try:
            wanted = parse_date(raw_value)
        except (ValueError, TypeError, ValidationError):
            return False
        if not current:
            return False
        if op == "eq":
            return current == wanted
        if op == "lt":
            return current < wanted
        if op == "gt":
            return current > wanted
    elif attr_type == AttributeType.SELECT.value:
        current = _text_of(definition, value_row)
        if op == "empty":
            return not current
        if op == "filled":
            return bool(current)
        if op == "eq":
            return (current or "") == raw_value
        if op == "ne":
            return (current or "") != raw_value
    elif attr_type in (
        AttributeType.FILE.value,
        AttributeType.REFERENCE_TASK.value,
        AttributeType.REFERENCE_ATTRIBUTE.value,
    ):
        has = value_row is not None and bool(
            value_row.value_text or value_row.value_reference_task_id
        )
        if op == "filled":
            return has
        if op == "empty":
            return not has
    return False
