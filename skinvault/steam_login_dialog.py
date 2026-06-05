"""Dialog de login Steam embutido (F10).

Abre um QWebEngineView com a pagina de login do Steam. O usuario loga
manualmente (incluindo 2FA). Cookies de steamcommunity.com sao
interceptados via QWebEngineProfile.cookieStore(); quando o redirect
final cai em /profiles/{id} ou /id/{vanity}, a sessao esta completa.

PyQt6-WebEngine e' opcional em tempo de import: se nao estiver instalado,
build_steam_login_dialog() retorna None e a UI mostra uma mensagem
de erro com instrucoes de instalacao.
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
_SUCCESS_FRAGMENTS = ("/profiles/", "/id/")
_LOGIN_FRAGMENTS = ("/login", "/openid")


def _webengine_available() -> bool:
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
        return True
    except ImportError:
        return False


class SteamLoginDialog(QDialog):
    """QDialog com webview embutido. Em sucesso, expoe self.session."""

    session_captured = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conectar conta Steam")
        self.resize(1000, 720)
        self.session: Optional[SteamSession] = None
        self._cookies: dict = {}
        self._finalized = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # webview
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        # Off-the-record profile (memory only): nao polui o Chromium global
        # e nao interfere com outras instancias do Qt no mesmo processo.
        self._profile = QWebEngineProfile(self)
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)

        from PyQt6.QtWebEngineCore import QWebEnginePage
        self._page = QWebEnginePage(self._profile, self)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._view.urlChanged.connect(self._on_url_changed)
        self._view.load(QUrl(_LOGIN_URL))
        layout.addWidget(self._view, 1)

        # footer
        footer = QWidget(self)
        flayout = QHBoxLayout(footer)
        flayout.setContentsMargins(16, 12, 16, 12)
        self._status = QLabel("Faça login na Steam. Após autenticar, a janela "
                              "fecha sozinha.")
        flayout.addWidget(self._status, 1)

        self._reload_btn = QPushButton("Reabrir login da Steam")
        self._reload_btn.clicked.connect(
            lambda: self._view.load(QUrl(_LOGIN_URL))
        )
        flayout.addWidget(self._reload_btn)

        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        flayout.addWidget(cancel)

        layout.addWidget(footer)

    def _on_cookie_added(self, cookie) -> None:
        """Filtra cookies de steamcommunity.com e acumula."""
        try:
            domain = bytes(cookie.domain()).decode("utf-8", "replace")
        except Exception:
            domain = ""
        if "steamcommunity.com" not in domain:
            return
        try:
            name = bytes(cookie.name()).decode("utf-8", "replace")
            value = bytes(cookie.value()).decode("utf-8", "replace")
        except Exception:
            return
        if not name:
            return
        self._cookies = merge_cookies(self._cookies, {name: value})

    def _on_url_changed(self, url: QUrl) -> None:
        if self._finalized:
            return
        s = url.toString()
        # ainda em fluxo de login
        if any(f in s for f in _LOGIN_FRAGMENTS):
            return
        # caiu no perfil = logado
        if any(f in s for f in _SUCCESS_FRAGMENTS):
            self._finalize()

    def _finalize(self) -> None:
        steamid = extract_steamid_from_cookie(self._cookies) or ""
        if not steamid or not self._cookies.get("steamLoginSecure"):
            # Sessao incompleta: ignora e aguarda mais cookies
            return
        self._finalized = True
        self.session = SteamSession(
            steamid=steamid,
            cookies=dict(self._cookies),
            captured_at=time.time(),
        )
        self.session_captured.emit(self.session)
        self.accept()


def build_steam_login_dialog(parent: QWidget | None = None) -> SteamLoginDialog | None:
    """Cria o dialog se QtWebEngine estiver disponivel. Caso contrario,
    mostra QMessageBox com instrucoes e retorna None.
    """
    if not _webengine_available():
        QMessageBox.warning(
            parent,
            "QtWebEngine ausente",
            "Para conectar a conta Steam, instale a dependencia:\n\n"
            "    pip install PyQt6-WebEngine\n\n"
            "Depois reabra o aplicativo.",
        )
        return None
    try:
        return SteamLoginDialog(parent)
    except ImportError:
        QMessageBox.warning(
            parent,
            "QtWebEngine ausente",
            "Para conectar a conta Steam, instale a dependencia:\n\n"
            "    pip install PyQt6-WebEngine",
        )
        return None
