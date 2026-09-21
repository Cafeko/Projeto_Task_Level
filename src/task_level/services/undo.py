"""Desfazer/refazer (Ctrl+Z / Ctrl+Y) — pilhas em memoria por banco (sessao).

Cada mutacao do TaskService empilha {"label", "undo": op, "redo": op}.
Ops sao dicts JSON-safe executados por `TaskService._apply_history_op`,
que ao aplicar uma op de arquivo atualiza os ponteiros de lixeira
dentro da propria op (para a volta funcionar).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


class EmptyHistory(Exception):
    """Nada a desfazer/refazer."""


class UndoManager:
    _managers: dict[str, UndoManager] = {}

    def __init__(self) -> None:
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.suspended = False

    @classmethod
    def for_db(cls, db_path: str | Path) -> UndoManager:
        key = str(db_path)
        manager = cls._managers.get(key)
        if manager is None:
            manager = cls()
            cls._managers[key] = manager
        return manager

    @classmethod
    def reset_db(cls, db_path: str | Path) -> None:
        cls._managers.pop(str(db_path), None)

    @contextmanager
    def hold(self):
        """Enquanto ativo: service nao loga nem empilha (aplica undo/redo)."""
        was = self.suspended
        self.suspended = True
        try:
            yield
        finally:
            self.suspended = was

    def push(
        self,
        label: str,
        undo_op: dict,
        redo_op: dict,
        log: dict | None = None,
    ) -> None:
        if self.suspended:
            return
        entry: dict = {"label": label, "undo": undo_op, "redo": redo_op}
        if log is not None:
            entry["log"] = log
        self.undo_stack.append(entry)
        self.redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo_label(self) -> str:
        return self.undo_stack[-1]["label"] if self.undo_stack else ""

    def redo_label(self) -> str:
        return self.redo_stack[-1]["label"] if self.redo_stack else ""

    def undo(self, svc) -> str:
        """Desfaz a ultima acao. Retorna o rotulo. Levanta EmptyHistory/DomainError."""
        from task_level.domain import DomainError

        if not self.undo_stack:
            raise EmptyHistory("nada a desfazer")
        entry = self.undo_stack.pop()
        try:
            with self.hold():
                svc._apply_history_op(entry["undo"])
        except DomainError:
            self.undo_stack.append(entry)  # devolve: nada mudou
            raise
        # remove do log o que foi desfeito
        if "log" in entry and entry["log"].get("log_id") is not None:
            try:
                svc._delete_log(entry["log"]["log_id"])
            except Exception:
                pass
        entry["redo"] = entry["undo"]  # op mutada ja e o inverso (lixeira etc.)
        self.redo_stack.append(entry)
        return entry["label"]

    def redo(self, svc) -> str:
        from task_level.domain import DomainError

        if not self.redo_stack:
            raise EmptyHistory("nada a refazer")
        entry = self.redo_stack.pop()
        try:
            with self.hold():
                svc._apply_history_op(entry["redo"])
        except DomainError:
            self.redo_stack.append(entry)
            raise
        entry["undo"] = entry["redo"]
        # reinsere no log o que foi refeito
        if "log" in entry:
            try:
                new_id = svc._reinsert_log(entry["log"], entry)
                entry["log"]["log_id"] = new_id
            except Exception:
                pass
        self.undo_stack.append(entry)
        return entry["label"]
