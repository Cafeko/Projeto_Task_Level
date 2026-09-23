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


def op_label(attr_type: str, op_id: str) -> str:
    """Rotulo do operador (p/ mensagens de bloqueio)."""
    for oid, label, _needs in ops_for(attr_type):
        if oid == op_id:
            return label
    return op_id


# -- arvore de condicoes AND/OR (condicoes de entrada de fase) -----------------
#
# Formatos aceitos (compat: lista antiga = AND):
#   None / []                              -> sem condicao
#   [{"attr","op","value"}]                -> AND (legado)
#   {"logic":"AND"|"OR","rules":[...]}     -> no (recursivo; folha ou no)
# Uma folha e {"attr": str, "op": str, "value": str}.
#
# A UI edita a arvore aninhada: cada grupo combina os filhos com E ou OU
# e pode conter folhas e/ou subgrupos. Ex: (A e B) ou (C) =
#     {"logic":"OR","rules":[{"logic":"AND","rules":[A,B]}, C]}.
# to_groups/from_groups mantidos p/ compat (visao DNF achatada).

def is_leaf(node: object) -> bool:
    return isinstance(node, dict) and isinstance(node.get("attr"), str)


def is_logic_node(node: object) -> bool:
    return (
        isinstance(node, dict)
        and node.get("logic") in ("AND", "OR")
        and isinstance(node.get("rules"), list)
    )


def validate_conditions(raw: object) -> None:
    """Valida a estrutura; lanca ValueError se invalida."""
    from task_level.domain import ValidationError

    if raw is None:
        return
    if isinstance(raw, list):
        for leaf in raw:
            if not (isinstance(leaf, dict) and isinstance(leaf.get("attr"), str)
                    and isinstance(leaf.get("op"), str)):
                raise ValidationError("phase.enter_conditions invalido")
        return
    if is_logic_node(raw):
        if not raw["rules"]:
            raise ValidationError("phase.enter_conditions invalido: grupo vazio")
        for rule in raw["rules"]:
            if is_leaf(rule):
                if not isinstance(rule.get("op"), str):
                    raise ValidationError("phase.enter_conditions invalido")
            elif is_logic_node(rule):
                validate_conditions(rule)
            else:
                raise ValidationError("phase.enter_conditions invalido")
        return
    raise ValidationError("phase.enter_conditions invalido")


def normalize_conditions(raw) -> dict | None:
    """Converte qualquer formato valido p/ arvore canonica ou None."""
    if raw is None:
        return None
    if isinstance(raw, list):
        leafs = [c for c in raw if isinstance(c, dict)]
        if not leafs:
            return None
        if len(leafs) == 1:
            return {"logic": "AND", "rules": [leafs[0]]}
        return {"logic": "AND", "rules": list(leafs)}
    if is_logic_node(raw):
        if not raw["rules"]:
            return None
        return {"logic": raw["logic"], "rules": list(raw["rules"])}
    return None


def evaluate_tree(tree: dict, match_fn) -> bool:
    """Avalia recursivamente; match_fn(folha)->bool."""
    if is_leaf(tree):
        return bool(match_fn(tree))
    logic = tree.get("logic", "AND")
    rules = tree.get("rules", [])
    if logic == "OR":
        return any(
            evaluate_tree(r, match_fn) if not is_leaf(r) else bool(match_fn(r))
            for r in rules
        )
    return all(
        evaluate_tree(r, match_fn) if not is_leaf(r) else bool(match_fn(r))
        for r in rules
    )


def to_groups(raw) -> list[list[dict]]:
    """Achata qualquer formato p/ grupos DNF (E dentro, OU entre)."""
    tree = normalize_conditions(raw)
    if tree is None:
        return []
    if tree["logic"] == "AND" and all(is_leaf(r) for r in tree["rules"]):
        return [[dict(r) for r in tree["rules"]]]
    groups: list[list[dict]] = []
    for rule in tree["rules"]:
        if is_leaf(rule):
            groups.append([dict(rule)])
        elif is_logic_node(rule) and rule["logic"] == "AND":
            groups.append([dict(r) for r in rule["rules"] if is_leaf(r)])
        elif is_logic_node(rule):
            # OR aninhado: cada folha vira um grupo
            for sub in rule["rules"]:
                if is_leaf(sub):
                    groups.append([dict(sub)])
                else:
                    groups.extend(to_groups(sub))
        else:
            continue
    groups = [g for g in groups if g]
    return groups or []


def from_groups(groups: list[list[dict]]) -> list | dict | None:
    """Serializa grupos DNF p/ armazenamento (None/lista/OR)."""
    clean = [[dict(c) for c in g if isinstance(c, dict) and c.get("attr")] for g in groups]
    clean = [g for g in clean if g]
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]  # lista legada = AND
    if all(len(g) == 1 for g in clean):
        return {"logic": "OR", "rules": [g[0] for g in clean]}
    rules = []
    for g in clean:
        if len(g) == 1:
            rules.append(g[0])
        else:
            rules.append({"logic": "AND", "rules": list(g)})
    return {"logic": "OR", "rules": rules}


def count_conditions(raw) -> tuple[int, int]:
    """(n_folhas, n_grupos) p/ qualquer formato (lista ou arvore aninhada)."""
    if not raw:
        return (0, 0)
    if isinstance(raw, list):
        return (len([c for c in raw if isinstance(c, dict)]), 1 if raw else 0)
    if is_logic_node(raw):
        leaves, groups = 0, 1
        for rule in raw.get("rules", []):
            if is_leaf(rule):
                leaves += 1
            elif is_logic_node(rule):
                sub_leaves, sub_groups = count_conditions(rule)
                leaves += sub_leaves
                groups += sub_groups
        return (leaves, groups)
    return (0, 0)


def describe_tree(tree: dict, describe_leaf) -> str:
    """Descricao legivel: "(A e B) ou (C)"."""

    def _desc(node: dict) -> str:
        if is_leaf(node):
            return describe_leaf(node)
        parts = [_desc(r) for r in node.get("rules", [])]
        joiner = " ou " if node.get("logic") == "OR" else " e "
        text = joiner.join(parts)
        # parenteses em subgrupo aninhado com >1 parte (ambas direcoes)
        if len(parts) > 1:
            return f"({text})"
        return text

    if is_leaf(tree):
        return describe_leaf(tree)
    top_or = tree.get("logic") == "OR"
    parts = []
    for rule in tree.get("rules", []):
        parts.append(_desc(rule))
    joiner = " ou " if top_or else " e "
    return joiner.join(parts)


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
