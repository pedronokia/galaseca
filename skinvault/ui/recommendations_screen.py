"""Tela — Recomendações.

Cruza o último scan do Scanner (candidatos de compra) com as posições já
validadas em Minha Conta (atenção na venda). Não acessa a rede: só lê o
que essas duas telas já gravaram em disco (`scan_store.json`,
`portfolio.json`) e o cache local de histórico de preço.

Factual, nunca previsão (AGENTS.md): os textos e tooltips sempre
descrevem o que já foi medido, nunca prometem retorno.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from skinvault import portfolio as portfolio_mod
from skinvault import recommendations as rec
from skinvault import scan_store, signals
from skinvault.ssr_cache import PriceHistoryCache
from skinvault.ui import theme as t
from skinvault.ui.components import (
    auto_cell, EmptyState, Footer, PageHeader, score_table_item,
    SectionHeader, SortableItem,
)

_RISK_COLORS = {"low": t.TEXT_MUTED, "medium": t.WARN, "high": t.DANGER}
_RISK_LABELS = {"low": "Baixo", "medium": "Médio", "high": "Alto"}


class RecommendationsScreen(QWidget):
    """Candidatos de compra (último scan) + atenção na venda (portfólio)."""

    # Pede navegacao pro router, que decide o que fazer -- esta tela nao
    # conhece o ScreenRouter (evita import circular com screen_router.py).
    navigate_to = pyqtSignal(str)       # SCREEN_SCANNER / SCREEN_ACCOUNT
    abrir_mercado = pyqtSignal(str)     # nome do item -> Market + busca
    abrir_inventario = pyqtSignal(str)  # nome do item -> Inventario + filtro

    COL_B_NAME = 0
    COL_B_PRICE = 1
    COL_B_SCORE = 2
    COL_B_CASE = 3
    COL_B_RISK = 4
    COL_B_REASONS = 5

    COL_S_NAME = 0
    COL_S_QTY = 1
    COL_S_SCORE = 2
    COL_S_TOPO = 3
    COL_S_RISK = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buy: list[dict] = []
        self._sell: list[dict] = []
        self._build()
        self.refresh()

    # ── construcao ────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        self._refresh_btn = QPushButton("Atualizar")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(t.btn_ghost(padding="8px 18px"))
        self._refresh_btn.setToolTip(
            "Relê o último scan do Scanner e as posições validadas em "
            "Minha Conta. Não acessa a rede."
        )
        self._refresh_btn.clicked.connect(self.refresh)

        root.addWidget(PageHeader(
            "Recomendações",
            "Cruza a nota do último scan com as posições da sua carteira."
            " Mostra o que já foi medido — a decisão é sempre sua.",
            actions=[self._refresh_btn],
        ))

        # ── Candidatos de compra ──────────────────
        root.addWidget(SectionHeader(
            "Candidatos de compra",
            "Melhores notas do último scan que você ainda não tem, sem"
            " alerta de subida rápida.",
        ))

        self._table_buy = QTableWidget(0, 6)
        self._table_buy.setHorizontalHeaderLabels(
            ["Item", "Preço", "Nota", "Caixa/Cápsula", "Risco", "Por quê"])
        t.configure_table(self._table_buy)
        self._table_buy.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        hhb = self._table_buy.horizontalHeader()
        hhb.setSectionResizeMode(
            self.COL_B_NAME, QHeaderView.ResizeMode.Interactive)
        hhb.setSectionResizeMode(
            self.COL_B_REASONS, QHeaderView.ResizeMode.Stretch)
        self._table_buy.doubleClicked.connect(
            lambda _i: self._on_open_market_selected())
        self._table_buy.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_buy.customContextMenuRequested.connect(self._on_ctx_buy)
        root.addWidget(self._table_buy, 1)

        self._empty_buy = EmptyState(
            "◇", "Nenhum candidato ainda",
            subtitle="Escaneie no Scanner (Todas as categorias) para ver"
                     " candidatos aqui.",
            cta_label="Ir para o Scanner",
            on_cta=lambda: self.navigate_to.emit("scanner"),
        )
        root.addWidget(self._empty_buy, 1)

        # ── Atencao na venda ───────────────────────
        root.addWidget(SectionHeader(
            "Atenção na venda",
            "Posições da sua carteira perto do maior preço já registrado"
            " ou com alerta de subida rápida.",
        ))

        self._table_sell = QTableWidget(0, 5)
        self._table_sell.setHorizontalHeaderLabels(
            ["Item", "Qtd", "Nota", "Topo", "Risco"])
        t.configure_table(self._table_sell)
        self._table_sell.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        hhs = self._table_sell.horizontalHeader()
        hhs.setSectionResizeMode(
            self.COL_S_NAME, QHeaderView.ResizeMode.Stretch)
        self._table_sell.doubleClicked.connect(
            lambda _i: self._on_open_inventory_selected())
        self._table_sell.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_sell.customContextMenuRequested.connect(
            self._on_ctx_sell)
        root.addWidget(self._table_sell, 1)

        self._empty_sell = EmptyState(
            "◇", "Nada chamando atenção",
            subtitle="Suas posições estão longe do topo histórico e sem"
                     " alerta de subida rápida — ou ainda não foram"
                     " validadas em Minha Conta.",
            cta_label="Validar notas em Minha Conta",
            on_cta=lambda: self.navigate_to.emit("account"),
        )
        root.addWidget(self._empty_sell, 1)

        self._footer = Footer()
        root.addWidget(self._footer)

    # ── dados ─────────────────────────────────────────────
    def refresh(self) -> None:
        positions = portfolio_mod.load_portfolio()
        owned = {p["name"] for p in positions if p.get("name")}

        scan = scan_store.load_last_scan()
        scan_results = (scan or {}).get("results") or []
        self._buy = rec.buy_candidates(scan_results, owned_names=owned)

        pr_map = self._cached_pump_risk(positions)
        self._sell = rec.sell_watch(positions, pump_risk_by_name=pr_map)

        self._populate_buy()
        self._populate_sell()
        self._update_footer(positions, scan)

    @staticmethod
    def _cached_pump_risk(positions: list[dict]) -> dict:
        """pump_risk por posição, só de cache local (sem rede).

        `PriceHistoryCache.get()` é leitura pura -- ao contrário de
        `ssr_cache.cached_price_history()`, nunca busca na rede em cache
        miss. Seguro rodar direto no refresh(), sem thread.
        """
        cache = PriceHistoryCache()
        out = {}
        for pos in positions:
            name = pos.get("name")
            if not name or name in out:
                continue
            ph = cache.get(name)
            if not ph:
                continue
            out[name] = signals.pump_risk(ph, signals.load_item_volume(name))
        return out

    def _update_footer(self, positions: list[dict],
                       scan: dict | None) -> None:
        if scan:
            quando = scan_store.idade_txt(scan["ts"])
            esquerda = (f"Último scan: {scan['category'] or 'categoria'},"
                       f" {quando}.")
        else:
            esquerda = "Nenhum scan salvo ainda — vá ao Scanner."
        if positions:
            faltam = len(rec.missing_validation(positions))
            validadas = len(positions) - faltam
            esquerda += f" {validadas} de {len(positions)} posições validadas."
        self._footer.set_left(esquerda)
        self._footer.set_right(
            f"{len(self._buy)} candidatos · {len(self._sell)} em atenção")

    def _populate_buy(self) -> None:
        is_empty = not self._buy
        self._table_buy.setVisible(not is_empty)
        self._empty_buy.setVisible(is_empty)
        self._table_buy.setSortingEnabled(False)
        self._table_buy.setRowCount(0)
        from skinvault.localization import localize_name as _ln
        for i, r in enumerate(self._buy):
            self._table_buy.insertRow(i)
            score = int(r.get("score") or 0)
            score_color = (t.POSITIVE if score >= 70
                           else (t.WARN if score >= 45 else t.DANGER))
            risk = (r.get("pump_risk") or {}).get("level", "low")
            reasons_txt = "; ".join(r.get("reasons") or []) or (
                "Nota neutra: nenhum fator se destacou")
            cells = [
                (_ln(r.get("name") or ""), None),
                (t.brl(r["price"]) if r.get("price") else "—", None),
                (str(score), score_color),
                (r.get("case_label") or "—", None),
                (_RISK_LABELS.get(risk, "—"), _RISK_COLORS.get(risk)),
                (reasons_txt, None),
            ]
            for col, (val, color) in enumerate(cells):
                item = (SortableItem(str(val), score)
                        if col == self.COL_B_SCORE else auto_cell(str(val)))
                if color:
                    item.setForeground(QBrush(QColor(color)))
                if col == self.COL_B_NAME:
                    item.setData(Qt.ItemDataRole.UserRole, r)
                self._table_buy.setItem(i, col, item)
            tip = r.get("score_tooltip") or signals.format_breakdown(
                r.get("breakdown") or [])
            self._table_buy.item(i, self.COL_B_SCORE).setToolTip(tip)
        self._table_buy.setSortingEnabled(True)

    def _populate_sell(self) -> None:
        is_empty = not self._sell
        self._table_sell.setVisible(not is_empty)
        self._empty_sell.setVisible(is_empty)
        self._table_sell.setSortingEnabled(False)
        self._table_sell.setRowCount(0)
        from skinvault.localization import localize_name as _ln
        for i, r in enumerate(self._sell):
            self._table_sell.insertRow(i)
            ctx = r.get("exit_context") or {}
            risk = (r.get("pump_risk") or {}).get("level", "low")

            name_item = auto_cell(_ln(r["name"]))
            name_item.setData(Qt.ItemDataRole.UserRole, r)
            self._table_sell.setItem(i, self.COL_S_NAME, name_item)

            self._table_sell.setItem(
                i, self.COL_S_QTY, auto_cell(str(r.get("quantity", 1))))

            self._table_sell.setItem(
                i, self.COL_S_SCORE,
                score_table_item(r.get("current_score"), r.get("score_ts")))

            topo_item = auto_cell(ctx.get("text", "—"))
            if ctx.get("level") == "topo":
                topo_item.setForeground(QBrush(QColor(t.WARN)))
            if ctx.get("tooltip"):
                topo_item.setToolTip(ctx["tooltip"])
            self._table_sell.setItem(i, self.COL_S_TOPO, topo_item)

            risk_item = auto_cell(_RISK_LABELS.get(risk, "—"))
            if _RISK_COLORS.get(risk):
                risk_item.setForeground(QBrush(QColor(_RISK_COLORS[risk])))
            risk_reasons = (r.get("pump_risk") or {}).get("reasons")
            if risk_reasons:
                risk_item.setToolTip("\n".join(f"• {m}" for m in risk_reasons))
            self._table_sell.setItem(i, self.COL_S_RISK, risk_item)
        self._table_sell.setSortingEnabled(True)

    # ── selecao / navegacao ─────────────────────────────────
    def _selected_buy(self) -> dict | None:
        row = self._table_buy.currentRow()
        if row < 0:
            return None
        item = self._table_buy.item(row, self.COL_B_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_sell(self) -> dict | None:
        row = self._table_sell.currentRow()
        if row < 0:
            return None
        item = self._table_sell.item(row, self.COL_S_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_open_market_selected(self) -> None:
        r = self._selected_buy()
        if r and r.get("name"):
            self.abrir_mercado.emit(r["name"])

    def _on_open_inventory_selected(self) -> None:
        r = self._selected_sell()
        if r and r.get("name"):
            self.abrir_inventario.emit(r["name"])

    def _on_ctx_buy(self, pos) -> None:
        if self._table_buy.currentRow() < 0:
            return
        menu = QMenu(self._table_buy)
        act = menu.addAction("Ver no Mercado")
        if menu.exec(self._table_buy.viewport().mapToGlobal(pos)) == act:
            self._on_open_market_selected()

    def _on_ctx_sell(self, pos) -> None:
        if self._table_sell.currentRow() < 0:
            return
        menu = QMenu(self._table_sell)
        act = menu.addAction("Ver no Inventário")
        if menu.exec(self._table_sell.viewport().mapToGlobal(pos)) == act:
            self._on_open_inventory_selected()
