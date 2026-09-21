"""Testes Parte 10: backup/restore + export JSON."""

from task_level.data import UnitOfWork
from task_level.data.backup import backup_db, export_project_json, restore_db, write_export
from task_level.seed import seed_demo
from task_level.services import ProjectService


def test_backup_and_restore_roundtrip(tmp_path):
    db = tmp_path / "b.db"
    seed_demo(db)
    assert len(ProjectService(db).list()) == 1

    dest = tmp_path / "backups"
    backup = backup_db(db, dest)
    assert backup.exists()

    ProjectService(db).create("Extra")
    assert len(ProjectService(db).list()) == 2

    restore_db(db, backup)
    assert len(ProjectService(db).list()) == 1


def test_export_project_json(tmp_path):
    db = tmp_path / "e.db"
    result = seed_demo(db)
    data = export_project_json(db, result["project_id"])
    assert data["project"]["name"] == "Projeto Demo"
    assert len(data["task_types"]) == 2
    assert len(data["tasks"]) == 3
    bug_tasks = [t for t in data["tasks"] if any(v["attribute"] == "sev" for v in t["values"])]
    assert len(bug_tasks) == 2

    out = write_export(tmp_path / "proj.json", data)
    assert out.exists()
    with UnitOfWork.open(db):
        pass  # conexao pos-export integra


def test_export_missing_project_fails(tmp_path):
    db = tmp_path / "x.db"
    seed_demo(db)
    try:
        export_project_json(db, 999)
    except ValueError as e:
        assert "nao encontrado" in str(e)
    else:
        raise AssertionError("esperava ValueError")


def test_backup_and_restore_includes_attachments(tmp_path):
    from task_level.data.files import attachments_root
    from task_level.services import TaskService, TaskTypeService

    db = tmp_path / "f.db"
    pid = ProjectService(db).create("P1").id
    tid = TaskTypeService(db).create_type(
        pid, "T", attributes=[{"name": "doc", "label": "Doc", "type": "file"}]
    ).id
    svc = TaskService(db)
    task = svc.create_task(pid, tid, "T1")
    src = tmp_path / "contrato.txt"
    src.write_text("conteudo", encoding="utf-8")
    svc.set_file_attribute(task.id, "doc", src)

    dest = tmp_path / "backups"
    backup = backup_db(db, dest)
    assert (dest / (backup.stem + "_files")).is_dir()

    svc.clear_attribute(task.id, "doc")  # apaga anexo atual
    assert not any(p.is_file() for p in attachments_root(db).rglob("*"))

    restore_db(db, backup)
    from task_level.data import UnitOfWork as _UoW

    with _UoW.open(db) as uow:
        definition = uow.attribute_definitions.get_by_name(tid, "doc")
        restored = uow.task_attributes.get(task.id, definition.id)
    assert restored is not None and restored.value_text.endswith("doc.txt")
    assert (attachments_root(db) / f"task_{task.id}" / "doc.txt").is_file()
    assert (attachments_root(db) / f"task_{task.id}" / "doc.txt").read_text(
        encoding="utf-8"
    ) == "conteudo"
