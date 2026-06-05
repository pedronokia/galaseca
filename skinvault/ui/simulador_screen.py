"""Tela — Simulador de Trade (F11).

Calcula lucro/prejuizo real apos taxa Steam de 15%.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
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
from skinvault.ui.components import Card, StatCard


class SimuladorScreen(QWidget):
    """Simulador de trade com fee-aware P&L."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buy_inp = QDoubleSpinBox()
        self._sell_inp = QDoubleSpinBox()
        self._qty_inp = QSpinBox()
        self._build()

    def _style_spin(self, s: QDoubleSpinBox | QSpinBox) -> None:
        s.setMinimum(0)
        s.setMaximum(9999999)
        s.setStyleSheet(
            f"QDoubleSpinBox, QSpinBox {{ background: {t.SURFACE};"
            f" border: 1px solid {t.BORDER}; border-radius: 8px;"
            f" padding: 10px 12px; font-size: {t.FS_INPUT}; color: {t.TEXT};"
            f" font-family: {t.FONT_FAMILY}; }}"
            f":focus {{ border: 1px solid {t.ACCENT}; }}"
        )

    def _labeled(self, text: str, w: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};")
        lay.addWidget(lbl)
        lay.addWidget(w)
        return wrap

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel("Simulador de Trade")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
        )
        root.addWidget(title)

        desc = QLabel(
            "Simule uma compra e venda na Steam Community Market.\n"
            "O calculo considera a taxa de 15% da Steam sobre o valor de venda."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};")
        root.addWidget(desc)

        card = Card(self, padding=(20, 18, 20, 18))
        params = QVBoxLayout()
        params.setSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(16)
        self._buy_inp.setPrefix("R$ ")
        self._style_spin(self._buy_inp)
        row1.addWidget(self._labeled("Preco de compra", self._buy_inp))
        self._sell_inp.setPrefix("R$ ")
        self._style_spin(self._sell_inp)
        row1.addWidget(self._labeled("Preco de venda", self._sell_inp))
        params.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(16)
        self._qty_inp.setMinimum(1)
        self._qty_inp.setMaximum(999)
        self._style_spin(self._qty_inp)
        row2.addWidget(self._labeled("Quantidade", self._qty_inp))
        params.addLayout(row2)

        self._simular_btn = QPushButton("Simular")
        self._simular_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._simular_btn.setStyleSheet(t.btn_primary(padding="12px 32px"))
        self._simular_btn.clicked.connect(self._on_simular)
        params.addWidget(self._simular_btn, 0, Qt.AlignmentFlag.AlignLeft)

        card.layout().addLayout(params)
        root.addWidget(card)

        result_card = Card(self, padding=(20, 18, 20, 18))
        rl = QVBoxLayout()
        rl.setSpacing(4)

        self._result_title = QLabel("Resultado")
        self._result_title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
        )
        rl.addWidget(self._result_title)

        self._result_detail = QLabel("Preencha os valores e clique em Simular.")
        self._result_detail.setWordWrap(True)
        self._result_detail.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
        )
        rl.addWidget(self._result_detail)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_pnl = StatCard("Lucro/Prejuizo", "—")
        self._stat_roi = StatCard("ROI", "—")
        self._stat_recebe = StatCard("Valor recebido (-15%)", "—",
                                     accent=t.STEAM_BLUE)
        self._stat_fee = StatCard("Taxa Steam (15%)", "—", accent=t.DANGER)
        for sc in (self._stat_pnl, self._stat_roi, self._stat_recebe,
                   self._stat_fee):
            stats_row.addWidget(sc, 1)
        rl.addLayout(stats_row)

        result_card.layout().addLayout(rl)
        root.addWidget(result_card)

        root.addStretch(1)

    def _on_simular(self) -> None:
        buy = self._buy_inp.value()
        sell = self._sell_inp.value()
        qty = self._qty_inp.value()
        if buy <= 0 or sell <= 0 or qty <= 0:
            self._result_detail.setText(
                "Preencha todos os campos com valores positivos."
            )
            self._result_detail.setStyleSheet(
                f"color: {t.DANGER}; font-size: {t.FS_BODY};"
            )
            return

        r = portfolio.simulate_trade(buy, sell, qty)

        pnl = r["pnl"]
        pnl_color = t.ACCENT if r["is_profit"] else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_color)
        self._stat_roi.set_value(f"{r['roi_pct']*100:+.1f}%")
        self._stat_recebe.set_value(t.brl(r["net_received"]),
                                    accent=t.STEAM_BLUE)
        self._stat_fee.set_value(t.brl(r["steam_fee"]))

        lines = [
            f"Custo total: {t.brl(r['cost_total'])}",
            f"Venda bruta: {t.brl(r['gross_sale'])}",
            f"Taxa Steam: {t.brl(r['steam_fee'])}",
            f"Valor recebido: {t.brl(r['net_received'])}",
            f"Lucro/Prejuizo: {t.brl(pnl)} ({r['roi_pct']*100:+.1f}%)",
        ]
        self._result_detail.setText("\n".join(lines))
        self._result_detail.setStyleSheet(
            f"color: {pnl_color}; font-size: {t.FS_BODY};"
        )
