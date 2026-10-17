"""Card e StatCard — frames estilizados (F11)."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLayout, QVBoxLayout, QWidget

from skinvault.ui import theme as t


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None,
                 padding: tuple[int, int, int, int] = t.CARD_PAD_LG,
                 radius: int = t.RADIUS_LG) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(t.card_style(radius))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*padding)
        lay.setSpacing(10)

    def set_layout(self, layout: QLayout) -> None:
        old = self.layout()
        if old is not None:
            QWidget().setLayout(old)
        self.setLayout(layout)


class StatCard(Card):
    def __init__(self, label: str, value: str = "—",
                 accent: str = t.TEXT,
                 icon: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=(20, 18, 20, 18), radius=t.RADIUS_LG)
        self.layout().setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._label.setStyleSheet(t.label_caption())
        header.addWidget(self._label)
        header.addStretch(1)
        from skinvault.ui.components import LineIcon
        self._icon_w = LineIcon("info", t.TEXT_MUTED) if icon else None
        if self._icon_w is not None:
            self._icon_w.set_name(icon)
            header.addWidget(self._icon_w, 0, Qt.AlignmentFlag.AlignRight)
        self.layout().addLayout(header)

        val_row = QHBoxLayout()
        val_row.setContentsMargins(0, 0, 0, 0)
        val_row.setSpacing(t.SPACE_SM)
        self._value = QLabel(value)
        self._value.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._value.setStyleSheet(
            f"color: {self._value_color(value, accent)};"
            f" font-size: {t.FS_STAT}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        val_row.addWidget(self._value)
        self._badge = QLabel("")
        self._badge.setVisible(False)
        self._badge.setStyleSheet(
            f"padding: 2px 8px; border-radius: 10px;"
            f" font-size: {t.FS_MUTED}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        val_row.addWidget(self._badge)
        val_row.addStretch(1)
        self.layout().addLayout(val_row)

        self._delta = QLabel("")
        self._delta.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._delta.setVisible(False)
        self.layout().addWidget(self._delta)
        # Conteudo preso no topo: numa linha de cartoes de mesma altura, o
        # que nao tinha legenda distribuia a sobra entre rotulo e numero e
        # o numero descia em relacao aos vizinhos.
        self.layout().addStretch(1)
        self.setMinimumWidth(120)

    def set_delta(self, pct: float | None,
                  label: str = "") -> None:
        if pct is None and not label:
            # Limpar o texto junto: esconder sozinho deixava a legenda
            # antiga guardada, e a proxima avaliacao que voltasse a mostrar
            # o rotulo exibia por um instante o numero da avaliacao anterior.
            self._delta.setText("")
            self._delta.setVisible(False)
            return
        self._delta.setVisible(True)
        if pct is None:
            self._delta.setText(label)
            self._delta.setStyleSheet(t.label_caption())
            return
        if pct > 0:
            prefix = chr(9650)
            color = t.POSITIVE
            formatted = f"+{pct:.1f}%".replace(".", ",")
        elif pct < 0:
            prefix = chr(9660)
            color = t.DANGER
            formatted = f"{pct:.1f}%".replace(".", ",")
        else:
            prefix = chr(8212)
            color = t.TEXT_MUTED
            formatted = "0,0%"
        suffix = f" {label}" if label else ""
        self._delta.setText(f"{prefix} {formatted}{suffix}")
        self._delta.setStyleSheet(
            f"color: {color}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )

    @staticmethod
    def _value_color(value: str, accent: str) -> str:
        return t.TEXT_MUTED if value.strip() in ("—", "") else accent

    def set_label(self, text: str) -> None:
        """Troca o rotulo do cartao.

        Existe porque um cartao pode passar a mostrar outra coisa quando a
        fonte primaria falha -- e manter o rotulo antigo mentiria sobre o
        que o numero significa.
        """
        self._label.setText(text)

    def set_value(self, value: str, accent: str | None = None) -> None:
        self._value.setText(value)
        if accent:
            self._value.setStyleSheet(
                f"color: {self._value_color(value, accent)};"
                f" font-size: {t.FS_STAT}; font-weight: 600;"
                f" font-family: {t.FONT_FAMILY};"
            )

    def set_badge(self, text: str, kind: str = "neutral") -> None:
        if kind == "positive":
            bg, fg = t.POSITIVE_DIM, t.POSITIVE
        elif kind == "danger":
            bg, fg = t.DANGER_DIM, t.DANGER
        else:
            bg, fg = t.SURFACE, t.TEXT_MUTED
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"padding: 2px 8px; border-radius: 10px;"
            f" font-size: {t.FS_MUTED}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
            f" background: {bg}; color: {fg};"
        )
        self._badge.setVisible(True)

    def clear_badge(self) -> None:
        self._badge.setVisible(False)
        self._badge.setText("")

    def set_icon(self, name: str) -> None:
        if self._icon_w is None:
            from skinvault.ui.components import LineIcon
            self._icon_w = LineIcon(name, t.TEXT_MUTED)
            hdr_item = self.layout().itemAt(0)
            if hdr_item is not None and hdr_item.layout() is not None:
                hdr_item.layout().addWidget(
                    self._icon_w, 0, Qt.AlignmentFlag.AlignRight)
            else:
                self._icon_w.setParent(self)
                self._icon_w.show()
        else:
            self._icon_w.set_name(name)
