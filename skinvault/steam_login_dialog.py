"""Dialog de login Steam (sem WebEngine).

Abre o navegador padrao do usuario na pagina de login da Steam.
Usuario loga manualmente, copia os cookies e cola no dialog.
Suporta tanto cookie string (nome=valor; nome=valor) como JSON.
"""
from __future__ import annotations

import json
import re
import time
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault.steam_session import (
    SteamSession,
    extract_steamid_from_cookie,
    merge_cookies,
)


_LOGIN_URL = "https://steamcommunity.com/login/home/?goto=my"


def _parse_cookie_input(text: str) -> dict:
    """Converte input do usuario em dict de cookies.

    Aceita:
      - JSON dict: {"steamLoginSecure": "...", "sessionid": "..."}
      - Cookie string: steamLoginSecure=xxx; sessionid=yyy
      - Linhas chave=valor
    """
    text = text.strip()
    if not text:
        return {}
    # Tenta JSON primeiro
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, ValueError):
            pass
    # Cookie string ou linhas chave=valor
    cookies: dict = {}
    for part in text.replace("\n", ";").replace("\r", "").split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


class SteamLoginDialog(QDialog):
    """Dialog manual: usuario cola cookies da Steam.

    self.session e' preenchido apos accept() se os cookies tiverem
    steamLoginSecure valido.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conectar conta Steam")
        self.resize(660, 440)
        self.session: Optional[SteamSession] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        title = QLabel(
            "Conectar conta Steam"
        )
        title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        layout.addWidget(title)

        instructions = QLabel(
            "1. Clique em \"Abrir navegador\" e faça login na Steam.\n"
            "2. Após logar, volte aqui.\n"
            "3. Copie os cookies da página steamcommunity.com:\n"
            "   - Chrome: F12 → Application → Cookies → steamcommunity.com\n"
            "   - Firefox: F12 → Storage → Cookies\n"
            "4. Selecione TODOS os cookies, copie e cole abaixo.\n"
            "5. Clique em \"Conectar\"."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            "color: #9D9DA8; font-size: 10pt; line-height: 1.5;"
        )
        layout.addWidget(instructions)

        btn_row = QHBoxLayout()
        open_btn = QPushButton("Abrir navegador")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setMinimumHeight(36)
        open_btn.setStyleSheet(self._btn_primary())
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(_LOGIN_URL)))
        btn_row.addWidget(open_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        paste_label = QLabel("Cookies da Steam (cole abaixo):")
        paste_label.setStyleSheet("font-size: 10pt; font-weight: 600;")
        layout.addWidget(paste_label)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText(
            'Cole os cookies aqui...\n'
            'Ex: steamLoginSecure=xxxxx; sessionid=yyyyy\n'
            'Ou JSON: {"steamLoginSecure": "xxx", "sessionid": "yyy"}'
        )
        self._input.setStyleSheet(
            "background: #1E1E28; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px;"
            " color: #E6E6EA; font-family: Consolas; font-size: 10pt;"
        )
        self._input.setMinimumHeight(120)
        layout.addWidget(self._input, 1)

        footer = QHBoxLayout()
        self._status = QLabel("")
        self._status.setStyleSheet("color: #9D9DA8; font-size: 9pt;")
        footer.addWidget(self._status, 1)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(self._btn_ghost())
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        connect_btn = QPushButton("  Conectar  ")
        connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        connect_btn.setMinimumHeight(36)
        connect_btn.setStyleSheet(self._btn_primary())
        connect_btn.clicked.connect(self._on_connect)
        footer.addWidget(connect_btn)

        layout.addLayout(footer)

    def _parse_input(self) -> dict:
        text = self._input.toPlainText().strip()
        return _parse_cookie_input(text)

    def _on_connect(self) -> None:
        cookies = self._parse_input()
        if not cookies:
            self._status.setText("Nenhum cookie encontrado. Cole os cookies primeiro.")
            return
        steamid = extract_steamid_from_cookie(cookies) or ""
        if not steamid or not cookies.get("steamLoginSecure"):
            self._status.setText(
                "Cookie steamLoginSecure não encontrado ou inválido. "
                "Certifique-se de copiar os cookies de steamcommunity.com."
            )
            return
        merged = merge_cookies({}, cookies)
        if not merged.get("steamLoginSecure"):
            self._status.setText("Cookies inválidos. Tente novamente.")
            return
        self.session = SteamSession(
            steamid=steamid,
            cookies=merged,
            captured_at=time.time(),
        )
        self.accept()

    @staticmethod
    def _btn_primary() -> str:
        return (
            "QPushButton { background: #1B2838; color: #66C0F4;"
            " border: 1px solid #66C0F4; border-radius: 6px;"
            " font-size: 10pt; font-weight: 600; padding: 8px 20px; }"
            "QPushButton:hover { background: #66C0F4; color: #1B2838; }"
        )

    @staticmethod
    def _btn_ghost() -> str:
        return (
            "QPushButton { background: transparent; color: #9D9DA8;"
            " border: none; font-size: 10pt; padding: 8px 16px; }"
            "QPushButton:hover { color: #E6E6EA; }"
        )


def build_steam_login_dialog(
    parent: QWidget | None = None,
) -> SteamLoginDialog | None:
    """Cria o dialog de login Steam (sem WebEngine)."""
    return SteamLoginDialog(parent)
