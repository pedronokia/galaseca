"""Animacao de shimmer compartilhada (QPainter puro).

Cards fantasma (SkeletonTile) e graficos em loading sao DEZENAS; um
QTimer por widget custaria caro e dessincronizaria as faixas de brilho.
Este modulo concentra UM QTimer (fase 0..1) e o conjunto de widgets
registrados -- o repaint de todos sai do mesmo tick, e o timer SO' roda
enquanto existe pelo menos um widget registrado.

O brilho respeita o Accent Color (paleta configuravel desde a Etapa 2):
a faixa usa ACCENT com alpha baixo. Com o controller parado (sem widget
registrado -- ex.: testes offscreen sem show()), os widgets pintam o
esqueleto estatico e nenhum timer fica preso.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRect, QTimer, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)

from skinvault.ui import theme as t


class ShimmerController:
    """Um unico QTimer animando a fase de shimmer de todos os widgets.

    O widget se registra quando vai desenhar brilho (apareceu na tela) e
    se desregistra quando para (escondeu, saiu do loading). O timer e'
    iniciado/parado pelo proprio fluxo de registro: sem widgets, nao ha'
    o que animar.

    O controller e' objeto Python puro, nao QObject. Um QObject de modulo
    morreria junto com o QApplication quando ele for destruido (testes
    destroem o app entre rodadas, e o PyQt deleta o C++ de todos os
    QObjects do thread) -- ai' o proximo register explodiria com "wrapped
    C/C++ object has been deleted". Aqui o QTimer e' criado sob demanda no
    primeiro register e recriado se o C++ dele morreu (app novo).
    """

    INTERVAL_MS = 80
    STEP = 0.04

    def __init__(self) -> None:
        self._widgets: set = set()
        self._phase = 0.0
        self._timer: QTimer | None = None

    def _ensure_timer(self) -> QTimer:
        timer = self._timer
        if timer is not None:
            try:
                timer.isActive()
                return timer
            except RuntimeError:
                # QTimer C++ morreu com um app destruido (testes): recria.
                # Os widgets da rodada anterior morreram junto -- descarta.
                self._widgets.clear()
                self._timer = None
        timer = QTimer()
        timer.setInterval(self.INTERVAL_MS)
        timer.timeout.connect(self._tick)
        self._timer = timer
        return timer

    def register(self, widget) -> None:
        """Passa a animar este widget (chama update() a cada tick)."""
        timer = self._ensure_timer()
        self._widgets.add(widget)
        if not timer.isActive():
            timer.start()

    def unregister(self, widget) -> None:
        self._widgets.discard(widget)
        if not self._widgets:
            self._stop()

    def _stop(self) -> None:
        timer = self._timer
        if timer is None:
            return
        try:
            if timer.isActive():
                timer.stop()
        except RuntimeError:
            self._timer = None

    def is_animating(self, widget) -> bool:
        if widget not in self._widgets:
            return False
        timer = self._timer
        if timer is None:
            return False
        try:
            return timer.isActive()
        except RuntimeError:
            return False

    def is_running(self) -> bool:
        timer = self._timer
        if timer is None:
            return False
        try:
            return timer.isActive()
        except RuntimeError:
            return False

    def registered_count(self) -> int:
        return len(self._widgets)

    def clear(self) -> None:
        """Desregistra tudo e para o timer (teardown de testes, sair)."""
        self._widgets.clear()
        self._stop()

    def phase(self) -> float:
        return self._phase

    def _tick(self) -> None:
        self._phase = (self._phase + self.STEP) % 1.0
        for w in list(self._widgets):
            try:
                w.update()
            except RuntimeError:
                # Widget destruido apos o C++ ter sido deletado: o proximo
                # tick so' anima quem existe.
                self._widgets.discard(w)
        if not self._widgets:
            self._stop()


SHIMMER = ShimmerController()


def paint_band(p: QPainter, w: int, h: int,
               phase: float | None = None) -> None:
    """Faixa de brilho accent deslizando pela area inteira.

    E' o que da' a ilusao de movimento ao esqueleto: um gradiente accent
    translucido varrendo a largura. Com `phase` fixo (controller parado)
    a faixa estaciona -- os callers so' chamam isto quando `is_animating`.
    """
    phase = SHIMMER.phase() if phase is None else phase
    band_w = max(36.0, w * 0.32)
    x0 = -band_w + phase * (w + band_w)
    grad = QLinearGradient(x0, 0, x0 + band_w, 0)
    c = QColor(t.ACCENT)
    c0 = QColor(c)
    c0.setAlpha(0)
    cmid = QColor(c)
    cmid.setAlpha(40)
    c2 = QColor(c)
    c2.setAlpha(0)
    grad.setColorAt(0.0, c0)
    grad.setColorAt(0.5, cmid)
    grad.setColorAt(1.0, c2)
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRect(QRect(0, 0, w, h))
    p.restore()


def _skeleton_points(x: float, y: float, w: float, h: float,
                     seed: float) -> list[QPointF]:
    """7 pontos pseudo-aleatorios DETERMINISTICOS (sin de `seed`).

    Determinismo importa: dois repaints do mesmo estado tem que desenhar
    o mesmo esqueleto, ou o teste de luminancia piscaria. O `seed` deixa
    cada widget (ou area do mesmo grafico) com uma forma diferente.
    """
    n = 7
    pts = []
    for i in range(n):
        px = x + w * i / (n - 1)
        onda = math.sin(seed + i * 1.9) + math.sin(seed * 2.0 + i * 3.1)
        frac = 0.28 + 0.44 * (0.5 + 0.5 * onda / 2.0)
        pts.append(QPointF(px, y + h * max(0.0, min(1.0, frac))))
    return pts


def paint_skeleton_line(p: QPainter, x: float, y: float, w: float,
                        h: float, seed: float = 0.0) -> None:
    """Esqueleto de LINHA (fill + traco) dentro do retangulo dado.

    Forma que os graficos em loading ocupam: um poligono SURFACE_HOV sob
    um traco SURFACE_PRESSED, mimetizando a linha de preco com a area
    preenchida por baixo.
    """
    pts = _skeleton_points(x, y, w, h, seed)
    poly = QPolygonF(
        pts + [QPointF(pts[-1].x(), y + h), QPointF(pts[0].x(), y + h)])
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t.SURFACE_HOV))
    p.drawPolygon(poly)
    pen = QPen(QColor(t.SURFACE_PRESSED))
    pen.setWidthF(2.0)
    p.setPen(pen)
    for i in range(1, len(pts)):
        p.drawLine(pts[i - 1], pts[i])
    p.restore()


def paint_skeleton_bars(p: QPainter, x: float, y: float, w: float,
                        h: float, seed: float = 0.0) -> None:
    """Esqueleto de BARRAS (ex.: volume do PriceHistoryChart)."""
    n = 8
    gap = w / n
    bar_w = gap * 0.5
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t.SURFACE_HOV))
    for i in range(n):
        onda = math.sin(seed + i * 2.3)
        frac = 0.25 + 0.5 * (0.5 + 0.5 * onda)
        bh = h * max(0.15, min(1.0, frac))
        bx = x + gap * i + (gap - bar_w) / 2
        p.drawRoundedRect(int(bx), int(y + h - bh), int(bar_w), int(bh), 2, 2)
    p.restore()
