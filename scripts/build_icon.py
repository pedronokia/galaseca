"""Gera o icone do app (skinvault/assets/icon.ico).

Design: vault dial (cofre) — circulo com tick marks + V central
como ponteiro. Paleta YouTube: BG_ELEVATED + ACCENT.

PyQt6 nao tem encoder ICO embarcado; monta o container ICO
manualmente a partir de PNGs renderizados nas sizes
16/24/32/48/64/128/256.

Roda 1x na dev; commitar o .ico resultante.
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QBuffer, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

from skinvault.ui import theme as t

OUT = (Path(__file__).resolve().parent.parent
       / "skinvault" / "assets" / "icon.ico")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def render(size: int) -> QPixmap:
    """Vault dial: ring + 12 tick marks + V central."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background rounded square
    radius = size * 0.18
    rect = QRectF(0.5, 0.5, size - 1.0, size - 1.0)
    p.setBrush(QBrush(QColor(t.BG_ELEVATED)))
    p.setPen(QPen(QColor(t.BORDER), max(1.0, size / 128.0)))
    p.drawRoundedRect(rect, radius, radius)

    cx = cy = size / 2.0
    outer_r = size * 0.34

    # Ring
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(t.ACCENT), max(2.0, size / 64.0)))
    p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

    # 12 tick marks (4 principais grossos + 8 finos)
    for i in range(12):
        ang = i * (2 * math.pi / 12) - math.pi / 2
        is_main = (i % 3 == 0)
        gap = size * 0.012
        tick_len = size * (0.055 if is_main else 0.028)
        thick = max(2.0, size / (48.0 if is_main else 96.0))
        x1 = cx + (outer_r + gap) * math.cos(ang)
        y1 = cy + (outer_r + gap) * math.sin(ang)
        x2 = cx + (outer_r + gap + tick_len) * math.cos(ang)
        y2 = cy + (outer_r + gap + tick_len) * math.sin(ang)
        p.setPen(QPen(QColor(t.ACCENT), thick,
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    # V central como ponteiro do dial
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


def _png_bytes(pix: QPixmap) -> bytes:
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return data


def _write_ico(pixmaps: list[QPixmap], out: Path) -> None:
    """Monta o container ICO no padrao Windows (PNG embutido em cada size)."""
    images = [(p.width(), p.height(), _png_bytes(p)) for p in pixmaps]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    dir_entries = b""
    blob = b""
    for w, h, png in images:
        ww = 0 if w >= 256 else w
        hh = 0 if h >= 256 else h
        dir_entries += struct.pack(
            "<BBBBHHII",
            ww, hh, 0, 0, 1, 32, len(png), offset,
        )
        blob += png
        offset += len(png)
    out.write_bytes(header + dir_entries + blob)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pixmaps = [render(s) for s in SIZES]
    _write_ico(pixmaps, OUT)
    print(f"icon: {OUT} ({OUT.stat().st_size} bytes)")
    del app


if __name__ == "__main__":
    main()
