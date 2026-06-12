"""Tela — Simulador de Trade (F11).

Calcula lucro/prejuizo real apos taxa Steam de 15%, mostra breakeven
e mantem historico in-memory das ultimas simulacoes.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from skinvault import portfolio
from skinvault.ui import theme as t
from skinvault.ui.components import Card, FormRow, PageHeader, SectionHeader, StatCard


_HIST_CAP = 5


class _HistoryChip(QPushButton):
    """Botao pill com resumo de uma simulacao previa."""

    def __init__(self, snap: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pnl = snap.get("pnl", 0)
        color = t.ACCENT if pnl >= 0 else t.DANGER
        label = (
            f"R$ {snap['buy_price']:.0f} → R$ {snap['sell_price']:.0f}"
            f" × {snap['quantity']}  •  {t.brl(pnl)}"
        )
        self.setText(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ color: {color}; background: transparent;"
            f" border: 1px solid {t.BORDER}; border-radius: 14px;"
            f" padding: 6px 12px; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ background: {t.SURFACE}; }}"
        )


class SimuladorScreen(QWidget):
    """Simulador de trade com fee-aware P&L."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buy_inp = QDoubleSpinBox()
        self._sell_inp = QDoubleSpinBox()
        self._qty_inp = QSpinBox()
        self._history: list[dict] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        root.addWidget(PageHeader(
            "Simulador de Trade",
            "Simule uma compra e venda no Steam Community Market e veja o "
            "lucro real após a taxa de 15%. O \"preço mínimo de venda\" "
            "mostra por quanto você precisa listar para empatar.",
        ))

        # ── Card de inputs ────────────────────────────────
        card = Card(self)
        params = QVBoxLayout()
        params.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(16)
        self._buy_inp.setPrefix("R$ ")
        self._buy_inp.setRange(0, 9999999)
        self._buy_inp.setStyleSheet(t.spin_style())
        row1.addWidget(FormRow(
            "Preço de compra (unitário)", self._buy_inp,
            tooltip="Quanto você paga por cada unidade ao comprar.",
        ))
        self._sell_inp.setPrefix("R$ ")
        self._sell_inp.setRange(0, 9999999)
        self._sell_inp.setStyleSheet(t.spin_style())
        row1.addWidget(FormRow(
            "Preço de venda (unitário, listagem)", self._sell_inp,
            tooltip="Preço pelo qual você lista cada unidade.\nA Steam cobra "
                    "15% sobre este valor.",
        ))
        params.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        self._qty_inp.setMinimum(1)
        self._qty_inp.setMaximum(999)
        self._qty_inp.setStyleSheet(t.input_style())
        row2.addWidget(FormRow(
            "Quantidade (listagens)", self._qty_inp,
            tooltip="Cada unidade vira uma listagem separada. A taxa de 15% "
                    "aplica sobre cada listagem.",
        ), 1)
        row2.addStretch(1)
        params.addLayout(row2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._simular_btn = QPushButton("Simular trade")
        self._simular_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._simular_btn.setStyleSheet(t.btn_primary(padding="12px 32px"))
        self._simular_btn.setToolTip(
            "Calcula custo, taxa Steam, valor líquido e ROI. Atalho: Enter."
        )
        self._simular_btn.clicked.connect(self._on_simular)
        btn_row.addWidget(self._simular_btn)

        self._clear_btn = QPushButton("Limpar")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(t.btn_ghost(padding="12px 18px",
                                                  fs=t.FS_BODY))
        self._clear_btn.setToolTip("Zera os campos e o resultado.")
        self._clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch(1)
        params.addLayout(btn_row)

        card.layout().addLayout(params)
        root.addWidget(card)

        # ── Card de resultado ─────────────────────────────
        result_card = Card(self)
        rl = QVBoxLayout()
        rl.setSpacing(8)

        self._result_title = QLabel("Resultado")
        self._result_title.setStyleSheet(t.label_section())
        rl.addWidget(self._result_title)

        self._result_detail = QLabel(
            "Preencha os valores e clique em Simular."
        )
        self._result_detail.setWordWrap(True)
        self._result_detail.setStyleSheet(t.label_body_muted())
        rl.addWidget(self._result_detail)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_pnl = StatCard("Lucro/Prejuízo", "—")
        self._stat_pnl.setToolTip(
            "Resultado líquido = valor recebido – custo total. "
            "Negativo = prejuízo."
        )
        self._stat_roi = StatCard("ROI", "—")
        self._stat_roi.setToolTip(
            "Retorno sobre o investimento: lucro líquido ÷ custo total."
        )
        self._stat_recebe = StatCard("Valor recebido (–15%)", "—",
                                     accent=t.STEAM_BLUE)
        self._stat_recebe.setToolTip(
            "Total que cai na sua carteira Steam após a taxa de 15%."
        )
        self._stat_break = StatCard("Preço mínimo de venda", "—",
                                    accent=t.WARN)
        self._stat_break.setToolTip(
            "Preço pelo qual você precisa listar para empatar — recuperar "
            "exatamente o custo de compra após a taxa Steam."
        )
        for sc in (self._stat_pnl, self._stat_roi, self._stat_recebe,
                   self._stat_break):
            stats_row.addWidget(sc, 1)
        rl.addLayout(stats_row)

        result_card.layout().addLayout(rl)
        root.addWidget(result_card)

        # ── Historico de simulacoes ───────────────────────
        self._hist_lbl = QLabel("Simulações recentes")
        self._hist_lbl.setStyleSheet(t.label_caption())
        self._hist_lbl.setToolTip(
            "Clique em uma para repor os campos com aqueles valores."
        )
        root.addWidget(self._hist_lbl)
        self._hist_lbl.setVisible(False)

        self._hist_row = QHBoxLayout()
        self._hist_row.setSpacing(8)
        root.addLayout(self._hist_row)

        root.addStretch(1)

        # Atalhos
        QShortcut(QKeySequence("Return"), self).activated.connect(
            self._on_simular
        )
        QShortcut(QKeySequence("Enter"), self).activated.connect(
            self._on_simular
        )

    # ── acoes ─────────────────────────────────────────────
    def _on_simular(self) -> None:
        buy = self._buy_inp.value()
        sell = self._sell_inp.value()
        qty = self._qty_inp.value()
        if buy <= 0 or sell <= 0 or qty <= 0:
            self._result_detail.setText(
                "Preencha compra, venda e quantidade com valores positivos."
            )
            self._result_detail.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FS_BODY};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            )
            return

        r = portfolio.simulate_trade(buy, sell, qty)

        pnl = r["pnl"]
        pnl_color = t.ACCENT if r["is_profit"] else (
            t.DANGER if r["is_loss"] else t.TEXT
        )
        # roi_pct ja vem em 0-100 do portfolio.simulate_trade
        roi = r["roi_pct"]

        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_color)
        self._stat_roi.set_value(f"{roi:+.1f}%", accent=pnl_color)
        self._stat_recebe.set_value(t.brl(r["net_received"]),
                                    accent=t.STEAM_BLUE)
        self._stat_break.set_value(t.brl(r["break_even_price"]),
                                   accent=t.WARN)

        # Mensagem do veredito
        if r["is_profit"]:
            msg = (
                f"Lucro líquido de {t.brl(pnl)} ({roi:+.1f}% sobre o custo). "
                f"A Steam fica com {t.brl(r['steam_fee'])} em taxa."
            )
        elif r["is_loss"]:
            gap = r["break_even_price"] - sell
            msg = (
                f"Prejuízo de {t.brl(pnl)} ({roi:+.1f}%). Para empatar você "
                f"precisaria listar por {t.brl(r['break_even_price'])} — "
                f"{t.brl(gap)} acima do preço atual."
            )
        else:
            msg = "Trade no zero a zero: receita líquida iguala o custo."
        self._result_detail.setText(msg)
        self._result_detail.setStyleSheet(
            f"color: {pnl_color}; font-size: {t.FS_BODY};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )

        # Atualiza historico
        self._push_history(r)

    def _on_clear(self) -> None:
        self._buy_inp.setValue(0)
        self._sell_inp.setValue(0)
        self._qty_inp.setValue(1)
        self._buy_inp.setFocus()
        for sc in (self._stat_pnl, self._stat_roi, self._stat_recebe,
                   self._stat_break):
            sc.set_value("—", accent=t.TEXT)
        self._result_detail.setText(
            "Preencha os valores e clique em Simular."
        )
        self._result_detail.setStyleSheet(t.label_body_muted())

    # ── historico ─────────────────────────────────────────
    def _push_history(self, snap: dict) -> None:
        self._history.insert(0, snap)
        self._history = self._history[:_HIST_CAP]
        self._rebuild_history()

    def _rebuild_history(self) -> None:
        # Remove todos os widgets do hist_row
        while self._hist_row.count() > 0:
            item = self._hist_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not self._history:
            self._hist_lbl.setVisible(False)
            return

        self._hist_lbl.setVisible(True)
        for snap in self._history:
            chip = _HistoryChip(snap, self)
            chip.clicked.connect(
                lambda _checked=False, s=snap: self._restore(s)
            )
            self._hist_row.addWidget(chip)
        self._hist_row.addStretch(1)

    def _restore(self, snap: dict) -> None:
        self._buy_inp.setValue(snap["buy_price"])
        self._sell_inp.setValue(snap["sell_price"])
        self._qty_inp.setValue(snap["quantity"])
        self._on_simular()
