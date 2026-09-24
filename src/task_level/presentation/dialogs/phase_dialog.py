"""Editor de fase (ordem/inicio/fim sao automaticos: posicao na lista)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from task_level.presentation.dialogs.screen_fit import ScreenFitMixin


class _CondGroup(QGroupBox):
    """Um nivel da arvore: combina os filhos com E ou OU.

    Filhos podem ser condicoes-folha (_FilterRow, como antes) ou outros
    _CondGroup aninhados — isto e, uma condicao pode conter condicoes.
    """

    def __init__(
        self,
        type_attrs: list[dict],
        scoped,
        on_leaf_added,
        on_leaf_removed,
        parent: QWidget | None = None,
        removable: bool = True,
        logic: str = "AND",
    ) -> None:
        super().__init__(parent)
        self._type_attrs = type_attrs
        self._scoped = scoped
        self._on_leaf_added = on_leaf_added
        self._on_leaf_removed = on_leaf_removed
        self._removable = removable
        self.children: list = []

        self._logic = QComboBox()
        self._logic.addItem("E — todas valem", "AND")
        self._logic.addItem("OU — basta uma valer", "OR")
        self._logic.setCurrentIndex(0 if logic == "AND" else 1)
        self._logic.currentIndexChanged.connect(self._refresh_title)

        add_cond = QPushButton("+ Condicao")
        add_cond.clicked.connect(lambda _=False: self.add_leaf())
        add_group = QPushButton("+ Grupo")
        add_group.clicked.connect(lambda _=False: self.add_subgroup())
        header = QHBoxLayout()
        header.addWidget(QLabel("Combinar com:"))
        header.addWidget(self._logic, stretch=1)
        header.addWidget(add_cond)
        header.addWidget(add_group)
        if removable:
            rm = QPushButton("X")
            rm.setFixedWidth(32)
            rm.setToolTip("Remover este grupo")
            rm.clicked.connect(self._ask_remove)
            header.addWidget(rm)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(12, 4, 4, 4)
        wrap = QVBoxLayout(self)
        wrap.addLayout(header)
        wrap.addLayout(self._body)
        self._refresh_title()

    # -- construcao ------------------------------------------------------
    def _refresh_title(self) -> None:
        logic = self._logic.currentData()
        if logic == "OR":
            self.setTitle("Grupo OU — basta UMA valer")
        else:
            self.setTitle("Grupo E — TODAS precisam valer")

    @property
    def logic(self) -> str:
        return self._logic.currentData() or "AND"

    def set_logic(self, logic: str) -> None:
        self._logic.setCurrentIndex(1 if logic == "OR" else 0)

    def add_leaf(self, preset: dict | None = None):
        from task_level.presentation.dialogs.filter_dialog import _FilterRow

        row = _FilterRow(self._type_attrs, self.remove_child, self)
        if preset:
            try:
                row.set_data(self._scoped(preset))
            except Exception:
                pass
        self.children.append(row)
        self._body.addWidget(row)
        self._on_leaf_added(row)
        return row

    def add_subgroup(self, node: dict | None = None):
        logic = "AND"
        if isinstance(node, dict) and node.get("logic") in ("AND", "OR"):
            logic = node["logic"]
        sub = _CondGroup(
            self._type_attrs,
            self._scoped,
            self._on_leaf_added,
            self._on_leaf_removed,
            parent=self,
            removable=True,
            logic=logic,
        )
        self.children.append(sub)
        self._body.addWidget(sub)
        if isinstance(node, dict):
            sub.load_node(node)
        return sub

    def load_node(self, node: dict) -> None:
        from task_level.services.filters import is_leaf, is_logic_node

        self.set_logic(node.get("logic", "AND"))
        for rule in node.get("rules", []):
            if is_leaf(rule):
                self.add_leaf(dict(rule))
            elif is_logic_node(rule):
                self.add_subgroup(dict(rule))

    def _ask_remove(self) -> None:
        # remove este grupo do pai (o pai e um _CondGroup ou o dialogo)
        parent = self.parent()
        while parent is not None and not isinstance(parent, _CondGroup):
            parent = parent.parent() if hasattr(parent, "parent") else None
        if isinstance(parent, _CondGroup):
            parent.remove_child(self)
        else:
            # raiz nao e removivel; este ramo so chega aqui p/ grupos com pai
            self.deleteLater()

    def remove_child(self, child) -> None:
        from task_level.presentation.dialogs.filter_dialog import _FilterRow

        if child not in self.children:
            # pode ser folha aninhada mais funda: repassa aos subgrupos
            for c in list(self.children):
                if isinstance(c, _CondGroup):
                    before = len(c.collect_leaves())
                    c.remove_child(child)
                    if len(c.collect_leaves()) != before or child not in c.children:
                        # se removeu algo, sai (o callback ja tratou a folha)
                        return
            return
        self.children.remove(child)
        if isinstance(child, _FilterRow):
            self._on_leaf_removed(child)
        else:
            # subgrupo: desregistra as folhas dele
            for leaf in child.collect_leaves():
                self._on_leaf_removed(leaf)
        child.deleteLater()

    def collect_leaves(self) -> list:
        from task_level.presentation.dialogs.filter_dialog import _FilterRow

        out = []
        for c in self.children:
            if isinstance(c, _FilterRow):
                out.append(c)
            elif isinstance(c, _CondGroup):
                out.extend(c.collect_leaves())
        return out

    def to_node(self) -> dict | None:
        from task_level.presentation.dialogs.filter_dialog import _FilterRow

        rules = []
        for c in self.children:
            if isinstance(c, _FilterRow):
                f = c.data()
                if f is not None:
                    rules.append({"attr": f["attr"], "op": f["op"], "value": f["value"]})
            elif isinstance(c, _CondGroup):
                sub = c.to_node()
                if sub is not None:
                    rules.append(sub)
        if not rules:
            return None
        return {"logic": self.logic, "rules": rules}

    def validate(self) -> str | None:
        """Retorna mensagem de erro ou None se ok."""
        from task_level.presentation.dialogs.filter_dialog import _FilterRow

        if not self.children:
            return "Ha grupo vazio: adicione uma condicao ou remova o grupo."
        for c in self.children:
            if isinstance(c, _FilterRow):
                if c.data() is None:
                    return "Ha condicao incompleta."
            else:
                err = c.validate()
                if err:
                    return err
        return None


class PhaseDialog(ScreenFitMixin, QDialog):
    """Editor de fase com condicoes aninhadas (como antes, mas com E/OU).

    Cada condicao e uma linha atributo/operador/valor (igual ao filtro);
    qualquer grupo pode conter novas condicoes OU novos grupos dentro dele.
    1 condicao sozinha = como antes; aninhar permite (A e B) ou (C), etc.
    Armazenamento: E-plano de folhas -> lista legada; resto -> arvore.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        spec: dict | None = None,
        type_attrs: list[dict] | None = None,
    ) -> None:
        """type_attrs: [{"type_id","type_name","name","label","type","options"}]."""
        super().__init__(parent)
        self.setWindowTitle("Fase")
        self.setSizeGripEnabled(True)
        spec = spec or {}
        self._name = QLineEdit(spec.get("name", ""))
        self._desc = QTextEdit(spec.get("description", ""))
        self._desc.setMaximumHeight(60)
        self._color = QLineEdit(spec.get("color", "#888888"))
        btn_color = QHBoxLayout()
        btn_color.addWidget(self._color)

        pick = QPushButton("Escolher...")
        pick.clicked.connect(self._pick_color)
        btn_color.addWidget(pick)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Nome:", self._name)
        form.addRow("Descricao:", self._desc)
        form.addRow("Cor:", btn_color)

        # -- condicoes de entrada (aninhadas, como o filtro) -----------------
        # Conteudo rolavel: grupos aninhados crescem sem limite e o dialogo
        # nunca passa da area util da tela; botoes ficam fixos no rodape.
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addLayout(form)
        self._type_attrs: list[dict] = list(type_attrs or [])
        content_layout.addWidget(QLabel("Condicoes para entrar (aninhaveis):"))
        hint = QLabel(
            "Cada linha e como antes. Use + Grupo para aninhar: "
            "E exige todas, OU exige uma."
        )
        hint.setWordWrap(True)
        content_layout.addWidget(hint)
        self._cond_rows: list = []  # folhas (compat: testes antigos)

        self._root = _CondGroup(
            self._type_attrs,
            self._scoped_preset,
            self._cond_rows.append,
            self._forget_leaf,
            parent=content,
            removable=False,
            logic="AND",
        )
        content_layout.addWidget(self._root)
        content_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # Aninhar recua para a direita: sem barra horizontal o fundo cortava
        # e nao havia como alcancar (a largura abre ate 95% da tela antes).
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, stretch=1)
        layout.addWidget(buttons)
        self.setMinimumSize(420, 300)

        raw = spec.get("enter_conditions")
        self._load_raw(raw)
        # Abre na altura do conteudo (pouca condicao = janela curta);
        # muita condicao = trava no teto da tela e rola por dentro.
        self._fit_content_to_screen(scroll, 560)

    # -- compat / helpers --------------------------------------------------
    def _forget_leaf(self, row) -> None:
        if row in self._cond_rows:
            self._cond_rows.remove(row)

    def _scoped_preset(self, preset: dict) -> dict:
        """Completa type_id pelo nome (presets salvos so tem attr/op/value)."""
        tid = preset.get("type_id", 0) or 0
        name = preset.get("attr")
        if not tid:
            for a in self._type_attrs:
                if a.get("name") == name:
                    tid = a.get("type_id", 0)
                    break
        return {"type_id": tid, "attr": name, "op": preset.get("op"),
                "value": preset.get("value", "")}

    def _load_raw(self, raw) -> None:
        from task_level.services.filters import is_logic_node

        if not raw:
            return
        if isinstance(raw, list):
            self._root.set_logic("AND")
            for preset in raw:
                if isinstance(preset, dict) and preset.get("attr"):
                    self._root.add_leaf(dict(preset))
                elif isinstance(preset, dict):
                    # preset sem attr (ex: teste legado com attr estranho): mostra mesmo assim
                    self._root.add_leaf(dict(preset))
            return
        if is_logic_node(raw):
            self._root.load_node(dict(raw))

    def _add_cond_row(self, preset: dict | None = None, **_) -> None:
        """Compat (testes antigos): adiciona folha na raiz."""
        self._root.add_leaf(dict(preset) if preset else None)

    def _add_group(self, presets: list[dict] | None = None, **_) -> None:
        """Compat: adiciona subgrupo na raiz (E com as folhas dadas)."""
        sub = self._root.add_subgroup()
        for preset in presets or []:
            sub.add_leaf(dict(preset))

    def _remove_cond_row(self, row) -> None:
        self._root.remove_child(row)

    def _pick_color(self) -> None:
        from PySide6.QtGui import QColor

        color = QColorDialog.getColor(QColor(self._color.text()), self)
        if color.isValid():
            self._color.setText(color.name())

    def accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Validacao", "Nome da fase nao pode ser vazio.")
            return
        # so valida se houver alguma condicao
        if self._root.children:
            err = self._root.validate()
            if err:
                QMessageBox.warning(self, "Validacao", err)
                return
        super().accept()

    def data(self) -> dict:
        node = self._root.to_node()
        storage = None
        if node is not None:
            from task_level.services.filters import is_leaf

            rules = node.get("rules", [])
            if node.get("logic") == "AND" and all(is_leaf(r) for r in rules):
                storage = [dict(r) for r in rules]  # lista legada
            else:
                storage = node
        return {
            "name": self._name.text().strip(),
            "description": self._desc.toPlainText(),
            "color": self._color.text().strip() or "#888888",
            "enter_conditions": storage,
        }

    @classmethod
    def create(
        cls, parent: QWidget | None = None, type_attrs: list[dict] | None = None
    ) -> dict | None:
        dlg = cls(parent, type_attrs=type_attrs)
        return dlg.data() if dlg.exec() else None

    @classmethod
    def edit(
        cls,
        parent: QWidget | None,
        spec: dict,
        type_attrs: list[dict] | None = None,
    ) -> dict | None:
        dlg = cls(parent, spec, type_attrs=type_attrs)
        return dlg.data() if dlg.exec() else None
