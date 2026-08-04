"""Dialog da Calculadora de Arbitragem/Taxas.

Responde duas perguntas: quanto sobra líquido em cada plataforma e por
quanto listar pra receber a margem desejada. A Steam é tratada à parte
(a taxa incide sobre o que o VENDEDOR recebe — lista 115, recebe 100) e o
líquido dela é SALDO, não dinheiro: a UI nunca mistura as duas coisas num
número só (mesma regra do rodapé do inventário).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import fee_calculator as calc
from skinvault.ui import theme as t

_COLS = ["Plataforma", "Taxa", "Você recebe", "Preço de listagem",
         "Taxa (R$)", "Lucro", "Moeda"]


class FeeCalculatorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None,
                 cost: str = "", margin: str = "0",
                 quantity: str = "1") -> None:
        super().__init__(parent)
        self.setWindowTitle("Calculadora de Arbitragem/Taxas")
        self.setMinimumWidth(640)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._build()
        self._cost.setText(cost)
        self._margin.setText(margin)
        self._quantity.setText(quantity)
        self._recalc()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 18, 20, 18)

        cab = QVBoxLayout()
        cab.setSpacing(2)
        title = QLabel("Calculadora de Arbitragem/Taxas")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};")
        cab.addWidget(title)
        sub = QLabel(
            "Dado o custo e a margem desejada, mostra por quanto listar em"
            " cada plataforma e quanto sobra líquido.")
        sub.setWordWrap(True)
        sub.setStyleSheet(t.label_caption())
        cab.addWidget(sub)
        lay.addLayout(cab)

        inp = QHBoxLayout()
        inp.setSpacing(t.SPACE_MD)
        inp.addWidget(self._campo("Custo (R$)", "_cost"))
        inp.addWidget(self._campo("Margem desejada (%)", "_margin"))
        inp.addWidget(self._campo("Quantidade", "_quantity"))
        lay.addLayout(inp)

        self._note = QLabel(
            "Steam: taxa sobre o que o vendedor recebe — você lista por "
            "R$ 115 e recebe R$ 100. Externos: % do preço de venda. "
            "Saldo Steam não saca pra conta.")
        self._note.setWordWrap(True)
        self._note.setStyleSheet(t.label_caption())
        lay.addWidget(self._note)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        t.configure_table(self._table)
        # A ordem da tabela É a ordem da quote_all (menor preço primeiro);
        # sort do usuário faria sentido, mas re-ordenar na digitação confunde.
        self._table.setSortingEnabled(False)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self._table, 1)

        self._resumo = QLabel("")
        self._resumo.setStyleSheet(t.label_section())
        lay.addWidget(self._resumo)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close = QPushButton("Fechar")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setStyleSheet(t.btn_ghost())
        close.clicked.connect(self.reject)
        btn_row.addWidget(close)
        lay.addLayout(btn_row)

    def _campo(self, label: str, attr: str) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(t.label_caption_bold())
        col.addWidget(lbl)
        edit = QLineEdit()
        edit.setStyleSheet(t.input_style())
        edit.textChanged.connect(self._recalc)
        setattr(self, attr, edit)
        col.addWidget(edit)
        return wrap

    def _recalc(self) -> None:
        try:
            cost = float(self._cost.text().replace(",", ".") or 0)
        except ValueError:
            cost = 0.0
        try:
            margin = float(self._margin.text().replace(",", ".") or 0)
        except ValueError:
            margin = 0.0
        try:
            qty = int(self._quantity.text() or 1)
        except ValueError:
            qty = 1
        if cost <= 0:
            self._table.setRowCount(0)
            self._resumo.setText("Informe um custo maior que zero.")
            return

        quotes = calc.quote_all(cost, margin, qty)
        self._table.setRowCount(0)
        for i, q in enumerate(quotes):
            self._table.insertRow(i)
            monetario = q["currency"] == "saldo Steam"
            for col, (txt, chave) in enumerate([
                ("plataforma", q["label"]),
                ("taxa", f"{q['fee'] * 100:.0f}%"),
                ("recebe", t.brl(q["net_total"])),
                ("listagem", t.brl(q["list_total"])),
                ("fee_abs", t.brl(q["fee_abs"] * q["quantity"])),
                ("lucro", t.brl(q["profit_total"])),
                ("moeda", q["currency"]),
            ]):
                item = QTableWidgetItem(str(chave))
                if col != 0 and col != 6:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter)
                if col == 3:  # preço de listagem: destaque
                    item.setForeground(QBrush(QColor(t.ACCENT)))
                if monetario and col in (2, 3, 4, 5):
                    item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
                self._table.setItem(i, col, item)
        menor = quotes[0]
        self._resumo.setText(
            f"Menor capital preso: {menor['label']} — lista "
            f"{t.brl(menor['list_total'])} p/ receber "
            f"{t.brl(menor['net_total'])} líquido.")
