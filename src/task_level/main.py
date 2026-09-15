"""Entry point da aplicacao (GUI PySide6 desde a Parte 7)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from task_level.data.database import default_db_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Task Level - gerenciador de tarefas")
    parser.add_argument("--db", default=str(default_db_path()), help="caminho do SQLite")
    parser.add_argument("--seed", action="store_true", help="roda o seed demo antes de abrir")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    db_path = Path(args.db)
    if args.seed:
        from task_level.seed import seed_demo

        result = seed_demo(db_path)
        print(f"Seed OK em {db_path}: projeto #{result['project_id']}")

    from task_level.presentation.app import run

    return run(db_path)


if __name__ == "__main__":
    sys.exit(main())
