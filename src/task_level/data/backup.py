"""Backup/restore do SQLite + export JSON do projeto (Parte 10)."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from task_level.data import UnitOfWork


def backups_dir() -> Path:
    return Path.home() / ".task_level" / "backups"


def _backup_files_dir(backup_file: Path) -> Path:
    return backup_file.with_name(backup_file.stem + "_files")


def backup_db(db_path: str | Path, dest_dir: str | Path | None = None) -> Path:
    """Copia o .db com timestamp (+ pasta `files/` de anexos, se houver)."""
    from task_level.data.files import attachments_root

    db_path = Path(db_path)
    dest = Path(dest_dir) if dest_dir else backups_dir()
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target = dest / f"{db_path.stem}_{stamp}.db"
    shutil.copy2(db_path, target)
    src_files = attachments_root(db_path)
    if src_files.is_dir():
        shutil.copytree(src_files, _backup_files_dir(target), dirs_exist_ok=True)
    return target


def restore_db(db_path: str | Path, backup_file: str | Path) -> None:
    """Substitui o .db atual pelo backup indicado (+ anexos, se houver)."""
    from task_level.data.files import attachments_root

    db_path = Path(db_path)
    shutil.copy2(Path(backup_file), db_path)
    backed_files = _backup_files_dir(Path(backup_file))
    current_files = attachments_root(db_path)
    if backed_files.is_dir():
        shutil.rmtree(current_files, ignore_errors=True)
        shutil.copytree(backed_files, current_files)


def export_project_json(db_path: str | Path, project_id: int) -> dict[str, Any]:
    """Dump completo de um projeto (tipos, fases, atributos, tasks, valores)."""
    with UnitOfWork.open(db_path) as uow:
        project = uow.projects.get(project_id)
        if project is None:
            raise ValueError(f"project {project_id} nao encontrado")
        data: dict[str, Any] = {
            "project": {
                "name": project.name,
                "description": project.description,
            },
            "task_types": [],
            "tasks": [],
        }
        defs_by_id: dict[int, dict] = {}
        phase_names: dict[int | None, str | None] = {}
        for t in uow.task_types.list_by_project(project_id):
            assert t.id is not None
            type_phases = uow.phases.list_by_task_type(t.id)
            phases = [asdict(p) for p in type_phases]
            for p in type_phases:
                phase_names[p.id] = p.name
            attr_defs = uow.attribute_definitions.list_by_task_type(t.id)
            for d in attr_defs:
                assert d.id is not None
                defs_by_id[d.id] = {"name": d.name, "type": d.type}
            data["task_types"].append(
                {
                    "name": t.name,
                    "description": t.description,
                    "color": t.color,
                    "icon": t.icon,
                    "order": t.order,
                    "phases": [
                        {k: p[k] for k in ("name", "description", "color", "order",
                                          "is_initial", "is_final", "enter_conditions")
                         if k in p}
                        for p in phases
                    ],
                    "attributes": [
                        {
                            "name": d.name,
                            "label": d.label,
                            "type": d.type,
                            "required": d.required,
                            "default_value": d.default_value,
                            "options": d.options,
                            "order": d.order,
                        }
                        for d in attr_defs
                    ],
                }
            )
        for task in uow.tasks.list_by_project(project_id):
            assert task.id is not None
            values = []
            for v in uow.task_attributes.list_by_task(task.id):
                meta = defs_by_id.get(v.attribute_definition_id, {})
                values.append(
                    {
                        "attribute": meta.get("name"),
                        "type": meta.get("type"),
                        "value": _scalar_value(v),
                    }
                )
            data["tasks"].append(
                {
                    "title": task.title,
                    "description": task.description,
                    "phase": phase_names.get(task.phase_id),
                    "values": values,
                }
            )
        return data


def _scalar_value(attr) -> Any:
    if attr.value_text is not None:
        return attr.value_text
    if attr.value_number is not None:
        return attr.value_number
    if attr.value_boolean is not None:
        return attr.value_boolean
    if attr.value_reference_attribute_id is not None:
        return {
            "task_id": attr.value_reference_task_id,
            "attribute_id": attr.value_reference_attribute_id,
        }
    if attr.value_reference_task_id is not None:
        return {"task_id": attr.value_reference_task_id}
    return None


def write_export(dest: str | Path, data: dict[str, Any]) -> Path:
    dest = Path(dest)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return dest
