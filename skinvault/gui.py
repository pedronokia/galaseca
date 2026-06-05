"""UI do SkinVault (PyQt6). Janela local: avalia o inventario e mostra o valor
no tempo. Importa PyQt6 -- so' carregada quando 'python -m skinvault --ui'.

Reaproveita os padroes do Future: tema escuro, valor em fonte tabular, grafico
custom-painted (estilo _Sparkline), worker em thread + signal pra nao travar a UI.
"""
from __future__ import annotations

import json
import os
import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

try:
    from PyQt6.QtWidgets import QSystemTrayIcon
except ImportError:
    QSystemTrayIcon = None

from skinvault import backup, history, portfolio, prices, signals, steam_api, trades, watchlist
from skinvault._paths import DATA_DIR
from skinvault.settings import DEFAULTS, load_settings, save_settings

_BG = "#0E0E12"
_SURFACE = "#16161C"
_TEXT = "#E6E6EA"
_MUTED = "#9D9DA8"
_GREEN = "#22C55E"
_RED = "#EF4444"


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── Stylesheet helpers ─────────────────────────────────────────
def _input_style() -> str:
    return (
        f"QLineEdit {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
        " border-radius: 8px; padding: 10px 12px; font-size: 11pt;"
        f" color: {_TEXT}; }}"
        f"QLineEdit:focus {{ border: 1px solid {_GREEN}; }}"
    )


def _btn_primary(padding: str = "10px 22px", fs: str = "11pt",
                 disabled: bool = False) -> str:
    s = (
        "QPushButton { color: #DCFFE6; background: rgba(34,197,94,0.16);"
        f" border: 1px solid {_GREEN}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600; }}"
        "QPushButton:hover { background: rgba(34,197,94,0.26); }"
    )
    if disabled:
        s += (
            "QPushButton:disabled { color: #777; border-color: #333;"
            " background: #1a1a20; }"
        )
    return s


def _btn_danger(padding: str = "8px 18px", fs: str = "10pt") -> str:
    return (
        "QPushButton { color: #FFE6E6; background: rgba(239,68,68,0.16);"
        f" border: 1px solid {_RED}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600; }}"
        "QPushButton:hover { background: rgba(239,68,68,0.26); }"
    )


def _btn_secondary(padding: str = "8px 18px", fs: str = "10pt") -> str:
    return (
        "QPushButton { color: #E6E6EA; background: rgba(255,255,255,0.06);"
        " border: 1px solid #3A3A44; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600; }}"
        "QPushButton:hover { background: rgba(255,255,255,0.12); }"
    )


def _table_style() -> str:
    return (
        f"QTableWidget {{ background: {_SURFACE}; border: none;"
        " border-radius: 10px; gridline-color: transparent; }"
        "QTableWidget::item { padding: 6px 10px;"
        " border-bottom: 1px solid rgba(255,255,255,0.04); }"
        "QHeaderView::section { background: transparent; color: #8A8A93;"
        " border: none; padding: 8px 10px; font-weight: 600; }"
    )


THEMES = {
    "dark": {
        "bg": "#0E0E12",
        "surface": "#16161C",
        "text": "#E6E6EA",
        "muted": "#9D9DA8",
    },
    "light": {
        "bg": "#F0F0F4",
        "surface": "#FFFFFF",
        "text": "#1A1A1E",
        "muted": "#6B6B76",
    },
}


def set_theme(theme: str) -> None:
    global _BG, _SURFACE, _TEXT, _MUTED
    t = THEMES.get(theme, THEMES["dark"])
    _BG = t["bg"]
    _SURFACE = t["surface"]
    _TEXT = t["text"]
    _MUTED = t["muted"]


def _save_column_widths(tab: str, widths: list[int]) -> None:
    s = load_settings()
    cw: dict = s.get("column_widths", {})
    cw[tab] = widths
    s["column_widths"] = cw
    save_settings(s)


def _load_column_widths(tab: str) -> list[int] | None:
    s = load_settings()
    cw: dict = s.get("column_widths", {})
    return cw.get(tab)


def _steam_market_url(name: str) -> str:
    import urllib.parse
    return f"https://steamcommunity.com/market/listings/730/{urllib.parse.quote(name)}"


def _make_context_menu(table: QTableWidget, actions: list[tuple[str, callable]]) -> QMenu:
    menu = QMenu()
    for label, cb in actions:
        a = menu.addAction(label)
        a.triggered.connect(cb)
    menu.setStyleSheet(
        f"QMenu {{ background: {_SURFACE}; color: {_TEXT};"
        " border: 1px solid #3A3A44; padding: 4px; }"
        "QMenu::item { padding: 6px 20px; }"
        "QMenu::item:selected { background: #2A2A33; }"
    )
    return menu


def _setup_table(table: QTableWidget, tab_key: str,
                 actions: list[tuple[str, callable]] | None = None
                 ) -> None:
    table.setSortingEnabled(True)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setStyleSheet(_table_style())

    def _open_steam(row, _col) -> None:
        item = table.item(row, 0)
        if item and item.text():
            QDesktopServices.openUrl(QUrl(_steam_market_url(item.text())))

    table.cellDoubleClicked.connect(_open_steam)

    if actions:
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos: _make_context_menu(table, actions).exec(table.mapToGlobal(pos))
        )


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
            p.setPen(QColor(_MUTED))
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
                p.setBrush(QColor(_GREEN))
            else:
                y = h - 12
                p.setBrush(QColor(_RED))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(x, y, bar_w, max(bar_h, 1), 2, 2)
            p.setPen(QColor(_MUTED))
            month_short = m["month"][:3]
            p.drawText(x, h - 1, bar_w, 10, Qt.AlignmentFlag.AlignCenter, month_short)
        p.end()


