"""Testes Parte 5: services (fluxo completo + ciclos + fases)."""

import pytest

from task_level.domain import CircularReferenceError, NotFoundError, ValidationError
from task_level.services import ProjectService, TaskService, TaskTypeService


@pytest.fixture()
def services(tmp_path):
    db = tmp_path / "svc.db"
    return (
        ProjectService(db),
        TaskTypeService(db),
        TaskService(db),
    )


def _bug_type(task_types, project_id):
    return task_types.create_type(
        project_id,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text", "required": True},
            {"name": "rel", "label": "Relacionada", "type": "reference_task"},
        ],
    )


def test_full_flow_create_move_final(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = _bug_type(task_types, p.id)
    task = tasks.create_task(p.id, t.id, "Bug #1")
    assert task.phase_id is not None and task.completed_at is None

    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        ordered = sorted(uow.phases.list_by_task_type(t.id), key=lambda p: p.order)
    initial, middle, final = (ph.id for ph in ordered)
    # pular direto p/ a final nao pode
    with pytest.raises(ValidationError):
        tasks.move_phase(task.id, final)
    # avanca uma: ok
    tasks.move_phase(task.id, middle)
    # final sem required -> falha
    with pytest.raises(ValidationError):
        tasks.move_phase(task.id, final)
    # preenche required e move -> ok + completed_at setado
    tasks.set_attribute(task.id, "sev", "alta")
    moved = tasks.move_phase(task.id, final)
    assert moved.phase_id == final and moved.completed_at is not None
    _ = initial


def test_move_phase_only_neighbors(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = _bug_type(task_types, p.id)
    task = tasks.create_task(p.id, t.id, "Bug #1", values={"sev": "alta"})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        ordered = sorted(uow.phases.list_by_task_type(t.id), key=lambda p: p.order)
    first, second, third = (ph.id for ph in ordered)
    with pytest.raises(ValidationError):  # pular p/ frente
        tasks.move_phase(task.id, third)
    tasks.move_phase(task.id, second)  # vizinha: ok
    tasks.move_phase(task.id, third)  # vizinha: ok
    with pytest.raises(ValidationError):  # voltar pulando
        tasks.move_phase(task.id, first)
    back = tasks.move_phase(task.id, second)  # voltar uma: ok
    assert back.phase_id == second and back.completed_at is None


def test_neighbors_and_check_move_single_point(services):
    """UI consulta neighbors; check_move valida (terreno p/ condicoes)."""
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = _bug_type(task_types, p.id)
    task = tasks.create_task(p.id, t.id, "Bug #1", values={"sev": "alta"})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        ordered = sorted(uow.phases.list_by_task_type(t.id), key=lambda p: p.order)
    prev, nxt = tasks.neighbors(task.id)
    assert prev is None and nxt is not None and nxt.id == ordered[1].id
    tasks.move_phase(task.id, nxt.id)
    tasks.move_phase(task.id, tasks.neighbors(task.id)[1].id)
    prev, nxt = tasks.neighbors(task.id)
    assert nxt is None and prev is not None and prev.id == ordered[1].id
    tasks.check_move(task.id, prev.id)  # vizinha: ok
    with pytest.raises(ValidationError):  # pular: rejeita no ponto unico
        tasks.check_move(task.id, ordered[0].id)


def test_reference_and_cycle_rejected(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = _bug_type(task_types, p.id)
    a = tasks.create_task(p.id, t.id, "A", values={"sev": "alta"})
    b = tasks.create_task(p.id, t.id, "B", values={"sev": "baixa"})
    tasks.set_attribute(a.id, "rel", b.id)  # A -> B ok
    with pytest.raises(CircularReferenceError):
        tasks.set_attribute(b.id, "rel", a.id)  # B -> A fecharia ciclo
    with pytest.raises(CircularReferenceError):
        tasks.set_attribute(a.id, "rel", a.id)  # auto-referencia


def test_reference_attribute_points_to_other_task_attr(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id,
        "T",
        attributes=[
            {"name": "nota", "label": "Nota", "type": "number"},
            {"name": "espelho", "label": "Espelho", "type": "reference_attribute"},
        ],
    )
    a = tasks.create_task(p.id, t.id, "A", values={"nota": 42})
    b = tasks.create_task(p.id, t.id, "B")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        nota_def = uow.attribute_definitions.get_by_name(t.id, "nota")
        nota_attr = uow.task_attributes.get(a.id, nota_def.id)
    tasks.set_attribute(b.id, "espelho", (a.id, nota_attr.id))
    with pytest.raises(NotFoundError):
        tasks.set_attribute(b.id, "espelho", (a.id, 999999))


def test_reference_task_cross_type_same_project(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    bug = task_types.create_type(
        p.id,
        "Bug",
        attributes=[{"name": "rel", "label": "Rel", "type": "reference_task"}],
    )
    feat = task_types.create_type(
        p.id,
        "Feature",
        attributes=[{"name": "nota", "label": "Nota", "type": "text"}],
    )
    f = tasks.create_task(p.id, feat.id, "F1")
    b = tasks.create_task(p.id, bug.id, "B1")
    tasks.set_attribute(b.id, "rel", f.id)  # tipos diferentes, mesmo projeto: ok
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        rel_def = uow.attribute_definitions.get_by_name(bug.id, "rel")
        got = uow.task_attributes.get(b.id, rel_def.id)
    assert got is not None and got.value_reference_task_id == f.id


def test_reference_other_project_rejected(services):
    projects, task_types, tasks = services
    p1 = projects.create("P1")
    p2 = projects.create("P2")
    t1 = task_types.create_type(
        p1.id,
        "T",
        attributes=[{"name": "rel", "label": "R", "type": "reference_task"}],
    )
    t2 = task_types.create_type(
        p2.id, "T", attributes=[{"name": "x", "label": "X", "type": "text"}]
    )
    other = tasks.create_task(p2.id, t2.id, "Outro")
    mine = tasks.create_task(p1.id, t1.id, "Minha")
    with pytest.raises(ValidationError):
        tasks.set_attribute(mine.id, "rel", other.id)


def test_reference_attribute_fixed_config_cross_type(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    a = task_types.create_type(
        p.id,
        "A",
        attributes=[{"name": "valor", "label": "Valor", "type": "number"}],
    )
    c = task_types.create_type(
        p.id,
        "C",
        attributes=[{"name": "valor", "label": "Valor", "type": "number"}],
    )
    b = task_types.create_type(
        p.id,
        "B",
        attributes=[
            {"name": "outro", "label": "Outro", "type": "text"},
            {
                "name": "espelho",
                "label": "Espelho",
                "type": "reference_attribute",
                "reference_config": {"attribute_name": "valor"},
            },
        ],
    )
    from task_level.data import UnitOfWork

    ta = tasks.create_task(p.id, a.id, "TA", values={"valor": 7})
    tc = tasks.create_task(p.id, c.id, "TC", values={"valor": 9})
    tb = tasks.create_task(p.id, b.id, "TB", values={"outro": "x"})
    with UnitOfWork.open(task_types._db_path) as uow:
        outro_def = uow.attribute_definitions.get_by_name(b.id, "outro")
        outro_val = uow.task_attributes.get(tb.id, outro_def.id)
    # entre tipos com o atributo fixo: ok
    resolved = tasks.resolve_reference_attribute(ta.id, "valor")
    assert resolved is not None and resolved[0] == ta.id
    tasks.set_attribute(tb.id, "espelho", resolved)
    # atributo diferente do fixo: rejeita
    with pytest.raises(ValidationError):
        tasks.set_attribute(tb.id, "espelho", (tb.id, outro_val.id))
    # sem valor no atributo fixo: nao resolve
    assert tasks.resolve_reference_attribute(tb.id, "valor") is None
    _ = tc


def test_reference_config_target_type_filter(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    a = task_types.create_type(
        p.id,
        "A",
        attributes=[{"name": "valor", "label": "Valor", "type": "number"}],
    )
    c = task_types.create_type(
        p.id,
        "C",
        attributes=[{"name": "valor", "label": "Valor", "type": "number"}],
    )
    b = task_types.create_type(
        p.id,
        "B",
        attributes=[
            {
                "name": "espelho",
                "label": "Espelho",
                "type": "reference_attribute",
                "reference_config": {"attribute_name": "valor"},
            },
        ],
    )
    from task_level.data import UnitOfWork

    # ajusta o filtro para o tipo A (id real so existe apos criar)
    with UnitOfWork.open(task_types._db_path) as uow:
        esp_def = uow.attribute_definitions.get_by_name(b.id, "espelho")
    task_types.update_attribute(
        esp_def.id,
        {
            "name": "espelho",
            "label": "Espelho",
            "type": "reference_attribute",
            "reference_config": {"attribute_name": "valor", "target_type_id": a.id},
            "order": 0,
        },
    )
    ta = tasks.create_task(p.id, a.id, "TA", values={"valor": 1})
    tc = tasks.create_task(p.id, c.id, "TC", values={"valor": 2})
    tb = tasks.create_task(p.id, b.id, "TB")
    tasks.set_attribute(tb.id, "espelho", tasks.resolve_reference_attribute(ta.id, "valor"))
    with pytest.raises(ValidationError):
        tasks.set_attribute(tb.id, "espelho", tasks.resolve_reference_attribute(tc.id, "valor"))


def test_reference_config_target_type_must_be_same_project(services):
    projects, task_types, _tasks = services
    p1 = projects.create("P1")
    p2 = projects.create("P2")
    other = task_types.create_type(p2.id, "Outro")
    with pytest.raises(ValidationError):
        task_types.create_type(
            p1.id,
            "X",
            attributes=[
                {
                    "name": "r",
                    "label": "R",
                    "type": "reference_task",
                    "reference_config": {"target_type_id": other.id},
                }
            ],
        )


def test_wrong_type_value_rejected(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id, "T", attributes=[{"name": "n", "label": "N", "type": "number"}]
    )
    task = tasks.create_task(p.id, t.id, "T1")
    with pytest.raises(ValidationError):
        tasks.set_attribute(task.id, "n", "nao-numerico")
    with pytest.raises(NotFoundError):
        tasks.set_attribute(task.id, "inexistente", "x")


def test_type_requires_single_initial_phase(services):
    projects, task_types, _tasks = services
    p = projects.create("P1")
    with pytest.raises(ValidationError):
        task_types.create_type(
            p.id, "Ruim", phases=[{"name": "A"}, {"name": "B"}]
        )


def test_type_requires_single_final_phase(services):
    projects, task_types, _tasks = services
    p = projects.create("P1")
    with pytest.raises(ValidationError):  # duas finais
        task_types.create_type(
            p.id,
            "Ruim",
            phases=[
                {"name": "A", "is_initial": True, "is_final": True},
                {"name": "B", "is_final": True},
            ],
        )
    with pytest.raises(ValidationError):  # nenhuma final
        task_types.create_type(
            p.id,
            "Ruim",
            phases=[
                {"name": "A", "is_initial": True},
                {"name": "B"},
            ],
        )


def test_final_phase_kept_single_on_edit_and_delete(services):
    projects, task_types, _tasks = services
    p = projects.create("P1")
    t = task_types.create_type(p.id, "T")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        ordered = sorted(uow.phases.list_by_task_type(t.id), key=lambda x: x.order)
    first, last = ordered[0], ordered[-1]
    assert last.is_final and not first.is_final
    # marcar outra como final desmarca a anterior (radio)
    task_types.update_phase(first.id, is_final=True)
    with UnitOfWork.open(task_types._db_path) as uow:
        finals = [x for x in uow.phases.list_by_task_type(t.id) if x.is_final]
    assert [x.id for x in finals] == [first.id]
    # nao da p/ ficar sem final nem excluir a unica
    with pytest.raises(ValidationError):
        task_types.update_phase(first.id, is_final=False)
    with pytest.raises(ValidationError):
        task_types.delete_phase(first.id)
