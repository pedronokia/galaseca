"""Dialog de login Steam embutido (F10).

Abre um QWebEngineView com a pagina de login do Steam. O usuario loga
manualmente (incluindo 2FA). Cookies de steamcommunity.com sao
interceptados via QWebEngineProfile.cookieStore(); quando o redirect
final cai em /profiles/{id} ou /id/{vanity}, a sessao esta completa.

PyQt6-WebEngine e' opcional: se nao estiver instalado,
build_steam_login_dialog() oferece instalacao automatica via pip.
"""
from __future__ import annotations

import subprocess
import sys
import time
from typing import Optional

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
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

# Cache de disponibilidade do WebEngine (evita import repetido)
_WEBENGINE_OK: bool | None = None


def _check_webengine() -> bool:
    global _WEBENGINE_OK
    if _WEBENGINE_OK is not None:
        return _WEBENGINE_OK
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
        _WEBENGINE_OK = True
    except ImportError:
        _WEBENGINE_OK = False
    return _WEBENGINE_OK


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
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._profile = QWebEngineProfile(self)
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)

        self._page = QWebEnginePage(self._profile, self)
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._view.urlChanged.connect(self._on_url_changed)
        self._view.load(QUrl(_LOGIN_URL))
        layout.addWidget(self._view, 1)

        footer = QWidget(self)
        flayout = QHBoxLayout(footer)
        flayout.setContentsMargins(16, 12, 16, 12)
        self._status = QLabel(
            "Faça login na Steam. Após autenticar, a janela fecha sozinha."
        )
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

    def _domain(self, cookie) -> str:
        raw = cookie.domain()
        if isinstance(raw, str):
            return raw
        try:
            return bytes(raw).decode("utf-8", "replace")
        except Exception:
            return ""

    def _to_str(self, raw) -> str:
        if isinstance(raw, str):
            return raw
        try:
            return bytes(raw).decode("utf-8", "replace")
        except Exception:
            return ""

    def _on_cookie_added(self, cookie) -> None:
        if "steamcommunity.com" not in self._domain(cookie):
            return
        name = self._to_str(cookie.name())
        value = self._to_str(cookie.value())
        if not name:
            return
        if not name:
            return
        self._cookies = merge_cookies(self._cookies, {name: value})

    def _on_url_changed(self, url: QUrl) -> None:
        if self._finalized:
            return
        s = url.toString()
        if any(f in s for f in _LOGIN_FRAGMENTS):
            return
        if any(f in s for f in _SUCCESS_FRAGMENTS):
            self._finalize()

    def _finalize(self) -> None:
        steamid = extract_steamid_from_cookie(self._cookies) or ""
        if not steamid or not self._cookies.get("steamLoginSecure"):
            return
        self._finalized = True
        self.session = SteamSession(
            steamid=steamid,
            cookies=dict(self._cookies),
            captured_at=time.time(),
        )
        self.session_captured.emit(self.session)
        self.accept()


def _install_webengine(parent: QWidget | None = None) -> bool:
    """Tenta instalar PyQt6-WebEngine via pip. Retorna True se sucesso."""
    msg = QMessageBox(parent)
    msg.setWindowTitle("Instalar QtWebEngine")
    msg.setText(
        "O PyQt6-WebEngine nao esta instalado.\n\n"
        "Deseja que o SkinVault tente instalar automaticamente?\n"
        "(necessario acesso a internet e permisao de administrador)"
    )
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msg.setDefaultButton(QMessageBox.StandardButton.Yes)
    if msg.exec() != QMessageBox.StandardButton.Yes:
        return False

    progress = QProgressBar()
    progress.setRange(0, 0)
    progress.setVisible(True)
    progress.setFixedHeight(24)

    install_dlg = QDialog(parent)
    install_dlg.setWindowTitle("Instalando…")
    install_dlg.resize(400, 100)
    install_dlg.setModal(True)
    lay = QVBoxLayout(install_dlg)
    lbl = QLabel("Instalando PyQt6-WebEngine...\nAguarde alguns segundos.")
    lay.addWidget(lbl)
    lay.addWidget(progress)
    install_dlg.show()

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "PyQt6-WebEngine"],
            capture_output=True, text=True, timeout=120,
        )
        install_dlg.close()
        if result.returncode != 0:
            QMessageBox.warning(
                parent, "Falha na instalacao",
                "Nao foi possivel instalar automaticamente.\n\n"
                "Erro:\n" + result.stderr[-300:] + "\n\n"
                "Tente manualmente:\n"
                "    pip install PyQt6-WebEngine",
            )
            return False
        # Tenta importar no processo atual
        global _WEBENGINE_OK
        _WEBENGINE_OK = None
        if _check_webengine():
            QMessageBox.information(
                parent, "Instalado com sucesso",
                "PyQt6-WebEngine instalado. Clique em Conectar novamente.",
            )
            return True
        # Instalou mas o import falhou — precisa reiniciar
        QMessageBox.warning(
            parent, "Reinicio necessario",
            "PyQt6-WebEngine foi instalado, mas o Python precisa reiniciar\n"
            "para reconhecer a nova biblioteca.\n\n"
            "Feche e abra o SkinVault novamente.",
        )
        return False
    except subprocess.TimeoutExpired:
        install_dlg.close()
        QMessageBox.warning(
            parent, "Tempo excedido",
            "A instalacao excedeu 120s. Verifique sua conexao e tente:\n"
            "    pip install PyQt6-WebEngine",
        )
        return False
    except Exception as exc:
        install_dlg.close()
        QMessageBox.warning(
            parent, "Erro na instalacao",
            f"Erro inesperado: {exc}\n\n"
            "Instale manualmente:\n    pip install PyQt6-WebEngine",
        )
        return False


def build_steam_login_dialog(
    parent: QWidget | None = None,
) -> SteamLoginDialog | None:
    """Cria o dialog se QtWebEngine estiver disponivel.

    Se nao estiver, oferece instalacao automatica via pip.
    Retorna None se o usuario recusar ou a instalacao falhar.
    """
    if _check_webengine():
        return SteamLoginDialog(parent)

    # Tenta instalar automaticamente
    if _install_webengine(parent):
        try:
            return SteamLoginDialog(parent)
        except ImportError:
            QMessageBox.warning(
                parent, "Reinicio necessario",
                "PyQt6-WebEngine foi instalado, mas o Python precisa reiniciar\n"
                "para reconhecer a nova biblioteca.\n\n"
                "Feche e abra o SkinVault novamente.",
            )
            return None

    return None