class ValueChart(QWidget):
    """Linha do valor do inventario no tempo (custom paint, sem dependencia)."""

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
            p.setPen(QColor(_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Avalie 2x+ pra ver a evolucao do valor")
            p.end()
            return
        vmin, vmax = min(self._values), max(self._values)
        rng = (vmax - vmin) or 1.0
        up = self._values[-1] >= self._values[0]
        pen = QPen(QColor(_GREEN if up else _RED))
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
    """Pequeno grafico do historico de preco de um item (custom paint).
    Suporta overlay de SMA e linhas de suporte/resistencia."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = []
        self._sma: list[float | None] | None = None
        self._sr: dict | None = None
        self.setMinimumHeight(50)
        self.setMaximumHeight(50)

    def set_series(self, values: list[float]) -> None:
        self._values = list(values)
        self._sma = None
        self._sr = None
        self.update()

    def set_sma(self, sma_data: list[float | None]) -> None:
        self._sma = sma_data
        self.update()

    def set_sr(self, sr_data: dict) -> None:
        self._sr = sr_data
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if len(self._values) < 2:
            p.setPen(QColor(_MUTED))
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

        # Linhas de suporte/resistencia
        if self._sr:
            sr_pen = QPen(QColor("#FACC15"))
            sr_pen.setStyle(Qt.PenStyle.DashLine)
            sr_pen.setWidthF(1)
            p.setPen(sr_pen)
            for level in self._sr.get("support", []):
                y = _y(level)
                p.drawLine(4, y, w - 4, y)
            res_pen = QPen(QColor(_RED))
            res_pen.setStyle(Qt.PenStyle.DashLine)
            res_pen.setWidthF(1)
            p.setPen(res_pen)
            for level in self._sr.get("resistance", []):
                y = _y(level)
                p.drawLine(4, y, w - 4, y)

        # Linha de precos principal
        up = self._values[-1] >= self._values[0]
        pen = QPen(QColor(_GREEN if up else _RED))
        pen.setWidthF(1.5)
        p.setPen(pen)
        n = len(self._values)
        prev = None
        for i, v in enumerate(self._values):
            x = _x(i)
            y = _y(v)
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), x, y)
            prev = (x, y)

        # SMA overlay
        if self._sma:
            sma_pen = QPen(QColor("#818CF8"))
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

        p.end()


class DepthChart(QWidget):
    """Grafico de profundidade do order book (bids vs asks) com QPainter."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bid_points: list[tuple[float, float]] = []  # (cum_qty, price_reais)
        self._ask_points: list[tuple[float, float]] = []
        self._best_bid: float | None = None
        self._best_ask: float | None = None
        self._spread: float | None = None
        self.setMinimumHeight(100)
        self.setMaximumHeight(160)

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

        # Bids: flat [price_cents, qty, ...], sorted descending price
        if buy_raw:
            pairs = [(buy_raw[i] / 100.0, buy_raw[i + 1])
                     for i in range(0, len(buy_raw), 2)]
            pairs.sort(key=lambda x: -x[0])  # descending price
            cum = 0
            pts = [(0.0, pairs[0][0])]
            for price, qty in pairs:
                cum += qty
                pts.append((float(cum), price))
            self._bid_points = pts

        # Asks: flat [price_cents, qty, ...], sorted ascending price
        if sell_raw:
            pairs = [(sell_raw[i] / 100.0, sell_raw[i + 1])
                     for i in range(0, len(sell_raw), 2)]
            pairs.sort(key=lambda x: x[0])  # ascending price
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
            p.setPen(QColor(_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Sem dados do order book")
            p.end()
            return

        # Calcular ranges
        all_prices: list[float] = []
        all_qty: list[float] = []
        for cum_qty, price in self._bid_points:
            all_prices.append(price)
            all_qty.append(cum_qty)
        for cum_qty, price in self._ask_points:
            all_prices.append(price)
            all_qty.append(cum_qty)

        if not all_prices:
            p.end()
            return

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
            return int(margin + chart_h - ((price - price_min) / price_rng) * chart_h)

        # Fundo bids (area verde)
        if len(self._bid_points) > 1:
            bid_path = QPainterPath()
            bid_path.moveTo(mid_x, margin + chart_h)
            for cum_qty, price in self._bid_points:
                bid_path.lineTo(_x_bid(cum_qty), _y(price))
            bid_path.lineTo(mid_x, _y(self._bid_points[-1][1]))
            bid_path.closeSubpath()
            p.fillPath(bid_path, QColor(34, 197, 94, 40))  # _GREEN alpha

            bid_pen = QPen(QColor(34, 197, 94))
            bid_pen.setWidthF(1.5)
            p.setPen(bid_pen)
            prev = None
            for cum_qty, price in self._bid_points:
                pt = (_x_bid(cum_qty), _y(price))
                if prev is not None:
                    p.drawLine(prev[0], prev[1], pt[0], pt[1])
                prev = pt

        # Fundo asks (area vermelha)
        if len(self._ask_points) > 1:
            ask_path = QPainterPath()
            ask_path.moveTo(mid_x, margin + chart_h)
            for cum_qty, price in self._ask_points:
                ask_path.lineTo(_x_ask(cum_qty), _y(price))
            ask_path.lineTo(mid_x, _y(self._ask_points[-1][1]))
            ask_path.closeSubpath()
            p.fillPath(ask_path, QColor(239, 68, 68, 40))  # _RED alpha

            ask_pen = QPen(QColor(239, 68, 68))
            ask_pen.setWidthF(1.5)
            p.setPen(ask_pen)
            prev = None
            for cum_qty, price in self._ask_points:
                pt = (_x_ask(cum_qty), _y(price))
                if prev is not None:
                    p.drawLine(prev[0], prev[1], pt[0], pt[1])
                prev = pt

        # Spread gap
        if self._best_bid is not None and self._best_ask is not None:
            spread_pen = QPen(QColor("#FACC15"))
            spread_pen.setStyle(Qt.PenStyle.DashLine)
            spread_pen.setWidthF(1)
            p.setPen(spread_pen)
            y_bid = _y(self._best_bid)
            y_ask = _y(self._best_ask)
            p.drawLine(mid_x - 4, y_bid, mid_x + 4, y_bid)
            p.drawLine(mid_x - 4, y_ask, mid_x + 4, y_ask)

        # Labels
        p.setPen(QColor(_MUTED))
        font = p.font()
        font.setPointSize(7)
        p.setFont(font)
        if self._best_bid:
            p.drawText(margin, margin, mid_x - margin, 14,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f"Bids {self._best_bid:.2f}")
        if self._best_ask:
            p.drawText(mid_x, margin, mid_x - margin, 14,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"Asks {self._best_ask:.2f}")
        if self._spread is not None:
            spread_text = f"Spread R$ {self._spread:.2f}"
            text_w = p.fontMetrics().horizontalAdvance(spread_text)
            p.drawText(mid_x - text_w // 2, h - margin - 14, text_w, 14,
                       Qt.AlignmentFlag.AlignCenter, spread_text)

        p.end()


class _Bridge(QObject):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(str, list, float)
    portfolio_done = pyqtSignal(dict)
    market_done = pyqtSignal(dict)
    watchlist_done = pyqtSignal(list)


class InventoryTab(QWidget):
    """Aba Inventario: SteamID -> valor total + tabela + grafico."""

    def __init__(self, cache: prices.PriceCache) -> None:
        super().__init__()
        self._cache = cache
        self._build()
        self._load_saved_steamids()
        self._refresh_chart()

    # ── SteamID persistence ──────────────────────────────────
    def _steamids_path(self) -> str:
        p = DATA_DIR / "steamids.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    def _load_saved_steamids(self) -> None:
        import json, os
        path = self._steamids_path()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    ids: list[str] = json.load(f)
                for sid in ids:
                    self._sid.addItem(sid)
            except Exception:
                pass

    def _save_steamid(self) -> None:
        import json, os
        sid = self._sid.currentText().strip()
        if not sid:
            return
        path = self._steamids_path()
        ids: list[str] = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    ids = json.load(f)
            except Exception:
                ids = []
        if sid in ids:
            ids.remove(sid)
        ids.insert(0, sid)
        ids = ids[:10]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(ids, f)
        except Exception:
            pass

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        top = QHBoxLayout()
        self._sid = QComboBox()
        self._sid.setEditable(True)
        self._sid.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._sid.lineEdit().setPlaceholderText("SteamID64 (17 digitos)")
        self._sid.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px 12px; font-size: 11pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 28px; }"
            "QComboBox::down-arrow { image: none; }"
            f"QComboBox:focus {{ border: 1px solid {_GREEN}; }}"
            f"QComboBox QAbstractItemView {{ background: {_SURFACE};"
            f" color: {_TEXT}; selection-background-color: #2A2A33;"
            " border: 1px solid #3A3A44; }"
        )
        self._sid.lineEdit().returnPressed.connect(self._on_evaluate)
        self._sid.activated.connect(self._on_evaluate)
        top.addWidget(self._sid, 1)
        self._btn = QPushButton("Avaliar")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setToolTip("Busca inventario publico na Steam e calcula o valor total")
        self._btn.setStyleSheet(
            _btn_primary(disabled=True)
        )
        self._btn.clicked.connect(self._on_evaluate)
        top.addWidget(self._btn)
        root.addLayout(top)

        self._total = QLabel("R$ --")
        f = QFont("Segoe UI", 30, QFont.Weight.DemiBold)
        try:
            f.setStyleHint(QFont.StyleHint.Monospace)
            f.setFeatures({"tnum": 1})
        except Exception:
            pass
        self._total.setFont(QFont("Segoe UI", 30, QFont.Weight.DemiBold))
        self._total.setStyleSheet("color: #FFFFFF;")
        root.addWidget(self._total)

        cap = QLabel("Valor total do inventario  -  dado publico, sem login")
        cap.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(cap)

        self._chart = ValueChart()
        self._chart.setStyleSheet(f"background: {_SURFACE}; border-radius: 10px;")
        root.addWidget(self._chart)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(
            "QProgressBar { background: #20202a; border: none; border-radius: 2px; }"
            f"QProgressBar::chunk {{ background: {_GREEN}; border-radius: 2px; }}"
        )
        self._bar.hide()
        root.addWidget(self._bar)

        self._status = QLabel("Digite teu SteamID64 e clique em Avaliar.")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(self._status)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Qtd", "Preco", "Total", "Grafico"]
        )
        _setup_table(self._table, "inventory")
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1, 2, 3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        saved = _load_column_widths("inventory")
        if saved:
            for i, w in enumerate(saved):
                if i < self._table.columnCount():
                    hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                    self._table.setColumnWidth(i, w)

        def _save_w() -> None:
            _save_column_widths("inventory", [
                self._table.columnWidth(i) for i in range(self._table.columnCount())
            ])
        hh.sectionResized.connect(_save_w)
        root.addWidget(self._table, 1)

        self._dist_label = QLabel("")
        self._dist_label.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(self._dist_label)

    def _on_evaluate(self) -> None:
        sid = self._sid.currentText().strip()
        if not sid.isdigit() or len(sid) != 17 or not sid.startswith("7656119"):
            self._status.setText(
                "SteamID64 invalido -- sao 17 digitos, comeca com 7656119"
                " (use steamid.io)."
            )
            return
        self._btn.setEnabled(False)
        self._bar.setRange(0, 0)
        self._bar.show()
        self._status.setText("Lendo inventario publico...")

        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_progress)
        self._bridge.done.connect(self._on_done)

        def work() -> None:
            status, rows, total = prices.value_inventory(
                sid, self._cache,
                progress=lambda i, n, name: self._bridge.progress.emit(i, n, name),
            )
            self._bridge.done.emit(status, rows, total)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, i: int, n: int, name: str) -> None:
        if self._bar.maximum() == 0:
            self._bar.setRange(0, n)
        self._bar.setValue(i)
        self._status.setText(f"Avaliando {i}/{n}: {name}")

    def _on_done(self, status: str, rows: list, total: float) -> None:
        self._btn.setEnabled(True)
        self._bar.hide()
        msgs = {
            steam_api.INV_PRIVATE: "Inventario nao acessivel (400): privado, vazio "
                                   "(sem skins CS2), ou Steam limitou. Confere no "
                                   "navegador, aba CS2.",
            steam_api.INV_RATE_LIMITED: "Steam limitou (rate-limit). Espera ~1 min.",
            steam_api.INV_EMPTY: "Inventario publico, mas sem itens marketaveis.",
            steam_api.INV_ERROR: "Nao consegui ler agora (rede/erro).",
        }
        if status != steam_api.INV_OK:
            self._status.setText(msgs.get(status, "Falha desconhecida."))
            return

        self._total.setText(_brl(total))
        self._status.setText(f"{len(rows)} itens avaliados.")
        history.record_snapshot(total)
        self._refresh_chart()
        self._save_steamid()

        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(row["name"]))
            self._table.setItem(r, 1, QTableWidgetItem(str(row["qty"])))
            self._table.setItem(r, 2, QTableWidgetItem(_brl(row["price"])))
            self._table.setItem(r, 3, QTableWidgetItem(_brl(row["total"])))
            sp = MiniSparkline()
            sp.set_series(signals.load_item_history(row["name"]))
            self._table.setCellWidget(r, 4, sp)

        conds = {"FN": 0, "MW": 0, "FT": 0, "WW": 0, "BS": 0, "Outros": 0}
        cond_map = [
            ("Factory New", "FN"), ("Minimal Wear", "MW"),
            ("Field-Tested", "FT"), ("Well-Worn", "WW"),
            ("Battle-Scarred", "BS"),
        ]
        for row in rows:
            matched = False
            for kw, short in cond_map:
                if kw in row["name"]:
                    conds[short] += row.get("qty", 1)
                    matched = True
                    break
            if not matched:
                conds["Outros"] += row.get("qty", 1)
        dist_text = "  |  ".join(f"{k}: {v}" for k, v in conds.items() if v)
        self._dist_label.setText(dist_text)

    def _refresh_chart(self) -> None:
        self._chart.set_series([h["total"] for h in history.load_history()])


