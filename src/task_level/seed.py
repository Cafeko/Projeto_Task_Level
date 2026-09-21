"""Seed de demonstracao: projeto + tipos + tasks com referencias (Parte 6)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from task_level.data import UnitOfWork
from task_level.data.database import default_db_path
from task_level.services import ProjectService, TaskService, TaskTypeService


def seed_demo(db_path: str | Path) -> dict[str, Any]:
    """Cria 'Projeto Demo' com Bug + Feature e tasks interligadas."""
    db_path = Path(db_path)
    projects = ProjectService(db_path)
    types = TaskTypeService(db_path)
    tasks = TaskService(db_path)

    project = projects.create("Projeto Demo", "Dados de exemplo gerados pelo seed")

    bug = types.create_type(
        project.id,
        "Bug",
        description="Defeitos reportados",
        color="#d64545",
        attributes=[
            {"name": "sev", "label": "Severidade", "type": "text", "required": True},
            {"name": "ambiente", "label": "Ambiente", "type": "text"},
            {"name": "bloqueado_por", "label": "Bloqueado por", "type": "reference_task"},
        ],
    )
    feature = types.create_type(
        project.id,
        "Feature",
        description="Novas funcionalidades",
        color="#2f9e44",
        attributes=[
            {"name": "prioridade", "label": "Prioridade", "type": "number",
             "required": True},
            {"name": "resumo", "label": "Resumo", "type": "text"},
            {"name": "bug_origem", "label": "Bug de origem",
             "type": "reference_attribute"},
        ],
    )

    b1 = tasks.create_task(
        project.id, bug.id, "Crash ao abrir anexo",
        values={"sev": "critica", "ambiente": "Win11"},
    )
    b2 = tasks.create_task(
        project.id, bug.id, "Typo no rodape",
        values={"sev": "baixa", "bloqueado_por": b1.id},
    )
    with UnitOfWork.open(db_path) as uow:
        sev_def = uow.attribute_definitions.get_by_name(bug.id, "sev")
        assert sev_def is not None and sev_def.id is not None
        sev_attr = uow.task_attributes.get(b1.id, sev_def.id)
    assert sev_attr is not None and sev_attr.id is not None
    f1 = tasks.create_task(
        project.id, feature.id, "Exportar CSV",
        values={
            "prioridade": 1,
            "resumo": "Exportar lista de tasks",
            "bug_origem": (b1.id, sev_attr.id),
        },
    )
    with UnitOfWork.open(db_path) as uow:
        ordered = sorted(
            uow.phases.list_by_task_type(bug.id), key=lambda p: p.order
        )
    for ph in ordered[1:]:  # avanca uma fase por vez ate a final
        tasks.move_phase(b1.id, ph.id)

    return {
        "project_id": project.id,
        "type_ids": [bug.id, feature.id],
        "task_ids": [b1.id, b2.id, f1.id],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed de demonstracao do Task Level")
    parser.add_argument("--db", default=str(default_db_path()))
    parser.add_argument("--reset", action="store_true", help="apaga o db antes do seed")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if args.reset and db_path.exists():
        db_path.unlink()
    result = seed_demo(db_path)
    print(f"Seed OK em {db_path}: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
