"""ScreenRouter — navegacao entre telas com gate de sessao (F11).

QStackedWidget com 3 telas: LoginGate, AccountScreen, HistoryScreen,
ScannerScreen. Sem sidebar propria — MainWindow gerencia um QDockWidget
com a Sidebar e conecta sinais aqui.

Emite navigated(screen) e sidebar_visibility_changed(bool).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from skinvault import steam_session
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.account_screen import AccountScreen
from skinvault.ui.components import Breadcrumb, Footer
from skinvault.ui.history_screen import HistoryScreen
from skinvault.ui.login_gate import LoginGate
from skinvault.ui.market_screen import MarketScreen
from skinvault.ui.scanner_screen import ScannerScreen
from skinvault.ui.simulador_screen import SimuladorScreen
from skinvault.ui.trades_screen import TradesScreen
from skinvault.ui.watchlist_screen import WatchlistScreen


SCREEN_ACCOUNT = "account"
SCREEN_HISTORY = "history"
SCREEN_SCANNER = "scanner"
SCREEN_MARKET = "market"
SCREEN_TRADES = "trades"
SCREEN_SIMULADOR = "simulador"
SCREEN_WATCHLIST = "watchlist"


class ScreenRouter(QWidget):
    """Widget raiz que gerencia navegacao entre telas + estado de sessao.
    Sidebar fica em QDockWidget gerenciado pelo MainWindow.
    """

    sync_requested = pyqtSignal(object)  # SteamSession
    sidebar_visibility_changed = pyqtSignal(bool)
    navigated = pyqtSignal(str)

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._session: steam_session.SteamSession | None = None
        self._build()

    @property
    def session(self) -> steam_session.SteamSession | None:
        return self._session

    @property
    def sidebar_visible(self) -> bool:
        return self._session is not None and self._session.is_complete()

    def start(self) -> None:
        """Deve ser chamado apos conectar sinais externos (sidebar)."""
        self._check_session()

    def _build(self) -> None:
        self.setStyleSheet(f"background: {t.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._breadcrumb = Breadcrumb(self)
        root.addWidget(self._breadcrumb)

        self._stack = QStackedWidget(self)

        self._login_gate = LoginGate(self)
        self._login_gate.session_connected.connect(self._on_session)
        self._stack.addWidget(self._login_gate)

        self._account_screen = AccountScreen(self._cache, self)
        self._account_screen.request_sync.connect(self._request_sync)
        self._stack.addWidget(self._account_screen)

        self._history_screen = HistoryScreen(self._cache, self)
        self._stack.addWidget(self._history_screen)

        self._scanner_screen = ScannerScreen(self._cache, self)
        self._stack.addWidget(self._scanner_screen)

        self._market_screen = MarketScreen(self._cache, self)
        self._stack.addWidget(self._market_screen)

        self._trades_screen = TradesScreen(self)
        self._stack.addWidget(self._trades_screen)

        self._simulador_screen = SimuladorScreen(self)
        self._stack.addWidget(self._simulador_screen)

        self._watchlist_screen = WatchlistScreen(self._cache, self)
        self._stack.addWidget(self._watchlist_screen)

        root.addWidget(self._stack, 1)

        self._footer = Footer(self)
        root.addWidget(self._footer)

    def _check_session(self) -> None:
        s = steam_session.load()
        if s and s.is_complete():
            if steam_session.validate(s):
                steam_session.persist(s)
                self._on_session(s)
                return
            steam_session.clear()
        self._show_login()

    def _show_login(self) -> None:
        self._stack.setCurrentWidget(self._login_gate)
        self._breadcrumb.set_path("Bem-vindo")
        self._footer.set_left("Nao conectado")
        self._footer.set_right("")
        self.sidebar_visibility_changed.emit(False)

    def _on_session(self, session: steam_session.SteamSession) -> None:
        self._session = session
        self._account_screen.set_session(session)
        sid = session.steamid
        # Tenta usar o nome do perfil em cache; cai pro steamid truncado
        from skinvault.ui.profile_fetcher import load_cached_profile
        try:
            prof = load_cached_profile(sid)
        except Exception:
            prof = None
        if prof and prof.get("name"):
            label = f"Conectado como {prof['name']}"
        else:
            label = "Conectado: {}…{}".format(sid[:8], sid[-4:])
        self._footer.set_left(label)
        self.sidebar_visibility_changed.emit(True)
        self.navigate(SCREEN_ACCOUNT)
        self._maybe_show_welcome()

    def _maybe_show_welcome(self) -> None:
        """Mostra o WelcomeDialog na primeira sessao (settings.welcome_seen)."""
        from skinvault import settings as _settings
        s = _settings.load_settings()
        if s.get("welcome_seen"):
            return
        try:
            from skinvault.ui.welcome_dialog import WelcomeDialog
            dlg = WelcomeDialog(self)
            dlg.exec()
        except Exception:
            pass
        s["welcome_seen"] = True
        _settings.save_settings(s)

    def navigate(self, screen: str) -> None:
        mapping = {
            SCREEN_ACCOUNT: (self._account_screen, "Minha Conta"),
            SCREEN_HISTORY: (self._history_screen, "Historico"),
            SCREEN_SCANNER: (self._scanner_screen, "Scanner"),
            SCREEN_MARKET: (self._market_screen, "Market"),
            SCREEN_TRADES: (self._trades_screen, "Trades"),
            SCREEN_SIMULADOR: (self._simulador_screen, "Simulador"),
            SCREEN_WATCHLIST: (self._watchlist_screen, "Watchlist"),
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
        elif screen == SCREEN_WATCHLIST:
            self._watchlist_screen.refresh()

        self.navigated.emit(screen)

    def _request_sync(self) -> None:
        if self._session is not None:
            self.sync_requested.emit(self._session)
