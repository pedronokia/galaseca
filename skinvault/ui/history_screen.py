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

from PyQt6.QtCore import Qt, pyqtSignal
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

from skinvault import portfolio, sync, trade_matcher, trades, watchlist
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui._price_worker import BatchPriceWorker
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


# ── Barra horizontal com filtros ──────────────────────────────
class _FilterBar(QWidget):
    """Barra horizontal compacta com chips de filtro (periodo + tipo)."""

    filters_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._periodo: str = "all"
        self._tipo: str = "all"
        self._periodo_btns: dict[str, QPushButton] = {}
        self._tipo_btns: dict[str, QPushButton] = {}
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # Periodo
        p_label = QLabel("Periodo:")
        p_label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(p_label)
        for key, label in [("7d", "7d"), ("30d", "30d"),
                           ("90d", "90d"), ("all", "Tudo")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._chip_style())
            btn.clicked.connect(lambda _, k=key: self._set_periodo(k))
            self._periodo_btns[key] = btn
            root.addWidget(btn)
            if key == "all":
                btn.setChecked(True)

        # Divisor
        sep = QLabel("|")
        sep.setStyleSheet(
            f"color: {t.BORDER}; font-size: {t.FS_BODY};"
            f" padding: 0 6px;"
        )
        root.addWidget(sep)

        # Tipo
        t_label = QLabel("Tipo:")
        t_label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(t_label)
        for key, label in [("all", "Todos"), ("buy", "Compra"),
                           ("sell", "Venda")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._chip_style())
            btn.clicked.connect(lambda _, k=key: self._set_tipo(k))
            self._tipo_btns[key] = btn
            root.addWidget(btn)
            if key == "all":
                btn.setChecked(True)

        # Separador
        sep2 = QLabel("|")
        sep2.setStyleSheet(
            f"color: {t.BORDER}; font-size: {t.FS_BODY};"
            f" padding: 0 6px;"
        )
        root.addWidget(sep2)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar por nome...")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {t.SURFACE}; color: {t.TEXT};"
            f" border: 1px solid {t.BORDER}; border-radius: 6px;"
            f" padding: 4px 10px; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; min-width: 240px; }}"
            f"QLineEdit:focus {{ border-color: {t.ACCENT}; }}"
        )
        self._search.textChanged.connect(self._on_search_changed)
        root.addWidget(self._search)

        root.addStretch(1)

        clear_btn = QPushButton("Limpar")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid {t.BORDER}; border-radius: 6px;"
            f" padding: 4px 12px; font-size: {t.FS_MUTED}; font-weight: 500;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; border-color: {t.TEXT_MUTED}; }}"
        )
        clear_btn.clicked.connect(self._clear)
        root.addWidget(clear_btn)

    def _chip_style(self) -> str:
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: {t.SURFACE};"
            f" border: 1px solid {t.BORDER}; border-radius: 6px;"
            f" padding: 4px 12px; font-size: {t.FS_MUTED}; font-weight: 500;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; }}"
            f"QPushButton:checked {{ color: {t.ACCENT};"
            f" border: 1px solid {t.ACCENT}; background: {t.ACCENT_DIM}; }}"
        )

    def _set_periodo(self, key: str) -> None:
        self._periodo = key
        self.filters_changed.emit()

    def _set_tipo(self, key: str) -> None:
        self._tipo = key
        self.filters_changed.emit()

    def _on_search_changed(self, _text: str) -> None:
        self.filters_changed.emit()

    def _clear(self) -> None:
        self._periodo = "all"
        self._tipo = "all"
        all_p = self._periodo_btns.get("all")
        if all_p:
            all_p.setChecked(True)
        all_t = self._tipo_btns.get("all")
        if all_t:
            all_t.setChecked(True)
        self._search.clear()
        self.filters_changed.emit()

    def set_tipo_enabled(self, enabled: bool) -> None:
        for btn in self._tipo_btns.values():
            btn.setEnabled(enabled)

    @property
    def periodo(self) -> str:
        return self._periodo

    @property
    def tipo(self) -> str:
        return self._tipo

    @property
    def search_text(self) -> str:
        return self._search.text().strip().lower()


def _in_period(ts: float, period: str) -> bool:
    if period == "all":
        return True
    days = {"7d": 7 * 86400, "30d": 30 * 86400, "90d": 90 * 86400}
    cutoff = time.time() - days.get(period, 0)
    return ts >= cutoff


