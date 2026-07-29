"""ScreenRouter — navegacao entre telas com gate de sessao (F11).

QStackedWidget com 3 telas: LoginGate, AccountScreen, HistoryScreen,
ScannerScreen. Sem sidebar propria — MainWindow gerencia um QDockWidget
com a Sidebar e conecta sinais aqui.

Emite navigated(screen) e sidebar_visibility_changed(bool).
"""
from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from skinvault import settings as settings_mod, steam_session
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.account_screen import AccountScreen
from skinvault.ui.inventory_screen import InventoryScreen
from skinvault.ui.components import Breadcrumb, LineIcon, fade_in
from skinvault.ui.history_screen import HistoryScreen
from skinvault.ui.login_gate import LoginGate
from skinvault.ui.market_screen import MarketScreen
from skinvault.ui.scanner_screen import ScannerScreen
from skinvault.ui.settings_screen import SettingsScreen
from skinvault.ui.trades_screen import TradesScreen
from skinvault.ui.watchlist_screen import WatchlistScreen

logger = logging.getLogger(__name__)


SCREEN_ACCOUNT = "account"
SCREEN_INVENTORY = "inventory"
SCREEN_HISTORY = "history"
SCREEN_SCANNER = "scanner"
SCREEN_MARKET = "market"
SCREEN_TRADES = "trades"
# SCREEN_SIMULADOR removido em 28/07/2026: o simulador calculava P&L de um
# trade hipotetico, mas o mesmo numero ja' sai do veredito do Market e do
# proprio inventario, com dado real em vez de digitado a mao.
SCREEN_WATCHLIST = "watchlist"
SCREEN_SETTINGS = "settings"


