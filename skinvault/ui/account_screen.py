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

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import portfolio as portfolio_mod
from skinvault import prices, steam_session
from skinvault.ui import theme as t
from skinvault.ui.components import Avatar, Card, StatCard
from skinvault.ui.profile_fetcher import (
    fetch_public_profile,
    load_avatar_bytes,
    load_cached_profile,
)


class _AccountBridge(QObject):
    profile_ready = pyqtSignal(dict)
    eval_done = pyqtSignal(dict)
    sync_requested = pyqtSignal()


class AccountScreen(QWidget):
    """Tela 1 -- Minha Conta + Inventario."""

    request_sync = pyqtSignal()

    def __init__(self, cache: prices.PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._session: steam_session.SteamSession | None = None
        self._bridge = _AccountBridge()
        self._bridge.profile_ready.connect(self._on_profile)
        self._bridge.eval_done.connect(self._on_eval)
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
        self._sub = QLabel("Conecte sua conta para sincronizar.")
        self._sub.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        ident.addWidget(self._sub)
        ident.addStretch(1)
        hlay.addLayout(ident, 1)

        self._sync_btn = QPushButton("Sincronizar com Steam")
        self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_btn.setStyleSheet(t.btn_steam())
        self._sync_btn.clicked.connect(self.request_sync.emit)
        hlay.addWidget(self._sync_btn, 0, Qt.AlignmentFlag.AlignTop)

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

        # Filtro
        filt = QLineEdit()
        filt.setPlaceholderText("Filtrar por nome do item…")
        filt.setStyleSheet(t.input_style())
        filt.textChanged.connect(self._apply_filter)
        self._filter_inp = filt
        root.addWidget(filt)

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
        self._table.setStyleSheet(t.table_style())
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            hh.setSectionResizeMode(i,
                                    QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

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

    def _on_profile(self, data: dict) -> None:
        self._name.setText(data.get("name") or "—")
        self._sub.setText(f"SteamID: {data.get('steamid', '')}")
        path = data.get("avatar_path")
        if path:
            self._avatar.set_image(path)
        else:
            avbytes = load_avatar_bytes(data.get("steamid", ""))
            if avbytes:
                self._avatar.set_image(avbytes)

    # ── avaliacao de inventario ──────────────────────────
    def refresh(self) -> None:
        """Avalia portfolio em thread e atualiza tabela + stats."""
        self._status.setText("Avaliando inventário…")
        cache = self._cache

        def worker() -> None:
            positions = portfolio_mod.load_portfolio()
            result = portfolio_mod.evaluate_portfolio(
                positions, cache.cached_price
            )
            self._bridge.eval_done.emit({
                "positions": positions,
                "rows": result["rows"],
                "totals": result["totals"],
            })

        threading.Thread(target=worker, daemon=True).start()

    def _on_eval(self, data: dict) -> None:
        rows = data["rows"]
        totals = data["totals"]
        # Atualiza stats
        self._stat_gross.set_value(t.brl(totals.get("market") or 0))
        self._stat_net.set_value(t.brl(totals.get("net_if_sold") or 0),
                                 accent=t.STEAM_BLUE)
        pnl = totals.get("pnl") or 0
        pnl_color = t.ACCENT if pnl >= 0 else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_color)
        self._stat_items.set_value(str(len(rows)))

        # Atualiza tabela
        self._populate_table(rows, data["positions"])
        self._status.setText(
            f"{len(rows)} item(ns) • atualizado {time.strftime('%H:%M')}"
        )

    def _populate_table(self, rows: list[dict],
                        positions: list[dict]) -> None:
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
                if col == 5:  # P&L color
                    pnl = r.get("pnl")
                    if pnl is not None:
                        item.setForeground(
                            QBrush(QColor(t.ACCENT if pnl >= 0 else t.DANGER))
                        )
                elif col == 6 and origin == "Steam":
                    item.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                self._table.setItem(i, col, item)

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for row in range(self._table.rowCount()):
            name = self._table.item(row, 0)
            visible = not text or (name and text in name.text().lower())
            self._table.setRowHidden(row, not visible)