class PortfolioTab(QWidget):
    """Aba Meu Portfolio: tabela com lucro real pos-taxa, form p/ adicionar."""

    def __init__(self, cache: prices.PriceCache) -> None:
        super().__init__()
        self._cache = cache
        self._bridge = _Bridge()
        self._bridge.portfolio_done.connect(self._on_done)
        self._last_result: dict | None = None
        self._last_update_ts: float = 0
        self._build()
        self._evaluate()
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._evaluate)
        self._auto_timer.start(900000)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Unitário", "Custo", "Vale", "Recebe", "Lucro Real", "Break-even"]
        )
        actions = [
            ("Remover", self._on_remove),
            ("Editar", self._on_edit_position),
            ("Vender", self._on_sell),
            ("Duplicar", self._on_duplicate),
        ]
        _setup_table(self._table, "portfolio", actions)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        saved = _load_column_widths("portfolio")
        if saved:
            for i, w in enumerate(saved):
                if i < self._table.columnCount():
                    hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                    self._table.setColumnWidth(i, w)

        def _save_w() -> None:
            _save_column_widths("portfolio", [
                self._table.columnWidth(i) for i in range(self._table.columnCount())
            ])
        hh.sectionResized.connect(_save_w)

        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._on_import)
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self._on_export_csv)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._on_remove)

        root.addWidget(self._table, 1)

        self._totals = QLabel("")
        self._totals.setStyleSheet(f"color: {_TEXT}; font-size: 10pt; font-weight: 600;")
        root.addWidget(self._totals)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(self._status)

        self._pf_chart = ValueChart()
        self._pf_chart.setStyleSheet(f"background: {_SURFACE}; border-radius: 10px;")
        root.addWidget(self._pf_chart)

        self._filter_inp = QLineEdit()
        self._filter_inp.setPlaceholderText("Filtrar por nome do item...")
        self._filter_inp.setStyleSheet(_input_style())
        self._filter_inp.textChanged.connect(self._apply_filter)
        root.addWidget(self._filter_inp)

        form = QHBoxLayout()
        self._name_inp = QLineEdit()
        self._name_inp.setPlaceholderText(
            "Nome exato do item (ex.: AK-47 | Redline (Field-Tested))"
        )
        self._name_inp.setStyleSheet(
            _input_style()
        )
        self._name_inp.returnPressed.connect(self._on_add)
        form.addWidget(self._name_inp, 1)

        self._cost_inp = QLineEdit()
        self._cost_inp.setPlaceholderText("Custo (R$)")
        self._cost_inp.setFixedWidth(120)
        self._cost_inp.setStyleSheet(
            _input_style()
        )
        self._cost_inp.returnPressed.connect(self._on_add)
        form.addWidget(self._cost_inp)

        self._qty_inp = QLineEdit("1")
        self._qty_inp.setFixedWidth(60)
        self._qty_inp.setStyleSheet(
            _input_style()
        )
        self._qty_inp.returnPressed.connect(self._on_add)
        form.addWidget(self._qty_inp)

        add_btn = QPushButton("Adicionar")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Adiciona item ao portfolio")
        add_btn.setStyleSheet(
            _btn_primary()
        )
        add_btn.clicked.connect(self._on_add)
        form.addWidget(add_btn)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        rem_btn = QPushButton("Remover selecionado")
        rem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rem_btn.setToolTip("Remove a posicao selecionada do portfolio")
        rem_btn.setStyleSheet(
            _btn_danger()
        )
        rem_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(rem_btn)

        edit_btn = QPushButton("Editar")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Edita custo ou quantidade da posicao selecionada")
        edit_btn.setStyleSheet(
            _btn_secondary("8px 18px", "10pt")
        )
        edit_btn.clicked.connect(self._on_edit_position)
        btn_row.addWidget(edit_btn)

        sell_btn = QPushButton("Vender selecionado")
        sell_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sell_btn.setToolTip("Registra venda e calcula lucro real pos-taxa")
        sell_btn.setStyleSheet(
            _btn_primary("8px 18px", "10pt")
        )
        sell_btn.clicked.connect(self._on_sell)
        btn_row.addWidget(sell_btn)

        import_btn = QPushButton("Importar CSV")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.setToolTip("Importa posicoes a partir de texto CSV")
        import_btn.setStyleSheet(
            _btn_secondary()
        )
        import_btn.clicked.connect(self._on_import)
        btn_row.addWidget(import_btn)

        self._refresh_btn = QPushButton("Atualizar precos")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setToolTip("Reavalia todas as posicoes com precos atuais")
        self._refresh_btn.setStyleSheet(
            _btn_secondary()
        )
        self._refresh_btn.clicked.connect(self._evaluate)
        btn_row.addWidget(self._refresh_btn)

        batch_btn = QPushButton("Adicionar lote")
        batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        batch_btn.setToolTip("Adiciona varias posicoes de uma vez")
        batch_btn.setStyleSheet(
            _btn_secondary()
        )
        batch_btn.clicked.connect(self._on_batch_add)
        btn_row.addWidget(batch_btn)

        export_btn = QPushButton("Exportar CSV")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setToolTip("Exporta portfolio para arquivo CSV")
        export_btn.setStyleSheet(
            _btn_secondary()
        )
        export_btn.clicked.connect(self._on_export_csv)
        btn_row.addWidget(export_btn)

        export_full_btn = QPushButton("Exportar valores")
        export_full_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_full_btn.setToolTip("Exporta portfolio com precos atuais")
        export_full_btn.setStyleSheet(
            _btn_secondary()
        )
        export_full_btn.clicked.connect(self._on_export_csv_full)
        btn_row.addWidget(export_full_btn)

        dup_btn = QPushButton("Duplicar")
        dup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dup_btn.setToolTip("Duplica a posicao selecionada")
        dup_btn.setStyleSheet(
            _btn_secondary("8px 18px", "10pt")
        )
        dup_btn.clicked.connect(self._on_duplicate)
        btn_row.addWidget(dup_btn)

        clear_all_btn = QPushButton("Limpar tudo")
        clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_all_btn.setToolTip("Remove todas as posicoes do portfolio")
        clear_all_btn.setStyleSheet(
            _btn_danger()
        )
        clear_all_btn.clicked.connect(self._on_clear_portfolio)
        btn_row.addWidget(clear_all_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, evt) -> None:  # noqa: N802
        if evt.mimeData().hasUrls():
            evt.acceptProposedAction()

    def dropEvent(self, evt) -> None:  # noqa: N802
        for url in evt.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".csv"):
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except Exception:
                    continue
                result = portfolio.import_csv(text)
                if result["imported"]:
                    self._status.setText(
                        f"Importado: {result['imported']} posicao(oes)."
                    )
                self._evaluate()
                break

    def _on_add(self) -> None:
        name = self._name_inp.text().strip()
        if not name:
            self._status.setText("Digite o nome do item.")
            return
        try:
            cost = float(self._cost_inp.text().strip().replace(",", "."))
        except ValueError:
            self._status.setText("Custo invalido. Use numeros (ex.: 200.50).")
            return
        if cost <= 0:
            self._status.setText("Custo deve ser maior que zero.")
            return
        try:
            qty = int(self._qty_inp.text().strip())
        except ValueError:
            qty = 1
        portfolio.add_position(name, cost, max(qty, 1))
        self._name_inp.clear()
        self._cost_inp.clear()
        self._qty_inp.setText("1")
        self._evaluate()

    def _on_remove(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()),
                      reverse=True)
        if not rows:
            self._status.setText("Nenhuma posicao selecionada.")
            return
        positions = portfolio.load_portfolio()
        rows = [r for r in rows if r < len(positions)]
        if not rows:
            return
        confirm = QMessageBox.question(
            self, "Remover posicao",
            f"Remover {len(rows)} posicao(oes) do portfolio?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for r in rows:
            positions.pop(r)
        portfolio.save_portfolio(positions)
        self._status.setText(f"{len(rows)} posicao(oes) removida(s).")
        self._evaluate()

    def _on_sell(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        positions = portfolio.load_portfolio()
        if row >= len(positions):
            return
        pos = positions[row]
        market_price = prices.cached_price(pos["name"], self._cache)
        dlg = QDialog(self)
        dlg.setWindowTitle("Registrar venda")
        dlg.resize(380, 200)
        dlg.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                          " font-family: 'Segoe UI';")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.addWidget(QLabel(
            f"Vendendo: {pos['name']}\n"
            f"Comprou: {_brl(pos['cost'])}  x {pos['quantity']}",
            styleSheet=f"color: {_MUTED}; font-size: 10pt;"
        ))
        inp = QLineEdit()
        if market_price is not None:
            inp.setText(f"{market_price:.2f}".replace(".", ","))
            inp.selectAll()
        inp.setPlaceholderText("Preco de venda (R$) por unidade")
        inp.setStyleSheet(_input_style())
        inp.returnPressed.connect(dlg.accept)
        layout.addWidget(inp)
        btns = QHBoxLayout()
        ok_btn = QPushButton("Vender")
        ok_btn.setStyleSheet(
            _btn_primary("8px 18px", "10pt")
        )
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(
            _btn_secondary()
        )
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            sell_price = float(inp.text().strip().replace(",", "."))
        except ValueError:
            return
        t = trades.record_trade(
            pos["name"], pos["cost"], sell_price, pos["quantity"],
            buy_ts=pos.get("added_ts"),
        )
        positions.pop(row)
        portfolio.save_portfolio(positions)
        sign = "+" if t["pnl"] >= 0 else "-"
        self._status.setText(
            f"Vendido: {pos['name']} | Lucro: {sign}{_brl(abs(t['pnl']))}"
        )
        self._evaluate()

    def _on_import(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Importar posicoes (CSV)")
        dlg.resize(520, 360)
        dlg.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                          " font-family: 'Segoe UI';")

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        hint = QLabel(
            "Cole uma linha por item:\n"
            "  Nome, Custo, Qtd (opcional)\n"
            "  Linhas com # sao ignoradas\n\n"
            "Exemplo:\n"
            "  AK-47 | Redline (Field-Tested), 200, 1\n"
            "  AWP | Asiimov (FT), 650.50"
        )
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        layout.addWidget(hint)

        self._import_text = QTextEdit()
        self._import_text.setStyleSheet(
            f"QTextEdit {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px; font-size: 10pt;"
            " color: #E6E6EA; }}"
        )
        layout.addWidget(self._import_text, 1)

        btn_import = QPushButton("Importar")
        btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_import.setStyleSheet(
            _btn_primary()
        )
        btn_import.clicked.connect(lambda: self._do_import(dlg))
        layout.addWidget(btn_import)

        dlg.exec()

    def _do_import(self, dlg) -> None:
        text = self._import_text.toPlainText()
        if not text.strip():
            return
        result = portfolio.import_csv(text)
        dlg.accept()
        msg = f"Importado: {result['imported']} posicao(oes)."
        if result["errors"]:
            msg += f" Erros: {len(result['errors'])}"
        self._status.setText(msg)
        self._evaluate()

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Portfolio", "portfolio.csv", "CSV (*.csv)"
        )
        if not path:
            return
        positions = portfolio.load_portfolio()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Item,Custo,Qtd\n")
                for p in positions:
                    name = p["name"].replace(",", " ")
                    f.write(f'{name},{p["cost"]},{p["quantity"]}\n')
            self._status.setText(f"Exportado: {len(positions)} posicao(oes) para {path}")
        except Exception as e:
            self._status.setText(f"Erro ao exportar: {e}")

    def _on_export_csv_full(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Portfolio (com valores)", "portfolio_valores.csv", "CSV (*.csv)"
        )
        if not path:
            return
        result = self._last_result
        if not result:
            self._status.setText("Avalie o portfolio primeiro.")
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Item,Custo,Quantidade,Valor Atual,Recebe,Lucro Real\n")
                for row in result["rows"]:
                    name = row["name"].replace(",", " ")
                    cost = row.get("cost_total", 0)
                    qty = row.get("quantity", 1)
                    market = row.get("market", 0)
                    net = row.get("net_if_sold", 0)
                    pnl = row.get("pnl", 0)
                    f.write(f'{name},{cost},{qty},{market},{net},{pnl}\n')
            self._status.setText("Portfolio exportado com valores.")
        except Exception as e:
            self._status.setText(f"Erro ao exportar: {e}")

    def _evaluate(self) -> None:
        positions = portfolio.load_portfolio()
        if not positions:
            self._table.setRowCount(0)
            self._totals.setText("Portfolio vazio. Adicione uma posicao acima.")
            self._status.setText("")
            return
        self._refresh_btn.setEnabled(False)
        self._status.setText("Consultando precos...")

        def work() -> None:
            result = portfolio.evaluate_portfolio(
                positions, lambda n: prices.cached_price(n, self._cache)
            )
            self._bridge.portfolio_done.emit(result)

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, result: dict) -> None:
        self._last_result = result
        self._last_update_ts = time.time()
        self._refresh_btn.setEnabled(True)
        self._status.setText(
            "Portfolio atualizado em "
            f"{time.strftime('%H:%M', time.localtime(self._last_update_ts))}."
        )
        net = result["totals"].get("net_if_sold")
        if net is not None:
            history.record_snapshot(net)
            self._pf_chart.set_series(
                [h["total"] for h in history.load_history()]
            )
        self._table.setRowCount(len(result["rows"]))
        for r, row in enumerate(result["rows"]):
            name_item = QTableWidgetItem(row["name"])
            name_item.setToolTip(row["name"])
            self._table.setItem(r, 0, name_item)

            qty = row.get("quantity", 1)
            unitario = _brl(row["cost"] / qty) if qty > 0 else "--"
            self._table.setItem(r, 1, QTableWidgetItem(unitario))

            if row.get("pnl") is None:
                cost_total = row["cost"] * row["quantity"]
                self._table.setItem(r, 2, QTableWidgetItem(_brl(cost_total)))
                for c in range(3, 7):
                    it = QTableWidgetItem("--")
                    it.setForeground(QColor(_MUTED))
                    self._table.setItem(r, c, it)
                continue

            self._table.setItem(r, 2, QTableWidgetItem(_brl(row["cost_total"])))
            self._table.setItem(r, 3, QTableWidgetItem(_brl(row["market"])))
            self._table.setItem(r, 4, QTableWidgetItem(_brl(row["net_if_sold"])))

            pnl = row["pnl"]
            tag = "+" if pnl >= 0 else "-"
            pnl_item = QTableWidgetItem(tag + _brl(abs(pnl)))
            pnl_item.setForeground(QColor(_GREEN if pnl >= 0 else _RED))
            self._table.setItem(r, 5, pnl_item)

            self._table.setItem(r, 6, QTableWidgetItem(_brl(row["break_even"])))

            bg = QColor(_GREEN if pnl >= 0 else _RED)
            bg.setAlpha(18)
            for c in range(7):
                it = self._table.item(r, c)
                if it:
                    it.setBackground(bg)

        t = result["totals"]
        self._apply_filter()
        sign = "+" if t["pnl"] >= 0 else "-"
        self._totals.setText(
            f"Investido {_brl(t['cost'])}  |  Vale {_brl(t['market'])}  |  "
            f"Recebe {_brl(t['net_if_sold'])}  |  "
            f"LUCRO REAL {sign}{_brl(abs(t['pnl']))} ({t['pnl_pct']*100:+.1f}%)"
        )

    def _apply_filter(self) -> None:
        text = self._filter_inp.text().strip().lower()
        visible = 0
        for r in range(self._table.rowCount()):
            name_item = self._table.item(r, 0)
            match = not text or (name_item and text in name_item.text().lower())
            self._table.setRowHidden(r, not match)
            if match:
                visible += 1
        if self._last_result and text:
            total = len(self._last_result["rows"])
            self._status.setText(
                f"Mostrando {visible} de {total} posicoes"
            )

    def _on_edit_position(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            self._status.setText("Nenhuma posicao selecionada.")
            return
        positions = portfolio.load_portfolio()
        if row >= len(positions):
            return
        pos = positions[row]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Editar: {pos['name']}")
        dlg.resize(360, 200)
        dlg.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                          " font-family: 'Segoe UI';")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            f"Item: {pos['name']}",
            styleSheet=f"color: {_MUTED}; font-size: 10pt;"
        ))
        cost_inp = QLineEdit(str(pos["cost"]))
        cost_inp.setPlaceholderText("Custo (R$)")
        cost_inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Custo:"))
        layout.addWidget(cost_inp)

        qty_inp = QLineEdit(str(pos["quantity"]))
        qty_inp.setPlaceholderText("Quantidade")
        qty_inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Quantidade:"))
        layout.addWidget(qty_inp)

        btns = QHBoxLayout()
        ok_btn = QPushButton("Salvar")
        ok_btn.setStyleSheet(_btn_primary("8px 18px", "10pt"))
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(_btn_secondary())
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            new_cost = float(cost_inp.text().strip().replace(",", "."))
        except ValueError:
            self._status.setText("Custo invalido.")
            return
        try:
            new_qty = int(qty_inp.text().strip())
        except ValueError:
            new_qty = pos["quantity"]
        if new_cost <= 0:
            self._status.setText("Custo deve ser > 0.")
            return
        positions[row] = {**pos, "cost": new_cost, "quantity": max(new_qty, 1)}
        portfolio.save_portfolio(positions)
        self._status.setText(f"Posicao atualizada: {pos['name']}")
        self._evaluate()

    def _on_clear_portfolio(self) -> None:
        positions = portfolio.load_portfolio()
        if not positions:
            self._status.setText("Portfolio ja esta vazio.")
            return
        confirm = QMessageBox.question(
            self, "Limpar portfolio",
            f"Remover todas as {len(positions)} posicoes do portfolio?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        portfolio.save_portfolio([])
        self._status.setText("Portfolio limpo.")
        self._evaluate()

    def _on_duplicate(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        if not rows:
            self._status.setText("Nenhuma posicao selecionada.")
            return
        positions = portfolio.load_portfolio()
        for r in rows:
            if r < len(positions):
                pos = dict(positions[r])
                positions.insert(r + 1, pos)
        portfolio.save_portfolio(positions)
        self._status.setText(f"{len(rows)} posicao(oes) duplicada(s).")
        self._evaluate()

    def _on_batch_add(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Adicionar em lote")
        dlg.resize(480, 320)
        dlg.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                          " font-family: 'Segoe UI';")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        hint = QLabel(
            "Cole um item por linha:\n"
            "  Nome, Custo, Qtd (opcional)\n\n"
            "Exemplo:\n"
            "  AK-47 | Redline (FT), 200\n"
            "  AWP | Asiimov (FT), 650.50, 2"
        )
        hint.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        layout.addWidget(hint)
        inp = QTextEdit()
        inp.setStyleSheet(
            f"QTextEdit {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px; font-size: 10pt;"
            " color: #E6E6EA; }}"
        )
        layout.addWidget(inp, 1)
        btns = QHBoxLayout()
        ok_btn = QPushButton("Adicionar")
        ok_btn.setStyleSheet(_btn_primary())
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(_btn_secondary())
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = inp.toPlainText().strip()
        if not text:
            return
        positions = portfolio.load_portfolio()
        added = 0
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                cost = float(parts[1].replace(",", "."))
            except ValueError:
                continue
            qty = int(parts[2]) if len(parts) > 2 and parts[2].strip().isdigit() else 1
            positions.append({"name": parts[0], "cost": cost, "quantity": max(qty, 1)})
            added += 1
        if added:
            portfolio.save_portfolio(positions)
            self._status.setText(f"{added} posicao(oes) adicionada(s) em lote.")
        self._evaluate()


class MarketTab(QWidget):
    """Aba Market Browser: consulta lowest + median + volume + veredito."""

    def __init__(self) -> None:
        super().__init__()
        self._bridge = _Bridge()
        self._bridge.market_done.connect(self._on_done)
        self._build()

    def _searches_path(self) -> str:
        p = DATA_DIR / "searches.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    def _save_search(self, text: str) -> None:
        import json, os
        path = self._searches_path()
        searches: list[str] = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    searches = json.load(f)
            except Exception:
                searches = []
        if text in searches:
            searches.remove(text)
        searches.insert(0, text)
        searches = searches[:10]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(searches, f)
        except Exception:
            pass

    def _load_searches(self) -> list[str]:
        import json, os
        path = self._searches_path()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        top = QHBoxLayout()
        self._inp = QComboBox()
        self._inp.setEditable(True)
        self._inp.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._inp.lineEdit().setPlaceholderText(
            "Nome exato do item (ex.: AK-47 | Redline (Field-Tested))"
        )
        for s in self._load_searches():
            self._inp.addItem(s)
        self._inp.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px 12px; font-size: 11pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 28px; }"
            f"QComboBox:focus {{ border: 1px solid {_GREEN}; }}"
            f"QComboBox QAbstractItemView {{ background: {_SURFACE};"
            f" color: {_TEXT}; selection-background-color: #2A2A33;"
            " border: 1px solid #3A3A44; }"
        )
        self._inp.lineEdit().returnPressed.connect(self._on_search)
        self._inp.activated.connect(self._on_search)

        self._completer = QCompleter(self._load_searches(), self)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._inp.setCompleter(self._completer)

        top.addWidget(self._inp, 1)

        self._btn = QPushButton("Consultar")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setToolTip("Busca precos de mercado e mostra veredito de valor justo")
        self._btn.setStyleSheet(
            _btn_primary(disabled=True)
        )
        self._btn.clicked.connect(self._on_search)
        top.addWidget(self._btn)
        root.addLayout(top)

        self._status = QLabel("Digite o nome de um item e clique em Consultar.")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 10pt;")
        root.addWidget(self._status)

        self._results = QWidget()
        res = QVBoxLayout(self._results)
        res.setSpacing(8)
        res.setContentsMargins(16, 16, 16, 16)

        self._lowest_lbl = QLabel("")
        self._lowest_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._lowest_lbl)

        self._median_lbl = QLabel("")
        self._median_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._median_lbl)

        self._volume_lbl = QLabel("")
        self._volume_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._volume_lbl)

        self._verdict_lbl = QLabel("")
        self._verdict_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 12pt; font-weight: 600;"
        )
        res.addWidget(self._verdict_lbl)

        sep = QLabel(
            "──────────────────────────────────────────────"
        )
        sep.setStyleSheet(f"color: #2A2A33; font-size: 9pt;")
        res.addWidget(sep)

        self._spread_lbl = QLabel("")
        self._spread_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._spread_lbl)

        self._depth_lbl = QLabel("")
        self._depth_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._depth_lbl)

        self._trend_lbl = QLabel("")
        self._trend_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._trend_lbl)

        self._disc_lbl = QLabel("")
        self._disc_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._disc_lbl)

        self._liq_lbl = QLabel("")
        self._liq_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._liq_lbl)

        spark_lbl = QLabel("Historico de precos")
        spark_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        res.addWidget(spark_lbl)

        self._sparkline = MiniSparkline()
        self._sparkline.setStyleSheet(
            f"background: {_BG}; border-radius: 6px;"
        )
        res.addWidget(self._sparkline)

        depth_lbl = QLabel("Profundidade do mercado")
        depth_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        res.addWidget(depth_lbl)

        self._depth_chart = DepthChart()
        self._depth_chart.setStyleSheet(
            f"background: {_BG}; border-radius: 6px;"
        )
        res.addWidget(self._depth_chart)

        self._results.setStyleSheet(
            f"background: {_SURFACE}; border-radius: 10px;"
        )
        self._results.hide()
        root.addWidget(self._results)

        root.addStretch()

    def _on_search(self) -> None:
        name = self._inp.currentText().strip()
        if not name:
            return
        self._save_search(name)
        self._btn.setEnabled(False)
        self._status.setText("Consultando...")
        self._results.hide()

        def work() -> None:
            try:
                overview = steam_api.get_market_overview(name)
                page = steam_api.get_market_page_data(name)
                overview = dict(overview) if overview else {}
                overview["page_data"] = page
                self._bridge.market_done.emit(overview or {})
            except Exception:
                self._bridge.market_done.emit({})

        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, data: dict) -> None:
        self._btn.setEnabled(True)
        if not data:
            self._status.setText(
                "Nao consegui obter dados. Item invalido ou rede falhou."
            )
            return

        name = self._inp.currentText().strip()
        lowest = data.get("lowest")
        median = data.get("median")
        volume = data.get("volume")

        page_data = data.get("page_data")
        order_book = (page_data or {}).get("order_book")
        price_history = (page_data or {}).get("price_history")
        spread = (order_book or {}).get("spread")
        buy_count = (order_book or {}).get("buy_count")
        sell_count = (order_book or {}).get("sell_count")

        verdict = steam_api.fair_value_verdict(
            lowest, median,
            spread=spread, buy_count=buy_count,
            sell_count=sell_count,
            price_history=price_history,
        )

        self._lowest_lbl.setText(
            f"Menor listagem:  {_brl(lowest) if lowest else 'N/D'}"
        )
        self._median_lbl.setText(
            f"Mediana:         {_brl(median) if median else 'N/D'}"
        )
        self._volume_lbl.setText(
            f"Volume (24h):    {volume if volume else 'N/D'}"
        )

        vcolors = {
            "below_median": _GREEN,
            "fair": _GREEN,
            "slightly_above": "#FACC15",
            "overpriced": _RED,
            "unknown": _MUTED,
        }
        vcolor = vcolors.get(verdict["verdict"], _MUTED)
        self._verdict_lbl.setStyleSheet(
            f"color: {vcolor}; font-size: 12pt; font-weight: 600;"
        )
        self._verdict_lbl.setText(f"VEREDITO: {verdict['message']}")

        if verdict.get("details"):
            d = verdict["details"]
        else:
            d = {}

        if "spread_verdict" in verdict:
            sp = d.get("spread", "")
            self._spread_lbl.setStyleSheet(
                f"color: {_TEXT}; font-size: 11pt;"
            )
            spread_text = (
                f"Spread: R$ {spread / 100:.2f} ({sp})" if spread
                else "Mercado sem ordens ativas"
            )
            self._spread_lbl.setText(spread_text)
        else:
            self._spread_lbl.setText("")

        if "book_verdict" in verdict:
            self._depth_lbl.setStyleSheet(
                f"color: {_TEXT}; font-size: 11pt;"
            )
            depth_text = (
                f"Ordens: {buy_count} compra / {sell_count} venda"
                if buy_count is not None and sell_count is not None
                else ""
            )
            self._depth_lbl.setText(depth_text)
        else:
            self._depth_lbl.setText("")

        if lowest:
            signals.record_item_price(name, lowest)
        h = signals.load_item_history(name)
        t = signals.trend(h)
        if t:
            tcolor = _GREEN if t["direction"] == "subiu" else _RED
            self._trend_lbl.setStyleSheet(
                f"color: {tcolor}; font-size: 11pt;"
            )
            self._trend_lbl.setText(f"Tendencia: {t['label']}")
        else:
            self._trend_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11pt;")
            self._trend_lbl.setText("Tendencia: historico insuficiente")

        self._sparkline.set_series(h)
        self._depth_chart.set_data(order_book)

        if len(h) >= 7:
            prices_only = [e["price"] for e in h]
            sma7 = signals.sma(prices_only, 7)
            self._sparkline.set_sma(sma7)
        else:
            self._sparkline.set_sma([])

        if price_history and len(price_history) >= 11:
            sr = signals.find_support_resistance(price_history, window=5)
            self._sparkline.set_sr(sr)

        disc = signals.discontinued_flag(name)
        if disc["is_discontinued"]:
            self._disc_lbl.setStyleSheet(
                f"color: #FACC15; font-size: 11pt;"
            )
            self._disc_lbl.setText(f"Oferta: {disc['flag']}")
        else:
            self._disc_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11pt;")
            self._disc_lbl.setText("")

        liq = signals.liquidity_flag(volume)
        if liq["level"] == "low":
            self._liq_lbl.setStyleSheet(
                f"color: {_RED}; font-size: 11pt;"
            )
            self._liq_lbl.setText(f"Liquidez: {liq['flag']}")
        else:
            self._liq_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 11pt;")
            self._liq_lbl.setText("")

        self._status.setText(f"Resultados para: {name}")
        self._results.show()


