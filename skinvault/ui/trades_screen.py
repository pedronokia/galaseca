"""Tela — Trades (F11).

CRUD de trades com filtros (periodo + resultado), edicao inline e
estatisticas fee-aware.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import trades as trades_mod
from skinvault.ui import theme as t
from skinvault.ui.components import RecentMatchesStrip, SegmentedControl, StatCard


_PERIODS = [
    ("all", "Tudo", None),
    ("7d", "7 dias", 7),
    ("30d", "30 dias", 30),
    ("90d", "90 dias", 90),
    ("365d", "Ano", 365),
]

_RESULTS = [
    ("all", "Todos"),
    ("profit", "Apenas lucro"),
    ("loss", "Apenas prejuízo"),
]


def _fmt_date(ts: float) -> str:
    if not ts:
        return "—"
    return time.strftime("%d/%m/%Y", time.localtime(ts))


def _source_label(source: str) -> tuple[str, str]:
    """(label, color) para a coluna Origem."""
    if source == "steam_sync" or source == "steam":
        return ("Steam", t.STEAM_BLUE)
    return ("Manual", t.TEXT_MUTED)


class _TradeDialog(QDialog):
    """Dialog para adicionar/editar trade."""

    def __init__(self, trade: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            "Editar trade" if trade else "Adicionar trade"
        )
        self.setMinimumWidth(420)
        self._trade = trade
        self._build()

    def _build(self) -> None:
        tr = self._trade or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_inp = QLineEdit(tr.get("name", ""))
        self._name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        form.addRow("Item:", self._name_inp)

        self._buy_inp = QDoubleSpinBox()
        self._buy_inp.setRange(0, 999999)
        self._buy_inp.setPrefix("R$ ")
        self._buy_inp.setValue(tr.get("buy_cost", 0))
        form.addRow("Preço de compra (unitário):", self._buy_inp)

        self._sell_inp = QDoubleSpinBox()
        self._sell_inp.setRange(0, 999999)
        self._sell_inp.setPrefix("R$ ")
        self._sell_inp.setValue(tr.get("sell_price", 0))
        form.addRow("Preço de venda (unitário, bruto):", self._sell_inp)

        self._qty_inp = QSpinBox()
        self._qty_inp.setRange(1, 999)
        self._qty_inp.setValue(tr.get("quantity", 1))
        form.addRow("Quantidade:", self._qty_inp)

        self._notes_inp = QLineEdit(tr.get("notes", ""))
        self._notes_inp.setPlaceholderText("Opcional")
        form.addRow("Notas:", self._notes_inp)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "name": self._name_inp.text().strip(),
            "buy_cost": self._buy_inp.value(),
            "sell_price": self._sell_inp.value(),
            "quantity": self._qty_inp.value(),
            "notes": self._notes_inp.text().strip(),
        }


class TradesScreen(QWidget):
    """Tela de Trades com CRUD, filtros e stats fee-aware."""

    COL_DATE = 0
    COL_NAME = 1
    COL_QTY = 2
    COL_COST = 3
    COL_SELL = 4
    COL_PNL = 5
    COL_ROI = 6
    COL_SOURCE = 7
    COL_NOTES = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trades: list[dict] = []
        self._filtered: list[dict] = []
        self._period_key = "all"
        self._result_key = "all"
        self._build()
        self.refresh()

    # ── construcao ────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # Header: titulo + subtitulo + acoes
        hdr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel("Histórico de Trades")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        subtitle = QLabel(
            "P&L líquido após a taxa de 15% da Steam, com filtros por "
            "período e resultado."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        col.addWidget(title)
        col.addWidget(subtitle)
        hdr.addLayout(col, 1)

        self._add_btn = QPushButton("Adicionar trade")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(t.btn_primary())
        self._add_btn.setToolTip(
            "Registra um trade manual com compra, venda e quantidade.\n"
            "Atalho: Ctrl+N."
        )
        self._add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self._add_btn)

        self._more_btn = QPushButton("⋯")
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.setStyleSheet(t.btn_ghost(padding="10px 14px",
                                                 fs=t.FS_BODY))
        self._more_btn.setToolTip("Mais ações.")
        self._more_menu = QMenu(self._more_btn)
        self._act_edit = self._more_menu.addAction("Editar selecionado")
        self._act_edit.triggered.connect(self._on_edit_selected)
        self._act_remove = self._more_menu.addAction("Remover selecionado")
        self._act_remove.triggered.connect(self._on_remove_selected)
        self._more_menu.addSeparator()
        self._act_clear = self._more_menu.addAction("Limpar tudo…")
        self._act_clear.triggered.connect(self._on_clear)
        self._more_btn.setMenu(self._more_menu)
        hdr.addWidget(self._more_btn)
        root.addLayout(hdr)

        # Stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_total = StatCard("Trades no filtro", "0")
        self._stat_total.setToolTip(
            "Quantidade de trades que casam com o filtro atual."
        )
        self._stat_pnl = StatCard("P&L líquido", "—")
        self._stat_pnl.setToolTip(
            "Lucro/prejuízo total já descontada a taxa Steam de 15%."
        )
        self._stat_winrate = StatCard("Taxa de acerto", "—")
        self._stat_winrate.setToolTip(
            "% de trades com P&L positivo (winning trades / total)."
        )
        self._stat_fees = StatCard("Taxas pagas", "—")
        self._stat_fees.setToolTip(
            "Soma das taxas Steam (15%) pagas pelos trades no filtro."
        )
        for sc in (self._stat_total, self._stat_pnl, self._stat_winrate,
                   self._stat_fees):
            stats_row.addWidget(sc, 1)
        root.addLayout(stats_row)

        # Recent Matches strip — chips W/L horizontais
        self._matches_strip = RecentMatchesStrip(self)
        root.addWidget(self._matches_strip)

        # Filtros: periodo + resultado em uma linha horizontal
        filt_row = QHBoxLayout()
        filt_row.setSpacing(10)

        self._period_seg = SegmentedControl(self)
        for key, label, _days in _PERIODS:
            self._period_seg.add(key, label)
        self._period_seg.segment_changed.connect(self._on_period)
        filt_row.addWidget(self._period_seg)

        sep = QLabel("•")
        sep.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
        )
        filt_row.addWidget(sep)

        self._result_seg = SegmentedControl(self)
        for key, label in _RESULTS:
            self._result_seg.add(key, label)
        self._result_seg.segment_changed.connect(self._on_result)
        filt_row.addWidget(self._result_seg)

        filt_row.addStretch(1)
        root.addLayout(filt_row)

        # Search
        search_row = QHBoxLayout()
        self._filter_inp = QLineEdit()
        self._filter_inp.setPlaceholderText(
            "Filtrar por nome ou nota… (Ctrl+F)"
        )
        self._filter_inp.setStyleSheet(t.input_style())
        self._filter_inp.setClearButtonEnabled(True)
        self._filter_inp.setToolTip(
            "Filtra por substring no nome do item ou nas notas."
        )
        self._filter_inp.textChanged.connect(lambda _: self._apply_filter())
        search_row.addWidget(self._filter_inp, 1)
        root.addLayout(search_row)

        # Tabela
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["Data", "Item", "Qtd", "Compra", "Venda",
             "P&L líquido", "ROI", "Origem", "Notas"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setStyleSheet(t.table_style())
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in (self.COL_DATE, self.COL_QTY, self.COL_COST, self.COL_SELL,
                  self.COL_PNL, self.COL_ROI, self.COL_SOURCE):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_NOTES,
                                QHeaderView.ResizeMode.Interactive)
        self._table.doubleClicked.connect(lambda _idx: self._on_edit_selected())
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.customContextMenuRequested.connect(self._on_ctx_menu)
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(self._status)

        # Atalhos
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self._filter_inp.setFocus
        )
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            self._on_add
        )
        QShortcut(QKeySequence("Delete"), self).activated.connect(
            self._on_remove_selected
        )
        QShortcut(QKeySequence("Return"), self._table).activated.connect(
            self._on_edit_selected
        )

    # ── filtros ───────────────────────────────────────────
    def refresh(self) -> None:
        self._trades = trades_mod.load_trades()
        # Strip mostra os 15 mais recentes independente de filtro
        sorted_recent = sorted(
            self._trades,
            key=lambda tr: tr.get("sell_ts") or tr.get("buy_ts") or 0,
            reverse=True,
        )
        self._matches_strip.set_trades(sorted_recent)
        self._apply_filter()

    def _on_period(self, key: str) -> None:
        self._period_key = key
        self._apply_filter()

    def _on_result(self, key: str) -> None:
        self._result_key = key
        self._apply_filter()

    def _apply_filter(self) -> None:
        keyword = (self._filter_inp.text() or "").strip().lower()
        days = next((d for k, _, d in _PERIODS if k == self._period_key), None)
        cutoff = time.time() - (days * 86400) if days else None

        rows = list(self._trades)
        if cutoff is not None:
            rows = [
                tr for tr in rows
                if (tr.get("sell_ts") or tr.get("buy_ts") or 0) >= cutoff
            ]
        if self._result_key == "profit":
            rows = [tr for tr in rows if (tr.get("pnl") or 0) > 0]
        elif self._result_key == "loss":
            rows = [tr for tr in rows if (tr.get("pnl") or 0) < 0]
        if keyword:
            rows = [
                tr for tr in rows
                if keyword in (tr.get("name", "")).lower()
                or keyword in (tr.get("notes", "")).lower()
            ]
        self._filtered = rows
        self._populate()

    # ── populate ──────────────────────────────────────────
    def _populate(self) -> None:
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, tr in enumerate(self._filtered):
            self._table.insertRow(i)
            pnl = tr.get("pnl") or 0
            pnl_color = t.ACCENT if pnl >= 0 else t.DANGER
            src_label, src_color = _source_label(tr.get("source", "manual"))
            sell_ts = tr.get("sell_ts") or tr.get("buy_ts") or 0
            roi = (tr.get("pnl_pct") or 0)
            from skinvault.localization import localize_name as _ln
            cells = [
                (_fmt_date(sell_ts), None),
                (_ln(tr.get("name", "")), None),
                (str(tr.get("quantity", 1)), None),
                (t.brl(tr.get("buy_cost", 0)), None),
                (t.brl(tr.get("sell_price", 0)), None),
                (t.brl(pnl), pnl_color),
                (f"{roi:+.1f}%", pnl_color),
                (src_label, src_color),
                (tr.get("notes", ""), None),
            ]
            for col, (val, color) in enumerate(cells):
                item = QTableWidgetItem(str(val))
                if color:
                    item.setForeground(QBrush(QColor(color)))
                # Guarda o indice original do trade pra editar/remover
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole,
                                 self._trades.index(tr))
                self._table.setItem(i, col, item)
        self._table.setSortingEnabled(was_sorting)

        # Stats sobre o filtrado
        stats = trades_mod.trade_stats(trades=self._filtered)
        self._stat_total.set_value(str(stats["total"]))

        pnl = stats["pnl_total"]
        pnl_c = t.ACCENT if pnl >= 0 else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_c)

        # win_rate ja vem em 0-100
        wr = stats.get("win_rate", 0) or 0
        wr_c = t.ACCENT if wr >= 50 else (t.WARN if wr >= 30 else t.DANGER)
        wr_extra = f"  ({stats['win_count']}W / {stats['loss_count']}L)"
        self._stat_winrate.set_value(f"{wr:.0f}%{wr_extra}", accent=wr_c)

        fees = stats.get("fees_total", 0)
        self._stat_fees.set_value(t.brl(fees))

        total_all = len(self._trades)
        if total_all == stats["total"]:
            self._status.setText(f"{stats['total']} trade(s).")
        else:
            self._status.setText(
                f"{stats['total']} de {total_all} trade(s) — filtro ativo."
            )

    # ── helpers de selecao ────────────────────────────────
    def _selected_index(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        if not item:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(idx, int):
            return None
        return idx

    # ── acoes ─────────────────────────────────────────────
    def _on_add(self) -> None:
        dlg = _TradeDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            QMessageBox.warning(self, "Trade",
                                "O nome do item é obrigatório.")
            return
        trades_mod.record_trade(
            data["name"], data["buy_cost"], data["sell_price"],
            data["quantity"], notes=data["notes"],
        )
        self.refresh()

    def _on_edit_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            self._status.setText("Selecione um trade para editar.")
            return
        trade = self._trades[idx]
        if trade.get("source") not in (None, "manual"):
            r = QMessageBox.question(
                self, "Editar trade",
                "Este trade veio do sync com a Steam. Edições manuais podem "
                "ser sobrescritas no próximo sync. Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if r != QMessageBox.StandardButton.Yes:
                return
        dlg = _TradeDialog(trade=trade, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            QMessageBox.warning(self, "Trade",
                                "O nome do item é obrigatório.")
            return
        trades_mod.update_trade(
            idx,
            cost=data["buy_cost"],
            sell_price=data["sell_price"],
            name=data["name"],
            quantity=data["quantity"],
            notes=data["notes"],
        )
        self.refresh()

    def _on_remove_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            self._status.setText("Selecione um trade para remover.")
            return
        trade = self._trades[idx]
        r = QMessageBox.question(
            self, "Remover trade",
            f"Remover “{trade.get('name', '')}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r != QMessageBox.StandardButton.Yes:
            return
        trades_mod.remove_trade(idx)
        self.refresh()

    def _on_clear(self) -> None:
        if not self._trades:
            self._status.setText("Nenhum trade para remover.")
            return
        r = QMessageBox.question(
            self, "Limpar todos os trades",
            f"Tem certeza? Todos os {len(self._trades)} trades serão "
            "removidos. Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            trades_mod.clear_trades()
            self.refresh()

    def _on_ctx_menu(self, pos) -> None:
        if self._table.currentRow() < 0:
            return
        menu = QMenu(self._table)
        act_edit = menu.addAction("Editar trade…")
        act_rm = menu.addAction("Remover trade")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == act_edit:
            self._on_edit_selected()
        elif action == act_rm:
            self._on_remove_selected()
