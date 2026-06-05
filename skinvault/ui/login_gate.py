"""LoginGate -- tela inicial bloqueante quando nao ha sessao Steam (F11).

Emite session_connected(SteamSession) ao terminar o login.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
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
from skinvault.ui.components import Card


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

        card = Card(self, padding=(48, 40, 48, 40))
        card.setFixedWidth(560)
        body = card.layout()
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setSpacing(18)

        icon = QLabel("◐")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {t.STEAM_BLUE}; font-size: 64pt;"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(icon)

        title = QLabel("Bem-vindo ao SkinVault")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(title)

        desc = QLabel(
            "Conecte sua conta Steam para acessar seu inventário,\n"
            "histórico de mercado e simular trades com o lucro real\n"
            "após a taxa de 15%."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(desc)

        connect_btn = QPushButton("  Conectar conta Steam  ")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setMinimumHeight(48)
        connect_btn.setStyleSheet(t.btn_primary(padding="14px 32px",
                                                fs=t.FS_INPUT))
        connect_btn.clicked.connect(self._on_connect)
        body.addWidget(connect_btn)

        warning = QLabel(
            "Cookies de sessão ficam apenas no seu computador "
            "(data/steam_session.json). Você pode desconectar a qualquer momento."
        )
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setWordWrap(True)
        warning.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(warning)

        outer.addWidget(card)

    def _on_connect(self) -> None:
        dlg = build_steam_login_dialog(self)
        if dlg is None:
            return
        from PyQt6.QtWidgets import QDialog
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