def _make_tray_icon() -> QIcon:
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(_GREEN)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 16, 16)
    p.end()
    return QIcon(pix)


_SCAN_DEFAULTS = [
    "AK-47 | Redline (Field-Tested)",
    "M4A4 | Howl (Field-Tested)",
    "AWP | Dragon Lore (Field-Tested)",
    "Desert Eagle | Blaze (Factory New)",
    "AK-47 | Fire Serpent (Field-Tested)",
    "Glock-18 | Fade (Factory New)",
    "AWP | Asiimov (Field-Tested)",
    "Butterfly Knife | Fade (Factory New)",
    "M4A1-S | Knight (Field-Tested)",
    "USP-S | Kill Confirmed (Field-Tested)",
    "Souvenir AWP | Dragon Lore (Minimal Wear)",
    "Karambit | Doppler (Factory New)",
    "AK-47 | Case Hardened (Field-Tested)",
    "M4A1-S | Hyper Beast (Field-Tested)",
    "SSG 08 | Death Strike (Field-Tested)",
]


class ScannerTab(QWidget):
    """Aba Scanner: busca oportunidades combinando sinais de mercado."""

    def __init__(self) -> None:
        super().__init__()
        self._bridge = _Bridge()
        self._bridge.market_done.connect(self._on_item_scanned)
        self._scan_items: list[str] = []
        self._scan_results: list[dict] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # Input area
        input_layout = QHBoxLayout()
        self._items_edit = QTextEdit()
        self._items_edit.setPlaceholderText(
            "Itens para escanear (um por linha)"
        )
        self._items_edit.setMaximumHeight(100)
        self._items_edit.setStyleSheet(
            f"QTextEdit {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px; font-size: 10pt;"
            f" color: {_TEXT}; }}"
        )
        self._items_edit.setText("\n".join(_SCAN_DEFAULTS[:8]))
        input_layout.addWidget(self._items_edit, 1)

        btn_layout = QVBoxLayout()
        self._scan_btn = QPushButton("Escanear")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: #000; border: none;"
            " border-radius: 8px; padding: 10px 24px; font-size: 11pt;"
            " font-weight: 600; }}"
            "QPushButton:disabled { background: #2A2A33; color: #666; }"
        )
        self._scan_btn.clicked.connect(self._on_scan)
        btn_layout.addWidget(self._scan_btn)

        self._load_btn = QPushButton("Carregar defaults")
        self._load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._load_btn.setStyleSheet(
            f"QPushButton {{ background: {_SURFACE}; color: {_TEXT};"
            " border: 1px solid #2A2A33; border-radius: 8px; padding: 8px 16px;"
            " font-size: 10pt; }}"
            "QPushButton:hover { background: #2A2A33; }"
        )
        self._load_btn.clicked.connect(self._load_defaults)
        btn_layout.addWidget(self._load_btn)
        input_layout.addLayout(btn_layout)
        root.addLayout(input_layout)

        self._status = QLabel("Adicione itens e clique em Escanear.")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 10pt;")
        root.addWidget(self._status)

        # Results table
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Preco", "Mediana", "Veredito", "Spread",
             "Book", "Tendencia", "Score"]
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().hide()
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {_SURFACE}; border: none;"
            " border-radius: 8px; font-size: 10pt; }}"
            f"QTableWidget::item {{ padding: 6px 10px; color: {_TEXT}; }}"
            f"QTableWidget::item:selected {{ background: #2A2A33; }}"
            "QHeaderView::section {"
            f" background: {_BG}; color: {_MUTED}; font-weight: 600;"
            " padding: 6px; border: none; }"
            f"{{ alternate-background-color: #1A1A22; }}"
        )
        root.addWidget(self._table, 1)

    def _load_defaults(self) -> None:
        self._items_edit.setText("\n".join(_SCAN_DEFAULTS))

    def _on_scan(self) -> None:
        items = [
            line.strip() for line in self._items_edit.toPlainText().splitlines()
            if line.strip()
        ]
        if not items:
            return
        self._scan_items = list(items)
        self._scan_results = []
        self._table.setRowCount(0)
        self._scan_btn.setEnabled(False)
        self._status.setText("Escaneando... (respeitando rate limit)")

        def work() -> None:
            for i, name in enumerate(self._scan_items):
                overview = steam_api.get_market_overview(name)
                page = steam_api.get_market_page_data(name)
                merged = dict(overview) if overview else {}
                merged["page_data"] = page
                merged["_scan_name"] = name
                merged["_scan_index"] = i
                self._bridge.market_done.emit(merged)
                import time
                time.sleep(4)  # rate limit ~20/min -> 3s between calls

            # Signal done
            self._bridge.market_done.emit({"_scan_done": True})

        threading.Thread(target=work, daemon=True).start()

    def _on_item_scanned(self, data: dict) -> None:
        if data.get("_scan_done"):
            self._scan_btn.setEnabled(True)
            self._status.setText(
                f"Scan concluido. {len(self._scan_results)} itens analisados "
                f"(melhor score: {self._scan_results[0]['score']}%)"
                if self._scan_results else "Nenhum resultado."
            )
            return

        name = data.get("_scan_name", "")
        if not name:
            return

        lowest = data.get("lowest")
        median = data.get("median")
        volume = data.get("volume")
        page_data = data.get("page_data")
        order_book = (page_data or {}).get("order_book")

        verdict = steam_api.fair_value_verdict(
            lowest, median,
            spread=(order_book or {}).get("spread"),
            buy_count=(order_book or {}).get("buy_count"),
            sell_count=(order_book or {}).get("sell_count"),
            price_history=(page_data or {}).get("price_history"),
        )
        score = signals.scan_score(verdict)

        row_data = {
            "name": name,
            "price": lowest,
            "median": median,
            "verdict": verdict.get("verdict", ""),
            "spread": verdict.get("spread_verdict", ""),
            "book": verdict.get("book_verdict", ""),
            "trend": verdict.get("trend_verdict", ""),
            "score": score,
            "message": verdict.get("message", ""),
        }
        self._scan_results.append(row_data)
        self._scan_results.sort(key=lambda r: -r["score"])

        # Refresh table
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._scan_results))
        for row, r in enumerate(self._scan_results):
            score_color = _GREEN if r["score"] >= 60 else (_RED if r["score"] < 30 else "#FACC15")

            items_data = [
                r["name"],
                _brl(r["price"]) if r["price"] else "N/D",
                _brl(r["median"]) if r["median"] else "N/D",
                r["verdict"].replace("_", " "),
                r["spread"].replace("_", " ") if r["spread"] else "-",
                r["book"].replace("_", " ") if r["book"] else "-",
                r["trend"] if r["trend"] else "-",
                f"{r['score']}%",
            ]
            for col, text in enumerate(items_data):
                item = QTableWidgetItem(text)
                if col == 7:
                    item.setForeground(QColor(score_color))
                    item.setFont(QFont("", 10, QFont.Weight.Bold))
                elif col == 4 and r.get("spread"):
                    item.setForeground(
                        QColor(_GREEN if r["spread"] == "tight" else _RED)
                    )
                elif col == 5 and r.get("book"):
                    item.setForeground(
                        QColor(_GREEN if r["book"] == "buyer_dominant" else _RED)
                    )
                self._table.setItem(row, col, item)

        self._table.setSortingEnabled(True)
        self._status.setText(
            f"Escaneando... {len(self._scan_results)}/{len(self._scan_items)} itens"
        )


