"""ScreenRouter — navegacao entre telas com gate de sessao (F11).

QStackedWidget com 3 telas: LoginGate, AccountScreen, HistoryScreen,
e placeholder pra ScannerScreen (premium lock). Gerencia estado de sessao
e notifica a sidebar/breadcrumb.

Estrutura do layout:
  +--------------+---------------------------------+
  |              |  Breadcrumb                     |
  |   Sidebar    +---------------------------------+
  |              |                                 |
  |              |   QStackedWidget (telas)        |
  |              |                                 |
  |              +---------------------------------+
  |              |  Footer                         |
  +--------------+---------------------------------+
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from skinvault import steam_session
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.account_screen import AccountScreen
from skinvault.ui.components import Breadcrumb, Footer, Sidebar
from skinvault.ui.history_screen import HistoryScreen
from skinvault.ui.login_gate import LoginGate
from skinvault.ui.scanner_screen import ScannerScreen


SCREEN_LOGIN = "login"
SCREEN_ACCOUNT = "account"
SCREEN_HISTORY = "history"
SCREEN_SCANNER = "scanner"

_SIDEBAR_ITEMS: list[tuple[str, str, str]] = [
    (SCREEN_ACCOUNT, chr(9676), "Minha Conta"),
    (SCREEN_HISTORY, chr(9672), "Historico"),
    (SCREEN_SCANNER, chr(9711), "Scanner"),
]


def _btn_ghost_sidebar() -> str:
    return (
        f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
        f" border: none; text-align: left; padding: 8px 14px;"
        f" font-size: {t.FS_MUTED}; font-family: {t.FONT_FAMILY}; }}"
        f"QPushButton:hover {{ color: {t.TEXT}; background: {t.SURFACE};"
        f" border-radius: 6px; }}"
    )


class ScreenRouter(QWidget):
    """Widget raiz que gerencia navegacao entre telas + estado de sessao."""

    sync_requested = pyqtSignal(object)  # SteamSession

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._session: steam_session.SteamSession | None = None
        self._on_settings: Callable | None = None
        self._on_about: Callable | None = None
        self._on_backup: Callable | None = None
        self._build()
        self._check_session()

    def set_utility_callbacks(self, settings: Callable | None = None,
                              about: Callable | None = None,
                              backup: Callable | None = None) -> None:
        self._on_settings = settings
        self._on_about = about
        self._on_backup = backup

    @property
    def session(self) -> steam_session.SteamSession | None:
        return self._session

    def _build(self) -> None:
        self.setStyleSheet(f"background: {t.BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar(width=220, parent=self)
        for key, icon, label in _SIDEBAR_ITEMS:
            self._sidebar.add_item(key, icon, label)
        self._sidebar.add_stretch()

        # Botoes utilitarios no final da sidebar
        for label, cb_attr in [
            ("  " + chr(9881) + "  Configuracoes", "_on_settings"),
            ("  Sobre", "_on_about"),
            ("  Backups", "_on_backup"),
        ]:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_btn_ghost_sidebar())
            callback = getattr(self, cb_attr, None)
            if callback:
                btn.clicked.connect(callback)
            self._sidebar.add_widget(btn)

        self._sidebar.item_selected.connect(self._navigate)
        body.addWidget(self._sidebar)

        # Coluna direita: breadcrumb + stack + footer
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self._breadcrumb = Breadcrumb(self)
        right.addWidget(self._breadcrumb)

        self._stack = QStackedWidget(self)

        self._login_gate = LoginGate(self)
        self._login_gate.session_connected.connect(self._on_session)
        self._stack.addWidget(self._login_gate)

        self._account_screen = AccountScreen(self._cache, self)
        self._account_screen.request_sync.connect(self._request_sync)
        self._stack.addWidget(self._account_screen)

        self._history_screen = HistoryScreen(self)
        self._stack.addWidget(self._history_screen)

        self._scanner_screen = ScannerScreen(self)
        self._stack.addWidget(self._scanner_screen)

        right.addWidget(self._stack, 1)

        self._footer = Footer(self)
        right.addWidget(self._footer)

        body.addLayout(right, 1)
        root.addLayout(body, 1)

    def _check_session(self) -> None:
        s = steam_session.load()
        if s and s.is_complete():
            self._on_session(s)
        else:
            self._show_login()

    def _show_login(self) -> None:
        self._stack.setCurrentWidget(self._login_gate)
        self._breadcrumb.set_path("Bem-vindo")
        self._sidebar.setVisible(False)
        self._footer.set_left("Nao conectado")
        self._footer.set_right("")

    def _on_session(self, session: steam_session.SteamSession) -> None:
        self._session = session
        self._account_screen.set_session(session)
        self._sidebar.setVisible(True)
        self._sidebar.select(SCREEN_ACCOUNT)
        self._navigate(SCREEN_ACCOUNT)
        sid = session.steamid
        self._footer.set_left(
            "Conectado: {}...{}".format(sid[:8], sid[-4:])
        )

    def _navigate(self, screen: str) -> None:
        mapping = {
            SCREEN_ACCOUNT: (self._account_screen, "Minha Conta"),
            SCREEN_HISTORY: (self._history_screen, "Historico"),
            SCREEN_SCANNER: (self._scanner_screen, "Scanner"),
        }
        widget, label = mapping.get(screen, (None, ""))
        if widget is None:
            return
        self._stack.setCurrentWidget(widget)
        self._breadcrumb.set_path("SkinVault", label)

        if screen == SCREEN_HISTORY:
            self._history_screen.refresh()
        elif screen == SCREEN_ACCOUNT:
            self._account_screen.refresh()

    def _request_sync(self) -> None:
        """Dispara sync dialog via sinal."""
        if self._session is not None:
            self.sync_requested.emit(self._session)
