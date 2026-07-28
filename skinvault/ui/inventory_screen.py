"""Tela — Inventário.

Saiu de dentro da "Minha Conta" em 28/07/2026. La' ele dividia a janela
com perfil, quatro cartoes de valor, cinco de desempenho e um grafico --
sobrava rodape pra o conteudo que da' nome a tela. Como aba propria, usa a
janela inteira.

A tela nao avalia nada por conta propria: recebe as linhas ja' avaliadas
pela AccountScreen, que e' quem tem o PriceWorker. Duplicar a avaliacao
seria dobrar o custo de rede num endpoint que ja' e' rate-limited.

Duas visoes, de proposito: a grade serve pra RECONHECER item pelo icone
(como a Steam mostra), a tabela pra conferir numero.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import markets
from skinvault.ui import theme as t
from skinvault.ui.components import EmptyState, PageHeader
from skinvault.ui.inventory_grid import InventoryGrid


class InventoryScreen(QWidget):
    """Grade + tabela do inventario, com filtro."""

    COL_NAME = 0
    COL_QTY = 1
    COL_PRICE = 2
    COL_SUBTOTAL = 3
    COL_RECEIVED = 4
    COL_PNL = 5
    COL_ORIGIN = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list = []
        self._positions: list = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        root.addWidget(PageHeader(
            "Inventário",
            "Cada item avaliado nos dois mercados: saldo Steam e dinheiro real.",
        ))

        linha = QHBoxLayout()
        linha.setSpacing(t.SPACE_SM)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrar por nome do item...")
        self._filter.setClearButtonEnabled(True)
        self._filter.setStyleSheet(t.input_style())
        self._filter.textChanged.connect(self._apply_filter)
        self._filter.setEnabled(False)   # comeca na grade
        linha.addWidget(self._filter, 1)

        self._view_btn = QPushButton("Ver em tabela")
        self._view_btn.setToolTip(
            "Alterna entre grade de ícones (estilo Steam) e tabela detalhada.")
        self._view_btn.setStyleSheet(t.btn_ghost())
        self._view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_btn.clicked.connect(self._toggle_view)
        linha.addWidget(self._view_btn, 0)
        root.addLayout(linha)

        self._grid = InventoryGrid(columns=8)
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Item", "Qtd", "Preço atual", "Subtotal", "Recebido (-15%)",
            "P&L", "Origem",
        ])
        t.configure_table(self._table)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, self.COL_ORIGIN + 1):
            hh.setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents)

        self._views = QStackedWidget()
        self._views.addWidget(self._grid)
        self._views.addWidget(self._table)
        root.addWidget(self._views, 1)

        self._empty = EmptyState(
            icon="◇",
            title="Inventário vazio",
            subtitle=("Sincronize com a Steam na tela Minha Conta\n"
                       "pra puxar seus itens."),
        )
        root.addWidget(self._empty, 1)
        self._views.setVisible(False)

        self._status = QLabel("")
        self._status.setStyleSheet(t.label_caption())
        root.addWidget(self._status)

    # ── dados ─────────────────────────────────────────────

    def set_data(self, rows: list, positions: list) -> None:
        """Recebe as linhas ja' avaliadas pela AccountScreen."""
        self._rows = list(rows or [])
        self._positions = list(positions or [])
        tem = bool(self._rows)
        self._views.setVisible(tem)
        self._empty.setVisible(not tem)
        if not tem:
            self._status.setText("")
            return
        self._populate_grid()
        self._populate_table()
        self._status.setText(f"{len(self._rows)} item(ns)")
        self._apply_filter(self._filter.text())

    def _populate_grid(self) -> None:
        """Alimenta a grade com as DUAS avaliacoes de cada item.

        Falha de rede deixa `market_net` em None, e a grade mostra
        "sem cotação" em vez de inventar numero.
        """
        try:
            precos = markets.cached_market("skinport")
            fx = markets.usd_brl()
        except Exception:
            precos, fx = {}, 0.0

        from skinvault.localization import localize_name as _ln
        itens = []
        for i, r in enumerate(self._rows):
            pos = self._positions[i] if i < len(self._positions) else {}
            nome = r.get("name") or ""
            cmp_ = markets.compare(r.get("price"), precos.get(nome), fx)
            itens.append({
                "name": _ln(nome) or nome,
                "raw_name": nome,
                "qty": r.get("quantity") or 1,
                "icon": pos.get("icon") or r.get("icon"),
                "type": pos.get("type") or r.get("type") or "",
                "steam_net": r.get("net_if_sold") or cmp_["steam_net"],
                "market_net": cmp_["market_net"],
                "premium_pct": cmp_["premium_pct"],
            })
        self._grid.set_items(itens)

    def _populate_table(self) -> None:
        from skinvault.localization import localize_name as _ln
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, r in enumerate(self._rows):
            self._table.insertRow(i)
            pos = self._positions[i] if i < len(self._positions) else {}
            origem = ("Steam" if pos.get("source") == "steam_sync"
                      else "Manual")
            pnl = r.get("pnl")
            celulas = [
                _ln(r.get("name") or "") or "—",
                str(r.get("quantity") or 1),
                t.brl(r.get("price")),
                t.brl(r.get("market")),
                t.brl(r.get("net_if_sold")),
                t.brl(pnl) if pnl is not None else "—",
                origem,
            ]
            for col, val in enumerate(celulas):
                item = QTableWidgetItem(val)
                if col == self.COL_PNL and pnl is not None:
                    item.setForeground(QBrush(QColor(
                        t.POSITIVE if pnl >= 0 else t.DANGER)))
                elif col == self.COL_ORIGIN and origem == "Steam":
                    item.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                if col != self.COL_NAME:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(i, col, item)
        self._table.setSortingEnabled(True)

    # ── interacao ─────────────────────────────────────────

    def _toggle_view(self) -> None:
        """`indo_pra_tabela` e' o estado DEPOIS do clique -- ler o anterior
        aqui inverte o filtro, que ja' foi bug nesta tela."""
        indo_pra_tabela = self._views.currentIndex() == 0
        self._views.setCurrentIndex(1 if indo_pra_tabela else 0)
        self._view_btn.setText(
            "Ver em grade" if indo_pra_tabela else "Ver em tabela")
        self._filter.setEnabled(indo_pra_tabela)

    def _apply_filter(self, texto: str) -> None:
        alvo = (texto or "").strip().lower()
        for i in range(self._table.rowCount()):
            item = self._table.item(i, self.COL_NAME)
            nome = item.text().lower() if item else ""
            self._table.setRowHidden(i, bool(alvo) and alvo not in nome)
