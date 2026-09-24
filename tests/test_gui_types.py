"""Testes Parte 8: edicao de tipos + dialogs (offscreen)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from task_level.domain import ValidationError
from task_level.presentation.dialogs.task_type_dialog import validate_type_payload
from task_level.services import ProjectService, TaskTypeService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def types(tmp_path):
    db = tmp_path / "types.db"
    p = ProjectService(db).create("P1")
    return TaskTypeService(db), p.id


def test_validate_type_payload_pure():
    assert validate_type_payload({"name": "", "phases": [], "attributes": []}) != []
    ok = {
        "name": "Bug",
        "phases": [
            {"name": "Novo", "is_initial": True},
            {"name": "Pronto", "is_final": True},
        ],
        "attributes": [{"name": "a"}, {"name": "b"}],
    }
    assert validate_type_payload(ok) == []
    two_initial = {
        "name": "Bug",
        "phases": [
            {"name": "A", "is_initial": True, "is_final": True},
            {"name": "B", "is_initial": True},
        ],
        "attributes": [],
    }
    assert validate_type_payload(two_initial) != []
    two_finals = {
        "name": "Bug",
        "phases": [
            {"name": "A", "is_initial": True, "is_final": True},
            {"name": "B", "is_final": True},
        ],
        "attributes": [],
    }
    assert validate_type_payload(two_finals) != []
    no_final = {
        "name": "Bug",
        "phases": [{"name": "A", "is_initial": True}],
        "attributes": [],
    }
    assert validate_type_payload(no_final) != []
    dup_attr = {
        "name": "Bug",
        "phases": [
            {"name": "A", "is_initial": True},
            {"name": "B", "is_final": True},
        ],
        "attributes": [{"name": "x"}, {"name": "x"}],
    }
    assert validate_type_payload(dup_attr) != []


def test_update_type_and_phase_flow(types):
    svc, pid = types
    t = svc.create_type(pid, "Bug")
    updated = svc.update_type(t.id, "Bugfix", color="#ff0000")
    assert updated.name == "Bugfix" and updated.color == "#ff0000"

    phases_before = svc.get(t.id)
    assert phases_before is not None
    from task_level.data import UnitOfWork

    with UnitOfWork.open(svc._db_path) as uow:
        initial = uow.phases.initial_of_type(t.id)
    renamed = svc.update_phase(initial.id, name="Triagem")
    assert renamed.name == "Triagem" and renamed.is_initial

    with pytest.raises(ValidationError):
        svc.delete_phase(initial.id)  # unica inicial


def test_update_attribute_duplicate_name(types):
    svc, pid = types
    t = svc.create_type(
        pid,
        "T",
        attributes=[
            {"name": "a", "label": "A", "type": "text"},
            {"name": "b", "label": "B", "type": "text"},
        ],
    )
    from task_level.data import UnitOfWork

    with UnitOfWork.open(svc._db_path) as uow:
        b = uow.attribute_definitions.get_by_name(t.id, "b")
    with pytest.raises(ValidationError):
        svc.update_attribute(
            b.id, {"name": "a", "label": "A2", "type": "text", "order": 1}
        )


def test_task_type_dialog_payload_roundtrip(tmp_path, qapp):
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog()
    try:
        assert validate_type_payload(dlg.payload()) != []
        dlg._name.setText("Bug")
        dlg._phases.append({"name": "Novo", "is_initial": True, "is_final": True})
        payload = dlg.payload()
        assert validate_type_payload(payload) == []
        assert payload["name"] == "Bug"
    finally:
        dlg.close()


def test_manager_dialog_lists_types(tmp_path, qapp):
    from task_level.presentation.dialogs.task_type_manager_dialog import (
        TaskTypeManagerDialog,
    )

    db = tmp_path / "mgr.db"
    pid = ProjectService(db).create("P1").id
    TaskTypeService(db).create_type(pid, "Bug")
    dlg = TaskTypeManagerDialog(None, db, pid)
    try:
        assert dlg._list.count() == 1
    finally:
        dlg.close()


def test_attribute_dialog_reference_config(qapp):
    from task_level.presentation.dialogs.attribute_dialog import AttributeDialog

    targets = [
        {
            "type_id": 1,
            "type_name": "Feature",
            "attrs": [{"name": "valor", "label": "Valor"}],
        }
    ]
    dlg = AttributeDialog(
        None,
        {"name": "espelho", "label": "Espelho", "type": "reference_attribute"},
        ref_targets=targets,
    )
    try:
        assert dlg._ref_section.isVisibleTo(dlg)
        assert dlg.data()["reference_config"] == {"attribute_name": "valor"}
    finally:
        dlg.close()


def test_attribute_dialog_reference_task_config(qapp):
    from task_level.presentation.dialogs.attribute_dialog import AttributeDialog

    targets = [
        {
            "type_id": 7,
            "type_name": "Feature",
            "attrs": [{"name": "valor", "label": "Valor"}],
        }
    ]
    dlg = AttributeDialog(
        None,
        {
            "name": "rel",
            "label": "Rel",
            "type": "reference_task",
            "reference_config": {"target_type_id": 7},
        },
        ref_targets=targets,
    )
    try:
        assert dlg.data()["reference_config"] == {"target_type_id": 7}
    finally:
        dlg.close()


def test_attribute_dialog_select_options(qapp):
    from task_level.presentation.dialogs.attribute_dialog import AttributeDialog

    dlg = AttributeDialog(
        None, {"name": "tam", "label": "Tamanho", "type": "select"}
    )
    try:
        assert dlg._options_section.isVisibleTo(dlg)
        dlg._options_edit.setPlainText("P\nM\nG\n")
        assert dlg.data()["options"] == ["P", "M", "G"]
    finally:
        dlg.close()


def test_phase_dialog_has_no_order_field(qapp):
    """Ordem e automatica: sai do dialogo de fase."""
    from task_level.presentation.dialogs.phase_dialog import PhaseDialog

    dlg = PhaseDialog()
    try:
        assert "order" not in dlg.data()
    finally:
        dlg.close()


def test_phases_reorder_by_drag_renumbers(qapp):
    """Arrastar na lista reordena e renumera (0..n)."""
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog(
        None,
        {
            "name": "T",
            "phases": [
                {"name": "A", "is_initial": True, "order": 0},
                {"name": "B", "order": 1},
                {"name": "C", "order": 2},
            ],
        },
    )
    try:
        assert [p["order"] for p in dlg._phases] == [0, 1, 2]
        # simula arrastar A (linha 0) para o fim
        item = dlg._phase_list.takeItem(0)
        dlg._phase_list.insertItem(2, item)
        dlg._sync_order_from_list()
        assert [p["name"] for p in dlg._phases] == ["B", "C", "A"]
        assert [p["order"] for p in dlg._phases] == [0, 1, 2]
        dlg._refresh_phases()  # no app o drop ja refresca
        assert dlg._phase_list.item(0).text().startswith("0. B")
    finally:
        dlg.close()


def test_phases_remove_renumbers(qapp):
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog(
        None,
        {
            "name": "T",
            "phases": [
                {"name": "A", "is_initial": True, "order": 0},
                {"name": "B", "order": 1},
                {"name": "C", "order": 2},
            ],
        },
    )
    try:
        dlg._phase_list.setCurrentRow(1)
        dlg._remove_phase()
        assert [p["name"] for p in dlg._phases] == ["A", "C"]
        assert [p["order"] for p in dlg._phases] == [0, 1]
    finally:
        dlg.close()


def test_payload_marks_first_last_as_start_end(qapp):
    """Sem opcao manual: primeira = inicio, ultima = fim."""
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog(
        None,
        {"name": "T", "phases": [{"name": "A"}, {"name": "B"}, {"name": "C"}]},
    )
    try:
        flags = [
            (p["is_initial"], p["is_final"]) for p in dlg.payload()["phases"]
        ]
        assert flags == [(True, False), (False, False), (False, True)]
        assert "inicio" in dlg._phase_list.item(0).text()
        assert "fim" in dlg._phase_list.item(2).text()
    finally:
        dlg.close()


def test_drag_toggle_defaults_locked(qapp):
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog(None, {"name": "T", "phases": [{"name": "A"}]})
    try:
        assert dlg._drag_toggle.isChecked() is False
        assert dlg._phase_list.dragEnabled() is False
        dlg._drag_toggle.setChecked(True)
        assert dlg._phase_list.dragEnabled() is True
    finally:
        dlg.close()


def test_attribute_dialog_has_no_order_field(qapp):
    """Ordem e automatica: sai do dialogo de atributo (como nas fases)."""
    from task_level.presentation.dialogs.attribute_dialog import AttributeDialog

    dlg = AttributeDialog(None, {"name": "a", "label": "A", "type": "text"})
    try:
        assert "order" not in dlg.data()
    finally:
        dlg.close()


def _attr_dialog(*names: str):
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    return TaskTypeDialog(
        None,
        {
            "name": "T",
            "phases": [{"name": "P"}],
            "attributes": [
                {"name": n, "label": n.upper(), "type": "text", "order": i}
                for i, n in enumerate(names)
            ],
        },
    )


def _move_table_row(table, src: int, dst: int) -> None:
    """Simula o arrasto de uma linha (reordena visualmente, como o drop)."""
    cells = [table.takeItem(src, c) for c in range(table.columnCount())]
    table.removeRow(src)
    table.insertRow(dst)
    for c, item in enumerate(cells):
        table.setItem(dst, c, item)


def test_attrs_reorder_by_drag_renumbers(qapp):
    """Arrastar a linha reordena e renumera (0..n), como nas fases."""
    dlg = _attr_dialog("a", "b", "c")
    try:
        assert [a["order"] for a in dlg._attrs] == [0, 1, 2]
        # simula arrastar A (linha 0) para o fim
        _move_table_row(dlg._attr_table, 0, 2)
        dlg._sync_attrs_order_from_list()
        assert [a["name"] for a in dlg._attrs] == ["b", "c", "a"]
        assert [a["order"] for a in dlg._attrs] == [0, 1, 2]
        dlg._refresh_attrs()  # no app o drop ja refresca
        assert dlg._attr_table.item(0, 0).text() == "b"
        assert dlg._attr_table.item(0, 1).text() == "B"
        assert [a["order"] for a in dlg.payload()["attributes"]] == [0, 1, 2]
    finally:
        dlg.close()


def test_attr_cells_display_only(qapp):
    """Linhas so exibem/arrastam: sem edicao inline nem drop em cima."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractItemView

    dlg = _attr_dialog("a", "b")
    try:
        assert (
            dlg._attr_table.editTriggers() == QAbstractItemView.NoEditTriggers
        )
        for row in range(dlg._attr_table.rowCount()):
            for col in range(dlg._attr_table.columnCount()):
                flags = dlg._attr_table.item(row, col).flags()
                assert not flags & Qt.ItemIsEditable
                assert not flags & Qt.ItemIsDropEnabled
                assert flags & Qt.ItemIsSelectable
    finally:
        dlg.close()


