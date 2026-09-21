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
