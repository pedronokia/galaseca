"""Tela — Trades (F11).

CRUD de trades com filtros e estatisticas.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
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
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import trades as trades_mod
from skinvault.ui import theme as t
from skinvault.ui.components import Card, StatCard


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
        t = self._trade or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name_inp = QLineEdit(t.get("name", ""))
        self._name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        form.addRow("Item:", self._name_inp)

        self._buy_inp = QDoubleSpinBox()
        self._buy_inp.setRange(0, 999999)
        self._buy_inp.setPrefix("R$ ")
        self._buy_inp.setValue(t.get("buy_cost", 0))
        form.addRow("Preco de compra:", self._buy_inp)

        self._sell_inp = QDoubleSpinBox()
        self._sell_inp.setRange(0, 999999)
        self._sell_inp.setPrefix("R$ ")
        self._sell_inp.setValue(t.get("sell_price", 0))
        form.addRow("Preco de venda:", self._sell_inp)

        self._qty_inp = QSpinBox()
        self._qty_inp.setRange(1, 999)
        self._qty_inp.setValue(t.get("quantity", 1))
        form.addRow("Quantidade:", self._qty_inp)

        self._notes_inp = QLineEdit(t.get("notes", ""))
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
    """Tela de Trades com CRUD e stats."""

    COL_NAME = 0
    COL_QTY = 1
    COL_COST = 2
    COL_SELL = 3
    COL_PNL = 4
    COL_ROI = 5
    COL_NOTES = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trades: list[dict] = []
        self._filtered: list[dict] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Trades")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
        )
        hdr.addWidget(title)
        hdr.addStretch(1)

        self._stats_lbl = QLabel("")
        self._stats_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
        )
        hdr.addWidget(self._stats_lbl)
        hdr.addSpacing(16)

        self._add_btn = QPushButton("+ Novo trade")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(t.btn_primary())
        self._add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self._add_btn)
        root.addLayout(hdr)

        # Stats cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_total = StatCard("Total trades", "0")
        self._stat_pnl = StatCard("P&L total", "—")
        self._stat_winrate = StatCard("Win rate", "—")
        self._stat_best = StatCard("Melhor trade", "—")
        for sc in (self._stat_total, self._stat_pnl, self._stat_winrate,
                   self._stat_best):
            stats_row.addWidget(sc, 1)
        root.addLayout(stats_row)

        # Filter
        filt_row = QHBoxLayout()
        self._filter_inp = QLineEdit()
        self._filter_inp.setPlaceholderText("Filtrar por item...")
        self._filter_inp.setStyleSheet(t.input_style())
        self._filter_inp.textChanged.connect(self._on_filter)
        filt_row.addWidget(self._filter_inp, 1)

        self._clear_btn = QPushButton("Limpar tudo")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(t.btn_danger())
        self._clear_btn.clicked.connect(self._on_clear)
        filt_row.addWidget(self._clear_btn)
        root.addLayout(filt_row)

        # Tabela
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Qtd", "Compra", "Venda", "P&L", "ROI", "Notas"]
        )
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
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 7):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        root.addWidget(self._status)

    def refresh(self) -> None:
        self._trades = trades_mod.load_trades()
        self._apply_filter()

    def _apply_filter(self) -> None:
        keyword = (self._filter_inp.text() or "").strip()
        if keyword:
            self._filtered = [
                t for t in self._trades
                if keyword.lower() in t.get("name", "").lower()
            ]
        else:
            self._filtered = list(self._trades)
        self._populate()

    def _populate(self) -> None:
        self._table.setRowCount(0)
        for i, tr in enumerate(self._filtered):
            self._table.insertRow(i)
            pnl = tr.get("pnl") or 0
            pnl_color = t.ACCENT if pnl >= 0 else t.DANGER
            cells = [
                (tr.get("name", ""), None),
                (str(tr.get("quantity", 1)), None),
                (t.brl(tr.get("buy_cost", 0)), None),
                (t.brl(tr.get("sell_price", 0)), None),
                (t.brl(pnl), pnl_color),
                (f"{tr.get('pnl_pct', 0)*100:+.1f}%", pnl_color),
                (tr.get("notes", ""), None),
            ]
            for col, (val, color) in enumerate(cells):
                item = QTableWidgetItem(str(val))
                if color:
                    item.setForeground(QBrush(QColor(color)))
                self._table.setItem(i, col, item)

        # Stats
        stats = trades_mod.trade_stats(trades=self._filtered)
        self._stat_total.set_value(str(stats["total"]))
        pnl = stats["pnl_total"]
        pnl_c = t.ACCENT if pnl >= 0 else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_c)
        wr = stats.get("win_rate", 0)
        self._stat_winrate.set_value(f"{wr*100:.0f}%")
        best = stats.get("best")
        if best:
            self._stat_best.set_value(
                f"{t.brl(best['pnl'])} ({best['name']})",
                accent=t.ACCENT
            )
        else:
            self._stat_best.set_value("—")
        self._stats_lbl.setText(f"{stats['win_count']}W / {stats['loss_count']}L")
        self._status.setText(f"{len(self._filtered)} trade(s)")

    def _on_filter(self, text: str) -> None:
        self._apply_filter()

    def _on_add(self) -> None:
        dlg = _TradeDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            return
        trades_mod.record_trade(
            data["name"], data["buy_cost"], data["sell_price"],
            data["quantity"], notes=data["notes"],
        )
        self.refresh()

    def _on_clear(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        r = QMessageBox.question(
            self, "Limpar trades",
            "Tem certeza? Todos os trades serao removidos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if r == QMessageBox.StandardButton.Yes:
            trades_mod.clear_trades()
            self.refresh()