def test_attrs_drop_applies_after_event_loop(qapp):
    """Drop real aplica a ordem assim que termina (sem corromper linhas)."""
    from PySide6.QtWidgets import QApplication

    dlg = _attr_dialog("a", "b", "c")
    try:
        _move_table_row(dlg._attr_table, 0, 2)
        dlg._attrs_dropped()  # agenda; o drop ainda esta terminando
        QApplication.processEvents()  # drop termina -> aplica
        assert [a["name"] for a in dlg._attrs] == ["b", "c", "a"]
        assert [a["order"] for a in dlg._attrs] == [0, 1, 2]
        assert dlg._attr_table.rowCount() == 3
        assert dlg._attr_table.item(2, 0).text() == "a"
        assert dlg._attr_table.item(2, 1).text() == "A"
    finally:
        dlg.close()


def test_attrs_sync_ignores_stray_row(qapp):
    """Linha estranha/vazia nao apaga specs (nao perde dados)."""
    dlg = _attr_dialog("a", "b")
    try:
        dlg._attr_table.insertRow(2)  # linha vazia, sem UserRole
        dlg._sync_attrs_order_from_list()
        assert [a["name"] for a in dlg._attrs] == ["a", "b"]
        assert [a["order"] for a in dlg._attrs] == [0, 1]
    finally:
        dlg.close()