class WatchlistTab(QWidget):
    """Aba Watchlist: monitora precos e notifica quando atinge o alvo."""

    _CHECK_INTERVAL_MS = 300000  # 5 min

    def __init__(self, cache: prices.PriceCache,
                 tray_icon: QSystemTrayIcon | None = None) -> None:
        super().__init__()
        self._cache = cache
        self._bridge = _Bridge()
        self._tray = tray_icon
        self._last_items: list[dict] = []
        self._build()
        self._init_tray()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_all)
        self._timer.start(self._CHECK_INTERVAL_MS)
        self._check_all()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Alvo (R$)", "Atual (R$)", "Status"]
        )
        actions = [
            ("Remover", self._on_remove),
            ("Editar alvo", self._on_edit_target),
        ]
        _setup_table(self._table, "watchlist", actions)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1, 2, 3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        saved = _load_column_widths("watchlist")
        if saved:
            for i, w in enumerate(saved):
                if i < self._table.columnCount():
                    hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                    self._table.setColumnWidth(i, w)

        def _save_w() -> None:
            _save_column_widths("watchlist", [
                self._table.columnWidth(i) for i in range(self._table.columnCount())
            ])
        hh.sectionResized.connect(_save_w)

        QShortcut(QKeySequence("Delete"), self).activated.connect(self._on_remove)

        root.addWidget(self._table, 1)

        self._filter_inp = QLineEdit()
        self._filter_inp.setPlaceholderText("Filtrar por nome do item...")
        self._filter_inp.setStyleSheet(_input_style())
        self._filter_inp.textChanged.connect(self._apply_filter)
        root.addWidget(self._filter_inp)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(self._status)

        form = QHBoxLayout()
        self._name_inp = QLineEdit()
        self._name_inp.setPlaceholderText(
            "Nome exato do item (ex.: AK-47 | Redline (Field-Tested))"
        )
        self._name_inp.setStyleSheet(
            _input_style()
        )
        self._name_inp.returnPressed.connect(self._on_add)
        form.addWidget(self._name_inp, 1)

        self._target_inp = QLineEdit()
        self._target_inp.setPlaceholderText("Alvo (R$)")
        self._target_inp.setFixedWidth(120)
        self._target_inp.setStyleSheet(
            _input_style()
        )
        self._target_inp.returnPressed.connect(self._on_add)
        form.addWidget(self._target_inp)

        add_btn = QPushButton("Adicionar")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setToolTip("Adiciona item a watchlist para monitoramento")
        add_btn.setStyleSheet(
            _btn_primary()
        )
        add_btn.clicked.connect(self._on_add)
        form.addWidget(add_btn)
        root.addLayout(form)

        btn_row = QHBoxLayout()
        rem_btn = QPushButton("Remover selecionado")
        rem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rem_btn.setToolTip("Remove o item selecionado da watchlist")
        rem_btn.setStyleSheet(
            _btn_danger()
        )
        rem_btn.clicked.connect(self._on_remove)
        btn_row.addWidget(rem_btn)

        edit_wl_btn = QPushButton("Editar alvo")
        edit_wl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_wl_btn.setToolTip("Altera o preco alvo do item selecionado")
        edit_wl_btn.setStyleSheet(
            _btn_secondary("8px 18px", "10pt")
        )
        edit_wl_btn.clicked.connect(self._on_edit_target)
        btn_row.addWidget(edit_wl_btn)

        check_btn = QPushButton("Verificar agora")
        check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        check_btn.setToolTip("Verifica precos agora (padrao: a cada 5 min)")
        check_btn.setStyleSheet(
            _btn_secondary()
        )
        check_btn.clicked.connect(self._check_all)
        btn_row.addWidget(check_btn)

        clear_all_btn = QPushButton("Limpar tudo")
        clear_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_all_btn.setToolTip("Remove todos os itens da watchlist")
        clear_all_btn.setStyleSheet(
            _btn_danger()
        )
        clear_all_btn.clicked.connect(self._on_clear_watchlist)
        btn_row.addWidget(clear_all_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

    def _init_tray(self) -> None:
        if self._tray is not None:
            return
        if QSystemTrayIcon is None:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(_make_tray_icon(), self)
        self._tray.show()

    def _notify(self, name: str, current: float, target: float) -> None:
        if self._tray is None:
            return
        self._tray.showMessage(
            "SkinVault - Alerta",
            f"{name}\n"
            f"Preco atual: {_brl(current)} (alvo: {_brl(target)})",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def _on_add(self) -> None:
        name = self._name_inp.text().strip()
        if not name:
            return
        try:
            target = float(self._target_inp.text().strip().replace(",", "."))
        except ValueError:
            return
        watchlist.add_watch(name, target)
        self._name_inp.clear()
        self._target_inp.clear()
        self._check_all()

    def _on_remove(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()),
                      reverse=True)
        if not rows:
            self._status.setText("Nenhum item selecionado na watchlist.")
            return
        items = watchlist.load_watchlist()
        rows = [r for r in rows if r < len(items)]
        if not rows:
            return
        confirm = QMessageBox.question(
            self, "Remover item",
            f"Remover {len(rows)} item(ns) da watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for r in reversed(rows):
            items.pop(r)
        watchlist.save_watchlist(items)
        self._check_all()

    def _on_edit_target(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            self._status.setText("Nenhum item selecionado na watchlist.")
            return
        items = watchlist.load_watchlist()
        if row >= len(items):
            return
        it = items[row]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Editar alvo: {it['name']}")
        dlg.resize(360, 160)
        dlg.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                          " font-family: 'Segoe UI';")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.addWidget(QLabel(
            f"Item: {it['name']}",
            styleSheet=f"color: {_MUTED}; font-size: 10pt;"
        ))
        inp = QLineEdit(str(it["target"]))
        inp.setPlaceholderText("Novo preco alvo (R$)")
        inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Alvo (R$):"))
        layout.addWidget(inp)
        btns = QHBoxLayout()
        ok_btn = QPushButton("Salvar")
        ok_btn.setStyleSheet(_btn_primary("8px 18px", "10pt"))
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(_btn_secondary())
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            new_target = float(inp.text().strip().replace(",", "."))
        except ValueError:
            self._status.setText("Valor invalido.")
            return
        watchlist.update_target(it["name"], new_target)
        self._status.setText(f"Alvo atualizado: {_brl(new_target)}")
        self._check_all()

    def _on_clear_watchlist(self) -> None:
        items = watchlist.load_watchlist()
        if not items:
            self._status.setText("Watchlist ja esta vazia.")
            return
        confirm = QMessageBox.question(
            self, "Limpar watchlist",
            f"Remover todos os {len(items)} itens da watchlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        watchlist.clear_watchlist()
        self._status.setText("Watchlist limpa.")
        self._check_all()

    def _check_all(self) -> None:
        items = watchlist.load_watchlist()
        if not items:
            self._table.setRowCount(0)
            self._status.setText(
                "Nenhum item na watchlist. Adicione um item e um preco alvo."
            )
            return
        self._status.setText("Verificando precos...")

        def work() -> None:
            for it in items:
                it["_current"] = prices.cached_price(it["name"], self._cache)
            self._bridge.watchlist_done.emit(items)

        threading.Thread(target=work, daemon=True).start()

    def _apply_filter(self) -> None:
        text = self._filter_inp.text().strip().lower()
        if not self._last_items:
            return
        self._table.setRowCount(len(self._last_items))
        visible = 0
        for r, it in enumerate(self._last_items):
            match = not text or text in it["name"].lower()
            self._table.setRowHidden(r, not match)
            if match:
                visible += 1
        if text:
            self._status.setText(
                f"Mostrando {visible} de {len(self._last_items)} itens"
            )

    def _on_check_done(self, items: list[dict]) -> None:
        self._last_items = list(items)
        n_alerts = 0
        self._table.setRowCount(len(items))
        for r, it in enumerate(items):
            name = it["name"]
            target = it["target"]
            current = it.get("_current")
            was_triggered = it.get("triggered", False)

            self._table.setItem(r, 0, QTableWidgetItem(name))
            self._table.setItem(r, 1, QTableWidgetItem(_brl(target)))

            if current is None:
                self._table.setItem(r, 2, QTableWidgetItem("N/D"))
                st = QTableWidgetItem("N/D")
                st.setForeground(QColor(_MUTED))
                self._table.setItem(r, 3, st)
                continue

            self._table.setItem(r, 2, QTableWidgetItem(_brl(current)))

            is_triggered = current <= target
            if is_triggered:
                if not was_triggered:
                    self._notify(name, current, target)
                    it["triggered"] = True
                    n_alerts += 1
                st = QTableWidgetItem("ALERTA!")
                st.setForeground(QColor(_RED))
            else:
                st = QTableWidgetItem("Monitorando")
                st.setForeground(QColor(_GREEN))
            self._table.setItem(r, 3, st)

        if n_alerts:
            watchlist.save_watchlist(items)
            msg = f"{n_alerts} alerta(s) disparado(s)! Veja a tabela."
            self._status.setText(msg)
        elif items:
            self._status.setText(
                f"{len(items)} item(ns) monitorado(s)."
                f" Proxima verificacao em 5 min."
            )


class TradeTab(QWidget):
    """Aba Trade Analyzer: trades realizados com P&L real pos-taxa."""

    def __init__(self) -> None:
        super().__init__()
        self._filter_kw = ""
        self._filter_tag = ""
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        self._stats = QLabel("")
        self._stats.setStyleSheet(f"color: {_TEXT}; font-size: 11pt; font-weight: 600;")
        root.addWidget(self._stats)

        filter_row = QHBoxLayout()
        self._search_inp = QLineEdit()
        self._search_inp.setPlaceholderText("Filtrar por item ou nota...")
        self._search_inp.setStyleSheet(
            _input_style()
        )
        self._search_inp.textChanged.connect(self._refresh)
        filter_row.addWidget(self._search_inp, 1)

        self._tag_filter = QComboBox()
        self._tag_filter.addItem("Todas as tags")
        self._tag_filter.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px 12px; font-size: 11pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 28px; }"
            "QComboBox QAbstractItemView {"
            f" background: {_SURFACE}; color: {_TEXT};"
            " selection-background-color: #2A2A33;"
            " border: 1px solid #3A3A44; }"
        )
        self._tag_filter.currentTextChanged.connect(self._refresh)
        filter_row.addWidget(self._tag_filter)

        self._pnl_filter = QComboBox()
        self._pnl_filter.addItems(["Todos", "Só lucro", "Só prejuízo"])
        self._pnl_filter.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px 12px; font-size: 11pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 28px; }"
            "QComboBox QAbstractItemView {"
            f" background: {_SURFACE}; color: {_TEXT};"
            " selection-background-color: #2A2A33;"
            " border: 1px solid #3A3A44; }"
        )
        self._pnl_filter.currentTextChanged.connect(self._refresh)
        filter_row.addWidget(self._pnl_filter)

        root.addLayout(filter_row)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Compra", "Venda", "Qtd", "Dias", "Lucro Real", "ROI"]
        )
        actions = [
            ("Editar notas/tags", self._on_edit),
            ("Remover", self._on_remove_trade),
        ]
        _setup_table(self._table, "trades", actions)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        saved = _load_column_widths("trades")
        if saved:
            for i, w in enumerate(saved):
                if i < self._table.columnCount():
                    hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                    self._table.setColumnWidth(i, w)

        def _save_w() -> None:
            _save_column_widths("trades", [
                self._table.columnWidth(i) for i in range(self._table.columnCount())
            ])
        hh.sectionResized.connect(_save_w)

        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self._on_export_csv)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._on_remove_trade)

        self._month_chart = MonthBarChart()
        self._month_chart.setStyleSheet(
            f"background: {_SURFACE}; border-radius: 10px;"
        )
        root.addWidget(self._month_chart)

        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setToolTip("Recarrega lista de trades")
        refresh_btn.setStyleSheet(
            _btn_secondary()
        )
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)

        edit_btn = QPushButton("Editar notas/tags")
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setToolTip("Edita notas e tags do trade selecionado")
        edit_btn.setStyleSheet(
            _btn_secondary()
        )
        edit_btn.clicked.connect(self._on_edit)
        btn_row.addWidget(edit_btn)

        rem_btn = QPushButton("Remover selecionado")
        rem_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rem_btn.setToolTip("Remove o trade selecionado do historico")
        rem_btn.setStyleSheet(
            _btn_danger("8px 18px", "10pt")
        )
        rem_btn.clicked.connect(self._on_remove_trade)
        btn_row.addWidget(rem_btn)

        clear_btn = QPushButton("Limpar historico")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setToolTip("Apaga todo o historico de trades")
        clear_btn.setStyleSheet(
            _btn_danger()
        )
        clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(clear_btn)

        export_btn = QPushButton("Exportar CSV")
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.setToolTip("Exporta historico de trades para arquivo CSV")
        export_btn.setStyleSheet(
            _btn_secondary()
        )
        export_btn.clicked.connect(self._on_export_csv)
        btn_row.addWidget(export_btn)

        export_m_btn = QPushButton("Exportar Mensal")
        export_m_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_m_btn.setToolTip("Exporta breakdown mensal de P&L para CSV")
        export_m_btn.setStyleSheet(
            _btn_secondary()
        )
        export_m_btn.clicked.connect(self._on_export_monthly)
        btn_row.addWidget(export_m_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        self._filter_kw = self._search_inp.text().strip()
        self._filter_tag = self._tag_filter.currentText()
        tag_filter = (
            [] if self._filter_tag in ("", "Todas as tags")
            else [self._filter_tag]
        )
        pnl_text = self._pnl_filter.currentText()
        pnl_filter = {"Todos": None, "Só lucro": "profit", "Só prejuízo": "loss"}.get(pnl_text)
        filtered = trades.filter_trades(
            keyword=self._filter_kw or None,
            tags=tag_filter or None,
            pnl=pnl_filter,
        )
        stats = trades.trade_stats(filtered)
        if not filtered:
            self._table.setRowCount(0)
            self._stats.setText("Nenhum trade encontrado.")
            self._rebuild_tag_list()
            return

        lines = []
        sign = "+" if stats["pnl_total"] >= 0 else ""
        lines.append(
            f"{stats['total']} trades  |  "
            f"P&L: {sign}{_brl(abs(stats['pnl_total']))}  |  "
            f"Taxas: {_brl(stats['fees_total'])}  |  "
            f"Win rate: {stats['win_rate']}%  "
            f"({stats['win_count']}W / {stats['loss_count']}L)"
        )
        if stats["avg_days"]:
            lines.append(f"Dias medio: {stats['avg_days']}d")
        if stats["best"]:
            b = stats["best"]
            lines.append(
                f"Melhor: {b['name']} ({_brl(b['pnl'])})"
            )
        if stats["worst"]:
            w = stats["worst"]
            lines.append(
                f"Pior: {w['name']} ({_brl(w['pnl'])})"
            )
        for m in stats.get("monthly", []):
            msign = "+" if m["pnl"] >= 0 else ""
            lines.append(
                f"{m['month']}: {m['trades']} trades, "
                f"{msign}{_brl(abs(m['pnl']))}"
            )
        self._stats.setText("  |  ".join(lines))
        self._month_chart.set_months(stats.get("monthly", []))

        self._table.setRowCount(len(filtered))
        for r, t in enumerate(reversed(filtered)):
            days_held = max(0, (t["sell_ts"] - t["buy_ts"]) / 86400)
            buy_date = time.strftime("%d/%m/%Y", time.localtime(t["buy_ts"]))
            sell_date = time.strftime("%d/%m/%Y", time.localtime(t["sell_ts"]))
            tooltip = (
                f"{t['name']}\n"
                f"Compra: {buy_date}  |  Venda: {sell_date}"
            )
            if days_held >= 1:
                tooltip += f"  |  {int(days_held)} dia(s)"
            else:
                tooltip += "  |  Mesmo dia"
            if t.get("notes"):
                tooltip += f"\n\nNotas: {t['notes']}"
            if t.get("tags"):
                tooltip += f"\nTags: {', '.join(t['tags'])}"
            name_item = QTableWidgetItem(t["name"])
            name_item.setToolTip(tooltip)
            self._table.setItem(r, 0, name_item)
            self._table.setItem(r, 1, QTableWidgetItem(_brl(t["cost_total"])))
            sell_total = t["sell_price"] * t["quantity"]
            self._table.setItem(r, 2, QTableWidgetItem(_brl(sell_total)))
            self._table.setItem(r, 3, QTableWidgetItem(str(t["quantity"])))
            self._table.setItem(r, 4, QTableWidgetItem(
                f"{int(days_held)}d" if days_held >= 1 else "< 1d"
            ))

            pnl = t["pnl"]
            tag = "+" if pnl >= 0 else "-"
            pnl_item = QTableWidgetItem(tag + _brl(abs(pnl)))
            pnl_item.setForeground(QColor(_GREEN if pnl >= 0 else _RED))
            self._table.setItem(r, 5, pnl_item)

            roi_item = QTableWidgetItem(f"{t['pnl_pct']:+.1f}%")
            roi_item.setForeground(QColor(_GREEN if pnl >= 0 else _RED))
            self._table.setItem(r, 6, roi_item)

        self._rebuild_tag_list()

    def _rebuild_tag_list(self) -> None:
        current = self._tag_filter.currentText()
        all_tags: set[str] = set()
        for t in trades.load_trades():
            all_tags.update(t.get("tags", []))
        self._tag_filter.blockSignals(True)
        self._tag_filter.clear()
        self._tag_filter.addItem("Todas as tags")
        for tag in sorted(all_tags):
            self._tag_filter.addItem(tag)
        idx = self._tag_filter.findText(current)
        if idx >= 0:
            self._tag_filter.setCurrentIndex(idx)
        self._tag_filter.blockSignals(False)

    def _on_edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        all_trades = trades.load_trades()
        if row >= len(all_trades):
            return
        idx = len(all_trades) - 1 - row
        t = all_trades[idx]
        dlg = QDialog(self)
        dlg.setWindowTitle("Editar trade")
        dlg.resize(400, 280)
        dlg.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                          " font-family: 'Segoe UI';")
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        layout.addWidget(QLabel(
            f"Item: {t['name']}",
            styleSheet=f"color: {_MUTED}; font-size: 10pt;"
        ))
        notes_inp = QLineEdit(t.get("notes", ""))
        notes_inp.setPlaceholderText("Notas sobre este trade...")
        notes_inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Notas:"))
        layout.addWidget(notes_inp)

        tags_inp = QLineEdit(", ".join(t.get("tags", [])))
        tags_inp.setPlaceholderText("Tags separadas por virgula (ex.: skin, profit)")
        tags_inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Tags:"))
        layout.addWidget(tags_inp)

        cost_inp = QLineEdit(f"{t['buy_cost']:.2f}".replace(".", ","))
        cost_inp.setPlaceholderText("Preco de compra por unidade")
        cost_inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Preço de compra:"))
        layout.addWidget(cost_inp)

        sell_inp = QLineEdit(f"{t['sell_price']:.2f}".replace(".", ","))
        sell_inp.setPlaceholderText("Preco de venda por unidade")
        sell_inp.setStyleSheet(_input_style())
        layout.addWidget(QLabel("Preço de venda:"))
        layout.addWidget(sell_inp)

        btns = QHBoxLayout()
        ok_btn = QPushButton("Salvar")
        ok_btn.setStyleSheet(_btn_primary("8px 18px", "10pt"))
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(ok_btn)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setStyleSheet(_btn_secondary())
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        notes = notes_inp.text().strip()
        tags = [t.strip() for t in tags_inp.text().split(",") if t.strip()]
        try:
            new_cost = float(cost_inp.text().strip().replace(",", "."))
        except ValueError:
            new_cost = t["buy_cost"]
        try:
            new_sell = float(sell_inp.text().strip().replace(",", "."))
        except ValueError:
            new_sell = t["sell_price"]
        trades.update_trade(idx, notes=notes, tags=tags, cost=new_cost, sell_price=new_sell)
        self._refresh()

    def _on_remove_trade(self) -> None:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()),
                      reverse=True)
        if not rows:
            return
        filtered = trades.filter_trades(
            keyword=self._filter_kw or None,
            tags=([self._filter_tag] if self._filter_tag
                  and self._filter_tag != "Todas as tags" else None),
        )
        all_trades = trades.load_trades()
        rows = [r for r in rows if r < len(filtered)]
        if not rows:
            return
        names = []
        for r in rows:
            t = filtered[-(r + 1)]
            idx = all_trades.index(t)
            trades.remove_trade(idx)
            names.append(t["name"])
        self._refresh()
        self._stats.setText(
            f"{len(rows)} trade(s) removido(s): {', '.join(names[:3])}"
            + ("..." if len(names) > 3 else "")
        )

    def _on_clear(self) -> None:
        confirm = QMessageBox.question(
            self, "Limpar historico",
            "Apagar todo o historico de trades?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        trades.clear_trades()
        self._refresh()

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Trades", "trades.csv", "CSV (*.csv)"
        )
        if not path:
            return
        all_trades = trades.load_trades()
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Item,Compra,Venda,Qtd,Lucro Real,ROI,Notas,Tags\n")
                for t in all_trades:
                    name = t["name"].replace(",", " ")
                    notes = t.get("notes", "").replace(",", " ").replace("\n", " ")
                    tags = ";".join(t.get("tags", []))
                    f.write(
                        f'{name},{t["cost_total"]},{t["sell_price"]},{t["quantity"]},'
                        f'{t["pnl"]},{t["pnl_pct"]},{notes},{tags}\n'
                    )
            self._stats.setText("Trades exportados para CSV.")
        except Exception as e:
            self._stats.setText(f"Erro ao exportar: {e}")

        self._refresh()

    def _on_export_monthly(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Mensal", "trades_mensal.csv", "CSV (*.csv)"
        )
        if not path:
            return
        stats = trades.trade_stats(trades.load_trades())
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("Mes,Trades,P&L\n")
                for m in stats.get("monthly", []):
                    f.write(f'{m["month"]},{m["trades"]},{m["pnl"]}\n')
            self._stats.setText("Mensal exportado para CSV.")
        except Exception as e:
            self._stats.setText(f"Erro ao exportar mensal: {e}")


