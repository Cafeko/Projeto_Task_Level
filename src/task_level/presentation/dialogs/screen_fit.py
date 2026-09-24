"""Padrao p/ dialogs nunca ultrapassarem a area util da tela.

Uso:
    class MeuDialog(ScreenFitMixin, QDialog):
        def __init__(self, ...):
            ...
            self.setSizeGripEnabled(True)
            self._fit_to_screen(560, 480)  # tamanho inicial desejado

O mixin prende o showEvent: cresce ate o conteudo caber (ou ate o
teto da tela) e reposiciona para a janela inteira ficar visivel.
Combine com QScrollArea no conteudo variavel (botoes OK/Cancel fixos
no rodape) para o excesso rolar em vez de cortar.
"""

from __future__ import annotations


class ScreenFitMixin:
    _fit_min_w = 320
    _fit_min_h = 200

    def _available_geometry(self):
        """Area util da tela onde o dialogo vai aparecer (sem taskbar)."""
        try:
            screen = self.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                parent = self.parentWidget()
                if parent is not None:
                    screen = parent.screen()
            except Exception:
                screen = None
        if screen is None:
            try:
                from PySide6.QtGui import QGuiApplication

                screen = QGuiApplication.primaryScreen()
            except Exception:
                screen = None
        if screen is not None:
            try:
                return screen.availableGeometry()
            except Exception:
                return None
        return None

    def _fit_to_screen(self, width: int = 520, height: int = 620) -> None:
        avail = self._available_geometry()
        if avail is None:
            self.resize(width, height)
            return
        max_w = max(self._fit_min_w, int(avail.width() * 0.95))
        max_h = max(self._fit_min_h, int(avail.height() * 0.92))
        self.setMaximumSize(max_w, max_h)
        self.resize(min(width, max_w), min(height, max_h))

    def _fit_content_to_screen(self, scroll, width: int = 560) -> None:
        """Abre o maior possivel para o conteudo inteiro aparecer.

        `scroll` e a QScrollArea do conteudo variavel. Tamanho desejado =
        tamanho do dialogo (sizeHint) trocando a parte da rolagem pelo
        tamanho real do conteudo; botoes e margens entram na conta sem
        chute. A largura nunca encolhe abaixo de `width` (formulario
        respira); a altura respeita o minimo da janela. Sobra cortada no
        teto da tela e rola por dentro.

        A medida final acontece no showEvent (_grow_to_fit_content):
        hints de layouts aninhados so ficam corretas depois que o dialogo
        ativa o layout ao exibir.
        """
        avail = self._available_geometry()
        max_w = (
            max(self._fit_min_w, int(avail.width() * 0.95))
            if avail is not None
            else max(width, 10**6)
        )
        max_h = (
            max(self._fit_min_h, int(avail.height() * 0.92))
            if avail is not None
            else 10**6
        )
        self.setMaximumSize(max_w, max_h)
        try:
            seen = getattr(self, "_fit_scrolls", None) or []
            if scroll not in seen:
                self._fit_scrolls = [*seen, scroll]
        except Exception:
            pass
        try:
            layout = self.layout()
            content = scroll.widget()
            # Layouts aninhados podem relatar hint zerada antes da primeira
            # ativacao (conteudo montado depois do layout): forca o calculo.
            if content is not None and content.layout() is not None:
                content.layout().activate()
            layout.activate()
            dlg_hint = layout.sizeHint()
            scr_hint = scroll.sizeHint()
            content_hint = content.sizeHint()
            want_h = dlg_hint.height() - scr_hint.height() + content_hint.height()
            want_w = dlg_hint.width() - scr_hint.width() + content_hint.width()
        except Exception:
            want_h, want_w = max_h, width
        try:
            min_h = self.minimumHeight()
        except Exception:
            min_h = 0
        w = min(max(width, int(want_w)), max_w)
        h = min(max(int(want_h), min_h, 1), max_h)
        self.resize(w, h)

    def _keep_inside(self, avail) -> None:
        """Garante o dialogo inteiro dentro da area util (move se preciso)."""
        w, h = self.width(), self.height()
        geom = self.frameGeometry()
        if avail.contains(geom):
            return
        geom.moveCenter(avail.center())
        x = max(avail.left(), min(geom.left(), avail.right() - w))
        y = max(avail.top(), min(geom.top(), avail.bottom() - h))
        self.move(x, y)

    def showEvent(self, event) -> None:  # noqa: N802 (assinatura Qt)
        super().showEvent(event)
        avail = self._available_geometry()
        if avail is None:
            return
        w = min(self.width(), avail.width())
        h = min(self.height(), int(avail.height() * 0.92))
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)
        self._keep_inside(avail)
        grew = self._grow_to_fit_content()
        if grew:
            # Crescer empurra para baixo/direita: reposiciona para a
            # janela inteira continuar visivel (topo nao some, rodape
            # com OK/Cancel nao fica fora da tela).
            self._keep_inside(avail)

    def _grow_to_fit_content(self) -> bool:
        """Cresce ate o conteudo caber (ou ate o teto da tela).

        Roda no showEvent, quando as hints dos layouts aninhados ja sao
        validas. So cresce, nunca encolhe (respeita ajuste do usuario e
        o teto). Antes da primeira pintura: sem tremor visivel.
        Retorna True se cresceu (chamador reposiciona).
        """
        scrolls = getattr(self, "_fit_scrolls", None) or []
        if not scrolls:
            return False
        try:
            max_w, max_h = self.maximumWidth(), self.maximumHeight()
            layout = self.layout()
            layout.activate()
            grew = False
            for scroll in scrolls:
                content = scroll.widget()
                if content is None:
                    continue
                if content.layout() is not None:
                    content.layout().activate()
                dlg_hint = layout.sizeHint()
                scr_hint = scroll.sizeHint()
                content_hint = content.sizeHint()
                want_h = (
                    dlg_hint.height() - scr_hint.height() + content_hint.height()
                )
                want_w = (
                    dlg_hint.width() - scr_hint.width() + content_hint.width()
                )
                w, h = self.width(), self.height()
                if want_w > w:
                    w = min(int(want_w), max_w)
                if want_h > h:
                    h = min(int(want_h), max_h)
                if (w, h) != (self.width(), self.height()):
                    self.resize(w, h)
                    grew = True
            return grew
        except Exception:
            return False
