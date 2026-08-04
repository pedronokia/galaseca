"""Widgets graficos custom (QPainter) migrados de gui.py.

MonthBarChart, ValueChart, MiniSparkline, DepthChart -- logica preservada,
cores agora vem do tema (skinvault.ui.theme).
"""
from __future__ import annotations

import time
from datetime import datetime

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QToolTip, QWidget

from skinvault.ui import shimmer
from skinvault.ui import theme as t

_MES_CURTO = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}
_MES_LONGO = {
    "01": "Janeiro", "02": "Fevereiro", "03": "Março", "04": "Abril",
    "05": "Maio", "06": "Junho", "07": "Julho", "08": "Agosto",
    "09": "Setembro", "10": "Outubro", "11": "Novembro", "12": "Dezembro",
}


def month_label(key: str) -> str:
    """Label curto pt-BR pra key '%Y-%m' ('2025-01' -> 'Jan').

    Keys fora do formato (ex.: 'Janeiro') caem no comportamento
    antigo: primeiros 3 caracteres."""
    if len(key) == 7 and key[4] == "-":
        nome = _MES_CURTO.get(key[5:7])
        if nome:
            return nome
    return key[:3]


def month_label_full(key: str) -> str:
    """'2025-01' -> 'Janeiro 2025' (fallback: a propria key)."""
    if len(key) == 7 and key[4] == "-":
        nome = _MES_LONGO.get(key[5:7])
        if nome:
            return f"{nome} {key[:4]}"
    return key