class ScreenRouter(QWidget):
    """Widget raiz que gerencia navegacao entre telas + estado de sessao.
    Sidebar fica em QDockWidget gerenciado pelo MainWindow.
    """

    sync_requested = pyqtSignal(object)  # SteamSession
    sidebar_visibility_changed = pyqtSignal(bool)
    navigated = pyqtSignal(str)
    notification_requested = pyqtSignal(str, str, str)  # title, body, severity
    session_changed = pyqtSignal(str, str)  # name, steamid ("","" = deslogado)
    theme_toggled = pyqtSignal()  # disparado quando usuario clica no toggle

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
        self.setObjectName("ScreenRouter")
        self.setStyleSheet(f"QWidget#ScreenRouter {{ background: {t.BG}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._breadcrumb = Breadcrumb(self)
        root.addWidget(self._breadcrumb)

        # Acoes trailing: toggle de tema + perfil
        self._theme_btn = QPushButton()
        self._theme_btn.setFixedSize(34, 34)
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # Botoes-icone de toolbar nao pegam foco de teclado — evita o anel de
        # foco espurio no toggle ao abrir (o foco inicial vai pro CTA).
        self._theme_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._theme_btn.setStyleSheet(t.btn_ghost(padding="0", fs=t.FS_MUTED))
        self._theme_btn.setToolTip("Alternar tema claro/escuro")
        self._theme_icon = LineIcon("sun", t.TEXT_MUTED, self._theme_btn)
        self._theme_icon.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._theme_btn.clicked.connect(self._on_toggle_theme)
        self._theme_icon.move(
            (self._theme_btn.width() - self._theme_icon.width()) // 2,
            (self._theme_btn.height() - self._theme_icon.height()) // 2,
        )

        self._profile_btn = QPushButton()
        self._profile_btn.setFixedSize(34, 34)
        self._profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._profile_btn.setStyleSheet(t.btn_ghost(padding="0", fs=t.FS_MUTED))
        self._profile_btn.setToolTip("Minha Conta")
        self._profile_icon = LineIcon("user", t.TEXT_MUTED, self._profile_btn)
        self._profile_icon.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._profile_btn.clicked.connect(
            lambda: self.navigate(SCREEN_ACCOUNT))
        self._profile_icon.move(
            (self._profile_btn.width() - self._profile_icon.width()) // 2,
            (self._profile_btn.height() - self._profile_icon.height()) // 2,
        )

        self._breadcrumb.set_actions([self._theme_btn, self._profile_btn])

        self._stack = QStackedWidget(self)

        self._login_gate = LoginGate(self)
        self._login_gate.session_connected.connect(self._on_session)
        self._stack.addWidget(self._login_gate)

        self._account_screen = AccountScreen(self._cache, self)
        self._account_screen.request_sync.connect(self._request_sync)
        self._stack.addWidget(self._account_screen)

        # O inventario e' tela propria, mas quem avalia continua sendo a
        # AccountScreen -- ela tem o PriceWorker. Duplicar a avaliacao
        # dobraria o custo num endpoint ja' rate-limited.
        self._inventory_screen = InventoryScreen(self)
        self._account_screen.inventory_ready.connect(
            self._inventory_screen.set_data)
        self._account_screen.inventory_progress.connect(
            self._inventory_screen.set_loading)
        self._stack.addWidget(self._inventory_screen)

        self._history_screen = HistoryScreen(self._cache, self)
        self._stack.addWidget(self._history_screen)

        self._scanner_screen = ScannerScreen(self._cache, self)
        self._stack.addWidget(self._scanner_screen)

        self._market_screen = MarketScreen(self._cache, self)
        self._stack.addWidget(self._market_screen)

        self._trades_screen = TradesScreen(self)
        self._stack.addWidget(self._trades_screen)


        self._watchlist_screen = WatchlistScreen(self._cache, self)
        self._watchlist_screen.notification_requested.connect(
            self.notification_requested,
        )
        self._stack.addWidget(self._watchlist_screen)

        self._settings_screen = SettingsScreen(self)
        self._stack.addWidget(self._settings_screen)

        root.addWidget(self._stack, 1)
        # Footer global removido na Frente S — o indicador de sessao virou
        # o chip no rodape da sidebar (session_changed -> Sidebar.set_session).

        # Faz o stack dimensionar pela tela ATUAL, nao pela maior — sem isto
        # o minimumSizeHint do stack e o max de todas as telas (~1187x1398),
        # impedindo a janela compacta do LoginGate.
        self._stack.currentChanged.connect(self._sync_stack_policies)
        self._sync_stack_policies()

    def _sync_stack_policies(self, *_a) -> None:
        """Telas nao-ativas recebem policy Ignored (minimumSize -> 0); a
        ativa volta a Preferred. Assim a janela pode encolher ao minimo da
        tela visivel (LoginGate cabe em ~460x530)."""
        cur = self._stack.currentIndex()
        for i in range(self._stack.count()):
            w = self._stack.widget(i)
            pol = w.sizePolicy()
            p = (QSizePolicy.Policy.Preferred if i == cur
                 else QSizePolicy.Policy.Ignored)
            pol.setHorizontalPolicy(p)
            pol.setVerticalPolicy(p)
            w.setSizePolicy(pol)

    def _check_session(self) -> None:
        s = steam_session.load()
        if s is None:
            logger.info("Nenhuma sessao salva em disco (data/steam_session.json ausente)")
        elif not s.is_complete():
            logger.warning("Sessao salva incompleta (falta steamid ou steamLoginSecure)")
        else:
            has_refresh = bool(s.cookies.get("steamRefresh_steam"))
            logger.info("Sessao carregada (steamid=%s, tem refresh token=%s)",
                        s.steamid, has_refresh)
            # ensure_valid_ex renova via steamRefresh_steam se o token de
            # acesso expirou — evita relogin manual a cada ~24h. persist
            # salva os cookies renovados in-place.
            status = steam_session.ensure_valid_ex(s)
            if status == "valid":
                logger.info("Sessao valida (ou renovada com sucesso), pulando login")
                steam_session.persist(s)
                self._on_session(s)
                return
            if status == "network_error":
                # Rede fora no boot: impossivel saber se a sessao expirou.
                # Apagar aqui forcaria relogin manual por causa de um blip.
                logger.warning(
                    "Sem resposta da Steam (rede fora?) -- mantendo "
                    "data/steam_session.json para o proximo start"
                )
            elif not has_refresh:
                logger.warning(
                    "Sessao invalida e sem refresh token -- apagando "
                    "data/steam_session.json, sera necessario relogin"
                )
                steam_session.clear()
            else:
                logger.warning(
                    "Sessao invalida mas refresh token presente -- "
                    "mantendo arquivo para nova tentativa no proximo start"
                )
        self._show_login()

    def _show_login(self) -> None:
        changed = self._login_gate is not self._stack.currentWidget()
        self._stack.setCurrentWidget(self._login_gate)
        if changed and self._stack.isVisible():
            fade_in(self._login_gate)
        self._set_surface(login=True)
        self._breadcrumb.set_path("Bem-vindo")
        self.session_changed.emit("", "")
        self.sidebar_visibility_changed.emit(False)

    def _set_surface(self, login: bool) -> None:
        """No login, a janela INTEIRA e' um tom so' (BG_ELEVATED).

        Qualquer diferenca de tom no login vira moldura escura em volta do
        conteudo -- foi o que aconteceu quando o router ficou em BG e o
        conteudo em BG_ELEVATED. No app o contraste e' desejado (telas e
        cards sobre BG), no login nao ha' nada pra destacar.

        O breadcrumb tambem some no login: "Bem-vindo" e' texto de
        enchimento, nao caminho de navegacao.
        """
        bg = t.BG_ELEVATED if login else t.BG
        self.setStyleSheet(f"QWidget#ScreenRouter {{ background: {bg}; }}")
        self._breadcrumb.set_surface(bg)
        self._breadcrumb.setVisible(not login)
        # Perfil leva a "Minha Conta" (exige sessao) — sem login e' peso
        # morto; some no gate, fica so o toggle de tema.
        self._profile_btn.setVisible(not login)

    def _on_session(self, session: steam_session.SteamSession) -> None:
        self._session = session
        self._set_surface(login=False)
        self._account_screen.set_session(session)
        sid = session.steamid
        # Tenta usar o nome do perfil em cache; cai pro steamid truncado
        from skinvault.ui.profile_fetcher import load_cached_profile
        try:
            prof = load_cached_profile(sid)
        except Exception:
            prof = None
        name = prof.get("name") if prof else ""
        self.session_changed.emit(name or "", sid)
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

    def _on_toggle_theme(self) -> None:
        s = settings_mod.load_settings()
        current = s.get("theme", "dark")
        new = "light" if current == "dark" else "dark"
        s["theme"] = new
        settings_mod.save_settings(s)
        # Atualiza icone
        self._theme_icon.set_icon_name(
            "moon" if new == "dark" else "sun")
        self.theme_toggled.emit()

    def navigate(self, screen: str) -> None:
        mapping = {
            SCREEN_ACCOUNT: (self._account_screen, "Minha Conta"),
            SCREEN_INVENTORY: (self._inventory_screen, "Inventário"),
            SCREEN_HISTORY: (self._history_screen, "Historico"),
            SCREEN_SCANNER: (self._scanner_screen, "Scanner"),
            SCREEN_MARKET: (self._market_screen, "Market"),
            SCREEN_TRADES: (self._trades_screen, "Trades"),
            SCREEN_WATCHLIST: (self._watchlist_screen, "Watchlist"),
            SCREEN_SETTINGS: (self._settings_screen, "Configurações"),
        }
        widget, label = mapping.get(screen, (None, ""))
        if widget is None:
            return
        changed = widget is not self._stack.currentWidget()
        self._stack.setCurrentWidget(widget)
        # Fade so em troca real de tela e com a janela visivel — grab()
        # do _screenshot.py e tests navegam sem show() e nao devem animar
        if changed and self._stack.isVisible():
            fade_in(widget)
        self._breadcrumb.set_path("SkinVault", label)

        if screen == SCREEN_HISTORY:
            self._history_screen.refresh()
        elif screen == SCREEN_ACCOUNT:
            self._account_screen.refresh()
        elif screen == SCREEN_WATCHLIST:
            self._watchlist_screen.refresh()
        elif screen == SCREEN_SETTINGS:
            self._settings_screen.refresh()

        self.navigated.emit(screen)

    def _request_sync(self) -> None:
        if self._session is not None:
            self.sync_requested.emit(self._session)
