"""Testes Parte 9: dialog de task + kanban (offscreen) + update_details."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from task_level.presentation.widgets.kanban_board import KanbanBoard
from task_level.services import ProjectService, TaskService, TaskTypeService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def setup(tmp_path):
    db = tmp_path / "tasks.db"
    p = ProjectService(db).create("P1")
    types = TaskTypeService(db)
    t = types.create_type(
        p.id,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text", "required": True},
            {"name": "ativo", "label": "Ativo", "type": "boolean"},
        ],
    )
    return db, p.id, t.id


def test_update_details_and_clear_attribute(setup):
    db, pid, tid = setup
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1", values={"sev": "alta", "ativo": True})
    updated = svc.update_details(task.id, "T1-renamed", "desc")
    assert updated.title == "T1-renamed" and updated.description == "desc"
    svc.clear_attribute(task.id, "sev")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(db) as uow:
        sev_def = uow.attribute_definitions.get_by_name(tid, "sev")
        assert uow.task_attributes.get(task.id, sev_def.id) is None


def test_task_dialog_payload(setup, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db, pid, _tid = setup
    dlg = TaskDialog(None, db, pid)
    try:
        assert dlg._type_combo.count() == 1
        dlg._title.setText("Bug #1")
        sev_widget = dlg._fields["sev"]
        sev_widget.setText("alta")
        payload = dlg.payload()
        assert payload["title"] == "Bug #1"
        assert payload["values"] == {"sev": "alta", "ativo": False}
    finally:
        dlg.close()


def test_kanban_board_columns_and_move(setup, qapp):
    db, pid, tid = setup
    svc = TaskService(db)
    a = svc.create_task(pid, tid, "A", values={"sev": "alta"})
    board = KanbanBoard(db, pid, tid)
    try:
        assert len(board._columns) == 3
        first_col_tasks = board._columns[0][2].count()
        assert first_col_tasks == 1
        from task_level.data import UnitOfWork

        with UnitOfWork.open(db) as uow:
            ordered = sorted(uow.phases.list_by_task_type(tid), key=lambda p: p.order)
        board._move_task(a.id, ordered[1].id)  # avanca uma
        counts = [lst.count() for _, _, lst in board._columns]
        assert sum(counts) == 1 and counts[1] == 1
        board._move_task(a.id, ordered[2].id)  # avanca p/ final
        counts = [lst.count() for _, _, lst in board._columns]
        assert sum(counts) == 1 and counts[-1] == 1
    finally:
        board.close()


def test_kanban_nav_buttons_step_one_phase(setup, qapp):
    db, pid, tid = setup
    svc = TaskService(db)
    a = svc.create_task(pid, tid, "A", values={"sev": "alta"})
    board = KanbanBoard(db, pid, tid)
    try:
        assert board._btn_back.isEnabled() is False  # nada selecionado
        assert board._btn_fwd.isEnabled() is False
        board._columns[0][2].setCurrentRow(0)
        assert board._btn_back.isEnabled() is False  # primeira fase
        assert board._btn_fwd.isEnabled() is True
        board._btn_fwd.click()  # avancar uma
        assert svc.get(a.id).phase_id is not None
        board._columns[1][2].setCurrentRow(0)
        assert board._btn_back.isEnabled() is True
        board._btn_back.click()  # voltar uma
        from task_level.data import UnitOfWork

        with UnitOfWork.open(db) as uow:
            ordered = sorted(uow.phases.list_by_task_type(tid), key=lambda p: p.order)
        assert svc.get(a.id).phase_id == ordered[0].id
    finally:
        board.close()


def test_task_dialog_phase_stepper_buttons(tmp_path, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db = tmp_path / "ph.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(pid, "Bug").id
    task = TaskService(db).create_task(pid, tid, "B1")
    dlg = TaskDialog(None, db, pid, task_id=task.id)
    try:
        assert dlg._phase_label.text() == "Novo"
        assert dlg._btn_phase_back.isEnabled() is False  # primeira fase
        assert dlg._btn_phase_fwd.isEnabled() is True
        dlg._btn_phase_fwd.click()  # avancar uma
        assert dlg._phase_label.text().startswith("Em andamento")
        assert dlg.payload()["phase_id"] != task.phase_id
        dlg._btn_phase_back.click()  # voltar
        assert dlg._phase_label.text() == "Novo"
        assert dlg.payload()["phase_id"] == task.phase_id
    finally:
        dlg.close()


def test_task_dialog_fixed_ref_attribute_task_only(tmp_path, qapp):
    """Ref-attr com atributo fixo: combo so de tasks (entre tipos) e resolve par."""
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db = tmp_path / "fixed.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    feat = types.create_type(
        pid,
        "Feature",
        attributes=[{"name": "valor", "label": "Valor", "type": "number"}],
    )
    bug = types.create_type(
        pid,
        "Bug",
        attributes=[
            {
                "name": "espelho",
                "label": "Espelho",
                "type": "reference_attribute",
                "reference_config": {"attribute_name": "valor"},
            },
            {"name": "rel", "label": "Rel", "type": "reference_task"},
        ],
    )
    svc = TaskService(db)
    f1 = svc.create_task(pid, feat.id, "F1", values={"valor": 10})
    svc.create_task(pid, feat.id, "F2")  # sem valor: nao entra na lista

    dlg = TaskDialog(None, db, pid, task_type_id=bug.id)
    try:
        idx = dlg._type_combo.findData(bug.id)
        dlg._type_combo.setCurrentIndex(idx)
        dlg._rebuild_attributes()
        combo, attr_name = dlg._ref_fixed["espelho"]
        assert attr_name == "valor"
        assert combo.count() == 2  # (nenhuma) + F1
        assert combo.itemData(1) == f1.id
        assert "Valor = 10" in combo.itemText(1)  # valor visivel na opcao
        # ref-task cruza tipos e mostra o tipo no texto
        rel_combo = dlg._fields["rel"]
        assert rel_combo.count() == 3  # (nenhuma) + F1 + F2
        assert "Feature" in rel_combo.itemText(1)
        dlg._title.setText("B1")
        combo.setCurrentIndex(1)
        payload = dlg.payload()
        task_id, _attr_value_id = payload["values"]["espelho"]
        assert task_id == f1.id
    finally:
        dlg.close()


def test_task_dialog_currency_and_date_payload(tmp_path, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db = tmp_path / "money.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid,
        "Venda",
        attributes=[
            {"name": "preco", "label": "Preco", "type": "currency"},
            {"name": "venc", "label": "Vencimento", "type": "date"},
        ],
    ).id
    TaskService(db).create_task(pid, tid, "V1", values={"preco": 10})

    dlg = TaskDialog(None, db, pid, task_type_id=tid)
    try:
        from PySide6.QtCore import QDate

        preco_widget = dlg._fields["preco"]
        preco_widget.setText("2.500,75")
        dlg._title.setText("V2")
        # sem valor previo: comeca no dia atual, ja editavel
        today = QDate.currentDate().toString("yyyy-MM-dd")
        assert dlg.payload()["values"]["venc"] == today
        dlg._date_edits["venc"].setDate(QDate(2026, 9, 20))
        payload = dlg.payload()
        assert payload["values"]["preco"] == 2500.75
        assert payload["values"]["venc"] == "2026-09-20"
    finally:
        dlg.close()


def test_task_dialog_file_field_pending_and_apply(tmp_path, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db = tmp_path / "doc.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid, "T", attributes=[{"name": "doc", "label": "Doc", "type": "file"}]
    ).id
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1")
    src = tmp_path / "rel.pdf"
    src.write_bytes(b"%PDF")

    dlg = TaskDialog(None, db, pid, task_id=task.id)
    try:
        assert "doc" not in dlg.payload()["values"]  # arquivo nao vai no payload
        dlg._file_pending["doc"] = str(src)
        dlg._apply_files(svc, task.id)
        from task_level.data import UnitOfWork

        with UnitOfWork.open(db) as uow:
            definition = uow.attribute_definitions.get_by_name(tid, "doc")
            got = uow.task_attributes.get(task.id, definition.id)
        assert got is not None and got.value_text.endswith("doc.pdf")
    finally:
        dlg.close()


def test_task_dialog_select_payload(tmp_path, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db = tmp_path / "sel.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid,
        "T",
        attributes=[
            {"name": "tam", "label": "Tamanho", "type": "select", "options": ["P", "M", "G"]}
        ],
    ).id
    task = TaskService(db).create_task(pid, tid, "T1", values={"tam": "M"})

    dlg = TaskDialog(None, db, pid, task_id=task.id)
    try:
        combo = dlg._fields["tam"]
        assert combo.count() == 4  # (nenhuma) + 3 opcoes
        assert combo.currentData() == "M"  # preenche salvo
        combo.setCurrentIndex(3)
        assert dlg.payload()["values"]["tam"] == "G"
    finally:
        dlg.close()


def test_task_dialog_phase_notes_tabs(tmp_path, qapp):
    from task_level.presentation.dialogs.task_dialog import TaskDialog

    db = tmp_path / "notes.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(pid, "T").id
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1")
    from task_level.data import UnitOfWork

    with UnitOfWork.open(db) as uow:
        ordered = sorted(uow.phases.list_by_task_type(tid), key=lambda p: p.order)
    svc.set_phase_note(task.id, ordered[0].id, "nota do inicio")

    dlg = TaskDialog(None, db, pid, task_id=task.id)
    try:
        assert dlg._notes_tabs.count() == 3  # uma aba por fase
        assert dlg._note_edits[ordered[0].id].toPlainText() == "nota do inicio"
        dlg._note_edits[ordered[1].id].setPlainText("nota do meio")
        dlg._apply_notes(svc, task.id)
        assert svc.phase_notes(task.id) == {
            ordered[0].id: "nota do inicio",
            ordered[1].id: "nota do meio",
        }
    finally:
        dlg.close()


def test_filter_dialog_roundtrip(tmp_path, qapp):
    from task_level.presentation.dialogs.filter_dialog import FilterDialog

    db = tmp_path / "flt.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(
        pid,
        "Bug",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text"},
            {"name": "tam", "label": "Tamanho", "type": "select", "options": ["P", "G"]},
        ],
    )
    preset = [{"type_id": bug.id, "attr": "sev", "op": "contains", "value": "crit"}]
    dlg = FilterDialog(None, db, pid, bug.id, preset)
    try:
        assert len(dlg._rows) == 1
        assert dlg.data() == preset
        # troca p/ atributo select: combo de opcoes aparece
        row = dlg._rows[0]
        for i in range(row.attr_combo.count()):
            if row.attr_combo.itemData(i)["name"] == "tam":
                row.attr_combo.setCurrentIndex(i)
                break
        assert row.stack.currentWidget() is row.combo
    finally:
        dlg.close()


def test_filter_dialog_scopes_attributes_by_type(tmp_path, qapp):
    """No Todos: escolhe o tipo primeiro, sem misturar atributos."""
    from task_level.presentation.dialogs.filter_dialog import FilterDialog

    db = tmp_path / "scope.db"
    pid = ProjectService(db).create("P1").id
    types = TaskTypeService(db)
    bug = types.create_type(
        pid, "Bug", attributes=[{"name": "sev", "label": "Severidade", "type": "text"}]
    )
    feat = types.create_type(
        pid, "Feature", attributes=[{"name": "pts", "label": "Pontos", "type": "number"}]
    )
    dlg = FilterDialog(None, db, pid, None, [])
    try:
        assert dlg._type_combo is not None
        assert dlg._type_combo.count() == 2
        assert dlg._rows[0].attr_combo.itemData(0)["name"] == "sev"
        idx = dlg._type_combo.findData(feat.id)
        dlg._type_combo.setCurrentIndex(idx)
        assert dlg._rows[0].attr_combo.itemData(0)["name"] == "pts"
        assert dlg._type_combo.currentData() == feat.id
        _ = bug
    finally:
        dlg.close()
