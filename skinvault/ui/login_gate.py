"""LoginGate -- tela inicial bloqueante quando nao ha sessao Steam (F11).

Emite session_connected(SteamSession) ao terminar o login.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault import steam_session
from skinvault.steam_login_dialog import build_steam_login_dialog
from skinvault.ui import theme as t
from skinvault.ui.components import Card, line_icon_pixmap


def _feature_card(icon_name: str, title: str, desc: str) -> Card:
    """Card de feature: glifo LineIcon + titulo + 1 linha de valor.

    Mesmo padrao do welcome_dialog, trazido pro gate pra preencher o
    espaco e dizer *o que* cada area faz (nao so o nome).
    """
    card = Card()
    card.setMinimumWidth(150)

    icn = QLabel()
    icn.setPixmap(line_icon_pixmap(icon_name, t.ACCENT, 26))
    icn.setAlignment(Qt.AlignmentFlag.AlignCenter)
    card.layout().addWidget(icn, 0, Qt.AlignmentFlag.AlignCenter)

    ttl = QLabel(title)
    ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    ttl.setStyleSheet(t.label_section())
    card.layout().addWidget(ttl)

    d = QLabel(desc)
    d.setAlignment(Qt.AlignmentFlag.AlignCenter)
    d.setWordWrap(True)
    d.setStyleSheet(t.label_body_muted())
    card.layout().addWidget(d)
    return card


class LoginGate(QWidget):
    """Tela cheia centralizada com CTA pra conectar Steam."""

    session_connected = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LoginGate")
        self.setStyleSheet(f"QWidget#LoginGate {{ background: {t.BG}; }}")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(0)

        # ── Hero central ──────────────────────────────────
        hero = QVBoxLayout()
        hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.setSpacing(12)

        # Accent line decorativa
        accent_line = QLabel()
        accent_line.setFixedSize(48, 3)
        accent_line.setStyleSheet(
            f"background: {t.ACCENT}; border-radius: 2px;"
        )
        hero.addWidget(accent_line, 0, Qt.AlignmentFlag.AlignCenter)

        hero.addSpacing(8)

        title = QLabel("SkinVault")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_ICON_LG}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY}; letter-spacing: -1px;"
        )
        hero.addWidget(title)

        tagline = QLabel("Análise inteligente do Steam Community Market")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: 14pt;"
            f" font-family: {t.FONT_FAMILY}; font-weight: 400;"
        )
        hero.addWidget(tagline)

        outer.addLayout(hero)
        outer.addSpacing(32)

        # ── Feature cards ─────────────────────────────────
        cards_host = QWidget()
        cards_host.setMaximumWidth(720)
        cards_row = QHBoxLayout(cards_host)
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(12)
        cards_row.addWidget(_feature_card(
            "wallet", "Inventário", "Avaliado a preço de mercado"
        ), 1)
        cards_row.addWidget(_feature_card(
            "history", "Histórico", "Evolução do patrimônio"
        ), 1)
        cards_row.addWidget(_feature_card(
            "calc", "Simulação", "Teste trades sem risco"
        ), 1)
        cards_row.addWidget(_feature_card(
            "radar", "Scanner", "Score 0–100 por item"
        ), 1)
        outer.addWidget(cards_host, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addSpacing(40)

        # ── CTA enorme ────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        connect_btn = QPushButton("  Conectar com Steam  ")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setMinimumHeight(64)
        connect_btn.setFixedWidth(400)
        connect_btn.setStyleSheet(t.btn_steam(padding="18px 44px", fs="14pt"))
        connect_btn.setIcon(QIcon(line_icon_pixmap("steam", "#DDF4FF", 20)))
        connect_btn.setIconSize(QSize(20, 20))
        connect_btn.setToolTip(
            "Abre o login do Steam no Chrome. Sua sessao fica salva no "
            "PC — voce so faz login uma vez."
        )
        connect_btn.clicked.connect(self._on_connect)
        btn_row.addWidget(connect_btn)

        outer.addLayout(btn_row)

        outer.addSpacing(16)

        footnote = QLabel(
            "Cookies de sessão salvos localmente · "
            "Desconecte quando quiser"
        )
        footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footnote.setStyleSheet(t.label_caption())
        outer.addWidget(footnote, 0, Qt.AlignmentFlag.AlignCenter)

    def _on_connect(self) -> None:
        dlg = build_steam_login_dialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sess = dlg.session
        if not sess or not sess.is_complete():
            QMessageBox.warning(
                self, "Login incompleto",
                "Nao foi possivel capturar a sessao. Tente novamente."
            )
            return
        steam_session.persist(sess)
        self.session_connected.emit(sess)
