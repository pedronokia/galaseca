"""LoginGate -- tela inicial bloqueante quando nao ha sessao Steam (F11).

Emite session_connected(SteamSession) ao terminar o login.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
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


class LoginGate(QWidget):
    """Tela cheia centralizada com CTA pra conectar Steam."""

    session_connected = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {t.BG};")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.setSpacing(0)

        # ── Hero central ──────────────────────────────────
        hero = QVBoxLayout()
        hero.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.setSpacing(16)

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

        features = QLabel("Inventário  ·  Histórico  ·  Simulação  ·  Scanner")
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        features.setStyleSheet(
            f"color: {t.ACCENT}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY}; font-weight: 500;"
            f" letter-spacing: 2px;"
        )
        hero.addWidget(features)

        outer.addLayout(hero)
        outer.addSpacing(48)

        # ── CTA enorme ────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        connect_btn = QPushButton("  Conectar com Steam  ")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setMinimumHeight(64)
        connect_btn.setFixedWidth(400)
        connect_btn.setStyleSheet(t.btn_steam(padding="18px 44px", fs="14pt"))
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
