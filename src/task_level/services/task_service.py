"""Task service: CRUD + atributos + fases + validacao de ciclos (Parte 5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from task_level.data import UnitOfWork
from task_level.domain import (
    ActivityEntry,
    AttributeType,
    CircularReferenceError,
    NotFoundError,
    Phase,
    Task,
    TaskAttribute,
    ValidationError,
    parse_currency,
    parse_date,
    task_number,
    utcnow,
)


def _has_value(attr: TaskAttribute, attr_type: str) -> bool:
    if attr_type == AttributeType.TEXT.value:
        return attr.value_text is not None and attr.value_text != ""
    if attr_type == AttributeType.NUMBER.value:
        return attr.value_number is not None
    if attr_type == AttributeType.BOOLEAN.value:
        return attr.value_boolean is not None
    if attr_type == AttributeType.CURRENCY.value:
        return attr.value_number is not None
    if attr_type == AttributeType.DATE.value:
        return attr.value_text is not None and attr.value_text != ""
    if attr_type == AttributeType.FILE.value:
        return attr.value_text is not None and attr.value_text != ""
    if attr_type == AttributeType.SELECT.value:
        return attr.value_text is not None and attr.value_text != ""
    if attr_type == AttributeType.REFERENCE_TASK.value:
        return attr.value_reference_task_id is not None
    if attr_type == AttributeType.REFERENCE_ATTRIBUTE.value:
        return attr.value_reference_attribute_id is not None
    return False


class TaskService:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    # -- historico + desfazer/refazer -----------------------------------------

    def _undo_manager(self):
        from task_level.services.undo import UndoManager

        return UndoManager.for_db(self._db_path)

    def _record(
        self,
        project_id: int,
        action: str,
        task_id: int | None,
        task_title: str,
        summary: str,
        label: str = "",
        undo_op: dict | None = None,
        redo_op: dict | None = None,
    ) -> None:
        """Loga a mudanca e empilha undo/redo (nada faz se suspenso)."""
        manager = self._undo_manager()
        if manager.suspended:
            return
        log: dict | None = None
        undo_json = None
        if undo_op is not None and redo_op is not None:
            log = {
                "project_id": project_id,
                "action": action,
                "task_id": task_id,
                "task_title": task_title,
                "summary": summary,
                "log_id": None,
            }
            manager.push(label or summary, undo_op, redo_op, log=log)
            undo_json = json.dumps(
                {"label": label or summary, "undo": undo_op, "redo": redo_op},
                ensure_ascii=False,
                default=str,
            )
        with UnitOfWork.open(self._db_path) as uow:
            entry = uow.activity.add(
                ActivityEntry(
                    project_id=project_id,
                    action=action,
                    task_id=task_id,
                    task_title=task_title,
                    summary=summary,
                    undo_json=undo_json,
                )
            )
            if log is not None and entry.id is not None:
                log["log_id"] = entry.id

    def _delete_log(self, log_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            uow.conn.execute("DELETE FROM activity_log WHERE id = ?", (log_id,))

    def _reinsert_log(self, log: dict, entry: dict) -> int | None:
        undo_json = json.dumps(
            {"label": entry["label"], "undo": entry["undo"], "redo": entry["redo"]},
            ensure_ascii=False,
            default=str,
        )
        with UnitOfWork.open(self._db_path) as uow:
            new_entry = uow.activity.add(
                ActivityEntry(
                    project_id=log["project_id"],
                    action=log["action"],
                    task_id=log["task_id"],
                    task_title=log["task_title"],
                    summary=log["summary"],
                    undo_json=undo_json,
                )
            )
            return new_entry.id

    @staticmethod
    def _raw_of(def_type: str, row) -> Any:
        """Valor python bruto a partir da linha (p/ snapshots de undo)."""
        if row is None:
            return None
        if def_type in (
            AttributeType.TEXT.value,
            AttributeType.DATE.value,
            AttributeType.FILE.value,
            AttributeType.SELECT.value,
        ):
            return row.value_text
        if def_type in (AttributeType.NUMBER.value, AttributeType.CURRENCY.value):
            return row.value_number
        if def_type == AttributeType.BOOLEAN.value:
            return row.value_boolean
        if def_type == AttributeType.REFERENCE_TASK.value:
            return row.value_reference_task_id
        if def_type == AttributeType.REFERENCE_ATTRIBUTE.value:
            if row.value_reference_attribute_id is None:
                return None
            return [row.value_reference_task_id, row.value_reference_attribute_id]
        return None

    @staticmethod
    def _raw_equal(def_type: str, old: Any, new: Any) -> bool:
        """Compara valores normalizados (None ~ False no booleano, 1 vs 1.0)."""
        if def_type == AttributeType.BOOLEAN.value:
            return bool(old) == bool(new)
        if isinstance(old, float) and isinstance(new, int):
            return old == float(new)
        if isinstance(old, int) and isinstance(new, float):
            return float(old) == new
        if isinstance(old, tuple):
            old = list(old)
        if isinstance(new, tuple):
            new = list(new)
        # texto / data / select: ignora espacos ao redor
        if isinstance(old, str) and isinstance(new, str):
            return old.strip() == new.strip()
        return old == new

    @staticmethod
    def _short_value(def_type: str, raw: Any) -> str:
        if raw is None:
            return "-"
        if def_type == AttributeType.BOOLEAN.value:
            return "sim" if raw else "nao"
        if def_type in (AttributeType.NUMBER.value, AttributeType.CURRENCY.value):
            return str(raw)
        if def_type == AttributeType.FILE.value:
            return Path(str(raw)).name
        if def_type == AttributeType.REFERENCE_TASK.value:
            return f"#{raw}"
        if def_type == AttributeType.REFERENCE_ATTRIBUTE.value:
            return f"#{raw[0]} atributo" if isinstance(raw, list) else str(raw)
        text = str(raw).strip().replace("\n", " ")
        return text if len(text) <= 40 else text[:39] + "…"

    def _seq_of(self, task_id: int) -> int:
        """Numero visivel da task (seq por tipo; fallback: id global)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
        if task is None:
            return task_id
        return task_number(task)

    def _display_value(self, def_type: str, raw: Any) -> str:
        """_short_value com referencias mostrando o numero visivel (#seq)."""
        if def_type == AttributeType.REFERENCE_TASK.value and isinstance(raw, int):
            return f"#{self._seq_of(raw)}"
        if def_type == AttributeType.REFERENCE_ATTRIBUTE.value and isinstance(
            raw, (list, tuple)
        ):
            return f"#{self._seq_of(raw[0])} atributo" if raw else str(raw)
        return self._short_value(def_type, raw)

    def _read_attr_raw(self, task_id: int, attr_name: str):
        """(definition, raw) atuais ou (None, None)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return None, None
            definition = uow.attribute_definitions.get_by_name(
                task.task_type_id, attr_name
            )
            if definition is None or definition.id is None:
                return None, None
            row = uow.task_attributes.get(task_id, definition.id)
            return definition, self._raw_of(definition.type, row)

    def _snapshot_task(self, task_id: int) -> dict:
        """Foto completa da task (linhas brutas, p/ desfazer exclusao)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            conn = uow.conn
            return {
                "task": dict(
                    conn.execute(
                        "SELECT * FROM tasks WHERE id = ?", (task_id,)
                    ).fetchone()
                ),
                "attrs": [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM task_attributes WHERE task_id = ?", (task_id,)
                    ).fetchall()
                ],
                "notes": [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM task_phase_notes WHERE task_id = ?", (task_id,)
                    ).fetchall()
                ],
            }

    def _restore_task(self, snap: dict) -> None:
        """Recria task do snapshot com os mesmos ids (+ arquivos da lixeira)."""
        from task_level.data.files import untrash

        with UnitOfWork.open(self._db_path) as uow:
            conn = uow.conn
            t = snap["task"]
            conn.execute(
                "INSERT INTO tasks (id, project_id, task_type_id, phase_id, title,"
                " description, created_at, updated_at, completed_at, seq)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    t["id"], t["project_id"], t["task_type_id"], t["phase_id"],
                    t["title"], t["description"], t["created_at"], t["updated_at"],
                    t["completed_at"], t.get("seq"),
                ),
            )
            for a in snap.get("attrs", []):
                conn.execute(
                    "INSERT INTO task_attributes (id, task_id, attribute_definition_id,"
                    " value_text, value_number, value_boolean,"
                    " value_reference_task_id, value_reference_attribute_id,"
                    " created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        a["id"], a["task_id"], a["attribute_definition_id"],
                        a["value_text"], a["value_number"], a["value_boolean"],
                        a["value_reference_task_id"],
                        a["value_reference_attribute_id"],
                        a["created_at"], a["updated_at"],
                    ),
                )
            for n in snap.get("notes", []):
                conn.execute(
                    "INSERT INTO task_phase_notes (id, task_id, phase_id, note,"
                    " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        n["id"], n["task_id"], n["phase_id"], n["note"],
                        n["created_at"], n["updated_at"],
                    ),
                )
        for entry in snap.get("files", []):
            untrash(entry.get("trash"), entry.get("path"))

    def _delete_with_snapshot(self, task_id: int) -> dict:
        """Apaga a task (anexos vao p/ lixeira) e devolve snapshot p/ undo."""
        from task_level.data.files import remove_task_files, trash_file

        snap = self._snapshot_task(task_id)
        trash_map = []
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            assert task is not None
            for definition in uow.attribute_definitions.list_by_task_type(
                task.task_type_id
            ):
                if definition.type != AttributeType.FILE.value:
                    continue
                assert definition.id is not None
                row = uow.task_attributes.get(task_id, definition.id)
                if row is not None and row.value_text:
                    trashed = trash_file(self._db_path, row.value_text)
                    trash_map.append({"path": row.value_text, "trash": trashed})
            uow.tasks.delete(task_id)
        remove_task_files(self._db_path, task_id)  # pasta (ja esvaziada)
        snap["files"] = trash_map
        return snap

    def _apply_history_op(self, op: dict) -> None:
        """Executa uma op de undo/redo (com hold ativo: sem log/pilha)."""
        from task_level.data.files import trash_file, untrash

        kind = op.get("k")
        if kind == "set_details":
            with UnitOfWork.open(self._db_path) as uow:
                task = uow.tasks.get(op["task"])
                assert task is not None
                cur = (task.title, task.description)
            self.update_details(op["task"], op["title"], op["description"])
            op["title"], op["description"] = cur
        elif kind == "set_attr":
            _def, cur_raw = self._read_attr_raw(op["task"], op["attr"])
            self.set_attribute(op["task"], op["attr"], op["value"])
            if cur_raw is None:
                op.pop("value", None)
                op["k"] = "clear_attr"
            else:
                op["value"] = cur_raw
        elif kind == "clear_attr":
            _def, cur_raw = self._read_attr_raw(op["task"], op["attr"])
            self.clear_attribute(op["task"], op["attr"])
            if cur_raw is not None:
                op["k"] = "set_attr"
                op["value"] = cur_raw
        elif kind == "set_file":
            _def, cur_raw = self._read_attr_raw(op["task"], op["attr"])
            cur_trash = (
                trash_file(self._db_path, cur_raw)
                if cur_raw and cur_raw != op["path"]
                else None
            )
            untrash(op.get("trash"), op["path"])
            with UnitOfWork.open(self._db_path) as uow:
                task = uow.tasks.get(op["task"])
                assert task is not None
                definition = uow.attribute_definitions.get_by_name(
                    task.task_type_id, op["attr"]
                )
                assert definition is not None and definition.id is not None
                uow.task_attributes.set(
                    TaskAttribute(
                        op["task"], definition.id, value_text=op["path"]
                    ),
                    definition.type,
                )
            if cur_raw is None:
                op["k"] = "clear_file"
                op.pop("path", None)
                op.pop("trash", None)
            else:
                op["path"], op["trash"] = cur_raw, cur_trash
        elif kind == "clear_file":
            _def, cur_raw = self._read_attr_raw(op["task"], op["attr"])
            if cur_raw is None:
                pass  # ja vazio: noop nos dois sentidos
            else:
                cur_trash = trash_file(self._db_path, cur_raw)
                with UnitOfWork.open(self._db_path) as uow:
                    task = uow.tasks.get(op["task"])
                    assert task is not None
                    definition = uow.attribute_definitions.get_by_name(
                        task.task_type_id, op["attr"]
                    )
                    assert definition is not None and definition.id is not None
                    uow.task_attributes.delete(op["task"], definition.id)
                op["k"] = "set_file"
                op["path"], op["trash"] = cur_raw, cur_trash
        elif kind == "move":
            cur_phase = self.get(op["task"]).phase_id
            self.move_phase(op["task"], op["phase"])
            op["phase"] = cur_phase
        elif kind == "delete_task":
            snap = self._delete_with_snapshot(op["task"])
            op["k"] = "restore_task"
            op["snapshot"] = snap
            op.pop("task", None)
        elif kind == "restore_task":
            self._restore_task(op["snapshot"])
            op["k"] = "delete_task"
            op["task"] = op["snapshot"]["task"]["id"]
            op.pop("snapshot", None)
        elif kind == "set_note":
            cur = self.phase_notes(op["task"]).get(op["phase"])
            self.set_phase_note(op["task"], op["phase"], op.get("note") or "")
            op["note"] = cur
        else:
            raise ValidationError(f"operacao de historico desconhecida: {kind!r}")

    # -- criacao/listagem -------------------------------------------------

    def create_task(
        self,
        project_id: int,
        task_type_id: int,
        title: str,
        description: str = "",
        values: dict[str, Any] | None = None,
    ) -> Task:
        with UnitOfWork.open(self._db_path) as uow:
            task_type = uow.task_types.get(task_type_id)
            if task_type is None:
                raise NotFoundError(f"task_type {task_type_id} nao encontrado")
            if task_type.project_id != project_id:
                raise ValidationError("task_type nao pertence ao project informado")
            initial = uow.phases.initial_of_type(task_type_id)
            if initial is None:
                raise ValidationError("task_type sem fase inicial")
            task = uow.tasks.add(
                Task(
                    project_id=project_id,
                    task_type_id=task_type_id,
                    phase_id=initial.id,
                    title=title,
                    description=description,
                )
            )
            assert task.id is not None
            for name, value in (values or {}).items():
                self._set_attribute(uow, task.id, task_type_id, name, value)
            created = task
        self._record(
            project_id,
            "created",
            created.id,
            created.title,
            f"#{task_number(created)} {created.title} criada",
            label=f"criar '{created.title}'",
            undo_op={"k": "delete_task", "task": created.id},
            redo_op={"k": "restore_task", "snapshot": self._snapshot_task(created.id)},
        )
        return created

    def list_by_project(
        self,
        project_id: int,
        task_type_id: int | None = None,
        phase_id: int | None = None,
    ) -> list[Task]:
        with UnitOfWork.open(self._db_path) as uow:
            return uow.tasks.list_by_project(project_id, task_type_id, phase_id)

    def list_filtered(
        self,
        project_id: int,
        task_type_id: int | None,
        filters: list[dict],
    ) -> list[Task]:
        """Tasks do projeto/tipo que casam TODOS os filtros de atributo."""
        from task_level.services.filters import matches_attr

        if not filters:
            return self.list_by_project(project_id, task_type_id)
        with UnitOfWork.open(self._db_path) as uow:
            if task_type_id is not None:
                defs = {
                    d.name: d
                    for d in uow.attribute_definitions.list_by_task_type(task_type_id)
                }
                by_type = {task_type_id: defs}
            else:
                by_type = {}
                for t in uow.task_types.list_by_project(project_id):
                    assert t.id is not None
                    by_type[t.id] = {
                        d.name: d
                        for d in uow.attribute_definitions.list_by_task_type(t.id)
                    }
            result = []
            for task in uow.tasks.list_by_project(project_id, task_type_id):
                assert task.id is not None
                values = {
                    v.attribute_definition_id: v
                    for v in uow.task_attributes.list_by_task(task.id)
                }
                ok = True
                for f in filters:
                    ftype = int(f.get("type_id")) if f.get("type_id") else None
                    definition = None
                    if ftype is not None and ftype in by_type:
                        definition = by_type[ftype].get(f.get("attr", ""))
                    elif task_type_id is not None:
                        definition = by_type.get(task_type_id, {}).get(
                            f.get("attr", "")
                        )
                    if definition is None or definition.id is None:
                        ok = False
                        break
                    if not matches_attr(
                        definition,
                        values.get(definition.id),
                        f.get("op", ""),
                        str(f.get("value", "")),
                    ):
                        ok = False
                        break
                if ok:
                    result.append(task)
            return result

    def get(self, task_id: int) -> Task:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
        if task is None:
            raise NotFoundError(f"task {task_id} nao encontrada")
        return task

    def delete(self, task_id: int) -> None:
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            project_id, title = task.project_id, task.title
            number = task_number(task)
        snap = self._delete_with_snapshot(task_id)
        self._record(
            project_id,
            "deleted",
            None,
            title,
            f"#{number} {title} excluida",
            label=f"excluir '{title}'",
            undo_op={"k": "restore_task", "snapshot": snap},
            redo_op={"k": "delete_task", "task": task_id},
        )

    def resolve_reference_attribute(
        self, task_id: int, attribute_name: str
    ) -> tuple[int, int] | None:
        """Resolve (task_id, attribute_id-valor) para o atributo `attribute_name`.

        Retorna None se a task nao tem definicao com esse nome ou se ainda
        nao ha valor preenchido. Usado pelo modo "atributo fixo" do form.
        """
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                return None
            definition = uow.attribute_definitions.get_by_name(
                task.task_type_id, attribute_name
            )
            if definition is None or definition.id is None:
                return None
            value = uow.task_attributes.get(task_id, definition.id)
            if value is None or value.id is None:
                return None
            return (task_id, value.id)

    def update_details(self, task_id: int, title: str, description: str = "") -> Task:
        """Atualiza titulo/descricao (usado pelo dialog de edicao - Parte 9)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            old = (task.title, task.description)
            project_id = task.project_id
            number = task_number(task)
            task.title = title
            task.description = description
            task.updated_at = utcnow()
            uow.tasks.update(task)
        if old != (title, description):
            details: list[str] = []
            if old[0] != title:
                s_old = self._short_value("text", old[0])
                s_new = self._short_value("text", title)
                details.append(f"titulo '{s_old}' → '{s_new}'")
            if old[1] != description:
                if not old[1] and description:
                    s_new = self._short_value("text", description)
                    details.append(f"descricao definida: '{s_new}'")
                elif old[1] and not description:
                    details.append("descricao removida")
                else:
                    s_old = self._short_value("text", old[1])
                    s_new = self._short_value("text", description)
                    details.append(f"descricao '{s_old}' → '{s_new}'")
            self._record(
                project_id,
                "updated",
                task_id,
                title,
                f"#{number} editada: " + ", ".join(details) if details else f"#{number} editada",
                label=f"editar '{title}'",
                undo_op={
                    "k": "set_details", "task": task_id,
                    "title": old[0], "description": old[1],
                },
                redo_op={
                    "k": "set_details", "task": task_id,
                    "title": title, "description": description,
                },
            )
        return task

    def clear_attribute(self, task_id: int, attr_name: str) -> None:
        """Remove o valor de um atributo (anexo vai p/ lixeira se for arquivo)."""
        from task_level.data.files import trash_file

        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            definition = uow.attribute_definitions.get_by_name(
                task.task_type_id, attr_name
            )
            if definition is None:
                raise NotFoundError(f"atributo '{attr_name}' nao existe neste tipo")
            assert definition.id is not None
            project_id = task.project_id
            number = task_number(task)
            existing = uow.task_attributes.get(task_id, definition.id)
            if existing is None:
                return  # nada a fazer
            old_raw = self._raw_of(definition.type, existing)
            old_trash = None
            if definition.type == AttributeType.FILE.value:
                old_trash = trash_file(self._db_path, existing.value_text)
            uow.task_attributes.delete(task_id, definition.id)
        short = self._display_value(definition.type, old_raw)
        if definition.type == AttributeType.FILE.value:
            undo_op: dict = {
                "k": "set_file", "task": task_id, "attr": attr_name,
                "path": old_raw, "trash": old_trash,
            }
            redo_op = {"k": "clear_file", "task": task_id, "attr": attr_name}
        else:
            undo_op = {
                "k": "set_attr", "task": task_id, "attr": attr_name,
                "value": old_raw,
            }
            redo_op = {"k": "clear_attr", "task": task_id, "attr": attr_name}
        self._record(
            project_id,
            "attribute",
            task_id,
            task.title,
            f"#{number} '{definition.label}' removido (era {short})",
            label=f"limpar '{definition.label}'",
            undo_op=undo_op,
            redo_op=redo_op,
        )

    def phase_notes(self, task_id: int) -> dict[int, str]:
        """Observacoes da task por fase: {phase_id: note} (so as preenchidas)."""
        with UnitOfWork.open(self._db_path) as uow:
            if uow.tasks.get(task_id) is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            return {n.phase_id: n.note for n in uow.phase_notes.list_by_task(task_id)}

    def set_phase_note(self, task_id: int, phase_id: int, note: str) -> None:
        """Salva a observacao da task na fase (vazia = apaga)."""
        from task_level.domain import TaskPhaseNote

        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            phase = uow.phases.get(phase_id)
            if phase is None:
                raise NotFoundError(f"phase {phase_id} nao encontrada")
            if phase.task_type_id != task.task_type_id:
                raise ValidationError("phase pertence a outro task_type")
            old = uow.phase_notes.get(task_id, phase_id)
            old_note = old.note if old else None
            project_id, title, phase_name = task.project_id, task.title, phase.name
            number = task_number(task)
            if not note.strip():
                uow.phase_notes.delete(task_id, phase_id)
            else:
                uow.phase_notes.set(TaskPhaseNote(task_id, phase_id, note.strip()))
        new_note = note.strip() or None
        if old_note != new_note:
            shown = (new_note[:60] + "…") if new_note and len(new_note) > 60 else (
                new_note or "apagada"
            )
            self._record(
                project_id,
                "note",
                task_id,
                title,
                f"#{number} observacao em '{phase_name}': {shown}",
                label=f"observacao em '{phase_name}'",
                undo_op={
                    "k": "set_note", "task": task_id, "phase": phase_id,
                    "note": old_note,
                },
                redo_op={
                    "k": "set_note", "task": task_id, "phase": phase_id,
                    "note": new_note,
                },
            )

    def set_file_attribute(
        self, task_id: int, attr_name: str, source: str | Path
    ) -> TaskAttribute:
        """Anexa arquivo: copia p/ area gerenciada e salva o caminho."""
        from task_level.data.files import store_attachment, trash_file

        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            definition = uow.attribute_definitions.get_by_name(
                task.task_type_id, attr_name
            )
            if definition is None:
                raise NotFoundError(f"atributo '{attr_name}' nao existe neste tipo")
            if definition.type != AttributeType.FILE.value:
                raise ValidationError(f"atributo '{attr_name}' nao e de arquivo")
            assert definition.id is not None
            src = Path(source)
            if not src.is_file():
                raise NotFoundError(f"arquivo nao encontrado: {source}")
            assert task.id is not None
            dest = store_attachment(self._db_path, task.id, attr_name, src)
            old = uow.task_attributes.get(task.id, definition.id)
            old_path = old.value_text if old else None
            old_trash = None
            attr = self._build_attribute(
                uow, task.id, definition.id, definition.type, str(dest)
            )
            saved = uow.task_attributes.set(attr, definition.type)
            if old_path and old_path != str(dest):
                old_trash = trash_file(self._db_path, old_path)
            project_id, title, label = task.project_id, task.title, definition.label
            number = task_number(task)
        if old_path is None:
            undo_op: dict = {"k": "clear_file", "task": task_id, "attr": attr_name}
        else:
            undo_op = {
                "k": "set_file", "task": task_id, "attr": attr_name,
                "path": old_path, "trash": old_trash,
            }
        self._record(
            project_id,
            "attribute",
            task_id,
            title,
            f"#{number} '{label}': anexo {Path(str(dest)).name}",
            label=f"anexar em '{label}'",
            undo_op=undo_op,
            redo_op={
                "k": "set_file", "task": task_id, "attr": attr_name,
                "path": str(dest), "trash": None,
            },
        )
        return saved

    # -- atributos ----------------------------------------------------------

    def set_attribute(self, task_id: int, attr_name: str, value: Any) -> TaskAttribute:
        definition, old_raw = self._read_attr_raw(task_id, attr_name)
        if definition is None:
            with UnitOfWork.open(self._db_path) as uow:
                task = uow.tasks.get(task_id)
                if task is None:
                    raise NotFoundError(f"task {task_id} nao encontrada")
            raise NotFoundError(f"atributo '{attr_name}' nao existe neste tipo")
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            assert task is not None
            assert definition.id is not None
            built = self._build_attribute(
                uow, task_id, definition.id, definition.type, value
            )
            new_raw = self._raw_of(definition.type, built)
            if self._raw_equal(definition.type, old_raw, new_raw):
                old_row = uow.task_attributes.get(task_id, definition.id)
                return old_row if old_row is not None else built
            saved = uow.task_attributes.set(built, definition.type)
            project_id, title = task.project_id, task.title
            number = task_number(task)
        short_old = self._display_value(definition.type, old_raw)
        short_new = self._display_value(definition.type, value)
        if old_raw is None:
            undo_op: dict = {"k": "clear_attr", "task": task_id, "attr": attr_name}
        else:
            undo_op = {
                "k": "set_attr", "task": task_id, "attr": attr_name,
                "value": old_raw,
            }
        self._record(
            project_id,
            "attribute",
            task_id,
            title,
            f"#{number} '{definition.label}': {short_old} → {short_new}",
            label=f"editar '{definition.label}'",
            undo_op=undo_op,
            redo_op={
                "k": "set_attr", "task": task_id, "attr": attr_name,
                "value": value,
            },
        )
        return saved

    def _set_attribute(
        self,
        uow: UnitOfWork,
        task_id: int,
        task_type_id: int,
        attr_name: str,
        value: Any,
    ) -> TaskAttribute:
        definition = uow.attribute_definitions.get_by_name(task_type_id, attr_name)
        if definition is None:
            raise NotFoundError(f"atributo '{attr_name}' nao existe neste tipo")
        assert definition.id is not None
        attr = self._build_attribute(
            uow, task_id, definition.id, definition.type, value
        )
        return uow.task_attributes.set(attr, definition.type)

    def _build_attribute(
        self,
        uow: UnitOfWork,
        task_id: int,
        definition_id: int,
        attr_type: str,
        value: Any,
    ) -> TaskAttribute:
        if attr_type == AttributeType.TEXT.value:
            return TaskAttribute(task_id, definition_id, value_text=str(value))
        if attr_type == AttributeType.NUMBER.value:
            try:
                number = float(value)
            except (TypeError, ValueError) as e:
                raise ValidationError(f"valor numerico invalido: {value!r}") from e
            return TaskAttribute(task_id, definition_id, value_number=number)
        if attr_type == AttributeType.BOOLEAN.value:
            if not isinstance(value, bool):
                raise ValidationError(f"valor booleano invalido: {value!r}")
            return TaskAttribute(task_id, definition_id, value_boolean=value)
        if attr_type == AttributeType.CURRENCY.value:
            try:
                number = (
                    float(value) if isinstance(value, (int, float)) else parse_currency(str(value))
                )
            except ValidationError as e:
                raise ValidationError(f"valor em dinheiro invalido: {value!r}") from e
            return TaskAttribute(task_id, definition_id, value_number=number)
        if attr_type == AttributeType.DATE.value:
            try:
                iso = parse_date(str(value))
            except ValidationError as e:
                raise ValidationError(f"data invalida: {value!r}") from e
            return TaskAttribute(task_id, definition_id, value_text=iso)
        if attr_type == AttributeType.FILE.value:
            text = str(value).strip()
            if not text:
                raise ValidationError("arquivo vazio")
            return TaskAttribute(task_id, definition_id, value_text=text)
        if attr_type == AttributeType.SELECT.value:
            text = str(value).strip()
            definition = uow.attribute_definitions.get(definition_id)
            allowed = definition.options if definition and definition.options else []
            if text not in allowed:
                raise ValidationError(f"opcao invalida: {value!r} (permitidas: {allowed})")
            return TaskAttribute(task_id, definition_id, value_text=text)
        if attr_type == AttributeType.REFERENCE_TASK.value:
            ref_id = int(value)
            origin = uow.tasks.get(task_id)
            target = uow.tasks.get(ref_id)
            if target is None:
                raise NotFoundError(f"task referenciada {ref_id} nao encontrada")
            if origin is not None and target.project_id != origin.project_id:
                raise ValidationError("referencia deve ser para task do mesmo projeto")
            self._check_ref_task_config(uow, definition_id, target)
            self._reject_cycle(uow, task_id, ref_id)
            return TaskAttribute(
                task_id, definition_id, value_reference_task_id=ref_id
            )
        if attr_type == AttributeType.REFERENCE_ATTRIBUTE.value:
            ref_task_id, ref_attr_id = self._parse_attr_reference(value)
            target = uow.task_attributes.get_by_id(ref_attr_id)
            if target is None:
                raise NotFoundError(f"atributo referenciado {ref_attr_id} nao existe")
            if target.task_id != ref_task_id:
                raise ValidationError("atributo referenciado nao pertence a task indicada")
            origin = uow.tasks.get(task_id)
            target_task = uow.tasks.get(ref_task_id)
            if target_task is None:
                raise NotFoundError(f"task referenciada {ref_task_id} nao encontrada")
            if origin is not None and target_task.project_id != origin.project_id:
                raise ValidationError("referencia deve ser para task do mesmo projeto")
            self._check_ref_attr_config(uow, definition_id, target_task, target)
            self._reject_cycle(uow, task_id, ref_task_id)
            return TaskAttribute(
                task_id,
                definition_id,
                value_reference_task_id=ref_task_id,
                value_reference_attribute_id=ref_attr_id,
            )
        raise ValidationError(f"tipo de atributo desconhecido: {attr_type}")

    @staticmethod
    def _parse_attr_reference(value: Any) -> tuple[int, int]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return int(value[0]), int(value[1])
        if isinstance(value, dict) and "task_id" in value and "attribute_id" in value:
            return int(value["task_id"]), int(value["attribute_id"])
        raise ValidationError(
            "referencia de atributo: esperado (task_id, attribute_id) ou "
            "{task_id, attribute_id}"
        )

    @staticmethod
    def _field_config(uow: UnitOfWork, definition_id: int) -> dict:
        definition = uow.attribute_definitions.get(definition_id)
        if definition is None or not isinstance(definition.reference_config, dict):
            return {}
        return definition.reference_config

    @staticmethod
    def _check_ref_task_config(uow: UnitOfWork, definition_id: int, target) -> None:
        """reference_task aceita qualquer tipo do projeto, salvo filtro configurado."""
        allowed = TaskService._field_config(uow, definition_id).get("target_type_id")
        if allowed is not None and target.task_type_id != allowed:
            raise ValidationError("referencia fora do tipo permitido neste atributo")

    @staticmethod
    def _check_ref_attr_config(
        uow: UnitOfWork, definition_id: int, target_task, target_value
    ) -> None:
        """reference_attribute com atributo fixo: o alvo tem que ser aquele atributo."""
        config = TaskService._field_config(uow, definition_id)
        wanted = config.get("attribute_name")
        if wanted:
            target_def = uow.attribute_definitions.get(
                target_value.attribute_definition_id
            )
            if target_def is None or target_def.name != wanted:
                raise ValidationError(
                    f"este atributo so referencia '{wanted}' (alvo e outro atributo)"
                )
        allowed = config.get("target_type_id")
        if allowed is not None and target_task.task_type_id != allowed:
            raise ValidationError("referencia fora do tipo permitido neste atributo")

    # -- ciclos ---------------------------------------------------------------

    def _reject_cycle(self, uow: UnitOfWork, task_id: int, ref_task_id: int) -> None:
        if ref_task_id == task_id or self._reaches(uow, ref_task_id, task_id):
            raise CircularReferenceError("referencia criaria ciclo entre tasks")

    def _reaches(self, uow: UnitOfWork, start_id: int, goal_id: int) -> bool:
        """DFS: start_id alcanca goal_id via referencias existentes?"""
        visited: set[int] = set()
        stack = [start_id]
        while stack:
            current = stack.pop()
            if current == goal_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(uow.task_attributes.referenced_task_ids(current) - visited)
        return False

    # -- fases ------------------------------------------------------------------

    # -- transicoes de fase (PONTO UNICO) ---------------------------------------
    #
    # Toda mudanca de fase passa por `check_move` + `move_phase`, e toda UI
    # consulta `neighbors` (destinos) + `transition_block` (motivo, p/ tooltip).
    # Condicoes de entrada vivem em `Phase.enter_conditions` e sao avaliadas
    # em `_check_conditions`.

    def neighbors(self, task_id: int) -> tuple[Phase | None, Phase | None]:
        """(fase anterior, proxima fase) na ordem das fases. None nas pontas."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            ordered = sorted(
                uow.phases.list_by_task_type(task.task_type_id), key=lambda p: p.order
            )
            ids = [p.id for p in ordered]
            if task.phase_id not in ids:
                return (None, None)
            pos = ids.index(task.phase_id)
            prev = ordered[pos - 1] if pos > 0 else None
            nxt = ordered[pos + 1] if pos < len(ordered) - 1 else None
            return (prev, nxt)

    def check_move(self, task_id: int, phase_id: int) -> None:
        """Valida uma transicao completa (vizinho, condicoes, obrigatorios)."""
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} nao encontrada")
            phase = uow.phases.get(phase_id)
            if phase is None:
                raise NotFoundError(f"phase {phase_id} nao encontrada")
            if phase.task_type_id != task.task_type_id:
                raise ValidationError("phase pertence a outro task_type")
            if phase_id == task.phase_id:
                return
            self._require_neighbor(uow, task, phase_id)
            self._check_conditions(uow, task, phase)
            if phase.is_final:
                self._require_required_attributes(uow, task)

    def transition_block(self, task_id: int, phase_id: int) -> str | None:
        """Motivo do bloqueio (p/ desabilitar botao com tooltip) ou None se livre."""
        from task_level.domain import DomainError

        try:
            self.check_move(task_id, phase_id)
        except DomainError as e:
            return str(e)
        return None

    @staticmethod
    def _check_conditions(uow: UnitOfWork, task: Task, phase: Phase) -> None:
        """Avalia a arvore AND/OR de entrada (grupos: E dentro, OU entre)."""
        from task_level.services.filters import (
            describe_tree,
            evaluate_tree,
            is_leaf,
            matches_attr,
            normalize_conditions,
            op_label,
        )

        raw = phase.enter_conditions
        if not raw:
            return
        tree = normalize_conditions(raw)
        if tree is None:
            return
        assert task.id is not None
        definitions = {
            d.name: d for d in uow.attribute_definitions.list_by_task_type(
                task.task_type_id
            )
        }
        values = {
            v.attribute_definition_id: v
            for v in uow.task_attributes.list_by_task(task.id)
        }

        def _match(cond: dict) -> bool:
            name = cond.get("attr", "")
            definition = definitions.get(name)
            if definition is None or definition.id is None:
                return False
            value = values.get(definition.id)
            return matches_attr(
                definition, value, cond.get("op", ""), str(cond.get("value", ""))
            )

        # atributo removido: bloqueia com aviso claro (vale p/ qualquer ramo)
        missing: list[str] = []

        def _collect(node: dict) -> None:
            if is_leaf(node):
                if node.get("attr", "") not in definitions:
                    missing.append(str(node.get("attr", "")))
                return
            for r in node.get("rules", []):
                _collect(r)

        _collect(tree)
        if missing:
            raise ValidationError(
                f"para entrar em '{phase.name}': atributo '{missing[0]}' nao existe mais"
            )
        if evaluate_tree(tree, _match):
            return

        def _leaf_text(cond: dict) -> str:
            definition = definitions.get(cond.get("attr", ""))
            if definition is None:
                return f"'{cond.get('attr', '')}' ?"
            label = op_label(definition.type, cond.get("op", ""))
            want = f" {cond.get('value', '')}" if cond.get("value") else ""
            return f"'{definition.label}' {label}{want}"

        detail = describe_tree(tree, _leaf_text)
        raise ValidationError(f"para entrar em '{phase.name}': precisa {detail}")

    def move_phase(self, task_id: int, phase_id: int) -> Task:
        with UnitOfWork.open(self._db_path) as uow:
            before = uow.tasks.get(task_id)
            old_phase_id = before.phase_id if before else None
            names = {p.id: p.name for p in (
                uow.phases.list_by_task_type(before.task_type_id) if before else []
            )}
        self.check_move(task_id, phase_id)  # valida tudo antes de aplicar
        with UnitOfWork.open(self._db_path) as uow:
            task = uow.tasks.get(task_id)
            assert task is not None
            phase = uow.phases.get(phase_id)
            assert phase is not None
            if phase_id == task.phase_id:
                return task  # ja esta nela: nada a fazer
            if phase.is_final:
                task.completed_at = utcnow()
            else:
                task.completed_at = None
            task.phase_id = phase_id
            task.updated_at = utcnow()
            uow.tasks.update(task)
            project_id, title = task.project_id, task.title
            number = task_number(task)
        if old_phase_id != phase_id:
            undo: dict | None = (
                {"k": "move", "task": task_id, "phase": old_phase_id}
                if old_phase_id is not None
                else None
            )
            redo: dict | None = {"k": "move", "task": task_id, "phase": phase_id}
            self._record(
                project_id,
                "moved",
                task_id,
                title,
                f"#{number} fase {names.get(old_phase_id, '?')} → "
                f"{names.get(phase_id, '?')}",
                label=f"mover '{title}'",
                undo_op=undo,
                redo_op=redo,
            )
        return task

    @staticmethod
    def _require_neighbor(uow: UnitOfWork, task: Task, phase_id: int) -> None:
        """So permite avancar ou voltar uma fase por vez (pela ordem das fases)."""
        ordered = sorted(
            uow.phases.list_by_task_type(task.task_type_id), key=lambda p: p.order
        )
        ids = [p.id for p in ordered]
        if task.phase_id not in ids or phase_id not in ids:
            return  # sem fase atual conhecida: permite posicionar
        if abs(ids.index(phase_id) - ids.index(task.phase_id)) != 1:
            raise ValidationError("so e possivel avancar ou voltar uma fase por vez")

    def _require_required_attributes(self, uow: UnitOfWork, task: Task) -> None:
        assert task.id is not None
        missing: list[str] = []
        for definition in uow.attribute_definitions.list_by_task_type(task.task_type_id):
            if not definition.required:
                continue
            assert definition.id is not None
            attr = uow.task_attributes.get(task.id, definition.id)
            if attr is None or not _has_value(attr, definition.type):
                missing.append(definition.label)
        if missing:
            raise ValidationError(
                "atributos obrigatorios sem valor: " + ", ".join(missing)
            )
