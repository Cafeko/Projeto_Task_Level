"""Helpers visuais para cor/icone de tipos e fases."""

from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPixmap

FALLBACK_COLOR = "#888888"


def normalize_color(color: str | None) -> str:
    """Retorna hex valido ou fallback (nunca quebra com texto invalido)."""
    if not color or not isinstance(color, str):
        return FALLBACK_COLOR
    text = color.strip()
    if QColor.isValidColorName(text):
        return QColor(text).name()
    return FALLBACK_COLOR


def make_color_icon(color: str | None, size: int = 16) -> QIcon:
    """Quadradinho arredondado com a cor (para combo/lista/tree)."""
    pix = QPixmap(size, size)
    pix.fill(QColor("transparent"))
    c = QColor(normalize_color(color))
    # desenha via stylesheet-like: preenche com borda simples usando o proprio pixmap
    from PySide6.QtGui import QBrush, QPainter, QPen

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(c))
    painter.setPen(QPen(c.darker(130), 1))
    painter.drawRoundedRect(1, 1, size - 2, size - 2, 4, 4)
    painter.end()
    return QIcon(pix)


def type_label(name: str, icon: str | None) -> str:
    """Nome com icone prefixado. Icone e texto livre (emoji, letra, etc)."""
    icon = (icon or "").strip()
    name = (name or "").strip() or "?"
    return f"{icon} {name}" if icon else name
