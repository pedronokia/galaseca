"""Tela 2 - Meu Historico (F11).

Segmented control: Todos / Trades / Market / Offers / Watchlist.
Tabela cronologica adapta colunas por segmento.
Botao "Simular trade" abre dialog simples.

Reusa:
  trades.load_trades, sync.load_market_events, sync.load_trade_offers,
  watchlist.load_watchlist, portfolio.simulate_trade
"""
from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import portfolio, sync, trades, watchlist
from skinvault.ui import theme as t
from skinvault.ui.components import Card, SegmentedControl


# ── Dialog: simular trade ────────────────────────────────────
class SimulateTradeDialog(QDialog):
    """Form simples buy/sell/qty -> exibe lucro real apos taxa Steam."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Simular trade")
        self.setStyleSheet(f"background: {t.BG};")
        self.resize(420, 360)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        title = QLabel("Simulador de lucro")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(title)

        cap = QLabel(
            "Veja o lucro real depois da taxa de 15% da Steam."
        )
        cap.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(cap)

        form = QFormLayout()
        form.setSpacing(10)
        self._buy = QLineEdit()
        self._buy.setPlaceholderText("0,00")
        self._buy.setStyleSheet(t.input_style())
        self._sell = QLineEdit()
        self._sell.setPlaceholderText("0,00")
        self._sell.setStyleSheet(t.input_style())
        self._qty = QLineEdit("1")
        self._qty.setStyleSheet(t.input_style())
        for w in (self._buy, self._sell, self._qty):
            w.returnPressed.connect(self._calc)
        form.addRow("Compra (R$):", self._buy)
        form.addRow("Venda (R$):", self._sell)
        form.addRow("Qtd:", self._qty)
        root.addLayout(form)

        btn = QPushButton("Calcular")
        btn.setStyleSheet(t.btn_primary())
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._calc)
        root.addWidget(btn)

        self._result = Card(self, padding=(16, 14, 16, 14))
        body = self._result.layout()
        self._pnl_lbl = QLabel("—")
        self._pnl_lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: 16pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(self._pnl_lbl)
        self._detail = QLabel("")
        self._detail.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        self._detail.setWordWrap(True)
        body.addWidget(self._detail)
        root.addWidget(self._result)

    def _parse_float(self, s: str) -> float | None:
        if not s:
            return None
        try:
            return float(s.replace(",", ".").replace("R$", "").strip())
        except ValueError:
            return None

    def _calc(self) -> None:
        buy = self._parse_float(self._buy.text())
        sell = self._parse_float(self._sell.text())
        try:
            qty = max(1, int(self._qty.text() or "1"))
        except ValueError:
            qty = 1
        if buy is None or sell is None:
            self._pnl_lbl.setText("Valores invalidos")
            self._detail.setText("Preencha compra e venda.")
            return
        r = portfolio.simulate_trade(buy, sell, qty)
        color = t.ACCENT if r["is_profit"] else (
            t.DANGER if r["is_loss"] else t.TEXT
        )
        self._pnl_lbl.setStyleSheet(
            f"color: {color}; font-size: 16pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        self._pnl_lbl.setText(
            f"{t.brl(r['pnl'])} (ROI {r['roi_pct']:+.1f}%)"
        )
        self._detail.setText(
            f"Custo total: {t.brl(r['cost_total'])} · "
            f"Bruto: {t.brl(r['gross_sale'])} · "
            f"Taxa Steam: {t.brl(r['steam_fee'])} · "
            f"Recebido líquido: {t.brl(r['net_received'])} · "
            f"Preço de empate: {t.brl(r['break_even_price'])}"
        )


# ── Tela 2 ───────────────────────────────────────────────────
class HistoryScreen(QWidget):
    """Tela 2 -- Historico unificado + Watchlist + Simulador."""

    SEGMENTS = [
        ("all", "Todos"),
        ("trades", "Trades"),
        ("market", "Steam Market"),
        ("offers", "Trade Offers"),
        ("watchlist", "Watchlist"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_segment = "all"
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        top = QHBoxLayout()
        self._seg = SegmentedControl(self)
        for key, label in self.SEGMENTS:
            self._seg.add(key, label)
        self._seg.segment_changed.connect(self._on_segment)
        top.addWidget(self._seg, 1)

        sim_btn = QPushButton("Simular trade")
        sim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sim_btn.setStyleSheet(t.btn_secondary())
        sim_btn.clicked.connect(self._open_simulator)
        top.addWidget(sim_btn)

        root.addLayout(top)

        self._table = QTableWidget(0, 0)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(t.table_style())
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(self._status)

    def _open_simulator(self) -> None:
        SimulateTradeDialog(self).exec()

    def _on_segment(self, key: str) -> None:
        self._current_segment = key
        self.refresh()

    def refresh(self) -> None:
        seg = self._current_segment
        if seg == "trades":
            headers, rows, count = self._load_trades()
        elif seg == "market":
            headers, rows, count = self._load_market()
        elif seg == "offers":
            headers, rows, count = self._load_offers()
        elif seg == "watchlist":
            headers, rows, count = self._load_watchlist()
        else:
            headers, rows, count = self._load_all()
        self._populate(headers, rows)
        self._status.setText(f"{count} registro(s)")

    # ── loaders ──────────────────────────────────────────
    def _load_trades(self):
        data = trades.load_trades()
        rows = []
        for tr in sorted(data, key=lambda x: x.get("sell_ts", 0),
                         reverse=True):
            rows.append([
                self._fmt_ts(tr.get("sell_ts", 0)),
                tr.get("name", "—"),
                str(tr.get("quantity", 1)),
                t.brl(tr.get("buy_cost")),
                t.brl(tr.get("sell_price")),
                t.brl(tr.get("pnl")),
                self._fmt_source(tr.get("source", "manual")),
            ])
        return (
            ["Data", "Item", "Qtd", "Compra", "Venda", "P&L", "Origem"],
            rows, len(rows),
        )

    def _load_market(self):
        data = sync.load_market_events()
        rows = []
        for ev in data:
            rows.append([
                ev.get("date_str", "—"),
                ev.get("name", "—"),
                ev.get("side", "—"),
                t.brl(ev.get("price")),
                ev.get("listing_id") or "—",
            ])
        return (
            ["Data", "Item", "Operação", "Preço", "Listing ID"],
            rows, len(rows),
        )

    def _load_offers(self):
        data = sync.load_trade_offers()
        rows = []
        for of in data:
            given = ", ".join(of.get("items_given") or [])
            rows.append([
                of.get("date_str", "—"),
                of.get("partner_steamid") or "—",
                given or "—",
                of.get("tradeofferid") or "—",
            ])
        return (
            ["Data", "Parceiro (SteamID)", "Itens", "Trade Offer ID"],
            rows, len(rows),
        )

    def _load_watchlist(self):
        data = watchlist.load_watchlist()
        rows = []
        for w in data:
            rows.append([
                w.get("name", "—"),
                t.brl(w.get("target")),
                "Disparado" if w.get("triggered") else "Aguardando",
                self._fmt_ts(w.get("added_ts", 0)),
            ])
        return (
            ["Item", "Preço-alvo", "Status", "Adicionado"],
            rows, len(rows),
        )

    def _load_all(self):
        """Timeline cronologica de tudo (trades + market + offers)."""
        events: list[tuple[float, list]] = []
        for tr in trades.load_trades():
            events.append((tr.get("sell_ts", 0), [
                self._fmt_ts(tr.get("sell_ts", 0)),
                "Trade",
                tr.get("name", "—"),
                t.brl(tr.get("pnl")),
                self._fmt_source(tr.get("source", "manual")),
            ]))
        for ev in sync.load_market_events():
            events.append((ev.get("synced_at", 0), [
                ev.get("date_str", "—"),
                f"Market ({ev.get('side', '—')})",
                ev.get("name", "—"),
                t.brl(ev.get("price")),
                "Steam",
            ]))
        for of in sync.load_trade_offers():
            events.append((of.get("synced_at", 0), [
                of.get("date_str", "—"),
                "Trade Offer",
                ", ".join(of.get("items_given") or []) or "—",
                "—",
                "Steam",
            ]))
        events.sort(key=lambda x: x[0], reverse=True)
        rows = [row for _, row in events]
        return (
            ["Data", "Tipo", "Item", "Valor", "Origem"],
            rows, len(rows),
        )

    # ── helpers ──────────────────────────────────────────
    def _fmt_ts(self, ts: float) -> str:
        if not ts:
            return "—"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

    def _fmt_source(self, src: str) -> str:
        return "Steam" if src in ("steam", "steam_sync") else "Manual"

    def _populate(self, headers: list[str], rows: list[list[str]]) -> None:
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(0)
        for i, row in enumerate(rows):
            self._table.insertRow(i)
            for c, val in enumerate(row):
                it = QTableWidgetItem(val)
                # cores: P&L verde/vermelho
                if val.startswith("R$") and ("-" in val or
                                             val.startswith("-")):
                    it.setForeground(QBrush(QColor(t.DANGER)))
                if (headers[c] == "Origem"
                        and val.strip().lower() == "steam"):
                    it.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                self._table.setItem(i, c, it)
        hh = self._table.horizontalHeader()
        for i in range(self._table.columnCount()):
            hh.setSectionResizeMode(
                i,
                QHeaderView.ResizeMode.Stretch if i == 1
                else QHeaderView.ResizeMode.ResizeToContents,
            )