class MonthBarChart(QWidget):
    """Barras do P&L mensal (custom paint).

    Clique numa barra emite month_clicked com a key do mes ('%Y-%m') --
    a tela dona decide o que fazer (ex.: filtrar a tabela naquele mes).
    set_selected() destaca a barra do filtro ativo; as demais esmaecem.
    """

    month_clicked = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._months: list[dict] = []
        self._selected: str | None = None
        self._hover_idx: int | None = None
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_months(self, months: list[dict]) -> None:
        self._months = list(months)
        if self._selected is not None and not any(
                m.get("month") == self._selected for m in self._months):
            self._selected = None
        self._hover_idx = None
        self.update()

    def set_selected(self, key: str | None) -> None:
        self._selected = key or None
        self.update()

    def _bar_w(self) -> int:
        return max(8, (self.width() - 20) // len(self._months) - 4)

    def _bar_index_at(self, x: float) -> int | None:
        """Indice da barra na coordenada x (coluna inteira, incl. gap)."""
        if not self._months:
            return None
        idx = int((x - 10) // (self._bar_w() + 4))
        if idx < 0 or idx >= len(self._months):
            return None
        return idx

    def mouseMoveEvent(self, evt) -> None:  # noqa: N802
        idx = self._bar_index_at(evt.position().x())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        if idx is not None:
            m = self._months[idx]
            key = m.get("month", "")
            txt = f"{month_label_full(key)} — P&L {t.brl(m.get('pnl', 0))}"
            n_trades = m.get("trades")
            if n_trades:
                plural = "s" if n_trades != 1 else ""
                txt += f" ({n_trades} trade{plural})"
            if key and key == self._selected:
                txt += "\nClique de novo pra limpar o filtro."
            else:
                txt += "\nClique pra filtrar o histórico neste mês."
            QToolTip.showText(evt.globalPosition().toPoint(), txt, self)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(evt)

    def leaveEvent(self, evt) -> None:  # noqa: N802
        if self._hover_idx is not None:
            self._hover_idx = None
            self.update()
        super().leaveEvent(evt)

    def mousePressEvent(self, evt) -> None:  # noqa: N802
        if evt.button() == Qt.MouseButton.LeftButton:
            idx = self._bar_index_at(evt.position().x())
            if idx is not None:
                key = self._months[idx].get("month", "")
                if key:
                    self.month_clicked.emit(key)
        super().mousePressEvent(evt)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if not self._months:
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Sem dados mensais")
            p.end()
            return
        bar_w = self._bar_w()
        all_pnl = [m["pnl"] for m in self._months]
        # Baseline dinamica: meses negativos descem a partir do zero
        # (o paint antigo fixava o zero no fundo e clipava as barras
        # negativas e os labels — nunca visto porque o widget era orfao)
        max_pos = max(0.0, max(all_pnl))
        max_neg = max(0.0, -min(all_pnl))
        rng = (max_pos + max_neg) or 1.0
        top = 4
        bottom = h - 12  # 12px reservados pros labels dos meses
        usable = max(1, bottom - top)
        baseline = top + (max_pos / rng) * usable
        p.setFont(QFont("Segoe UI", 7))

        base_pen = QPen(QColor(t.BORDER))
        base_pen.setWidthF(1)
        p.setPen(base_pen)
        p.drawLine(10, int(baseline), w - 10, int(baseline))

        for i, m in enumerate(self._months):
            pnl = m["pnl"]
            key = m.get("month", "")
            is_selected = self._selected is not None and key == self._selected
            bar_h = max(1, int((abs(pnl) / rng) * usable))
            x = 10 + i * (bar_w + 4)
            fill = QColor(t.POSITIVE if pnl >= 0 else t.DANGER)
            if self._selected is not None and not is_selected:
                fill.setAlpha(90)
            y = int(baseline) - bar_h if pnl >= 0 else int(baseline)
            p.setBrush(fill)
            if is_selected:
                p.setPen(QPen(QColor(t.TEXT), 1.5))
            elif i == self._hover_idx:
                p.setPen(QPen(QColor(t.TEXT_MUTED), 1))
            else:
                p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, bar_h, 2, 2)
            p.setPen(QColor(t.TEXT if is_selected else t.TEXT_MUTED))
            p.drawText(x, h - 11, bar_w, 10,
                       Qt.AlignmentFlag.AlignCenter, month_label(key))
        p.end()


class ValueChart(QWidget):
    """Linha do valor do inventario no tempo (custom paint).

    Preenchimento em gradiente sob a curva (POSITIVE/DANGER conforme a
    tendencia, esmaecendo ate' transparente), crosshair com tooltip
    rich-text no hover (data + valor + variacao % no periodo visivel) e
    filtro rapido de periodo via set_range() -- "1d"/"7d"/"30d"/"365d"/
    "all", tipicamente ligado a um SegmentedControl 1D/7D/1M/1A/Tudo.
    """

    RANGES = ("1d", "7d", "30d", "365d", "all")
    _RANGE_DAYS = {"1d": 1, "7d": 7, "30d": 30, "365d": 365}

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = []
        self._timestamps: list[float | None] | None = None
        self._range = "all"
        self._hover_idx: int | None = None
        self._loading = False
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def set_series(self, totals: list[float],
                   timestamps: list[float | None] | None = None) -> None:
        """timestamps (unix, opcional): habilita o filtro de periodo.

        Sem timestamp o widget continua funcionando exatamente como
        antes -- set_range() so' tem o que cortar quando sabe QUANDO
        cada ponto aconteceu.
        """
        self._values = list(totals)
        self._timestamps = list(timestamps) if timestamps else None
        self._hover_idx = None
        self._loading = False
        self._sync_shimmer()
        self.update()

    def set_loading(self, loading: bool) -> None:
        """Alterna pro estado de carregamento (esqueleto shimmer).

        O dono liga antes de buscar os dados e desliga quando os entrega.
        Mostrar o esqueleto e' decisao do dono: com historico ja'
        desenhado, uma reavaliacao nao deve apagar a linha que existe.
        """
        if loading == self._loading:
            return
        self._loading = loading
        self._hover_idx = None
        self._sync_shimmer()
        self.update()

    def loading(self) -> bool:
        return self._loading

    def _sync_shimmer(self) -> None:
        """Timer compartilhado so' roda com widget visivel em loading."""
        if self._loading and self.isVisible():
            shimmer.SHIMMER.register(self)
        else:
            shimmer.SHIMMER.unregister(self)

    def showEvent(self, evt) -> None:  # noqa: N802
        super().showEvent(evt)
        self._sync_shimmer()

    def hideEvent(self, evt) -> None:  # noqa: N802
        super().hideEvent(evt)
        shimmer.SHIMMER.unregister(self)

    def set_range(self, key: str) -> None:
        if key in self.RANGES and key != self._range:
            self._range = key
            self._hover_idx = None
            self.update()

    def range(self) -> str:
        return self._range

    def _visible(self) -> tuple[list[float], list[float | None]]:
        """(valores, timestamps) recortados pelo periodo atual."""
        if not self._timestamps or self._range == "all":
            return self._values, (self._timestamps or [None] * len(self._values))
        dias = self._RANGE_DAYS.get(self._range)
        if dias is None:
            return self._values, self._timestamps
        cutoff = time.time() - dias * 86400
        vals: list[float] = []
        tss: list[float | None] = []
        for v, ts in zip(self._values, self._timestamps):
            if ts is not None and ts >= cutoff:
                vals.append(v)
                tss.append(ts)
        return vals, tss

    # ── interacao ──────────────────────────────────────────

    def _hover_index_at(self, x: float, n: int) -> int:
        step = (self.width() - 12) / (n - 1) if n > 1 else 1.0
        idx = round((x - 6) / step) if step > 0 else 0
        return max(0, min(n - 1, int(idx)))

    def mouseMoveEvent(self, evt) -> None:  # noqa: N802
        vals, tss = self._visible()
        if len(vals) < 2:
            super().mouseMoveEvent(evt)
            return
        idx = self._hover_index_at(evt.position().x(), len(vals))
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        QToolTip.showText(evt.globalPosition().toPoint(),
                          self._tooltip_html(vals, tss, idx), self)
        super().mouseMoveEvent(evt)

    def leaveEvent(self, evt) -> None:  # noqa: N802
        if self._hover_idx is not None:
            self._hover_idx = None
            self.update()
        super().leaveEvent(evt)

    def _tooltip_html(self, vals: list[float],
                      tss: list[float | None], idx: int) -> str:
        """Rich-text: data + valor formatado + variacao % vs 1o ponto
        visivel (o inicio do periodo escolhido, nao do historico todo)."""
        linhas = []
        ts = tss[idx] if idx < len(tss) else None
        if ts:
            linhas.append(
                f"<b>{datetime.fromtimestamp(ts).strftime('%d/%m/%Y %H:%M')}</b>")
        linhas.append(t.brl(vals[idx]))
        base = vals[0]
        if base:
            var = (vals[idx] - base) / base * 100
            cor = t.POSITIVE if var >= 0 else t.DANGER
            linhas.append(
                f"<span style='color:{cor}'>{var:+.1f}%</span> no período")
        return "<br>".join(linhas)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self._loading:
            # Esqueleto shimmer no lugar da linha: o dono liga antes de
            # buscar os dados (avaliacao em andamento, sem serie ainda).
            shimmer.paint_skeleton_line(p, 6, 8, w - 12, h - 16, seed=0.0)
            if shimmer.SHIMMER.is_animating(self):
                shimmer.paint_band(p, w, h)
            p.end()
            return
        vals, _tss = self._visible()
        if len(vals) < 3:
            # Mostra os pontos que JA' existem, nao so' quantos faltam. Sao
            # avaliacoes reais da carteira; escondê-las pra escrever uma
            # contagem regressiva desperdicava o cartao inteiro.
            n = len(vals)
            p.setPen(QColor(t.TEXT_MUTED))
            if n == 0:
                # Distingue "nunca avaliou" de "nao ha' avaliacao NESTE
                # periodo" -- o historico pode existir fora do recorte.
                msg = ("Nenhuma avaliação registrada ainda"
                       if not self._values else
                       "Nenhuma avaliação neste período")
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)
                p.end()
                return
            faltam = 3 - n
            msg = (f"{n} avaliação registrada" if n == 1
                   else f"{n} avaliações registradas")
            msg += (f" — falta {faltam} pra desenhar a linha" if faltam == 1
                    else f" — faltam {faltam} pra desenhar a linha")
            p.drawText(QRectF(0, h / 2 - 34, w, 18),
                       Qt.AlignmentFlag.AlignCenter, msg)
            fonte = p.font()
            fonte.setPointSize(12)
            fonte.setBold(True)
            p.setFont(fonte)
            p.setPen(QColor(t.TEXT))
            valores = "     ".join(t.brl(v) for v in vals)
            p.drawText(QRectF(0, h / 2 - 10, w, 30),
                       Qt.AlignmentFlag.AlignCenter, valores)
            p.end()
            return
        vmin, vmax = min(vals), max(vals)
        rng = (vmax - vmin) or 1.0
        up = vals[-1] >= vals[0]
        cor_linha = QColor(t.POSITIVE if up else t.DANGER)
        n = len(vals)
        pontos = []
        for i, v in enumerate(vals):
            x = 6 + i * ((w - 12) / (n - 1))
            y = h - 8 - ((v - vmin) / rng) * (h - 24)
            pontos.append(QPointF(x, y))

        # Gradiente sob a curva: mesma cor da linha, esmaecendo ate'
        # transparente na base -- reforca a tendencia sem competir com
        # o traco (que continua solido, e' o que os testes de cor leem).
        poligono = QPolygonF(
            pontos + [QPointF(pontos[-1].x(), float(h)),
                     QPointF(pontos[0].x(), float(h))])
        grad = QLinearGradient(0, 0, 0, h)
        topo = QColor(cor_linha)
        topo.setAlpha(70)
        base_cor = QColor(cor_linha)
        base_cor.setAlpha(0)
        grad.setColorAt(0.0, topo)
        grad.setColorAt(1.0, base_cor)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPolygon(poligono)

        pen = QPen(cor_linha)
        pen.setWidthF(2.0)
        p.setPen(pen)
        for i in range(1, n):
            p.drawLine(pontos[i - 1], pontos[i])

        if self._hover_idx is not None and self._hover_idx < n:
            hx = pontos[self._hover_idx].x()
            hy = pontos[self._hover_idx].y()
            guide = QPen(QColor(t.TEXT_MUTED))
            guide.setStyle(Qt.PenStyle.DashLine)
            guide.setWidthF(1)
            p.setPen(guide)
            p.drawLine(QPointF(hx, 4), QPointF(hx, h - 4))
            p.setBrush(cor_linha)
            p.setPen(QPen(QColor(t.BG), 1.5))
            p.drawEllipse(QRectF(hx - 4, hy - 4, 8, 8))

        p.end()


