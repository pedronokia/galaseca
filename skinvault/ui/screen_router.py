"""ScreenRouter — navegacao entre telas (F11).

QStackedWidget com as telas do app. Sem sidebar propria — MainWindow
gerencia um QDockWidget com a Sidebar e conecta sinais aqui.

2026-08-07: o login/sync de conta (F10, gate por sessao) foi REVERTIDO
por decisao do usuario -- ver ROADMAP.md. O router sempre abre direto na
Conta, sidebar sempre visivel; nao ha mais LoginGate nem estado de sessao.

Emite navigated(screen) e sidebar_visibility_changed(bool).
"""
from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from skinvault import settings as settings_mod
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.account_screen import AccountScreen
from skinvault.ui.cleanup_screen import CleanupScreen
from skinvault.ui.inventory_screen import InventoryScreen
from skinvault.ui.components import Breadcrumb, LineIcon, fade_in
from skinvault.ui.history_screen import HistoryScreen
from skinvault.ui.market_screen import MarketScreen
from skinvault.ui.recommendations_screen import RecommendationsScreen
from skinvault.ui.scanner_screen import ScannerScreen
from skinvault.ui.settings_screen import SettingsScreen
from skinvault.ui.trades_screen import TradesScreen
from skinvault.ui.tradeup_screen import TradeUpScreen
from skinvault.ui.watchlist_screen import WatchlistScreen

logger = logging.getLogger(__name__)


SCREEN_ACCOUNT = "account"
SCREEN_INVENTORY = "inventory"
SCREEN_HISTORY = "history"
SCREEN_SCANNER = "scanner"
SCREEN_MARKET = "market"
SCREEN_TRADES = "trades"
SCREEN_TRADEUP = "tradeup"
# SCREEN_SIMULADOR removido em 28/07/2026: o simulador calculava P&L de um
# trade hipotetico, mas o mesmo numero ja' sai do veredito do Market e do
# proprio inventario, com dado real em vez de digitado a mao.
SCREEN_WATCHLIST = "watchlist"
SCREEN_RECOMMENDATIONS = "recommendations"
SCREEN_CLEANUP = "cleanup"
SCREEN_SETTINGS = "settings"