class SimuladorTab(QWidget):
    """Simulador de lucro: custo total vs. recebido pos-taxa."""

    def __init__(self) -> None:
        super().__init__()
        self._build()
        s = load_settings()
        last = s.get("last_scenario")
        if last:
            self._buy_inp.setText(last.get("buy", ""))
            self._sell_inp.setText(last.get("sell", ""))
            self._qty_inp.setText(last.get("qty", "1"))
            self._calc()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        title = QLabel("Simulador de Lucro")
        title.setStyleSheet(
            f"color: {_TEXT}; font-size: 14pt; font-weight: 700;"
        )
        root.addWidget(title)

        cap = QLabel(
            "Veja o quanto voce realmente ganha depois da taxa de 15% da Steam."
        )
        cap.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        cap.setWordWrap(True)
        root.addWidget(cap)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._buy_inp = QLineEdit()
        self._buy_inp.setPlaceholderText("Preco de compra por unidade")
        self._buy_inp.setStyleSheet(_input_style())
        self._buy_inp.returnPressed.connect(self._calc)
        form.addRow("Compra (R$):", self._buy_inp)

        self._sell_inp = QLineEdit()
        self._sell_inp.setPlaceholderText("Preco de venda por unidade")
        self._sell_inp.setStyleSheet(_input_style())
        self._sell_inp.returnPressed.connect(self._calc)
        form.addRow("Venda (R$):", self._sell_inp)

        self._qty_inp = QLineEdit("1")
        self._qty_inp.setStyleSheet(_input_style())
        self._qty_inp.returnPressed.connect(self._calc)
        form.addRow("Qtd:", self._qty_inp)

        root.addLayout(form)

        calc_btn = QPushButton("Calcular")
        calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        calc_btn.setToolTip("Calcula lucro real considerando taxa Steam de 15%")
        calc_btn.setStyleSheet(_btn_primary())
        calc_btn.clicked.connect(self._calc)
        root.addWidget(calc_btn)

        scn_row = QHBoxLayout()
        self._scn_combo = QComboBox()
        self._scn_combo.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px 10px; font-size: 10pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 24px; }"
            f"QComboBox QAbstractItemView {{ background: {_SURFACE};"
            f" color: {_TEXT}; selection-background-color: #2A2A33; }}"
        )
        self._scn_combo.activated.connect(self._load_scenario)
        scn_row.addWidget(self._scn_combo, 1)

        save_scn_btn = QPushButton("Salvar")
        save_scn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_scn_btn.setToolTip("Salva valores atuais como cenario")
        save_scn_btn.setStyleSheet(_btn_secondary("8px 16px", "9pt"))
        save_scn_btn.clicked.connect(self._save_scenario)
        scn_row.addWidget(save_scn_btn)

        root.addLayout(scn_row)

        self._results = QWidget()
        self._results.setStyleSheet(
            f"background: {_SURFACE}; border-radius: 10px;"
        )
        res = QVBoxLayout(self._results)
        res.setSpacing(8)
        res.setContentsMargins(16, 16, 16, 16)

        self._cost_lbl = QLabel("")
        self._cost_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._cost_lbl)

        self._gross_lbl = QLabel("")
        self._gross_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._gross_lbl)

        self._fee_lbl = QLabel("")
        self._fee_lbl.setStyleSheet(f"color: {_MUTED}; font-size: 10pt;")
        res.addWidget(self._fee_lbl)

        self._net_lbl = QLabel("")
        self._net_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._net_lbl)

        sep2 = QLabel(
            "────────────────────────────────────"
        )
        sep2.setStyleSheet(f"color: #2A2A33; font-size: 9pt;")
        res.addWidget(sep2)

        self._pnl_lbl = QLabel("")
        self._pnl_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 13pt; font-weight: 700;"
        )
        res.addWidget(self._pnl_lbl)

        self._roi_lbl = QLabel("")
        self._roi_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11pt;")
        res.addWidget(self._roi_lbl)

        self._warn_lbl = QLabel("")
        self._warn_lbl.setStyleSheet(
            f"color: {_RED}; font-size: 10pt; font-weight: 600;"
        )
        self._warn_lbl.setWordWrap(True)
        res.addWidget(self._warn_lbl)

        self._results.hide()
        root.addWidget(self._results)
        root.addStretch()

    def _calc(self) -> None:
        try:
            buy = float(self._buy_inp.text().strip().replace(",", "."))
            sell = float(self._sell_inp.text().strip().replace(",", "."))
            qty = int(self._qty_inp.text().strip() or "1")
        except ValueError:
            return

        cost_total = buy * qty
        gross = sell * qty
        fee = gross * 0.15
        net = gross - fee
        pnl = net - cost_total
        pnl_pct = (pnl / cost_total * 100) if cost_total else 0.0

        self._cost_lbl.setText(f"Custo total:      {_brl(cost_total)}")
        self._gross_lbl.setText(f"Venda bruta:      {_brl(gross)}")
        self._fee_lbl.setText(f"Taxa Steam (15%):  {_brl(fee)}")
        self._net_lbl.setText(f"Voce recebe:      {_brl(net)}")

        sign = "+" if pnl >= 0 else "-"
        color = _GREEN if pnl >= 0 else _RED
        self._pnl_lbl.setStyleSheet(
            f"color: {color}; font-size: 13pt; font-weight: 700;"
        )
        self._pnl_lbl.setText(f"LUCRO REAL: {sign}{_brl(abs(pnl))}")
        self._roi_lbl.setText(f"ROI: {pnl_pct:+.1f}%")
        self._roi_lbl.setStyleSheet(f"color: {color}; font-size: 11pt;")

        if buy > net / qty:
            self._warn_lbl.setText(
                "Atencao: voce esta vendendo por menos do que pagou "
                "depois da taxa da Steam."
            )
            self._warn_lbl.show()
        else:
            self._warn_lbl.hide()

        self._results.show()
        self._rebuild_scenario_combo()
        self._auto_save_scenario()

    def _auto_save_scenario(self) -> None:
        buy = self._buy_inp.text().strip()
        sell = self._sell_inp.text().strip()
        if buy and sell:
            s = load_settings()
            s["last_scenario"] = {"buy": buy, "sell": sell, "qty": self._qty_inp.text().strip() or "1"}
            save_settings(s)

    def _scenarios_path(self) -> str:
        p = DATA_DIR / "scenarios.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)

    def _load_scenarios(self) -> list[dict]:
        import json, os
        path = self._scenarios_path()
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_scenarios(self, scenarios: list[dict]) -> None:
        import json
        path = self._scenarios_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(scenarios, f, indent=2)
        except Exception:
            pass

    def _rebuild_scenario_combo(self) -> None:
        scenarios = self._load_scenarios()
        self._scn_combo.blockSignals(True)
        self._scn_combo.clear()
        self._scn_combo.addItem("Carregar cenario...")
        for s in scenarios:
            self._scn_combo.addItem(s["name"])
        self._scn_combo.blockSignals(False)

    def _save_scenario(self) -> None:
        buy = self._buy_inp.text().strip()
        sell = self._sell_inp.text().strip()
        qty = self._qty_inp.text().strip()
        if not buy or not sell:
            return
        scenarios = self._load_scenarios()
        name = f"{buy}x{sell} (qty {qty or 1})"
        count = sum(1 for s in scenarios if s["name"] == name)
        if count:
            name += f" ({count + 1})"
        scenarios.append({"name": name, "buy": buy, "sell": sell, "qty": qty or "1"})
        self._save_scenarios(scenarios)
        self._rebuild_scenario_combo()
        self._scn_combo.setCurrentIndex(len(scenarios))  # placeholder + count

    def _load_scenario(self, idx: int) -> None:
        scenarios = self._load_scenarios()
        if idx <= 0 or not scenarios:
            return
        s = scenarios[idx - 1]
        self._buy_inp.setText(s["buy"])
        self._sell_inp.setText(s["sell"])
        self._qty_inp.setText(s.get("qty", "1"))
        self._calc()


