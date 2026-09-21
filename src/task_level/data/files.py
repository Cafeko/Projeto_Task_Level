"""Anexos de arquivo: copia gerenciada ao lado do banco.

Layout: `<pasta-do-db>/files/task_<id>/<attr>[_n].ext`.
O banco guarda o caminho absoluto em `task_attributes.value_text`;
o arquivo real e copiado (nao linkado) para sobreviver a mudancas
na origem e entrar no backup.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def attachments_root(db_path: str | Path) -> Path:
    return Path(db_path).parent / "files"


def task_files_dir(db_path: str | Path, task_id: int) -> Path:
    return attachments_root(db_path) / f"task_{task_id}"


def store_attachment(
    db_path: str | Path, task_id: int, attr_name: str, source: str | Path
) -> Path:
    """Copia `source` para a area gerenciada. Retorna o destino absoluto."""
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"arquivo nao encontrado: {source}")
    safe_attr = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in attr_name)
    dest_dir = task_files_dir(db_path, task_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{safe_attr}{src.suffix}"
    counter = 1
    while dest.exists():
        counter += 1
        dest = dest_dir / f"{safe_attr}_{counter}{src.suffix}"
    shutil.copy2(src, dest)
    return dest


def remove_task_files(db_path: str | Path, task_id: int) -> None:
    """Apaga anexos da task (best-effort)."""
    shutil.rmtree(task_files_dir(db_path, task_id), ignore_errors=True)


def remove_file(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def attachment_label(path: str | Path | None) -> str:
    """'relatorio.pdf (12 KB)' ou '(arquivo nao encontrado)' / '(nenhum)'."""
    if not path:
        return "(nenhum)"
    p = Path(path)
    if not p.is_file():
        return f"{p.name} (arquivo nao encontrado)"
    size = p.stat().st_size
    if size < 1024:
        human = f"{size} B"
    elif size < 1024 * 1024:
        human = f"{size / 1024:.0f} KB"
    else:
        human = f"{size / (1024 * 1024):.1f} MB"
    return f"{p.name} ({human})"
