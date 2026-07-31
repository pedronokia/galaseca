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
    QDoubleSpinBox,
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
from skinvault.ui.components import FormRow, PageHeader, RecentMatchesStrip, SectionHeader, SegmentedControl, SortableItem, StatCard, Toast


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
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._trade = trade
        self._build()

    def _build(self) -> None:
        tr = self._trade or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        self._name_inp = QLineEdit(tr.get("name", ""))
        self._name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        self._name_inp.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Item:", self._name_inp))

        self._buy_inp = QDoubleSpinBox()
        self._buy_inp.setRange(0, 999999)
        self._buy_inp.setPrefix("R$ ")
        self._buy_inp.setValue(tr.get("buy_cost", 0))
        self._buy_inp.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Preço de compra (unitário):", self._buy_inp))

        self._sell_inp = QDoubleSpinBox()
        self._sell_inp.setRange(0, 999999)
        self._sell_inp.setPrefix("R$ ")
        self._sell_inp.setValue(tr.get("sell_price", 0))
        self._sell_inp.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Preço de venda (unitário, bruto):", self._sell_inp))

        self._qty_inp = QSpinBox()
        self._qty_inp.setRange(1, 999)
        self._qty_inp.setValue(tr.get("quantity", 1))
        self._qty_inp.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Quantidade:", self._qty_inp))

        self._notes_inp = QLineEdit(tr.get("notes", ""))
        self._notes_inp.setPlaceholderText("Opcional")
        self._notes_inp.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Notas:", self._notes_inp))

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.setStyleSheet(t.btn_ghost())
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setToolTip("Fecha o dialogo sem salvar.")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Salvar")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setToolTip("Salva o trade e fecha.")
        ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

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
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        # Header: PageHeader + acoes
        self._add_btn = QPushButton("Adicionar trade")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(t.btn_primary())
        self._add_btn.setToolTip(
            "Registra um trade manual com compra, venda e quantidade.\n"
            "Atalho: Ctrl+N."
        )
        self._add_btn.clicked.connect(self._on_add)

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
        self._act_import = self._more_menu.addAction(
            "Importar trades da Steam"
        )
        self._act_import.setToolTip(
            "Pareia as compras e vendas do seu histórico do Steam Market e "
            "registra cada par como um trade.\n"
            "Usa o que o último sync baixou — não acessa a rede.\n"
            "Pode rodar quantas vezes quiser: trades já importados são "
            "ignorados."
        )
        self._act_import.triggered.connect(self._on_import_steam)
        self._more_menu.addSeparator()
        self._act_clear = self._more_menu.addAction("Limpar tudo…")
        self._act_clear.triggered.connect(self._on_clear)
        self._more_btn.setMenu(self._more_menu)

        root.addWidget(PageHeader(
            "Histórico de Trades",
            "P&L líquido após a taxa de 15% da Steam, com filtros por "
            "período e resultado.",
            actions=[self._add_btn, self._more_btn],
        ))

        # Stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_total = StatCard("Trades no filtro", "0")
        self._stat_total.setMaximumWidth(200)
        self._stat_total.setToolTip(
            "Quantidade de trades que casam com o filtro atual."
        )
        self._stat_pnl = StatCard("P&L líquido", "—", icon="chart")
        self._stat_pnl.setMaximumWidth(300)
        self._stat_pnl.setToolTip(
            "Lucro/prejuízo total já descontada a taxa Steam de 15%."
        )
        self._stat_winrate = StatCard("Taxa de acerto", "—", icon="percent")
        self._stat_winrate.setMaximumWidth(300)
        self._stat_winrate.setToolTip(
            "% de trades com P&L positivo (winning trades / total)."
        )
        self._stat_fees = StatCard("Taxas pagas", "—", icon="coins")
        self._stat_fees.setMaximumWidth(200)
        self._stat_fees.setToolTip(
            "Soma das taxas Steam (15%) pagas pelos trades no filtro."
        )
        for sc in (self._stat_total, self._stat_pnl, self._stat_winrate,
                   self._stat_fees):
            stats_row.addWidget(sc)
        stats_row.addStretch(1)
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
        t.configure_table(self._table)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        _tips = {
            self.COL_DATE: "Quando a venda aconteceu (data do encerramento do trade).",
            self.COL_NAME: "Item negociado.",
            self.COL_QTY: "Quantidade do lote.",
            self.COL_COST: (
                "Quanto você pagou pela entrada, por unidade. A Steam não "
                "cobra taxa na compra — só na venda."),
            self.COL_SELL: (
                "Preço de listagem da venda na Steam, por unidade. A taxa "
                "de 15% (incidente sobre o valor do vendedor) já sai no "
                "P&L."),
            self.COL_PNL: (
                "Lucro/prejuízo líquido em R$: recebido (venda com taxa "
                "descontada) − custo da compra."),
            self.COL_ROI: (
                "Retorno sobre o investimento: P&L ÷ custo total, em "
                "percentual 0–100."),
            self.COL_SOURCE: "Origem do registro: manual ou importado.",
            self.COL_NOTES: "Observação livre anotada no trade.",
        }
        for col, tip in _tips.items():
            cab = self._table.horizontalHeaderItem(col)
            if cab is not None:
                cab.setToolTip(tip)
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

        # Empty state hero (mostrado quando self._trades == [])
        self._empty_hero = self._build_empty_hero()
        root.addWidget(self._empty_hero, 1)
        self._empty_hero.setVisible(False)

        self._status = QLabel("")
        self._status.setStyleSheet(t.label_caption())
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

    def _build_empty_hero(self) -> QWidget:
        from skinvault.ui.components import EmptyState
        es = EmptyState(
            icon="◇",
            title="Nenhum trade ainda",
            subtitle=("Adicione ou sincronize seus trades pra ver\n"
                       "o histórico completo aqui."),
            steps=["Adicione um trade manualmente ou sincronize com a Steam.",
                   "Acompanhe P&L, taxa de acerto e desempenho mensal.",
                   "Clique numa barra do P&L mensal para filtrar a tabela."],
            cta_label="+ Adicionar trade",
            on_cta=self._on_add,
        )
        return es

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
        # Empty state quando nao ha nenhum trade
        is_empty = not self._trades
        self._table.setVisible(not is_empty)
        self._empty_hero.setVisible(is_empty)
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
            raw_pnl = tr.get("pnl")  # None/0 preservado pro tint
            row_tint = t.row_tint(raw_pnl)
            pnl_color = t.POSITIVE if pnl >= 0 else t.DANGER
            src_label, src_color = _source_label(tr.get("source", "manual"))
            sell_ts = tr.get("sell_ts") or tr.get("buy_ts") or 0
            roi = (tr.get("pnl_pct") or 0)
            from skinvault.localization import localize_name as _ln
            # 3o campo = chave de ordenacao. None -> ordena pelo texto, que
            # e' o certo pras colunas textuais (item, origem, notas).
            # Sem chave, "R$ -7,54" vinha antes de "R$ 1,63" e 30/04 antes
            # de 29/05 -- ver components.SortableItem.
            cells = [
                (_fmt_date(sell_ts), None, sell_ts),
                (_ln(tr.get("name", "")), None, None),
                (str(tr.get("quantity", 1)), None, tr.get("quantity", 1)),
                (t.brl(tr.get("buy_cost", 0)), None, tr.get("buy_cost", 0)),
                (t.brl(tr.get("sell_price", 0)), None,
                 tr.get("sell_price", 0)),
                (t.brl(pnl), pnl_color, pnl),
                (f"{roi:+.1f}%", pnl_color, roi),
                (src_label, src_color, None),
                (tr.get("notes", ""), None, None),
            ]
            for col, (val, color, chave) in enumerate(cells):
                item = (QTableWidgetItem(str(val)) if chave is None
                        else SortableItem(str(val), chave))
                if color:
                    item.setForeground(QBrush(QColor(color)))
                if row_tint is not None:
                    item.setBackground(QBrush(row_tint))
                # Guarda o indice original do trade pra editar/remover
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole,
                                 self._trades.index(tr))
                self._table.setItem(i, col, item)
        # Alinhamento por coluna: qtd/dinheiro → direita, data/origem → centro
        right_cols = {
            self.COL_QTY, self.COL_COST, self.COL_SELL,
            self.COL_PNL, self.COL_ROI,
        }
        center_cols = {self.COL_DATE, self.COL_SOURCE}
        t.align_table_columns(self._table, right=right_cols, center=center_cols)
        self._table.setSortingEnabled(was_sorting)

        # Stats sobre o filtrado
        stats = trades_mod.trade_stats(trades=self._filtered)
        self._stat_total.set_value(str(stats["total"]))

        pnl = stats["pnl_total"]
        if stats["total"] == 0:
            pnl_c = t.TEXT
        else:
            pnl_c = t.POSITIVE if pnl >= 0 else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_c)
        # Delta vs mes anterior, em REAIS e nao em porcentagem.
        #
        # Variacao percentual de P&L nao tem sentido: a base pode ser ~zero
        # ou trocar de sinal. Com o historico real do usuario, junho fechou
        # em R$ 0,03 e julho em R$ 1,63 -- a conta dava "+5333,3%", correta
        # e inutil. A diferenca absoluta responde a mesma pergunta ("melhorou
        # quanto?") e vale em qualquer base.
        _monthly = trades_mod.monthly_pnl(trades=self._trades)
        if len(_monthly) >= 2:
            _diff = _monthly[-1]["pnl"] - _monthly[-2]["pnl"]
            _sinal = "+" if _diff >= 0 else "−"
            self._stat_pnl.set_delta(
                None, f"{_sinal}{t.brl(abs(_diff))} vs mês anterior")
        else:
            self._stat_pnl.set_delta(None)

        # win_rate ja vem em 0-100
        wr = stats.get("win_rate", 0) or 0
        if stats["total"] == 0:
            wr_c = t.TEXT_MUTED
        elif wr >= 50:
            wr_c = t.POSITIVE
        elif wr >= 30:
            wr_c = t.WARN
        else:
            wr_c = t.DANGER
        # V/D e nao W/L: a faixa de resultados logo acima (RecentMatchesStrip)
        # ja' marca vitoria e derrota assim, e a tela inteira e' em portugues.
        wr_extra = f"  ({stats['win_count']}V / {stats['loss_count']}D)"
        self._stat_winrate.set_value(f"{wr:.0f}%{wr_extra}", accent=wr_c)
        # Badge no P&L com a taxa de acerto
        if stats["total"] > 0 and wr >= 0:
            wk = "positive" if wr >= 50 else "danger"
            self._stat_pnl.set_badge(f"{wr:.0f}% acerto", wk)
        else:
            self._stat_pnl.clear_badge()

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
            Toast.show_toast(self, "Selecione um trade para editar.", "warning")
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
            Toast.show_toast(self, "O nome do item é obrigatório.", "error")
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
            Toast.show_toast(self, "Selecione um trade para remover.", "warning")
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

    def _on_import_steam(self) -> None:
        """Importa o historico do Steam Market ja' sincronizado.

        Le' `steam_market_events.json` -- o que `sync.py` baixou -- e nao
        toca na rede. Se o arquivo esta vazio, o caminho e' sincronizar
        primeiro na tela de Conta, e a mensagem diz isso.
        """
        from skinvault import trade_matcher

        closed = trade_matcher.load_closed_trades()
        if not closed:
            Toast.show_toast(
                self,
                "Nenhuma compra pareada com venda no histórico da Steam. "
                "Sincronize sua conta primeiro.",
                "warning",
            )
            return

        result = trade_matcher.import_closed_trades(closed)
        if not result["imported"]:
            Toast.show_toast(
                self,
                f"Nada novo — os {result['total']} trades da Steam já "
                "estavam importados.",
                "info",
            )
            return

        self.refresh()
        msg = f"{result['imported']} trade(s) importado(s) da Steam."
        if result["skipped"]:
            msg += f" {result['skipped']} já estava(m) aqui."
        Toast.show_toast(self, msg, "success")

    def _on_clear(self) -> None:
        if not self._trades:
            Toast.show_toast(self, "Nenhum trade para remover.", "warning")
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
