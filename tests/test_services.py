"""Testes Parte 5: services (fluxo completo + ciclos + fases)."""

from pathlib import Path

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


def test_currency_and_date_attributes(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id,
        "T",
        attributes=[
            {"name": "preco", "label": "Preco", "type": "currency"},
            {"name": "venc", "label": "Vencimento", "type": "date"},
        ],
    )
    task = tasks.create_task(p.id, t.id, "T1", values={"preco": "1.234,56"})
    tasks.set_attribute(task.id, "venc", "20/09/2026")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        preco_def = uow.attribute_definitions.get_by_name(t.id, "preco")
        venc_def = uow.attribute_definitions.get_by_name(t.id, "venc")
        preco = uow.task_attributes.get(task.id, preco_def.id)
        venc = uow.task_attributes.get(task.id, venc_def.id)
    assert preco is not None and preco.value_number == 1234.56
    assert venc is not None and venc.value_text == "2026-09-20"
    with pytest.raises(ValidationError):
        tasks.set_attribute(task.id, "preco", "muito dinheiro")
    with pytest.raises(ValidationError):
        tasks.set_attribute(task.id, "venc", "ontem")


def test_file_attribute_copies_clears_and_cleans_up(tmp_path):
    from task_level.data.files import attachments_root, task_files_dir
    from task_level.services import ProjectService, TaskService, TaskTypeService

    db = tmp_path / "files.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid, "T", attributes=[{"name": "doc", "label": "Doc", "type": "file"}]
    ).id
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1")
    src = tmp_path / "orig.txt"
    src.write_text("dados", encoding="utf-8")

    saved = svc.set_file_attribute(task.id, "doc", src)
    assert saved.value_text is not None and saved.value_text != str(src)
    assert Path(saved.value_text).is_file()  # copia gerenciada
    assert src.is_file()  # original preservada

    with pytest.raises(NotFoundError):
        svc.set_file_attribute(task.id, "doc", tmp_path / "falta.txt")

    svc.clear_attribute(task.id, "doc")  # apaga valor + arquivo
    assert not Path(saved.value_text).exists()

    svc.set_file_attribute(task.id, "doc", src)
    svc.delete(task.id)  # apaga task + pasta de anexos
    assert not task_files_dir(db, task.id).exists()
    _ = attachments_root(db)


