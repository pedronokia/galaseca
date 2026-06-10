"""Dialogo de boas-vindas — primeira sessao do usuario.

Mostra 3 feature cards (Inventario / Scanner / Alertas) com texto curto
explicando o que cada um faz. Exibido uma vez (settings.welcome_seen).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from skinvault.ui import theme as t
from skinvault.ui.components import Card


def _feature_card(icon: str, title: str, desc: str) -> Card:
    card = Card()
    icn = QLabel(icon)
    icn.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icn.setStyleSheet(
        f"color: {t.ACCENT}; font-size: {t.FS_ICON_MD};"
        f" font-family: {t.FONT_FAMILY};"
    )
    card.layout().addWidget(icn)

    ttl = QLabel(title)
    ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ttl.setStyleSheet(t.label_section())
    card.layout().addWidget(ttl)

    d = QLabel(desc)
    d.setAlignment(Qt.AlignmentFlag.AlignCenter)
    d.setWordWrap(True)
    d.setStyleSheet(t.label_body_muted())
    card.layout().addWidget(d)
    card.setMinimumWidth(220)
    return card


class WelcomeDialog(QDialog):
    """Modal de boas-vindas com 3 features + CTA."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bem-vindo ao SkinVault")
        self.setMinimumWidth(760)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 36, 40, 32)
        outer.setSpacing(20)

        # Hero
        title = QLabel("Bem-vindo ao SkinVault")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(t.label_hero())
        outer.addWidget(title)

        sub = QLabel(
            "Análise factual do Steam Community Market — sem palpites, "
            "só dados. Aqui vai um resumo do que você pode fazer:"
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(t.label_body_muted())
        outer.addWidget(sub)

        # 3 feature cards
        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(_feature_card(
            "◐",
            "Conta + Inventário",
            "Sincronize com a Steam e veja seu inventário avaliado "
            "ao preço de mercado (já com a taxa de 15% descontada)."
        ), 1)
        row.addWidget(_feature_card(
            "◎",
            "Scanner de Skins",
            "Score 0–100 por item baseado em spread, tendência, volume "
            "e oferta. Saiba o que comprar e o que evitar."
        ), 1)
        row.addWidget(_feature_card(
            "★",
            "Watchlist + Alertas",
            "Defina alvos de preço, anomalias de volume e quedas de "
            "oferta. Notificações na bandeja quando a regra dispara."
        ), 1)
        outer.addLayout(row)

        # CTA
        cta = QPushButton("Vamos lá")
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setStyleSheet(t.btn_primary(padding="14px 36px", fs=t.FS_INPUT))
        cta.setToolTip("Fecha este modal e abre o app. Voce nao vera mais.")
        cta.clicked.connect(self.accept)
        outer.addWidget(cta, 0, Qt.AlignmentFlag.AlignCenter)