def test_attrs_remove_renumbers(qapp):
    dlg = _attr_dialog("a", "b", "c")
    try:
        dlg._attr_table.setCurrentCell(1, 0)
        dlg._remove_attr()
        assert [a["name"] for a in dlg._attrs] == ["a", "c"]
        assert [a["order"] for a in dlg._attrs] == [0, 1]
    finally:
        dlg.close()


def test_attr_drag_toggle_defaults_locked(qapp):
    from task_level.presentation.dialogs.task_type_dialog import TaskTypeDialog

    dlg = TaskTypeDialog(None, {"name": "T", "phases": [{"name": "A"}]})
    try:
        assert dlg._attr_drag_toggle.isChecked() is False
        assert dlg._attr_table.dragEnabled() is False
        dlg._attr_drag_toggle.setChecked(True)
        assert dlg._attr_table.dragEnabled() is True
    finally:
        dlg.close()


def test_attr_order_persists_in_list_order(tmp_path, qapp):
    """Salvar mante a ordem da lista (posicao vira order no banco)."""
    from task_level.data import UnitOfWork
    from task_level.presentation.dialogs.task_type_manager_dialog import (
        TaskTypeManagerDialog,
    )

    db = tmp_path / "attr_order.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid,
        "T",
        attributes=[
            {"name": "a", "label": "A", "type": "text"},
            {"name": "b", "label": "B", "type": "text"},
            {"name": "c", "label": "C", "type": "text"},
        ],
    ).id
    mgr = TaskTypeManagerDialog(None, db, pid)
    try:
        payload = mgr._load_payload(tid)
        # simula arrastar A para o fim (como no dialogo)
        attrs = payload["attributes"]
        payload["attributes"] = [attrs[1], attrs[2], attrs[0]]
        mgr._apply_edit(tid, payload)
        with UnitOfWork.open(db) as uow:
            names = [
                a.name
                for a in uow.attribute_definitions.list_by_task_type(tid)
            ]
        assert names == ["b", "c", "a"]
    finally:
        mgr.close()


