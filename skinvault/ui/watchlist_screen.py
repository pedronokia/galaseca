"""Tela — Watchlist + Alertas (F11).

Tabela de itens monitorados com preco alvo, regras configur井eis,
e log de alertas disparados.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import alerts, steam_api, watchlist as wl
from skinvault._paths import DATA_DIR
from skinvault.prices import PriceCache
from skinvault.ui import theme as t


class _RulesDialog(QDialog):
    """Dialog para configurar regras de alerta de um item."""

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar regras - " + item["name"])
        self.setMinimumWidth(400)
        self._item = item
        self._build()

    def _build(self) -> None:
        rules = self._item.get("rules") or {}
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        # Price below target
        self._below_target = QDoubleSpinBox()
        self._below_target.setRange(0, 99999)
        self._below_target.setPrefix("R$ ")
        self._below_target.setValue(rules.get("price_below", 0))
        form.addRow("Alerta abaixo de:", self._below_target)

        # Drop %
        self._drop_pct = QDoubleSpinBox()
        self._drop_pct.setRange(0, 100)
        self._drop_pct.setSuffix(" %")
        self._drop_pct.setValue(rules.get("price_drop_pct", 0))
        form.addRow("Queda percentual:", self._drop_pct)

        # Volume spike
        self._volume_spike = QDoubleSpinBox()
        self._volume_spike.setRange(0, 100)
        self._volume_spike.setValue(rules.get("volume_spike", 0))
        self._volume_spike.setSpecialValueText("Desligado")
        form.addRow("Volume anomalia (x):", self._volume_spike)

        # Supply drop
        qb = QGroupBox("Supply drop")
        qb_lay = QVBoxLayout(qb)
        self._supply_drop = QDoubleSpinBox()
        self._supply_drop.setRange(0, 100)
        self._supply_drop.setValue(rules.get("supply_drop", 0))
        self._supply_drop.setSpecialValueText("Desligado")
        qb_lay.addWidget(QLabel("Limiar de queda na oferta:"))
        qb_lay.addWidget(self._supply_drop)
        form.addRow(qb)

        layout.addLayout(form)

        self._rules_instr = QLabel(
            "Regras com valor 0 ou 'Desligado' ficam inativas."
        )
        self._rules_instr.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        layout.addWidget(self._rules_instr)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_rules(self) -> dict:
        rules = {}
        v = self._below_target.value()
        if v > 0:
            rules["price_below"] = v
        v = self._drop_pct.value()
        if v > 0:
            rules["price_drop_pct"] = v / 100.0
        v = self._volume_spike.value()
        if v > 0:
            rules["volume_spike"] = v
        v = self._supply_drop.value()
        if v > 0:
            rules["supply_drop"] = v
        return rules


class WatchlistScreen(QWidget):
    """Watchlist + Alertas."""

    COL_NAME = 0
    COL_TARGET = 1
    COL_PRICE = 2
    COL_STATUS = 3
    COL_RULES = 4

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._items: list[dict] = []
        self._alerts_log: list[dict] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Watchlist")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
        )
        hdr.addWidget(title)
        hdr.addStretch(1)

        self._add_btn = QPushButton("+ Adicionar item")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(t.btn_primary())
        self._add_btn.setToolTip(
            "Adiciona um item para monitoramento e dispara alertas quando"
            " a regra escolhida for satisfeita."
        )
        self._add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self._add_btn)
        root.addLayout(hdr)

        # Tabela
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Preco alvo", "Preco atual", "Status", "Regras"]
        )
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
        hh.setSectionResizeMode(self.COL_TARGET,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_PRICE,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_STATUS,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_RULES,
                                QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        root.addWidget(self._status)

    def refresh(self) -> None:
        self._items = wl.load_watchlist()
        self._alerts_log = alerts.load_alerts_log()
        self._populate()

    def _populate(self) -> None:
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, item in enumerate(self._items):
            self._table.insertRow(i)
            name = item["name"]
            target = item.get("target", 0)
            triggered = item.get("triggered", False)
            rules = item.get("rules") or {}
            baseline = item.get("baseline_price")

            # Nome
            self._table.setItem(i, self.COL_NAME, QTableWidgetItem(name))

            # Target
            self._table.setItem(i, self.COL_TARGET,
                                QTableWidgetItem(t.brl(target) if target else "—"))

            # Preco atual (try cache)
            price = self._cache.get(name)
            price_item = QTableWidgetItem(
                t.brl(price) if price else "Consultando…"
            )
            if price:
                color = t.DANGER if price <= target else t.ACCENT
                price_item.setForeground(Qt.GlobalColor.white)
            self._table.setItem(i, self.COL_PRICE, price_item)

            # Status
            status_txt = "Alerta!" if triggered else "OK"
            st = QTableWidgetItem(status_txt)
            if triggered:
                st.setForeground(QBrush(QColor(t.DANGER)))
            else:
                st.setForeground(QBrush(QColor(t.ACCENT)))
            self._table.setItem(i, self.COL_STATUS, st)

            # Regras summary
            self._table.setItem(
                i, self.COL_RULES,
                QTableWidgetItem(alerts.format_rules_summary(rules)),
            )

            # Acoes (context menu via botoes na ultima coluna ou botoes inline)
            # Usa botoes simples: Editar e Remover
        self._table.setSortingEnabled(was_sorting)
        self._status.setText(
            f"{len(self._items)} itens • "
            f"{len([x for x in self._items if x.get('triggered')])} alertas ativos"
        )

    def _on_add(self) -> None:
        # Dialog simples para adicionar
        dlg = QDialog(self)
        dlg.setWindowTitle("Adicionar a Watchlist")
        dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        name_inp = QLineEdit()
        name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        form.addRow("Nome do item:", name_inp)

        target_inp = QDoubleSpinBox()
        target_inp.setRange(0, 99999)
        target_inp.setPrefix("R$ ")
        target_inp.setDecimals(2)
        form.addRow("Preco alvo:", target_inp)

        lay.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        def on_ok():
            name = name_inp.text().strip()
            target = target_inp.value()
            if not name:
                return
            wl.add_watch(name, target)
            self.refresh()
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.exec()
