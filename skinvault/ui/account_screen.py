"""Tela 1 - Minha Conta + Inventario (F11).

Header: avatar + nome Steam + SteamID + 4 stat cards.
Corpo: filtro + tabela inventario.
Acao: botao "Sincronizar com Steam".

Reusa:
  portfolio.load_portfolio / evaluate_portfolio
  prices.PriceCache
  profile_fetcher.fetch_public_profile
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import portfolio as portfolio_mod
from skinvault import prices, steam_session
from skinvault.ui import theme as t
from skinvault.ui._price_worker import PriceWorker
from skinvault.ui.components import Avatar, Card, StatCard
from skinvault.ui.profile_fetcher import (
    fetch_public_profile,
    load_avatar_bytes,
    load_cached_profile,
)
from skinvault.ui.widgets import MiniSparkline


class _AccountBridge(QObject):
    profile_ready = pyqtSignal(dict)


class AccountScreen(QWidget):
    """Tela 1 -- Minha Conta + Inventario."""

    COL_NAME = 0
    COL_QTY = 1
    COL_PRICE = 2
    COL_SUBTOTAL = 3
    COL_RECEIVED = 4
    COL_PNL = 5
    COL_ORIGIN = 6

    request_sync = pyqtSignal()

    def __init__(self, cache: prices.PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._session: steam_session.SteamSession | None = None
        self._bridge = _AccountBridge()
        self._bridge.profile_ready.connect(self._on_profile)
        self._price_worker = PriceWorker(cache, self)
        self._price_worker.eval_done.connect(self._on_eval)
        self._price_worker.progress.connect(self._on_eval_progress)
        self._build()

    def set_session(self, session: steam_session.SteamSession | None) -> None:
        self._session = session
        self._reload_profile()
        self.refresh()

    # ── construcao do layout ──────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Header card
        header = Card(self, padding=(20, 18, 20, 18))
        hlay = QHBoxLayout()
        hlay.setSpacing(18)

        self._avatar = Avatar(size=72, parent=header)
        hlay.addWidget(self._avatar)

        ident = QVBoxLayout()
        ident.setSpacing(2)
        self._name = QLabel("—")
        self._name.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        ident.addWidget(self._name)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)

        self._sub = QLabel("Conecte sua conta para sincronizar.")
        self._sub.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        sub_row.addWidget(self._sub)

        self._profile_link = QLabel("")
        self._profile_link.setStyleSheet(
            f"color: {t.STEAM_BLUE}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; text-decoration: underline;"
        )
        self._profile_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_link.mousePressEvent = lambda _: self._open_steam_profile()
        sub_row.addWidget(self._profile_link)

        sub_row.addStretch(1)
        ident.addLayout(sub_row)
        ident.addStretch(1)
        hlay.addLayout(ident, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        self._sync_btn = QPushButton("Sincronizar com Steam")
        self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_btn.setStyleSheet(t.btn_steam())
        self._sync_btn.clicked.connect(self.request_sync.emit)
        btn_col.addWidget(self._sync_btn, 0, Qt.AlignmentFlag.AlignRight)

        self._last_sync_lbl = QLabel("")
        self._last_sync_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        btn_col.addWidget(self._last_sync_lbl, 0, Qt.AlignmentFlag.AlignRight)

        hlay.addLayout(btn_col, 0)

        # Substituir layout default do card
        header.layout().addLayout(hlay)

        # Stat cards row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_gross = StatCard("Valor bruto (Market)", "—")
        self._stat_net = StatCard("Valor líquido (-15%)", "—",
                                  accent=t.STEAM_BLUE)
        self._stat_pnl = StatCard("P&L total", "—")
        self._stat_items = StatCard("Total de itens", "0")
        for sc in (self._stat_gross, self._stat_net, self._stat_pnl,
                   self._stat_items):
            stats_row.addWidget(sc, 1)
        header.layout().addLayout(stats_row)

        root.addWidget(header)

        # Portfolio breakdown card
        breakdown_card = Card(self, padding=(16, 14, 16, 14))
        bd_lay = QVBoxLayout()
        bd_lay.setSpacing(8)
        bd_title = QLabel("Desempenho da carteira")
        bd_title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
        )
        bd_lay.addWidget(bd_title)

        bd_row = QHBoxLayout()
        bd_row.setSpacing(16)
        self._bd_invested = StatCard("Total investido", "—")
        self._bd_profit_count = StatCard("Itens no lucro", "—",
                                         accent=t.ACCENT)
        self._bd_loss_count = StatCard("Itens no prejuizo", "—",
                                       accent=t.DANGER)
        self._bd_best = StatCard("Melhor P&L", "—")
        self._bd_worst = StatCard("Pior P&L", "—", accent=t.DANGER)
        for sc in (self._bd_invested, self._bd_profit_count,
                   self._bd_loss_count, self._bd_best, self._bd_worst):
            bd_row.addWidget(sc, 1)
        bd_lay.addLayout(bd_row)
        breakdown_card.layout().addLayout(bd_lay)
        self._breakdown_card = breakdown_card
        root.addWidget(breakdown_card)

        # Filtro
        filt = QLineEdit()
        filt.setPlaceholderText("Filtrar por nome do item...")
        filt.setToolTip(
            "Filtra a tabela por nome (case-insensitive). Ctrl+F foca; Esc limpa."
        )
        filt.setClearButtonEnabled(True)
        filt.setStyleSheet(t.input_style())
        filt.textChanged.connect(self._apply_filter)
        self._filter_inp = filt
        root.addWidget(filt)

        # Progress bar (indeterminate, hidden by default)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE}; border: none;"
            f" border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {t.ACCENT};"
            " border-radius: 3px; }}"
        )
        root.addWidget(self._progress)

        # Tabela
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Item", "Qtd", "Preço atual", "Subtotal", "Recebido (-15%)",
            "P&L", "Origem",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setStyleSheet(t.table_style())
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(max(self.COL_QTY, self.COL_ORIGIN + 1)):
            if i != self.COL_NAME:
                hh.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        from PyQt6.QtGui import QKeySequence, QShortcut
        find_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        find_sc.activated.connect(self._focus_filter)
        esc_sc = QShortcut(QKeySequence("Esc"), self)
        esc_sc.activated.connect(self._filter_inp.clear)

    def _focus_filter(self) -> None:
        self._filter_inp.setFocus()
        self._filter_inp.selectAll()

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(self._status)

    # ── perfil ───────────────────────────────────────────
    def _reload_profile(self) -> None:
        s = self._session
        if not s or not s.steamid:
            self._name.setText("—")
            self._sub.setText("Conecte sua conta para sincronizar.")
            return

        # 1. tenta cache imediato (rapido)
        cached = load_cached_profile(s.steamid)
        if cached:
            self._on_profile(cached)

        # 2. atualiza em background
        steamid = s.steamid

        def worker() -> None:
            data = fetch_public_profile(steamid)
            if data:
                self._bridge.profile_ready.emit(data)

        threading.Thread(target=worker, daemon=True).start()

    def _open_steam_profile(self) -> None:
        if self._session and self._session.steamid:
            url = f"https://steamcommunity.com/profiles/{self._session.steamid}"
            QDesktopServices.openUrl(QUrl(url))

    def _on_profile(self, data: dict) -> None:
        steamid = data.get("steamid", "")
        self._name.setText(data.get("name") or "—")
        self._sub.setText(f"SteamID: {steamid}")
        if steamid:
            self._profile_link.setText("Ver perfil na Steam ›")
            self._profile_link.setVisible(True)
        else:
            self._profile_link.setVisible(False)
        path = data.get("avatar_path")
        if path:
            self._avatar.set_image(path)
        else:
            avbytes = load_avatar_bytes(steamid)
            if avbytes:
                self._avatar.set_image(avbytes)

    # ── avaliacao de inventario ──────────────────────────
    def refresh(self) -> None:
        """Avalia portfolio em thread e atualiza tabela + stats."""
        self._progress.setVisible(True)
        self._status.setText("Avaliando inventario...")
        self._price_worker.start()

    def _on_eval_progress(self, done: int, total: int) -> None:
        self._status.setText(f"Avaliando inventario... {done}/{total}")

    def _on_eval(self, data: dict) -> None:
        rows = data["rows"]
        totals = data["totals"]
        positions = data.get("positions", [])
        self._progress.setVisible(False)
        # Atualiza stats
        self._stat_gross.set_value(t.brl(totals.get("market") or 0))
        self._stat_net.set_value(t.brl(totals.get("net_if_sold") or 0),
                                 accent=t.STEAM_BLUE)
        pnl = totals.get("pnl") or 0
        pnl_color = t.ACCENT if pnl >= 0 else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_color)
        self._stat_items.set_value(str(len(rows)))

        # Portfolio breakdown
        total_cost = sum(
            r.get("cost_total", 0) or 0 for r in rows
        )
        profit_items = sum(1 for r in rows if (r.get("pnl") or 0) > 0)
        loss_items = sum(1 for r in rows if (r.get("pnl") or 0) < 0)
        best = max(rows, key=lambda r: r.get("pnl") or 0) if rows else None
        worst = min(rows, key=lambda r: r.get("pnl") or 0) if rows else None
        self._bd_invested.set_value(t.brl(total_cost))
        self._bd_profit_count.set_value(
            f"{profit_items} ({profit_items/len(rows)*100:.0f}%)" if rows else "0",
            accent=t.ACCENT
        )
        self._bd_loss_count.set_value(
            f"{loss_items} ({loss_items/len(rows)*100:.0f}%)" if rows else "0",
            accent=t.DANGER
        )
        self._bd_best.set_value(
            f"{t.brl(best['pnl'])} ({best.get('name','')[:20]})" if best else "—",
            accent=t.ACCENT
        )
        self._bd_worst.set_value(
            f"{t.brl(worst['pnl'])} ({worst.get('name','')[:20]})" if worst else "—",
            accent=t.DANGER
        )

        # Atualiza tabela
        self._populate_table(rows, data["positions"])
        now = time.strftime('%H:%M')
        self._status.setText(
            f"{len(rows)} item(ns) • atualizado {now}"
        )
        self._last_sync_lbl.setText(f"Ultima sync: {now}")

    def _populate_table(self, rows: list[dict],
                        positions: list[dict]) -> None:
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, r in enumerate(rows):
            self._table.insertRow(i)
            src = positions[i].get("source", "manual") if i < len(positions) else "manual"
            origin = "Steam" if src == "steam_sync" else "Manual"
            cells = [
                r.get("name") or "—",
                str(r.get("quantity") or 1),
                t.brl(r.get("price")),
                t.brl(r.get("market")),
                t.brl(r.get("net_if_sold")),
                t.brl(r.get("pnl")),
                origin,
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if col == self.COL_PNL:
                    pnl = r.get("pnl")
                    if pnl is not None:
                        item.setForeground(
                            QBrush(QColor(t.ACCENT if pnl >= 0 else t.DANGER))
                        )
                elif col == self.COL_ORIGIN and origin == "Steam":
                    item.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                self._table.setItem(i, col, item)
        self._table.setSortingEnabled(was_sorting)

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for row in range(self._table.rowCount()):
            name = self._table.item(row, 0)
            visible = not text or (name and text in name.text().lower())
            self._table.setRowHidden(row, not visible)