def test_dialogs_fit_screen_with_growing_content(qapp):
    """Conteudo grande rola em vez de estourar a area util da tela."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QScrollArea

    from task_level.presentation.dialogs.phase_dialog import PhaseDialog

    avail = QGuiApplication.primaryScreen().availableGeometry()
    attrs = [
        {
            "type_id": 1,
            "type_name": "T",
            "name": "nota",
            "label": "Nota",
            "type": "number",
            "options": None,
        }
    ]
    dlg = PhaseDialog(None, {"name": "F"}, type_attrs=attrs)
    try:
        group = dlg._root.add_subgroup({"logic": "OR"})
        for i in range(30):
            group.add_leaf(
                {"type_id": 1, "attr": "nota", "op": "gte", "value": str(i)}
            )
        # comeca com o topo na metade da tela (caso real do bug)
        dlg.move(avail.left() + 50, avail.top() + avail.height() // 2)
        dlg.show()
        qapp.processEvents()
        qapp.processEvents()
        assert dlg.height() <= avail.height()
        # abre grande (conteudo inteiro ou teto da tela), nao minima
        assert dlg.height() > 600
        # inteira visivel: topo e rodape (OK/Cancel) dentro da tela
        assert avail.contains(dlg.frameGeometry())
        scroll = dlg.findChildren(QScrollArea)[0]
        assert scroll.verticalScrollBar().maximum() > 0  # rola de verdade
        assert dlg.data()["enter_conditions"] is not None
    finally:
        dlg.close()


def test_phase_dialog_conditions_roundtrip(qapp):
    from task_level.presentation.dialogs.phase_dialog import PhaseDialog

    attrs = [
        {
            "type_id": 0,
            "type_name": "",
            "name": "nota",
            "label": "Nota",
            "type": "number",
            "options": None,
        }
    ]
    dlg = PhaseDialog(
        None,
        {"name": "Revisao", "enter_conditions": [{"attr": "x", "op": "eq", "value": "1"}]},
        type_attrs=attrs,
    )
    try:
        assert len(dlg._cond_rows) == 1  # preset carregada
        dlg._add_cond_row()
        row = dlg._cond_rows[-1]
        row.set_data({"type_id": 0, "attr": "nota", "op": "gte", "value": "5"})
        conds = dlg.data()["enter_conditions"]
        assert {"attr": "nota", "op": "gte", "value": "5"} in conds
    finally:
        dlg.close()