class MiniSparkline(QWidget):
    """Sparkline com overlay opcional de SMA + suporte/resistencia.

    Hover: marcador no ponto mais proximo + tooltip com preco (e data,
    quando timestamps unix foram passados em set_series).
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = []
        self._timestamps: list[float | None] | None = None
        self._sma: list[float | None] | None = None
        self._sr: dict | None = None
        self._hover_idx: int | None = None
        self.setMinimumHeight(50)
        self.setMouseTracking(True)

    def set_series(self, values: list[float],
                   timestamps: list[float | None] | None = None) -> None:
        self._values = list(values)
        self._timestamps = list(timestamps) if timestamps else None
        self._sma = None
        self._sr = None
        self._hover_idx = None
        self.update()

    def set_sma(self, sma_data: list[float | None]) -> None:
        self._sma = sma_data
        self.update()

    def set_sr(self, sr_data: dict) -> None:
        self._sr = sr_data
        self.update()

    def _hover_index_at(self, x: float) -> int:
        """Indice do ponto mais proximo de uma coordenada x do widget.
        Assume len(self._values) >= 2 (caller garante)."""
        n = len(self._values)
        step = (self.width() - 8) / (n - 1)
        idx = round((x - 4) / step) if step > 0 else 0
        return max(0, min(n - 1, int(idx)))

    def mouseMoveEvent(self, evt) -> None:  # noqa: N802
        if len(self._values) < 2:
            super().mouseMoveEvent(evt)
            return
        idx = self._hover_index_at(evt.position().x())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
        txt = t.brl(self._values[idx])
        ts = None
        if self._timestamps and idx < len(self._timestamps):
            ts = self._timestamps[idx]
        if ts:
            txt += datetime.fromtimestamp(ts).strftime(" — %d/%m/%Y")
        QToolTip.showText(evt.globalPosition().toPoint(), txt, self)
        super().mouseMoveEvent(evt)

    def leaveEvent(self, evt) -> None:  # noqa: N802
        if self._hover_idx is not None:
            self._hover_idx = None
            self.update()
        super().leaveEvent(evt)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if len(self._values) < 2:
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Sem histórico")
            p.end()
            return
        vmin, vmax = min(self._values), max(self._values)
        rng = (vmax - vmin) or 1.0

        def _y(val: float) -> int:
            return int(h - 4 - ((val - vmin) / rng) * (h - 8))

        def _x(i: int) -> int:
            n = len(self._values)
            return int(4 + i * ((w - 8) / (n - 1)))

        if self._sr:
            sr_pen = QPen(QColor(t.CHART_YELLOW))
            sr_pen.setStyle(Qt.PenStyle.DashLine)
            sr_pen.setWidthF(1)
            p.setPen(sr_pen)
            for level in self._sr.get("support", []):
                y = _y(level)
                p.drawLine(4, y, w - 4, y)
            res_pen = QPen(QColor(t.DANGER))
            res_pen.setStyle(Qt.PenStyle.DashLine)
            res_pen.setWidthF(1)
            p.setPen(res_pen)
            for level in self._sr.get("resistance", []):
                y = _y(level)
                p.drawLine(4, y, w - 4, y)

        up = self._values[-1] >= self._values[0]
        pen = QPen(QColor(t.POSITIVE if up else t.DANGER))
        pen.setWidthF(1.5)
        p.setPen(pen)
        prev = None
        for i, v in enumerate(self._values):
            x = _x(i)
            y = _y(v)
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), x, y)
            prev = (x, y)

        if self._sma:
            sma_pen = QPen(QColor(t.CHART_INDIGO))
            sma_pen.setWidthF(1)
            p.setPen(sma_pen)
            prev = None
            for i, v in enumerate(self._sma):
                if v is None:
                    prev = None
                    continue
                x = _x(i)
                y = _y(v)
                if prev is not None:
                    p.drawLine(int(prev[0]), int(prev[1]), x, y)
                prev = (x, y)

        if self._hover_idx is not None and self._hover_idx < len(self._values):
            hx = _x(self._hover_idx)
            hy = _y(self._values[self._hover_idx])
            guide = QPen(QColor(t.TEXT_MUTED))
            guide.setStyle(Qt.PenStyle.DashLine)
            guide.setWidthF(1)
            p.setPen(guide)
            p.drawLine(hx, 2, hx, h - 2)
            p.setBrush(QColor(t.POSITIVE if up else t.DANGER))
            p.setPen(QPen(QColor(t.BG), 1.5))
            p.drawEllipse(hx - 4, hy - 4, 8, 8)

        p.end()


class PriceHistoryChart(QWidget):
    """Histórico de preços completo: eixo, volume e intervalo.

    Substituiu o MiniSparkline na tela Market em 2026-07-31. O sparkline
    era ~100 pontos sem eixo nenhum -- ilegível como "histórico". Aqui a
    série inteira (até a Steam servir) aparece com eixo de preço e de
    data, barras de volume (as `purchases` do SSR) e crosshair no hover.

    O intervalo (7d/30d/tudo) é controlado pelo dono via `set_range`; o
    widget não decide por conta própria. Dados: pontos DIÁRIOS como o
    `signals.daily_series` devolve -- {"time", "price_median", "purchases"}.
    """

    _LEFT = 52
    _RIGHT = 10
    _TOP = 8
    _DATE_H = 18
    _GRID = 4

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._points: list[dict] = []
        self._sma: list[float | None] | None = None
        self._sr: dict | None = None
        self._range = "all"
        self._hover: int | None = None
        self._loading = False
        self.setMinimumHeight(140)
        self.setMouseTracking(True)

    # ── API ────────────────────────────────────────────────

    def set_data(self, points: list[dict]) -> None:
        """points: lista diaria (daily_series) com time/price_median/purchases."""
        self._points = list(points or [])
        self._sma = None
        self._sr = None
        self._hover = None
        self._loading = False
        self._sync_shimmer()
        self.update()

    def set_loading(self, loading: bool) -> None:
        """Alterna pro estado de carregamento (esqueleto shimmer).

        O dono liga ao iniciar a consulta e desliga quando `set_data`
        chega. Com historico ja' desenhado, consultar outro item nao
        deve apagar o grafico que esta na tela -- desligue antes.
        """
        if loading == self._loading:
            return
        self._loading = loading
        self._hover = None
        self._sync_shimmer()
        self.update()

    def loading(self) -> bool:
        return self._loading

    def _sync_shimmer(self) -> None:
        if self._loading and self.isVisible():
            shimmer.SHIMMER.register(self)
        else:
            shimmer.SHIMMER.unregister(self)

    def showEvent(self, evt) -> None:  # noqa: N802
        super().showEvent(evt)
        self._sync_shimmer()

    def hideEvent(self, evt) -> None:  # noqa: N802
        super().hideEvent(evt)
        shimmer.SHIMMER.unregister(self)

    def set_sma(self, sma_data: list[float | None]) -> None:
        self._sma = sma_data
        self.update()

    def set_sr(self, sr_data: dict) -> None:
        self._sr = sr_data
        self.update()

    def set_range(self, key: str) -> None:
        if key in ("7d", "30d", "all"):
            self._range = key
            self._hover = None
            self.update()

    def range(self) -> str:
        return self._range

    # ── visibilidade ───────────────────────────────────────

    def _visible(self) -> list[dict]:
        if self._range == "7d":
            return self._points[-7:]
        if self._range == "30d":
            return self._points[-30:]
        return self._points

    def _visible_sma(self) -> list[float | None] | None:
        """SMA alinhada a `_visible`: a serie e' do comprimento total."""
        if not self._sma or not self._points:
            return None
        n = len(self._visible())
        if not n:
            return None
        return self._sma[len(self._points) - n:]

    @staticmethod
    def _fmt_axis(v: float) -> str:
        """Rótulo compacto de eixo: "R$ 1.234" (inteiro) ou "R$ 12,34"."""
        s = f"R$ {v:,.0f}" if abs(v) >= 100 else f"R$ {v:,.2f}"
        return s.replace(",", ".")

    # ── interacao ──────────────────────────────────────────

    def _index_at(self, x: float) -> int | None:
        n = len(self._visible())
        if n < 2:
            return None
        step = (self.width() - self._LEFT - self._RIGHT) / (n - 1)
        idx = round((x - self._LEFT) / step) if step > 0 else 0
        return max(0, min(n - 1, int(idx)))

    def mouseMoveEvent(self, evt) -> None:  # noqa: N802
        vis = self._visible()
        if len(vis) < 2:
            super().mouseMoveEvent(evt)
            return
        idx = self._index_at(evt.position().x())
        if idx != self._hover:
            self._hover = idx
            self.update()
        QToolTip.showText(evt.globalPosition().toPoint(),
                          self._tooltip_html(vis, idx), self)
        super().mouseMoveEvent(evt)

    def _tooltip_html(self, vis: list[dict], idx: int) -> str:
        """Rich-text: data + preco + variacao % vs o 1o ponto do
        intervalo visivel (o inicio do periodo escolhido em set_range)."""
        d = vis[idx]
        linhas = []
        ts = d.get("time")
        if ts:
            linhas.append(
                f"<b>{datetime.fromtimestamp(ts).strftime('%d/%m/%Y')}</b>")
        linhas.append(t.brl(d.get("price_median") or 0))
        base = vis[0].get("price_median")
        atual = d.get("price_median")
        if base and atual is not None:
            var = (atual - base) / base * 100
            cor = t.POSITIVE if var >= 0 else t.DANGER
            linhas.append(
                f"<span style='color:{cor}'>{var:+.1f}%</span> no período")
        vol = d.get("purchases")
        if vol:
            linhas.append(
                f"<span style='color:{t.TEXT_MUTED}'>{vol} vendas</span>")
        return "<br>".join(linhas)

    def leaveEvent(self, evt) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(evt)

    # ── pintura ────────────────────────────────────────────

    def _layout(self, h: int) -> tuple[int, int, int, int]:
        vol_h = max(26, int(h * 0.16))
        bottom = self._DATE_H + vol_h + 6
        price_top = self._TOP
        price_bottom = h - bottom
        vol_top = price_bottom + 4
        vol_bottom = h - self._DATE_H - 2
        return price_top, price_bottom, vol_top, vol_bottom

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if self._loading:
            # Esqueleto shimmer mimetizando o layout real: linha de preco
            # na area de cima, barras de volume embaixo, faixa accent por
            # cima de tudo quando o controller esta' animando.
            price_top, price_bottom, vol_top, vol_bottom = self._layout(h)
            shimmer.paint_skeleton_line(
                p, self._LEFT, price_top,
                w - self._LEFT - self._RIGHT, price_bottom - price_top,
                seed=1.0)
            shimmer.paint_skeleton_bars(
                p, self._LEFT, vol_top,
                w - self._LEFT - self._RIGHT, vol_bottom - vol_top,
                seed=3.0)
            if shimmer.SHIMMER.is_animating(self):
                shimmer.paint_band(p, w, h)
            p.end()
            return
        vis = self._visible()
        if len(vis) < 2:
            p.setPen(QColor(t.TEXT_MUTED))
            msg = ("Sem histórico" if not self._points
                   else "Sem dados para este intervalo")
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)
            p.end()
            return

        price_top, price_bottom, vol_top, vol_bottom = self._layout(h)
        n = len(vis)
        step = (w - self._LEFT - self._RIGHT) / (n - 1)

        def _x(i: int) -> float:
            return self._LEFT + i * step

        # Faixa de preço cobre preços, SMA e níveis de S/R (senao as linhas
        # sobem pra fora do grafico e a leitura perde a referencia).
        vmin = min(d["price_median"] for d in vis)
        vmax = max(d["price_median"] for d in vis)
        for v in (self._visible_sma() or []):
            if v is not None:
                vmin = min(vmin, v)
                vmax = max(vmax, v)
        for lvl in ((self._sr or {}).get("support", [])
                    + (self._sr or {}).get("resistance", [])):
            vmin = min(vmin, lvl)
            vmax = max(vmax, lvl)
        pad = (vmax - vmin) * 0.06 or max(vmax * 0.01, 1.0)
        vmin -= pad
        vmax += pad
        rng = (vmax - vmin) or 1.0

        def _y(v: float) -> float:
            return price_bottom - (v - vmin) / rng * (price_bottom - price_top)

        fonte = p.font()
        fonte.setPointSize(7)
        p.setFont(fonte)

        # Grade + rotulos de preco.
        for i in range(self._GRID):
            frac = i / (self._GRID - 1)
            y = price_top + frac * (price_bottom - price_top)
            grid_pen = QPen(QColor(t.BORDER))
            grid_pen.setWidthF(1)
            p.setPen(grid_pen)
            p.drawLine(self._LEFT, int(y), w - self._RIGHT, int(y))
            val = vmax - frac * rng
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(0, int(y) - 8, self._LEFT - 6, 16,
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter,
                       self._fmt_axis(val))

        # Barras de volume coloridas pela direcao do dia.
        vols = [d.get("purchases") or 0 for d in vis]
        vmax_vol = max(vols) or 1
        bar_w = max(2.0, step * 0.6)
        for i, d in enumerate(vis):
            v = d.get("purchases") or 0
            if v <= 0:
                continue
            prev = vis[i - 1]["price_median"] if i else None
            atual = d["price_median"]
            if prev is None or prev == atual:
                cor = QColor(t.TEXT_MUTED)
            else:
                cor = QColor(t.POSITIVE if atual > prev else t.DANGER)
            cor.setAlpha(150)
            bh = (v / vmax_vol) * (vol_bottom - vol_top)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(cor)
            p.drawRect(QRectF(_x(i) - bar_w / 2, vol_bottom - bh, bar_w, bh))

        # Suporte/resistencia (tracejadas, atras da linha).
        if self._sr:
            for level in self._sr.get("support", []):
                pen = QPen(QColor(t.CHART_YELLOW))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidthF(1)
                p.setPen(pen)
                p.drawLine(self._LEFT, int(_y(level)),
                           w - self._RIGHT, int(_y(level)))
            for level in self._sr.get("resistance", []):
                pen = QPen(QColor(t.DANGER))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setWidthF(1)
                p.setPen(pen)
                p.drawLine(self._LEFT, int(_y(level)),
                           w - self._RIGHT, int(_y(level)))

        # Gradiente sob a linha de preco: mesma cor da tendencia,
        # esmaecendo ate' transparente na BASE DA AREA DE PRECO (nao do
        # widget inteiro -- a faixa de volume fica abaixo, invadi-la
        # sobreporia as barras).
        up = vis[-1]["price_median"] >= vis[0]["price_median"]
        cor_linha = QColor(t.POSITIVE if up else t.DANGER)
        pontos_preco = [QPointF(_x(i), _y(d["price_median"]))
                        for i, d in enumerate(vis)]
        poligono = QPolygonF(
            pontos_preco + [QPointF(pontos_preco[-1].x(), float(price_bottom)),
                           QPointF(pontos_preco[0].x(), float(price_bottom))])
        grad = QLinearGradient(0, price_top, 0, price_bottom)
        topo = QColor(cor_linha)
        topo.setAlpha(70)
        base_cor = QColor(cor_linha)
        base_cor.setAlpha(0)
        grad.setColorAt(0.0, topo)
        grad.setColorAt(1.0, base_cor)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPolygon(poligono)

        # Linha de preco.
        pen = QPen(cor_linha)
        pen.setWidthF(2.0)
        p.setPen(pen)
        prev_pt = None
        for pt in pontos_preco:
            if prev_pt is not None:
                p.drawLine(int(prev_pt.x()), int(prev_pt.y()),
                           int(pt.x()), int(pt.y()))
            prev_pt = pt

        # SMA 7 (indigo).
        sma_vis = self._visible_sma()
        if sma_vis:
            sma_pen = QPen(QColor(t.CHART_INDIGO))
            sma_pen.setWidthF(1.2)
            p.setPen(sma_pen)
            prev_pt = None
            for i, v in enumerate(sma_vis):
                if v is None:
                    prev_pt = None
                    continue
                pt = (_x(i), _y(v))
                if prev_pt is not None:
                    p.drawLine(int(prev_pt[0]), int(prev_pt[1]),
                               int(pt[0]), int(pt[1]))
                prev_pt = pt

        # Rotulos de data (5 ticks espalhados; "dd/mm" vira "mm/aa" em
        # series muito longas, senao o rotulo cola no vizinho).
        span_days = 0
        if vis[0].get("time") and vis[-1].get("time"):
            span_days = (vis[-1]["time"] - vis[0]["time"]) / 86400
        fmt = "%m/%y" if span_days > 180 else "%d/%m"
        if n <= 8:
            tick_idx = list(range(n))
        else:
            tick_idx = sorted(set(round(i * (n - 1) / 4) for i in range(5)))
        for i in tick_idx:
            ts = vis[i].get("time")
            if not ts:
                continue
            rotulo = datetime.fromtimestamp(ts).strftime(fmt)
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(QRectF(_x(i) - 40, vol_bottom + 4, 80, 14),
                       Qt.AlignmentFlag.AlignHCenter
                       | Qt.AlignmentFlag.AlignTop, rotulo)

        # Crosshair do hover.
        if self._hover is not None and self._hover < n:
            hx = _x(self._hover)
            hy = _y(vis[self._hover]["price_median"])
            guide = QPen(QColor(t.TEXT_MUTED))
            guide.setStyle(Qt.PenStyle.DashLine)
            guide.setWidthF(1)
            p.setPen(guide)
            p.drawLine(int(hx), price_top, int(hx), vol_top)
            p.setBrush(QColor(t.POSITIVE if up else t.DANGER))
            p.setPen(QPen(QColor(t.BG), 1.5))
            p.drawEllipse(int(hx) - 4, int(hy) - 4, 8, 8)

        p.end()