class SettingsDialog(QDialog):
    """Dialogo de configuracao do SkinVault."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = load_settings()
        self.setWindowTitle("Configuracoes")
        self.resize(420, 300)
        self.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                           " font-family: 'Segoe UI';")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("Configuracoes")
        title.setStyleSheet(
            f"color: {_TEXT}; font-size: 13pt; font-weight: 700;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._cache_ttl = QLineEdit(str(self._settings.get("cache_ttl_hours", 6)))
        self._cache_ttl.setPlaceholderText("Horas")
        self._cache_ttl.setStyleSheet(_input_style())
        form.addRow("Cache TTL (h):", self._cache_ttl)

        self._fee_rate = QLineEdit(str(self._settings.get("fee_rate", 0.15)))
        self._fee_rate.setPlaceholderText("Ex.: 0.15")
        self._fee_rate.setStyleSheet(_input_style())
        form.addRow("Taxa Steam:", self._fee_rate)

        self._auto_backup = QLineEdit(
            "Sim" if self._settings.get("auto_backup", True) else "Nao"
        )
        self._auto_backup.setPlaceholderText("Sim ou Nao")
        self._auto_backup.setStyleSheet(_input_style())
        form.addRow("Backup auto:", self._auto_backup)

        self._keep_backups = QLineEdit(str(self._settings.get("keep_backups", 10)))
        self._keep_backups.setPlaceholderText("Numero de backups")
        self._keep_backups.setStyleSheet(_input_style())
        form.addRow("Manter backups:", self._keep_backups)

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Escuro", "Claro"])
        current = self._settings.get("theme", "dark")
        self._theme_combo.setCurrentIndex(0 if current == "dark" else 1)
        self._theme_combo.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px 10px; font-size: 10pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 24px; }"
            f"QComboBox QAbstractItemView {{ background: {_SURFACE};"
            f" color: {_TEXT}; selection-background-color: #2A2A33; }}"
        )
        form.addRow("Tema:", self._theme_combo)

        self._start_min = QLineEdit(
            "Sim" if self._settings.get("start_minimized", False) else "Nao"
        )
        self._start_min.setPlaceholderText("Sim ou Nao")
        self._start_min.setStyleSheet(_input_style())
        form.addRow("Iniciar minimizado:", self._start_min)

        layout.addLayout(form)
        layout.addStretch()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Salvar")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(_btn_primary())
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(_btn_secondary())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _save(self) -> None:
        try:
            ttl = int(self._cache_ttl.text().strip())
        except ValueError:
            ttl = 6
        try:
            fee = float(self._fee_rate.text().strip().replace(",", "."))
        except ValueError:
            fee = 0.15
        backup_val = self._auto_backup.text().strip().lower()
        auto_backup = backup_val in ("sim", "s", "yes", "y", "true", "1")
        try:
            keep = int(self._keep_backups.text().strip())
        except ValueError:
            keep = 10
        theme = "dark" if self._theme_combo.currentIndex() == 0 else "light"
        start_min = self._start_min.text().strip().lower() in ("sim", "s", "yes", "y", "true", "1")
        self._settings = {
            "cache_ttl_hours": max(1, ttl),
            "fee_rate": max(0, min(1, fee)),
            "auto_backup": auto_backup,
            "keep_backups": max(0, keep),
            "theme": theme,
            "start_minimized": start_min,
        }
        save_settings(self._settings)
        self.accept()


class BackupDialog(QDialog):
    """Gerenciador de backups: listar, restaurar, deletar."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar Backups")
        self.resize(520, 360)
        self.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                           " font-family: 'Segoe UI';")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("Backups dos dados")
        title.setStyleSheet(
            f"color: {_TEXT}; font-size: 13pt; font-weight: 700;"
        )
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px; font-size: 10pt;"
            f" color: {_TEXT}; }}"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #2A2A33; }"
        )
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(_btn_secondary())
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)

        restore_btn = QPushButton("Restaurar")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setStyleSheet(_btn_primary("8px 18px", "10pt"))
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(restore_btn)

        delete_btn = QPushButton("Deletar")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(_btn_danger())
        delete_btn.clicked.connect(self._delete)
        btn_row.addWidget(delete_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Fechar")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(_btn_secondary())
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for b in backup.list_backups():
            dt = time.strftime("%d/%m/%Y %H:%M", time.localtime(b["mtime"]))
            size_kb = b["size"] / 1024
            self._list.addItem(
                f"{b['name']}  ({size_kb:.0f} KB)  -  {dt}"
            )

    def _selected_path(self) -> str | None:
        row = self._list.currentRow()
        if row < 0:
            return None
        backups = backup.list_backups()
        if row >= len(backups):
            return None
        return backups[row]["path"]

    def _restore(self) -> None:
        path = self._selected_path()
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Restaurar backup",
            "Restaurar este backup?\n"
            "Os dados atuais serao SUBSTITUIDOS.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        count = backup.restore_backup(path)
        if count:
            QMessageBox.information(
                self, "Restaurado",
                f"{count} arquivo(s) restaurados com sucesso."
            )
        else:
            QMessageBox.warning(self, "Erro", "Falha ao restaurar backup.")

    def _delete(self) -> None:
        path = self._selected_path()
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Deletar backup",
            "Deletar este backup permanentemente?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if backup.delete_backup(path):
            self._refresh()
        else:
            QMessageBox.warning(self, "Erro", "Falha ao deletar backup.")


class MainWindow(QTabWidget):
    def __init__(self) -> None:
        super().__init__()
        settings = load_settings()
        theme = settings.get("theme", "dark")
        set_theme(theme)
        self._current_theme = theme
        self.setWindowTitle("SkinVault")
        geo = settings.get("window_geometry", {})
        if geo.get("w") and geo.get("h"):
            self.resize(geo["w"], geo["h"])
        else:
            self.resize(720, 640)
        self._apply_stylesheet()
        ttl = settings.get("cache_ttl_hours", 6) * 3600
        self._cache = prices.PriceCache(ttl=ttl)

        self._tray_icon: QSystemTrayIcon | None = None
        self._init_tray()

        self.addTab(InventoryTab(self._cache), "Inventario")
        self.addTab(PortfolioTab(self._cache), "Meu Portfolio")
        self.addTab(MarketTab(), "Market Browser")
        self.addTab(WatchlistTab(self._cache, self._tray_icon), "Watchlist")
        self.addTab(TradeTab(), "Trade Analyzer")
        self.addTab(SimuladorTab(), "Simulador")
        self.addTab(ScannerTab(), "Scanner")

        cfg_btn = QPushButton("Config")
        cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cfg_btn.setToolTip("Configuracoes do SkinVault")
        cfg_btn.setStyleSheet(
            "QPushButton { color: #9D9DA8; background: transparent;"
            " border: 1px solid #3A3A44; border-radius: 6px;"
            " padding: 6px 14px; font-size: 9pt; }"
            "QPushButton:hover { color: #E6E6EA; border-color: #5A5A66; }"
        )
        cfg_btn.clicked.connect(self._open_settings)

        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_filter)
        QShortcut(QKeySequence("?"), self).activated.connect(self._show_shortcuts)

        about_btn = QPushButton("Sobre")
        about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        about_btn.setToolTip("Sobre o SkinVault")
        about_btn.setStyleSheet(
            "QPushButton { color: #9D9DA8; background: transparent;"
            " border: 1px solid #3A3A44; border-radius: 6px;"
            " padding: 6px 14px; font-size: 9pt; }"
            "QPushButton:hover { color: #E6E6EA; border-color: #5A5A66; }"
        )
        about_btn.clicked.connect(self._open_about)

        backup_btn = QPushButton("Backups")
        backup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        backup_btn.setToolTip("Gerenciar backups dos dados")
        backup_btn.setStyleSheet(
            "QPushButton { color: #9D9DA8; background: transparent;"
            " border: 1px solid #3A3A44; border-radius: 6px;"
            " padding: 6px 14px; font-size: 9pt; }"
            "QPushButton:hover { color: #E6E6EA; border-color: #5A5A66; }"
        )
        backup_btn.clicked.connect(self._open_backups)

        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(6)
        corner_layout.addWidget(about_btn)
        corner_layout.addWidget(backup_btn)
        corner_layout.addWidget(cfg_btn)
        self.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        if settings.get("auto_backup", True):
            backup.make_backup()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {_BG}; }}"
            f"QTabBar::tab {{ background: {_SURFACE}; color: {_MUTED};"
            " padding: 10px 24px; border: none;"
            " border-bottom: 2px solid transparent;"
            " font-size: 10pt; font-weight: 600; font-family: 'Segoe UI'; }"
            f"QTabBar::tab:selected {{ color: {_TEXT};"
            f" border-bottom: 2px solid {_GREEN}; }}"
            f"QTabBar::tab:hover {{ color: {_TEXT}; }}"
        )

    def _init_tray(self) -> None:
        if QSystemTrayIcon is None:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = _make_tray_icon()
        self._tray_icon = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        if hasattr(QMenu, "setStyleSheet"):
            menu.setStyleSheet(
                f"QMenu {{ background: {_SURFACE}; color: {_TEXT};"
                " border: 1px solid #3A3A44; padding: 4px; }"
                "QMenu::item { padding: 6px 20px; }"
                "QMenu::item:selected { background: #2A2A33; }"
            )
        restore_action = menu.addAction("Abrir SkinVault")
        restore_action.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        quit_action = menu.addAction("Sair")
        quit_action.triggered.connect(QApplication.instance().quit)
        self._tray_icon.setContextMenu(menu)
        self._tray_icon.setToolTip("SkinVault - Gerenciador de portfolio CS2")
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    def _save_geometry(self) -> None:
        s = load_settings()
        s["window_geometry"] = {"w": self.width(), "h": self.height()}
        save_settings(s)

    def closeEvent(self, evt) -> None:  # noqa: N802
        self._save_geometry()
        has_data = bool(portfolio.load_portfolio()) or bool(trades.load_trades())
        if has_data:
            confirm = QMessageBox.question(
                self, "Sair",
                "Tem dados nao salvos. Deseja realmente sair?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                evt.ignore()
                return
        if self._tray_icon is not None:
            self.hide()
            evt.ignore()
        else:
            evt.accept()

    def _open_backups(self) -> None:
        dlg = BackupDialog(self)
        dlg.exec()

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Atalhos de teclado",
            "<b>Atalhos globais:</b><br>"
            "? &nbsp;&nbsp; Mostra esta janela<br><br>"
            "<b>Portfolio:</b><br>"
            "Ctrl+O &nbsp;&nbsp; Importar CSV<br>"
            "Ctrl+E &nbsp;&nbsp; Exportar CSV<br>"
            "Del &nbsp;&nbsp;&nbsp; Remover selecionado(s)<br>"
            "Enter &nbsp;&nbsp; Confirmar formulario<br><br>"
            "<b>Trades:</b><br>"
            "Ctrl+E &nbsp;&nbsp; Exportar CSV<br>"
            "Del &nbsp;&nbsp;&nbsp; Remover trade(s) selecionado(s)<br><br>"
            "<b>Geral:</b><br>"
            "Duplo clique no item &nbsp;&nbsp; Abrir Steam Market<br>"
            "Botao direito &nbsp;&nbsp; Menu de contexto",
        )

    def _focus_filter(self) -> None:
        w = self.currentWidget()
        for attr in ("_filter_inp", "_search_inp"):
            inp = getattr(w, attr, None)
            if inp:
                inp.setFocus()
                inp.selectAll()
                break

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        s = load_settings()
        theme = s.get("theme", "dark")
        if theme != self._current_theme:
            set_theme(theme)
            self._apply_stylesheet()
            QMessageBox.information(
                self, "Tema alterado",
                "Reinicie o SkinVault para aplicar o novo tema completamente."
            )

    def _open_about(self) -> None:
        QMessageBox.about(
            self, "Sobre o SkinVault",
            "<b>SkinVault</b> v1.0<br><br>"
            "Avaliacao de inventario CS2 sem login.<br>"
            "Precos publicos da Steam Community Market.<br><br>"
            "Lucro real apos taxa de 15% da Steam.<br>"
            "Nao preve futuro — so' dados factuais.<br><br>"
            "Feito por Pedro S. | 2026",
        )


def launch() -> int:
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    win = MainWindow()
    settings = load_settings()
    if settings.get("start_minimized", False) and win._tray_icon is not None:
        win.hide()
    else:
        win.show()
    return app.exec()
