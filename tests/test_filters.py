"""Testes do motor de filtros por atributo (puro, sem Qt)."""

from types import SimpleNamespace

from task_level.services.filters import matches_attr, ops_for


def _def(type_id, name, attr_type, options=None):
    return SimpleNamespace(
        id=1, task_type_id=type_id, name=name, type=attr_type, options=options
    )


def _val(**kwargs):
    base = dict(
        value_text=None,
        value_number=None,
        value_boolean=None,
        value_reference_task_id=None,
        value_reference_attribute_id=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_ops_cover_all_types():
    from task_level.domain import AttributeType

    for t in AttributeType.values():
        assert ops_for(t), t


def test_text_contains_eq_empty():
    d = _def(1, "titulo", "text")
    assert matches_attr(d, _val(value_text="Crash ao abrir"), "contains", "crash")
    assert not matches_attr(d, _val(value_text="Crash"), "contains", "lento")
    assert matches_attr(d, _val(value_text="X"), "eq", "X")
    assert matches_attr(d, None, "empty", "")
    assert matches_attr(d, _val(value_text="x"), "filled", "")


def test_number_comparisons():
    d = _def(1, "n", "number")
    v = _val(value_number=10)
    assert matches_attr(d, v, "eq", "10")
    assert matches_attr(d, v, "gt", "9")
    assert matches_attr(d, v, "lte", "10")
    assert not matches_attr(d, v, "lt", "10")
    assert not matches_attr(d, None, "eq", "10")
    assert matches_attr(d, None, "empty", "")
    assert not matches_attr(d, v, "eq", "batman")


def test_currency_and_date():
    money = _def(1, "preco", "currency")
    assert matches_attr(money, _val(value_number=1234.56), "eq", "1.234,56")
    assert matches_attr(money, _val(value_number=5), "gt", "10") is False
    day = _def(1, "venc", "date")
    assert matches_attr(day, _val(value_text="2026-09-20"), "eq", "20/09/2026")
    assert matches_attr(day, _val(value_text="2026-09-20"), "lt", "21/09/2026")
    assert not matches_attr(day, _val(value_text="2026-09-20"), "gt", "21/09/2026")


def test_boolean_select_file_ref():
    b = _def(1, "ativo", "boolean")
    assert matches_attr(b, _val(value_boolean=True), "is_true", "")
    assert matches_attr(b, _val(value_boolean=False), "is_false", "")
    assert matches_attr(b, None, "is_false", "")  # nunca marcado = nao
    s = _def(1, "tam", "select", options=["P", "M"])
    assert matches_attr(s, _val(value_text="M"), "eq", "M")
    assert matches_attr(s, _val(value_text="M"), "ne", "P")
    f = _def(1, "doc", "file")
    assert matches_attr(f, _val(value_text="/x.pdf"), "filled", "")
    assert matches_attr(f, None, "empty", "")
    r = _def(1, "rel", "reference_task")
    assert matches_attr(r, _val(value_reference_task_id=3), "filled", "")
    assert matches_attr(r, None, "empty", "")