class DepthChart(QWidget):
    """Profundidade do order book (bids vs asks)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bid_points: list[tuple[float, float]] = []
        self._ask_points: list[tuple[float, float]] = []
        self._best_bid: float | None = None
        self._best_ask: float | None = None
        self._spread: float | None = None
        self.setMinimumHeight(100)

    def set_data(self, order_book: dict | None) -> None:
        self._bid_points = []
        self._ask_points = []
        self._best_bid = None
        self._best_ask = None
        self._spread = None

        if not order_book:
            self.update()
            return

        buy_raw = order_book.get("buy_orders") or []
        sell_raw = order_book.get("sell_orders") or []
        best_bid = order_book.get("best_bid")
        best_ask = order_book.get("best_ask")
        if best_bid is not None:
            self._best_bid = best_bid / 100.0
        if best_ask is not None:
            self._best_ask = best_ask / 100.0
        spread_raw = order_book.get("spread")
        if spread_raw is not None:
            self._spread = spread_raw / 100.0

        if buy_raw:
            pairs = [(buy_raw[i] / 100.0, buy_raw[i + 1])
                     for i in range(0, len(buy_raw), 2)]
            pairs.sort(key=lambda x: -x[0])
            cum = 0
            pts = [(0.0, pairs[0][0])]
            for price, qty in pairs:
                cum += qty
                pts.append((float(cum), price))
            self._bid_points = pts

        if sell_raw:
            pairs = [(sell_raw[i] / 100.0, sell_raw[i + 1])
                     for i in range(0, len(sell_raw), 2)]
            pairs.sort(key=lambda x: x[0])
            cum = 0
            pts = [(0.0, pairs[0][0])]
            for price, qty in pairs:
                cum += qty
                pts.append((float(cum), price))
            self._ask_points = pts

        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin = 4

        if not self._bid_points and not self._ask_points:
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Sem dados do order book")
            p.end()
            return

        all_prices: list[float] = []
        all_qty: list[float] = []
        for cum_qty, price in self._bid_points:
            all_prices.append(price)
            all_qty.append(cum_qty)
        for cum_qty, price in self._ask_points:
            all_prices.append(price)
            all_qty.append(cum_qty)

        price_min = min(all_prices)
        price_max = max(all_prices)
        price_rng = (price_max - price_min) or 1.0
        max_qty = max(all_qty) or 1.0

        chart_w = w - margin * 2
        chart_h = h - margin * 2
        mid_x = margin + chart_w // 2

        def _x_bid(cum_qty: float) -> int:
            return int(mid_x - (cum_qty / max_qty) * (chart_w / 2))

        def _x_ask(cum_qty: float) -> int:
            return int(mid_x + (cum_qty / max_qty) * (chart_w / 2))

        def _y(price: float) -> int:
            return int(margin + chart_h
                       - ((price - price_min) / price_rng) * chart_h)

        if len(self._bid_points) > 1:
            bid_path = QPainterPath()
            bid_path.moveTo(mid_x, margin + chart_h)
            for cum_qty, price in self._bid_points:
                bid_path.lineTo(_x_bid(cum_qty), _y(price))
            bid_path.lineTo(mid_x, _y(self._bid_points[-1][1]))
            bid_path.closeSubpath()
            bid_fill = QColor(t.POSITIVE)
            bid_fill.setAlpha(40)
            p.fillPath(bid_path, bid_fill)

            bid_pen = QPen(QColor(t.POSITIVE))
            bid_pen.setWidthF(1.5)
            p.setPen(bid_pen)
            prev = None
            for cum_qty, price in self._bid_points:
                pt = (_x_bid(cum_qty), _y(price))
                if prev is not None:
                    p.drawLine(prev[0], prev[1], pt[0], pt[1])
                prev = pt

        if len(self._ask_points) > 1:
            ask_path = QPainterPath()
            ask_path.moveTo(mid_x, margin + chart_h)
            for cum_qty, price in self._ask_points:
                ask_path.lineTo(_x_ask(cum_qty), _y(price))
            ask_path.lineTo(mid_x, _y(self._ask_points[-1][1]))
            ask_path.closeSubpath()
            ask_fill = QColor(t.DANGER)
            ask_fill.setAlpha(40)
            p.fillPath(ask_path, ask_fill)

            ask_pen = QPen(QColor(t.DANGER))
            ask_pen.setWidthF(1.5)
            p.setPen(ask_pen)
            prev = None
            for cum_qty, price in self._ask_points:
                pt = (_x_ask(cum_qty), _y(price))
                if prev is not None:
                    p.drawLine(prev[0], prev[1], pt[0], pt[1])
                prev = pt

        if self._best_bid is not None and self._best_ask is not None:
            spread_pen = QPen(QColor(t.CHART_YELLOW))
            spread_pen.setStyle(Qt.PenStyle.DashLine)
            spread_pen.setWidthF(1)
            p.setPen(spread_pen)
            y_bid = _y(self._best_bid)
            y_ask = _y(self._best_ask)
            p.drawLine(mid_x - 4, y_bid, mid_x + 4, y_bid)
            p.drawLine(mid_x - 4, y_ask, mid_x + 4, y_ask)

        font = p.font()
        font.setPointSize(7)
        p.setFont(font)

        def _label_y(price: float) -> int:
            # Centraliza no tick, clampado dentro da area util
            return max(margin, min(h - margin - 12, _y(price) - 6))

        if self._best_bid is not None:
            p.setPen(QColor(t.POSITIVE))
            p.drawText(margin, _label_y(self._best_bid),
                       mid_x - 8 - margin, 12,
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter,
                       t.brl(self._best_bid))
        if self._best_ask is not None:
            p.setPen(QColor(t.DANGER))
            p.drawText(mid_x + 8, _label_y(self._best_ask),
                       mid_x - 8 - margin, 12,
                       Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter,
                       t.brl(self._best_ask))

        if self._bid_points:
            p.setPen(QColor(t.POSITIVE))
            p.drawText(margin, margin, mid_x - margin, 14,
                       Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter,
                       "Bids")
        if self._ask_points:
            p.setPen(QColor(t.DANGER))
            p.drawText(mid_x, margin, mid_x - margin, 14,
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter,
                       "Asks")
        if self._spread is not None:
            p.setPen(QColor(t.TEXT_MUTED))
            spread_text = f"Spread {t.brl(self._spread)}"
            text_w = p.fontMetrics().horizontalAdvance(spread_text)
            p.drawText(mid_x - text_w // 2, h - margin - 14, text_w, 14,
                       Qt.AlignmentFlag.AlignCenter, spread_text)

        p.end()


class CompositionChart(QWidget):
    """Barras horizontais: onde a carteira esta' concentrada.

    Monocromatico de proposito. Verde e vermelho no projeto significam
    lucro e prejuizo (theme.POSITIVE/DANGER); categoria nao e' nem um nem
    outro, e colorir por categoria roubaria esse significado.

    A barra mede VALOR quando ha' preco e CONTAGEM quando nao ha'. Os dois
    modos ficam declarados no rotulo da direita -- uma barra que muda de
    unidade sem avisar e' pior que barra nenhuma.
    """

    _LINHA_H = 26

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._grupos: list[dict] = []
        self.setMinimumHeight(self._LINHA_H * 3)

    def set_groups(self, grupos: list) -> None:
        self._grupos = [g for g in (grupos or []) if isinstance(g, dict)]
        alt = max(1, len(self._grupos)) * self._LINHA_H
        self.setMinimumHeight(alt)
        self.setMaximumHeight(alt)
        self.updateGeometry()
        self.update()

    def _por_valor(self) -> bool:
        return any((g.get("value") or 0) > 0 for g in self._grupos)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._grupos:
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Sem itens avaliados")
            p.end()
            return

        por_valor = self._por_valor()
        chave = "value" if por_valor else "count"
        maior = max((g.get(chave) or 0) for g in self._grupos) or 1

        w = self.width()
        rotulo_w = 150
        valor_w = 110
        barra_x = rotulo_w + 8
        barra_max = max(20, w - rotulo_w - valor_w - 16)

        fonte = p.font()
        fonte.setPointSize(9)
        p.setFont(fonte)

        for i, g in enumerate(self._grupos):
            y = i * self._LINHA_H
            centro = y + self._LINHA_H // 2

            p.setPen(QColor(t.TEXT))
            p.drawText(0, y, rotulo_w, self._LINHA_H,
                       Qt.AlignmentFlag.AlignLeft
                       | Qt.AlignmentFlag.AlignVCenter,
                       str(g.get("label", "")))

            larg = int(barra_max * ((g.get(chave) or 0) / maior))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.SURFACE))
            p.drawRoundedRect(barra_x, centro - 5, barra_max, 10, 5, 5)
            if larg > 0:
                p.setBrush(QColor(t.TEXT_MUTED))
                p.drawRoundedRect(barra_x, centro - 5, max(larg, 6), 10, 5, 5)

            qtd = g.get("count") or 0
            if por_valor:
                texto = f"{t.brl(g.get('value') or 0)}  ·  {qtd}"
            else:
                texto = f"{qtd} {'item' if qtd == 1 else 'itens'}"
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(w - valor_w, y, valor_w, self._LINHA_H,
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter, texto)
        p.end()