def test_select_attribute_options_validated(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    with pytest.raises(ValidationError):  # select sem opcoes
        task_types.create_type(
            p.id,
            "Ruim",
            attributes=[{"name": "s", "label": "S", "type": "select"}],
        )
    t = task_types.create_type(
        p.id,
        "T",
        attributes=[
            {
                "name": "tam",
                "label": "Tamanho",
                "type": "select",
                "options": ["P", "M", "G"],
            }
        ],
    )
    task = tasks.create_task(p.id, t.id, "T1", values={"tam": "M"})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        tam_def = uow.attribute_definitions.get_by_name(t.id, "tam")
        assert tam_def is not None and tam_def.options == ["P", "M", "G"]
        got = uow.task_attributes.get(task.id, tam_def.id)
    assert got is not None and got.value_text == "M"
    with pytest.raises(ValidationError):  # fora das opcoes
        tasks.set_attribute(task.id, "tam", "XG")


def test_phase_notes_crud(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(p.id, "T")
    task = tasks.create_task(p.id, t.id, "T1")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        ordered = sorted(uow.phases.list_by_task_type(t.id), key=lambda x: x.order)
    first, second = ordered[0].id, ordered[1].id

    assert tasks.phase_notes(task.id) == {}
    tasks.set_phase_note(task.id, first, "começou bem")
    tasks.set_phase_note(task.id, second, "  ")
    assert tasks.phase_notes(task.id) == {first: "começou bem"}
    tasks.set_phase_note(task.id, first, "")  # vazia apaga
    assert tasks.phase_notes(task.id) == {}
    with pytest.raises(NotFoundError):
        tasks.set_phase_note(task.id, 999999, "x")


def test_phase_enter_conditions_block_and_release(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id,
        "T",
        phases=[
            {"name": "Novo", "is_initial": True},
            {
                "name": "Revisao",
                "enter_conditions": [
                    {"attr": "nota", "op": "gte", "value": "5"}
                ],
            },
            {"name": "Pronto", "is_final": True},
        ],
        attributes=[{"name": "nota", "label": "Nota", "type": "number"}],
    )
    task = tasks.create_task(p.id, t.id, "T1", values={"nota": 2})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        ordered = sorted(uow.phases.list_by_task_type(t.id), key=lambda x: x.order)
    review = ordered[1].id
    assert tasks.transition_block(task.id, review) is not None
    assert "Revisao" in tasks.transition_block(task.id, review)
    with pytest.raises(ValidationError):
        tasks.move_phase(task.id, review)
    tasks.set_attribute(task.id, "nota", 8)
    assert tasks.transition_block(task.id, review) is None
    tasks.move_phase(task.id, review)
    assert tasks.get(task.id).phase_id == review


def test_list_filtered_by_attributes(services):
    projects, task_types, tasks = services
    p = projects.create("P1")
    bug = task_types.create_type(
        p.id,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text"},
            {"name": "nota", "label": "Nota", "type": "number"},
        ],
    )
    feat = task_types.create_type(
        p.id,
        "Feature",
        attributes=[{"name": "sev", "label": "Severidade", "type": "text"}],
    )
    b1 = tasks.create_task(p.id, bug.id, "B1", values={"sev": "critica", "nota": 9})
    tasks.create_task(p.id, bug.id, "B2", values={"sev": "baixa", "nota": 2})
    f1 = tasks.create_task(p.id, feat.id, "F1", values={"sev": "critica"})
    _ = f1

    only_crit = tasks.list_filtered(
        p.id, None, [{"type_id": bug.id, "attr": "sev", "op": "eq", "value": "critica"}]
    )
    assert {t.id for t in only_crit} == {b1.id}
    both = tasks.list_filtered(
        p.id, None, [{"type_id": feat.id, "attr": "sev", "op": "eq", "value": "critica"}]
    )
    assert {t.title for t in both} == {"F1"}
    high = tasks.list_filtered(
        p.id, bug.id, [{"type_id": bug.id, "attr": "nota", "op": "gte", "value": "5"}]
    )
    assert [t.title for t in high] == ["B1"]
    assert tasks.list_filtered(p.id, None, []) is not None
    assert len(tasks.list_filtered(p.id, None, [])) == 3


def test_phase_enter_conditions_or(services):
    """OU: basta uma condicao valer."""
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id,
        "T",
        phases=[
            {"name": "Novo", "is_initial": True},
            {
                "name": "Rev",
                "enter_conditions": {
                    "logic": "OR",
                    "rules": [
                        {"attr": "nota", "op": "gte", "value": "5"},
                        {"attr": "vip", "op": "is_true", "value": ""},
                    ],
                },
            },
            {"name": "Fim", "is_final": True},
        ],
        attributes=[
            {"name": "nota", "label": "Nota", "type": "number"},
            {"name": "vip", "label": "Vip", "type": "boolean"},
        ],
    )
    task = tasks.create_task(p.id, t.id, "T1", values={"nota": 2})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        rev = sorted(uow.phases.list_by_task_type(t.id), key=lambda x: x.order)[1].id
    assert tasks.transition_block(task.id, rev) is not None
    tasks.set_attribute(task.id, "vip", True)
    assert tasks.transition_block(task.id, rev) is None
    tasks.move_phase(task.id, rev)


def test_phase_enter_conditions_groups_dnf(services):
    """(A E B) OU (C): grupos com E dentro, OU entre."""
    projects, task_types, tasks = services
    p = projects.create("P1")
    t = task_types.create_type(
        p.id,
        "T",
        phases=[
            {"name": "A", "is_initial": True},
            {
                "name": "B",
                "enter_conditions": {
                    "logic": "OR",
                    "rules": [
                        {
                            "logic": "AND",
                            "rules": [
                                {"attr": "n", "op": "gte", "value": "5"},
                                {"attr": "v", "op": "is_true", "value": ""},
                            ],
                        },
                        {"attr": "p", "op": "is_true", "value": ""},
                    ],
                },
            },
            {"name": "C", "is_final": True},
        ],
        attributes=[
            {"name": "n", "label": "N", "type": "number"},
            {"name": "v", "label": "V", "type": "boolean"},
            {"name": "p", "label": "P", "type": "boolean"},
        ],
    )
    task = tasks.create_task(p.id, t.id, "K", values={"n": 9})
    from task_level.data import UnitOfWork

    with UnitOfWork.open(task_types._db_path) as uow:
        target = sorted(uow.phases.list_by_task_type(t.id), key=lambda x: x.order)[1].id
    assert tasks.transition_block(task.id, target) is not None  # n=9 sem v, sem p
    tasks.set_attribute(task.id, "v", True)
    assert tasks.transition_block(task.id, target) is None  # grupo 1 completo
    # legado AND continua funcionando
    from task_level.services.filters import from_groups, to_groups

    assert to_groups([{"attr": "n", "op": "gte", "value": "5"}]) == [
        [{"attr": "n", "op": "gte", "value": "5"}]
    ]
    assert from_groups([[{"attr": "a", "op": "eq", "value": "1"}]]) == [
        {"attr": "a", "op": "eq", "value": "1"}
    ]
