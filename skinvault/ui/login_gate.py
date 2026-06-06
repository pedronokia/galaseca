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
        hero.setSpacing(20)

        icon = QLabel("◐")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {t.ACCENT}; font-size: 96pt;"
            f" font-family: {t.FONT_FAMILY};"
        )
        hero.addWidget(icon)

        title = QLabel("SkinVault")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: 40pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY}; letter-spacing: -1px;"
        )
        hero.addWidget(title)

        tagline = QLabel("Análise inteligente do Steam Community Market")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_INPUT};"
            f" font-family: {t.FONT_FAMILY}; font-weight: 400;"
        )
        hero.addWidget(tagline)

        desc = QLabel(
            "Conecte sua conta Steam para acompanhar seu inventário, "
            "histórico de mercado e simular trades com o lucro real "
            "após a taxa de 15%."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setFixedWidth(480)
        desc.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY}; line-height: 1.6;"
        )
        hero.addWidget(desc, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addLayout(hero)
        outer.addSpacing(32)

        # ── CTA enorme ────────────────────────────────────
        connect_btn = QPushButton("  Conectar conta Steam  ")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setMinimumHeight(56)
        connect_btn.setFixedWidth(340)
        connect_btn.setStyleSheet(t.btn_primary(padding="16px 40px",
                                                fs="13pt"))
        connect_btn.clicked.connect(self._on_connect)
        outer.addWidget(connect_btn, 0, Qt.AlignmentFlag.AlignCenter)

        outer.addSpacing(48)

        # ── Disclaimer ────────────────────────────────────
        warning = QLabel(
            "Cookies de sessão ficam apenas no seu computador "
            "(data/steam_session.json). Você pode desconectar a qualquer momento."
        )
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setWordWrap(True)
        warning.setFixedWidth(480)
        warning.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        outer.addWidget(warning, 0, Qt.AlignmentFlag.AlignCenter)

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
