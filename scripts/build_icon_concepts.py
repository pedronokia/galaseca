"""Renderiza 3 conceitos de icone lado a lado pra escolha.

Saida: skinvault/assets/icon_concepts.png (preview grid).
Nada gravado em .ico ainda — depois que escolher, atualizar build_icon.py.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

from skinvault.ui import theme as t

SIZE = 256
PAD = 40
OUT = (Path(__file__).resolve().parent.parent
       / "skinvault" / "assets" / "icon_concepts.png")


def _base_frame(p: QPainter, size: int) -> QRectF:
    radius = size * 0.18
    rect = QRectF(0.5, 0.5, size - 1.0, size - 1.0)
    p.setBrush(QBrush(QColor(t.BG_ELEVATED)))
    p.setPen(QPen(QColor(t.BORDER), max(1.0, size / 128.0)))
    p.drawRoundedRect(rect, radius, radius)
    return rect


def concept_dial(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _base_frame(p, size)

    cx = cy = size / 2.0
    outer_r = size * 0.34
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(t.ACCENT), max(2.0, size / 64.0)))
    p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

    # 12 tick marks (4 principais + 8 finos)
    for i in range(12):
        ang = i * (2 * math.pi / 12) - math.pi / 2
        is_main = (i % 3 == 0)
        gap = size * 0.012
        tl = size * (0.055 if is_main else 0.028)
        w = max(2.0, size / (48.0 if is_main else 96.0))
        x1 = cx + (outer_r + gap) * math.cos(ang)
        y1 = cy + (outer_r + gap) * math.sin(ang)
        x2 = cx + (outer_r + gap + tl) * math.cos(ang)
        y2 = cy + (outer_r + gap + tl) * math.sin(ang)
        p.setPen(QPen(QColor(t.ACCENT), w,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # V central como ponteiro
    v = QPainterPath()
    v.moveTo(cx - size * 0.115, cy + size * 0.07)
    v.lineTo(cx, cy - size * 0.15)
    v.lineTo(cx + size * 0.115, cy + size * 0.07)
    p.setPen(QPen(QColor(t.ACCENT), max(3.0, size / 38.0),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.drawPath(v)
    p.end()
    return pix


def concept_diamond(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _base_frame(p, size)

    cx = cy = size / 2.0
    top_y = cy - size * 0.22
    side_y = cy - size * 0.06
    bot_y = cy + size * 0.30
    side_x = size * 0.24
    top_x = size * 0.11

    outline = QPainterPath()
    outline.moveTo(cx - top_x, top_y)
    outline.lineTo(cx + top_x, top_y)
    outline.lineTo(cx + side_x, side_y)
    outline.lineTo(cx, bot_y)
    outline.lineTo(cx - side_x, side_y)
    outline.closeSubpath()
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(t.ACCENT), max(2.8, size / 48.0),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.drawPath(outline)

    p.setPen(QPen(QColor(t.ACCENT), max(1.8, size / 80.0),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.drawLine(QPointF(cx - top_x, top_y), QPointF(cx, bot_y))
    p.drawLine(QPointF(cx + top_x, top_y), QPointF(cx, bot_y))
    p.drawLine(QPointF(cx - side_x, side_y), QPointF(cx + side_x, side_y))
    p.end()
    return pix


def concept_sv_heavy(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    _base_frame(p, size)

    font = QFont("Segoe UI Black")
    font.setBold(True)
    font.setPixelSize(int(size * 0.64))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -size * 0.05)
    p.setFont(font)
    p.setPen(QColor(t.ACCENT))
    p.drawText(QRectF(0, 0, size, size),
               int(Qt.AlignmentFlag.AlignCenter), "SV")

    # Underline accent ("vault swoosh") embaixo da SV
    p.setPen(QPen(QColor(t.ACCENT), max(2.0, size / 64.0),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    y = size * 0.78
    p.drawLine(QPointF(size * 0.30, y), QPointF(size * 0.70, y))
    p.end()
    return pix


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    items = [
        ("vault dial", concept_dial(SIZE)),
        ("diamante facetado", concept_diamond(SIZE)),
        ("SV heavy + swoosh", concept_sv_heavy(SIZE)),
    ]

    label_h = 32
    grid_w = PAD + (SIZE + PAD) * len(items)
    grid_h = PAD + SIZE + label_h + PAD
    grid = QPixmap(grid_w, grid_h)
    grid.fill(QColor(t.BG))
    p = QPainter(grid)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont("Segoe UI")
    font.setPixelSize(16)
    p.setFont(font)
    for i, (name, pix) in enumerate(items):
        x = PAD + i * (SIZE + PAD)
        p.drawPixmap(x, PAD, pix)
        p.setPen(QColor(t.TEXT_MUTED))
        p.drawText(QRectF(x, PAD + SIZE + 4, SIZE, label_h),
                   int(Qt.AlignmentFlag.AlignCenter), name)
    p.end()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    grid.save(str(OUT), "PNG")
    print(f"concepts: {OUT}")
    del app


if __name__ == "__main__":
    main()