class ScreenRouter(QWidget):
    """Widget raiz que gerencia navegacao entre telas + estado de sessao.
    Sidebar fica em QDockWidget gerenciado pelo MainWindow.
    """

    sidebar_visibility_changed = pyqtSignal(bool)
    navigated = pyqtSignal(str)
    notification_requested = pyqtSignal(str, str, str)  # title, body, severity
    theme_toggled = pyqtSignal()  # disparado quando usuario clica no toggle

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._build()

    @property
    def sidebar_visible(self) -> bool:
        # Sem login pra' gatear: a sidebar e' sempre visivel.
        return True

    def start(self) -> None:
        """Deve ser chamado apos conectar sinais externos (sidebar).

        Sem sessao pra' checar: abre direto na Conta.
        """
        self.sidebar_visibility_changed.emit(True)
        self.navigate(SCREEN_ACCOUNT)
        self._maybe_show_welcome()

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

        self._account_screen = AccountScreen(self._cache, self)
        self._stack.addWidget(self._account_screen)

        # O inventario e' tela propria, mas quem avalia continua sendo a
        # AccountScreen -- ela tem o PriceWorker. Duplicar a avaliacao
        # dobraria o custo num endpoint ja' rate-limited.
        self._inventory_screen = InventoryScreen(self)
        self._account_screen.inventory_ready.connect(
            self._inventory_screen.set_data)
        self._account_screen.ver_sem_custo.connect(self._abrir_sem_custo)
        self._account_screen.inventory_progress.connect(
            self._inventory_screen.set_loading)
        # Custo editado na tabela pede reavaliacao: a posicao mudou e o P&L
        # calculado na ultima passada ficou velho.
        self._inventory_screen.request_reeval.connect(
            self._account_screen.refresh)
        self._stack.addWidget(self._inventory_screen)

        self._history_screen = HistoryScreen(self._cache, self)
        # Custo retroativo gravado no Histórico muda o P&L da carteira:
        # reavalia reativamente (mesmo caminho do custo editado na tabela).
        self._history_screen.costs_updated.connect(
            self._on_costs_updated)
        self._stack.addWidget(self._history_screen)

        self._scanner_screen = ScannerScreen(self._cache, self)
        self._stack.addWidget(self._scanner_screen)

        self._market_screen = MarketScreen(self._cache, self)
        self._stack.addWidget(self._market_screen)

        self._trades_screen = TradesScreen(self)
        self._stack.addWidget(self._trades_screen)

        self._tradeup_screen = TradeUpScreen(self)
        self._stack.addWidget(self._tradeup_screen)


        self._watchlist_screen = WatchlistScreen(self._cache, self)
        self._watchlist_screen.notification_requested.connect(
            self.notification_requested,
        )
        self._stack.addWidget(self._watchlist_screen)

        self._recommendations_screen = RecommendationsScreen(self)
        self._recommendations_screen.navigate_to.connect(self.navigate)
        self._recommendations_screen.abrir_mercado.connect(
            self._abrir_mercado_item)
        self._recommendations_screen.abrir_inventario.connect(
            self._abrir_inventario_item)
        self._stack.addWidget(self._recommendations_screen)

        self._cleanup_screen = CleanupScreen(self)
        self._stack.addWidget(self._cleanup_screen)

        self._settings_screen = SettingsScreen(self)
        self._stack.addWidget(self._settings_screen)

        root.addWidget(self._stack, 1)

        # Faz o stack dimensionar pela tela ATUAL, nao pela maior — sem isto
        # o minimumSizeHint do stack e o max de todas as telas (~1187x1398).
        self._stack.currentChanged.connect(self._sync_stack_policies)
        self._sync_stack_policies()

    def _sync_stack_policies(self, *_a) -> None:
        """Telas nao-ativas recebem policy Ignored (minimumSize -> 0); a
        ativa volta a Preferred. Assim a janela pode encolher ao minimo da
        tela visivel."""
        cur = self._stack.currentIndex()
        for i in range(self._stack.count()):
            w = self._stack.widget(i)
            pol = w.sizePolicy()
            p = (QSizePolicy.Policy.Preferred if i == cur
                 else QSizePolicy.Policy.Ignored)
            pol.setHorizontalPolicy(p)
            pol.setVerticalPolicy(p)
            w.setSizePolicy(pol)

    def _abrir_sem_custo(self) -> None:
        self.navigate(SCREEN_INVENTORY)
        self._inventory_screen.mostrar_sem_custo()

    def _abrir_mercado_item(self, name: str) -> None:
        self.navigate(SCREEN_MARKET)
        self._market_screen._search_and_run(name)

    def _abrir_inventario_item(self, name: str) -> None:
        self.navigate(SCREEN_INVENTORY)
        if name:
            self._inventory_screen._filter.setText(name)

    def _maybe_show_welcome(self) -> None:
        """Mostra o WelcomeDialog uma vez, no primeiro boot do app.

        Antes disparava no primeiro LOGIN; sem login, dispara no primeiro
        `start()` mesmo (settings.welcome_seen continua sendo o gate).
        """
        from skinvault import settings as _settings
        s = _settings.load_settings()
        if s.get("welcome_seen"):
            return
        quer_importar = False
        try:
            from skinvault.ui.welcome_dialog import WelcomeDialog
            dlg = WelcomeDialog(self)
            dlg.exec()
            quer_importar = bool(getattr(dlg, "quer_importar", False))
        except Exception:
            pass
        s["welcome_seen"] = True
        _settings.save_settings(s)
        if quer_importar:
            # Depois do exec: a janela principal ja' esta' de pe' e o
            # dialogo de importacao abre por cima do Inventario.
            self.navigate(SCREEN_INVENTORY)
            QTimer.singleShot(0, self._inventory_screen._on_importar_steam)

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
            SCREEN_HISTORY: (self._history_screen, "Histórico"),
            SCREEN_SCANNER: (self._scanner_screen, "Scanner"),
            SCREEN_MARKET: (self._market_screen, "Market"),
            SCREEN_TRADES: (self._trades_screen, "Trades"),
            SCREEN_TRADEUP: (self._tradeup_screen, "Trade-up"),
            SCREEN_WATCHLIST: (self._watchlist_screen, "Watchlist"),
            SCREEN_RECOMMENDATIONS: (self._recommendations_screen,
                                     "Recomendações"),
            SCREEN_CLEANUP: (self._cleanup_screen, "Limpeza"),
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
        elif screen == SCREEN_RECOMMENDATIONS:
            self._recommendations_screen.refresh()
        elif screen == SCREEN_CLEANUP:
            self._cleanup_screen.refresh()
        elif screen == SCREEN_SETTINGS:
            self._settings_screen.refresh()
        elif screen == SCREEN_TRADEUP:
            self._tradeup_screen.refresh()

        self.navigated.emit(screen)

    def _on_costs_updated(self, _count: int) -> None:
        """Custo retroativo gravado -> reavalia a carteira (KPIs reativas)."""
        self._account_screen.refresh()