# ── Tela 2 ───────────────────────────────────────────────────
class HistoryScreen(QWidget):
    """Tela 2 -- Historico unificado + Watchlist + Simulador."""

    SEGMENTS = [
        ("all", "Todos"),
        ("trades", "Trades"),
        ("matched", "Pareados"),
        ("open", "Abertas"),
        ("market", "Steam Market"),
        ("offers", "Trade Offers"),
        ("watchlist", "Watchlist"),
    ]

    def __init__(self, cache: PriceCache | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_segment = "all"
        self._matched_cache: list[trade_matcher.ClosedTrade] | None = None
        self._open_cache: list[trade_matcher.OpenBuy] | None = None
        self._price_cache = cache or PriceCache()
        self._price_worker = BatchPriceWorker(self._price_cache, self)
        self._price_worker.batch_done.connect(self._on_prices_updated)
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

        self._update_prices_btn = QPushButton("Atualizar precos")
        self._update_prices_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_prices_btn.setStyleSheet(t.btn_secondary())
        self._update_prices_btn.clicked.connect(self._on_update_prices)
        self._update_prices_btn.setVisible(False)
        top.addWidget(self._update_prices_btn)

        sim_btn = QPushButton("Simular trade")
        sim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sim_btn.setStyleSheet(t.btn_secondary())
        sim_btn.clicked.connect(self._open_simulator)
        top.addWidget(sim_btn)

        root.addLayout(top)

        # Barra horizontal de filtros (acima da tabela)
        self._filter_panel = _FilterBar(self)
        self._filter_panel.filters_changed.connect(self.refresh)
        root.addWidget(self._filter_panel)

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
        self._filter_panel.set_tipo_enabled(key == "market")
        self._update_prices_btn.setVisible(key == "open")
        self.refresh()

    def _on_update_prices(self) -> None:
        opens = self._open_cache or []
        names_missing = [
            o.name for o in opens if self._price_cache.get(o.name) is None
        ]
        if not names_missing:
            self._status.setText(
                self._status.text() + "  (todos os precos ja' estao em cache)"
            )
            return
        self._update_prices_btn.setEnabled(False)
        self._update_prices_btn.setText("Atualizando...")
        self._price_worker.start(names_missing)

    def _on_prices_updated(self) -> None:
        self._update_prices_btn.setEnabled(True)
        self._update_prices_btn.setText("Atualizar precos")
        if self._current_segment == "open":
            self.refresh()

    def refresh(self) -> None:
        seg = self._current_segment
        if seg == "trades":
            headers, rows, count, pnl_col, pnl_vals = self._load_trades()
        elif seg == "matched":
            headers, rows, count, pnl_col, pnl_vals = self._load_matched()
        elif seg == "open":
            headers, rows, count, pnl_col, pnl_vals = self._load_open()
        elif seg == "market":
            headers, rows, count, pnl_col, pnl_vals = self._load_market()
        elif seg == "offers":
            headers, rows, count, pnl_col, pnl_vals = self._load_offers()
        elif seg == "watchlist":
            headers, rows, count, pnl_col, pnl_vals = self._load_watchlist()
        else:
            headers, rows, count, pnl_col, pnl_vals = self._load_all()
        self._populate(headers, rows, pnl_col=pnl_col, pnl_vals=pnl_vals)
        if seg == "matched":
            s = trade_matcher.summarize(self._matched_cache or [])
            self._status.setText(
                f"{s['count']} pareados • P&L total {t.brl(s['total_pnl'])}"
                f" • {s['winners']}W / {s['losers']}L"
                f" ({s['win_rate']*100:.0f}% win rate)"
            )
        elif seg == "open":
            opens = self._open_cache or []
            total = sum(o.buy_price for o in opens)
            self._status.setText(
                f"{len(opens)} compras abertas • {t.brl(total)} investido"
            )
        else:
            self._status.setText(f"{count} registro(s)")

    # ── loaders ──────────────────────────────────────────
    def _load_trades(self):
        data = trades.load_trades()
        rows = []
        pnl_vals: list[float | None] = []
        periodo = self._filter_panel.periodo
        for tr in sorted(data, key=lambda x: x.get("sell_ts", 0),
                         reverse=True):
            ts = tr.get("sell_ts", 0)
            if not _in_period(ts, periodo):
                continue
            pnl = tr.get("pnl")
            pnl_vals.append(pnl)
            rows.append([
                self._fmt_ts(ts),
                tr.get("name", "—"),
                str(tr.get("quantity", 1)),
                t.brl(tr.get("buy_cost")),
                t.brl(tr.get("sell_price")),
                t.brl(pnl),
                self._fmt_source(tr.get("source", "manual")),
            ])
        return (
            ["Data", "Item", "Qtd", "Compra", "Venda", "P&L", "Origem"],
            rows, len(rows), 5, pnl_vals,
        )

    def _load_matched(self):
        closed = trade_matcher.load_closed_trades()
        periodo = self._filter_panel.periodo
        visible = [c for c in closed if _in_period(c.sell_ts, periodo)]
        self._matched_cache = visible
        rows: list[list[str]] = []
        pnl_vals: list[float | None] = []
        for c in visible:
            pnl_vals.append(c.pnl)
            rows.append([
                c.sell_date or "—",
                c.name,
                t.brl(c.buy_price),
                t.brl(c.sell_price),
                t.brl(c.pnl),
                f"{c.pnl_pct*100:+.1f}%",
            ])
        return (
            ["Vendido em", "Item", "Compra", "Venda", "P&L liquido", "ROI"],
            rows, len(rows), 4, pnl_vals,
        )

    def _load_open(self):
        opens = trade_matcher.load_open_buys()
        periodo = self._filter_panel.periodo
        search = self._filter_panel.search_text
        visible = [
            o for o in opens
            if _in_period(o.buy_ts, periodo)
            and (not search or search in o.name.lower())
        ]
        self._open_cache = visible
        rows: list[list[str]] = []
        pnl_vals: list[float | None] = []
        for o in visible:
            current = self._price_cache.get(o.name)
            if current is None:
                preco_atual_str = "—"
                pnl_str = "—"
                pnl_val: float | None = None
            else:
                d = portfolio.position_pnl(o.buy_price, current, 1)
                preco_atual_str = t.brl(current)
                pnl_str = t.brl(d["pnl"])
                pnl_val = d["pnl"]
            pnl_vals.append(pnl_val)
            rows.append([
                o.buy_date or "—",
                o.name,
                t.brl(o.buy_price),
                preco_atual_str,
                pnl_str,
            ])
        return (
            ["Comprado em", "Item", "Preco de compra",
             "Preco atual", "P&L se vender hoje"],
            rows, len(rows), 4, pnl_vals,
        )

    def _load_market(self):
        data = sync.load_market_events()
        rows = []
        periodo = self._filter_panel.periodo
        tipo = self._filter_panel.tipo
        for ev in data:
            if not _in_period(ev.get("synced_at", 0), periodo):
                continue
            side = ev.get("side", "").lower()
            if tipo != "all" and side != tipo:
                continue
            rows.append([
                ev.get("date_str", "—"),
                ev.get("name", "—"),
                ev.get("side", "—"),
                t.brl(ev.get("price")),
                ev.get("listing_id") or "—",
            ])
        return (
            ["Data", "Item", "Operação", "Preço", "Listing ID"],
            rows, len(rows), None, None,
        )

    def _load_offers(self):
        data = sync.load_trade_offers()
        rows = []
        periodo = self._filter_panel.periodo
        for of in data:
            if not _in_period(of.get("synced_at", 0), periodo):
                continue
            given = ", ".join(of.get("items_given") or [])
            rows.append([
                of.get("date_str", "—"),
                of.get("partner_steamid") or "—",
                given or "—",
                of.get("tradeofferid") or "—",
            ])
        return (
            ["Data", "Parceiro (SteamID)", "Itens", "Trade Offer ID"],
            rows, len(rows), None, None,
        )

    def _load_watchlist(self):
        data = watchlist.load_watchlist()
        rows = []
        periodo = self._filter_panel.periodo
        for w in data:
            if not _in_period(w.get("added_ts", 0), periodo):
                continue
            rows.append([
                w.get("name", "—"),
                t.brl(w.get("target")),
                "Disparado" if w.get("triggered") else "Aguardando",
                self._fmt_ts(w.get("added_ts", 0)),
            ])
        return (
            ["Item", "Preço-alvo", "Status", "Adicionado"],
            rows, len(rows), None, None,
        )

    def _load_all(self):
        """Timeline cronologica de tudo (trades + market + offers)."""
        events: list[tuple[float, list]] = []
        pnl_vals: list[float | None] = []
        periodo = self._filter_panel.periodo
        for tr in trades.load_trades():
            ts = tr.get("sell_ts", 0)
            if not _in_period(ts, periodo):
                continue
            pnl = tr.get("pnl")
            pnl_vals.append(pnl)
            events.append((ts, [
                self._fmt_ts(ts),
                "Trade",
                tr.get("name", "—"),
                t.brl(pnl),
                self._fmt_source(tr.get("source", "manual")),
            ]))
        for ev in sync.load_market_events():
            ts = ev.get("synced_at", 0)
            if not _in_period(ts, periodo):
                continue
            pnl_vals.append(None)
            events.append((ts, [
                ev.get("date_str", "—"),
                f"Market ({ev.get('side', '—')})",
                ev.get("name", "—"),
                t.brl(ev.get("price")),
                "Steam",
            ]))
        for of in sync.load_trade_offers():
            ts = of.get("synced_at", 0)
            if not _in_period(ts, periodo):
                continue
            pnl_vals.append(None)
            events.append((ts, [
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
            rows, len(rows), 3, pnl_vals,
        )

    # ── helpers ──────────────────────────────────────────
    def _fmt_ts(self, ts: float) -> str:
        if not ts:
            return "—"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

    def _fmt_source(self, src: str) -> str:
        return "Steam" if src in ("steam", "steam_sync") else "Manual"

    def _populate(self, headers: list[str], rows: list[list[str]],
                   pnl_col: int | None = None,
                   pnl_vals: list[float | None] | None = None) -> None:
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(0)
        for i, row in enumerate(rows):
            self._table.insertRow(i)
            for c, val in enumerate(row):
                it = QTableWidgetItem(val)
                # cores: P&L verde/vermelho (numeric)
                if pnl_col is not None and c == pnl_col and pnl_vals:
                    pnl = pnl_vals[i] if i < len(pnl_vals) else None
                    if pnl is not None:
                        it.setForeground(
                            QBrush(QColor(t.ACCENT if pnl >= 0 else t.DANGER))
                        )
                elif (headers[c] == "Origem"
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
