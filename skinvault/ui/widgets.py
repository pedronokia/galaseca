"""Widgets graficos custom (QPainter) migrados de gui.py.

MonthBarChart, ValueChart, MiniSparkline, DepthChart -- logica preservada,
cores agora vem do tema (skinvault.ui.theme).
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QToolTip, QWidget

from skinvault.ui import theme as t


class MonthBarChart(QWidget):
    """Barras do P&L mensal (custom paint)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._months: list[dict] = []
        self.setMinimumHeight(120)

    def set_months(self, months: list[dict]) -> None:
        self._months = list(months)
        self.update()

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
        bar_w = max(8, (w - 20) // len(self._months) - 4)
        all_pnl = [m["pnl"] for m in self._months]
        mx = max(abs(v) for v in all_pnl) or 1
        p.setFont(QFont("Segoe UI", 7))
        for i, m in enumerate(self._months):
            pnl = m["pnl"]
            bar_h = int((abs(pnl) / mx) * (h - 24))
            x = 10 + i * (bar_w + 4)
            if pnl >= 0:
                y = h - 12 - bar_h
                p.setBrush(QColor(t.ACCENT))
            else:
                y = h - 12
                p.setBrush(QColor(t.DANGER))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, max(bar_h, 1), 2, 2)
            p.setPen(QColor(t.TEXT_MUTED))
            month_short = m["month"][:3]
            p.drawText(x, h - 1, bar_w, 10,
                       Qt.AlignmentFlag.AlignCenter, month_short)
        p.end()


class ValueChart(QWidget):
    """Linha do valor do inventario no tempo (custom paint)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = []
        self.setMinimumHeight(120)

    def set_series(self, totals: list[float]) -> None:
        self._values = list(totals)
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if len(self._values) < 2:
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Avalie 2x+ pra ver a evolucao do valor")
            p.end()
            return
        vmin, vmax = min(self._values), max(self._values)
        rng = (vmax - vmin) or 1.0
        up = self._values[-1] >= self._values[0]
        pen = QPen(QColor(t.ACCENT if up else t.DANGER))
        pen.setWidthF(2.0)
        p.setPen(pen)
        n = len(self._values)
        prev = None
        for i, v in enumerate(self._values):
            x = 6 + i * ((w - 12) / (n - 1))
            y = h - 8 - ((v - vmin) / rng) * (h - 24)
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
            prev = (x, y)
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
                       "Sem historico")
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
        pen = QPen(QColor(t.ACCENT if up else t.DANGER))
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
            p.setBrush(QColor(t.ACCENT if up else t.DANGER))
            p.setPen(QPen(QColor(t.BG), 1.5))
            p.drawEllipse(hx - 4, hy - 4, 8, 8)

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
            bid_fill = QColor(t.ACCENT)
            bid_fill.setAlpha(40)
            p.fillPath(bid_path, bid_fill)

            bid_pen = QPen(QColor(t.ACCENT))
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
            p.setPen(QColor(t.ACCENT))
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
            p.setPen(QColor(t.ACCENT))
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
