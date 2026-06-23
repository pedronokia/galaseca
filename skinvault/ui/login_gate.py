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
from skinvault.ui.components import LineIcon, line_icon_pixmap


def _divider() -> QWidget:
    """Linha fina 1px (BORDER) pra separar blocos dentro do cartao."""
    d = QWidget()
    d.setFixedHeight(1)
    d.setStyleSheet(f"background: {t.BORDER};")
    return d


def _feature_row(icon_name: str, title: str, desc: str) -> QWidget:
    """Linha de feature: glifo LineIcon + titulo + descricao (lista limpa).

    Substitui as caixas/cards — leve, alinhada a esquerda, sem fundo.
    """
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)

    icn = LineIcon(icon_name, t.ACCENT)
    lay.addWidget(icn, 0, Qt.AlignmentFlag.AlignTop)

    text = QVBoxLayout()
    text.setContentsMargins(0, 0, 0, 0)
    text.setSpacing(1)

    ttl = QLabel(title)
    ttl.setStyleSheet(
        f"color: {t.TEXT}; font-size: {t.FS_INPUT}; font-weight: 600;"
        f" font-family: {t.FONT_FAMILY};"
    )
    text.addWidget(ttl)

    d = QLabel(desc)
    d.setWordWrap(True)
    d.setStyleSheet(t.label_caption())
    text.addWidget(d)

    lay.addLayout(text, 1)
    return row


class LoginGate(QWidget):
    """Tela cheia com cartao de login contido e centralizado."""

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

        # ── Cartao contido ────────────────────────────────
        card = QWidget()
        card.setObjectName("LoginCard")
        card.setFixedWidth(440)
        card.setStyleSheet(
            f"QWidget#LoginCard {{ background: {t.BG_ELEVATED};"
            f" border: 1px solid {t.BORDER};"
            f" border-radius: {t.RADIUS_LG}px; }}"
        )
        col = QVBoxLayout(card)
        col.setContentsMargins(36, 34, 36, 28)
        col.setSpacing(0)

        # Accent line decorativa
        accent_line = QLabel()
        accent_line.setFixedSize(40, 3)
        accent_line.setStyleSheet(f"background: {t.ACCENT}; border-radius: 2px;")
        col.addWidget(accent_line)
        col.addSpacing(18)

        title = QLabel("SkinVault")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_HERO}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY}; letter-spacing: -1px;"
        )
        col.addWidget(title)
        col.addSpacing(10)

        tagline = QLabel("Análise inteligente do Steam Community Market")
        tagline.setWordWrap(True)
        tagline.setStyleSheet(t.label_body_muted())
        col.addWidget(tagline)

        col.addSpacing(24)
        col.addWidget(_divider())
        col.addSpacing(24)

        # ── Lista de features ─────────────────────────────
        features = [
            ("wallet", "Inventário", "Avaliado a preço de mercado, já com a taxa"),
            ("history", "Histórico", "Evolução do patrimônio a cada sync"),
            ("calc", "Simulação", "Teste trades antes de fazer"),
            ("radar", "Scanner", "Score 0–100 do que comprar e evitar"),
        ]
        for i, (icon, ttl, desc) in enumerate(features):
            if i:
                col.addSpacing(16)
            col.addWidget(_feature_row(icon, ttl, desc))

        col.addSpacing(26)

        # ── CTA full-width ────────────────────────────────
        connect_btn = QPushButton("  Conectar com Steam  ")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setMinimumHeight(52)
        connect_btn.setStyleSheet(t.btn_steam(padding="14px 24px", fs="12pt"))
        connect_btn.setIcon(QIcon(line_icon_pixmap("steam", "#DDF4FF", 19)))
        connect_btn.setIconSize(QSize(19, 19))
        connect_btn.setToolTip(
            "Abre o login do Steam no Chrome. Sua sessao fica salva no "
            "PC — voce so faz login uma vez."
        )
        connect_btn.clicked.connect(self._on_connect)
        col.addWidget(connect_btn)

        col.addSpacing(14)

        footnote = QLabel(
            "Cookies de sessão salvos localmente · Desconecte quando quiser"
        )
        footnote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footnote.setWordWrap(True)
        footnote.setStyleSheet(t.label_caption())
        col.addWidget(footnote)

        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)

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
