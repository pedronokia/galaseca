"""UI do SkinVault (PyQt6).

F11 redesign: QMainWindow + QDockWidget sidebar + 3 telas.
Dialogs reutilizaveis aqui. Importada via 'python -m skinvault --ui'.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import QUrl

try:
    from PyQt6.QtWidgets import QSystemTrayIcon
except ImportError:
    QSystemTrayIcon = None

from skinvault import backup, prices
from skinvault._paths import DATA_DIR, ensure_data_dir
from skinvault.settings import DEFAULTS, load_settings, save_settings
from skinvault.single_instance import SingleInstance
from skinvault.ui import theme as t
from skinvault.ui.components import Sidebar, Toast

THEMES = {
    "dark": {"bg": "#0F0F0F", "surface": "#212121", "surface2": "#272727", "text": "#F1F1F1", "muted": "#AAAAAA"},
    "light": {"bg": "#F5F5F5", "surface": "#FFFFFF", "surface2": "#ECECEC", "text": "#1C1C1C", "muted": "#888888"},
}


def _set_dark_titlebar(window: QWidget) -> None:
    """Escurece a titlebar no Windows 11/10 via DWM.

    Falha silenciosa em SOs antigos ou sem ctypes.
    """
    try:
        import ctypes
        hwnd = int(window.winId())
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(ctypes.c_int(1)),
                    ctypes.sizeof(ctypes.c_int)) == 0:
                break
    except Exception:
        pass


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _btn_primary(padding: str = "10px 22px", fs: str = "11pt",
                 disabled: bool = False) -> str:
    """Delega pro theme. Mantido como wrapper porque dialogos (backup,
    toast) chamavam a versao local verde-legada do pre-F11; o CTA real
    agora e' o solid do theme."""
    return t.btn_primary(padding, fs, disabled)


def _btn_danger(padding: str = "8px 18px", fs: str = "10pt") -> str:
    return t.btn_danger(padding, fs)


def _btn_secondary(padding: str = "8px 18px", fs: str = "10pt") -> str:
    return t.btn_secondary(padding, fs)


def _table_style() -> str:
    """Wrapper legado — delega pro theme (antes tinha tint verde aqui)."""
    return t.table_style()


def set_theme(theme_name: str, accent: str | None = None) -> None:
    from skinvault.ui.theme import _reload_palette
    if accent is None:
        _reload_palette(theme_name)
    else:
        _reload_palette(theme_name, accent)


def _steam_market_url(name: str) -> str:
    import urllib.parse
    return f"https://steamcommunity.com/market/listings/730/{urllib.parse.quote(name)}"


_APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"


def _app_icon() -> QIcon:
    """Icone do app (vault dial). Fallback pra circulo branco se faltar."""
    if _APP_ICON_PATH.is_file():
        return QIcon(str(_APP_ICON_PATH))
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(t.ACCENT)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 16, 16)
    p.end()
    return QIcon(pix)


def _make_tray_icon() -> QIcon:
    return _app_icon()


# ── BackupDialog ────────────────────────────────────────────────
class BackupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar Backups")
        self.resize(520, 360)
        self.setStyleSheet(
            f"QDialog {{ background: {t.BG}; }}"
            f"* {{ color: {t.TEXT}; font-family: 'Segoe UI'; }}"
        )
        self._build()

    def showEvent(self, evt) -> None:  # noqa: N802
        super().showEvent(evt)
        if not hasattr(self, '_dark_titlebar_set'):
            _set_dark_titlebar(self)
            self._dark_titlebar_set = True

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("Backups dos dados")
        title.setStyleSheet(f"color: {t.TEXT}; font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {t.BG_ELEVATED}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px; font-size: 10pt;"
            f" color: {t.TEXT}; }}"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #2A2A33; }"
        )
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(_btn_secondary())
        refresh_btn.setToolTip("Recarrega a lista de backups do disco.")
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)

        restore_btn = QPushButton("Restaurar")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setStyleSheet(_btn_primary("8px 18px", "10pt"))
        restore_btn.setToolTip(
            "Restaura o backup selecionado, sobrescrevendo todos os dados atuais."
        )
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(restore_btn)

        delete_btn = QPushButton("Deletar")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(_btn_danger())
        delete_btn.setToolTip("Apaga o backup selecionado do disco. Acao irreversivel.")
        delete_btn.clicked.connect(self._delete)
        btn_row.addWidget(delete_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Fechar")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(_btn_secondary())
        close_btn.setToolTip("Fecha o dialogo sem alterar nada.")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        for b in backup.list_backups():
            dt = time.strftime("%d/%m/%Y %H:%M", time.localtime(b["mtime"]))
            size_kb = b["size"] / 1024
            self._list.addItem(f"{b['name']}  ({size_kb:.0f} KB)  -  {dt}")

    def _selected_path(self) -> str | None:
        row = self._list.currentRow()
        if row < 0:
            return None
        backups = backup.list_backups()
        if row >= len(backups):
            return None
        return backups[row]["path"]

    def _restore(self) -> None:
        path = self._selected_path()
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Restaurar backup",
            "Restaurar este backup?\nOs dados atuais serao SUBSTITUIDOS.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        count = backup.restore_backup(path)
        if count:
            Toast.show_toast(self, f"{count} arquivo(s) restaurados com sucesso.", "success")
        else:
            Toast.show_toast(self, "Falha ao restaurar backup.", "error")

    def _delete(self) -> None:
        path = self._selected_path()
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Deletar backup",
            "Deletar este backup permanentemente?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        if backup.delete_backup(path):
            self._refresh()
        else:
            Toast.show_toast(self, "Falha ao deletar backup.", "error")


class _GamedataBridge(QObject):
    events_found = pyqtSignal(list)


# ── MainWindow (QMainWindow) ────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        settings = load_settings()
        theme = settings.get("theme", "dark")
        accent = settings.get("accent_color") or DEFAULTS["accent_color"]
        # Chamada de 1 argumento quando nao ha' accent salvo: preserva a
        # assinatura legada e o que o app ja' aplicou na sessao.
        if settings.get("accent_color"):
            set_theme(theme, accent)
        else:
            set_theme(theme)
        self._current_theme = theme
        self._current_accent = accent
        self.setWindowTitle("SkinVault")
        self.setWindowIcon(_app_icon())

        geo = settings.get("window_geometry", {})
        pos = settings.get("window_position", {})
        w = geo.get("w", 1200)
        h = geo.get("h", 800)
        x = pos.get("x")
        y = pos.get("y")
        if x is not None and y is not None:
            self.setGeometry(x, y, w, h)
        else:
            self.resize(w, h)
            self._center_on_screen()

        self._apply_stylesheet()
        # Modo overlay: nao rouba foco de jogos fullscreen (CS2, etc).
        # Combina stays-on-top + WA_ShowWithoutActivating pra que a
        # janela apareca sobre o jogo sem minimiza-lo.
        self._overlay_mode: bool = bool(settings.get("overlay_mode", False))
        if self._overlay_mode:
            self._apply_overlay_flags(True)

        ttl = settings.get("cache_ttl_hours", 6) * 3600
        self._cache = prices.PriceCache(ttl=ttl)

        self._tray_icon: QSystemTrayIcon | None = None
        self._geo_timer = QTimer(self)
        self._init_tray()

        from skinvault.ui.screen_router import ScreenRouter
        self._router = ScreenRouter(self._cache, self)
        self._router.notification_requested.connect(self._on_notification)
        self.setCentralWidget(self._router)

        self._create_sidebar_dock(settings)

        self._router.navigated.connect(self._on_navigated)
        self._router.theme_toggled.connect(self._on_theme_changed)
        self._router.sidebar_visibility_changed.connect(self._on_sidebar_visibility)
        self._router.start()

        self._setup_shortcuts()
        self._init_gamedata_watcher()

        if settings.get("auto_backup", True):
            backup.make_backup()

    def _center_on_screen(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        center = screen.availableGeometry().center()
        fg = self.frameGeometry()
        fg.moveCenter(center)
        self.move(fg.topLeft())

    def showEvent(self, evt) -> None:  # noqa: N802
        super().showEvent(evt)
        if not hasattr(self, '_dark_titlebar_set'):
            _set_dark_titlebar(self)
            self._dark_titlebar_set = True

    def _apply_stylesheet(self) -> None:
        from skinvault.ui.theme import (
            BG, BG_ELEVATED, BORDER, TEXT, TEXT_MUTED,
            FONT_FAMILY, SCROLL_THUMB, SCROLL_THUMB_HOV, menu_style,
        )
        self.setStyleSheet(
            f"QMainWindow {{ background: {BG}; }}"
            f"* {{ color: {TEXT};"
            f" font-family: '{FONT_FAMILY}', 'Segoe UI', system-ui; }}"
            # QMenu e' popup (janela propria) e nao herda o stylesheet do
            # widget que o abriu -- so' da raiz. Sem esta linha os menus
            # das telas saem com o tema claro do Qt (ver theme.menu_style).
            + menu_style() +
            # ── Scrollbar global fina ──
            f"QScrollBar:vertical {{ width: 10px;"
            f" background: transparent; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {SCROLL_THUMB};"
            f" border-radius: 5px; min-height: 32px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {SCROLL_THUMB_HOV}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            f" {{ height: 0; }}"
            f"QScrollBar:horizontal {{ height: 10px;"
            f" background: transparent; margin: 0; }}"
            f"QScrollBar::handle:horizontal {{ background: {SCROLL_THUMB};"
            f" border-radius: 5px; min-width: 32px; }}"
            f"QScrollBar::handle:horizontal:hover {{ background: {SCROLL_THUMB_HOV}; }}"
            f"QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal"
            f" {{ width: 0; }}"
        )

    def _apply_overlay_flags(self, enable: bool) -> None:
        """Liga/desliga flags que permitem coexistir com jogo fullscreen.

        WindowStaysOnTopHint: janela fica acima do jogo.
        WA_ShowWithoutActivating: aparecer nao rouba foco do jogo.
        """
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enable)
        self.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating, enable,
        )

    def set_overlay_mode(self, enable: bool) -> None:
        """Toggle do overlay em runtime. Persiste em settings."""
        was_visible = self.isVisible()
        self._overlay_mode = bool(enable)
        self._apply_overlay_flags(self._overlay_mode)
        s = load_settings()
        s["overlay_mode"] = self._overlay_mode
        save_settings(s)
        # setWindowFlag exige re-show pra ter efeito
        if was_visible:
            self.show()
        # Atualiza label do menu da tray, se existir
        if hasattr(self, "_overlay_action") and self._overlay_action is not None:
            self._overlay_action.setText(
                "Modo overlay: ATIVO" if self._overlay_mode
                else "Modo overlay (CS fullscreen)"
            )
            self._overlay_action.setChecked(self._overlay_mode)

    # ── sidebar dock ──────────────────────────────────────────
    def _create_sidebar_dock(self, settings: dict) -> None:
        self._sidebar_dock = QDockWidget("Navegacao", self)
        self._sidebar_dock.setFeatures(
            QDockWidget.DockWidgetFeature.NoDockWidgetFeatures
        )
        title_bar = QWidget()
        self._sidebar_dock.setTitleBarWidget(title_bar)

        # Rail ou barra com rotulos, lembrado entre sessoes. Um rail de
        # icones exige decorar sete glifos; com o rotulo do lado o alvo do
        # clique tambem cresce. Quem ja' decorou colapsa e recupera a
        # largura.
        self._sidebar = None
        self._sidebar_screen = "account"
        self._sidebar_rail = bool(settings.get("sidebar_collapsed", True))
        self._sidebar_dock.setWidget(self._build_sidebar(self._sidebar_rail))
        self._apply_sidebar_metrics()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                           self._sidebar_dock)

    _SIDEBAR_ITENS = (
        ("account", "user", "Minha Conta"),
        ("inventory", "wallet", "Inventário"),
        ("history", "history", "Histórico"),
        ("scanner", "radar", "Scanner"),
        ("market", "chart", "Market"),
        ("trades", "swap", "Trades"),
        ("tradeup", "calc", "Trade-up"),
        ("watchlist", "eye", "Watchlist"),
    )

    def _build_sidebar(self, rail: bool) -> Sidebar:
        """Monta a barra do zero no modo pedido.

        Reconstruir em vez de alternar propriedade widget a widget: o chip
        de sessao tem estrutura diferente nos dois modos (bolinha de 32px
        contra nome + subtitulo), e alternar no lugar deixava metade do
        estado do modo anterior.
        """
        from skinvault.ui.theme import SIZE_SIDEBAR_RAIL, SIZE_SIDEBAR_W
        largura = SIZE_SIDEBAR_RAIL if rail else SIZE_SIDEBAR_W
        sidebar = Sidebar(width=largura, rail=rail)
        sidebar.add_action("menu", "Recolher barra" if not rail
                           else "Expandir barra", self._toggle_sidebar)
        # Icones de linha (QPainter) por nome — vide components.LineIcon
        for key, icon, label in self._SIDEBAR_ITENS:
            sidebar.add_item(key, icon, label)
        sidebar.add_stretch()

        # Limpeza e' utilitario de maquina, nao etapa do fluxo de mercado:
        # fica depois do stretch, junto de Configuracoes.
        sidebar.add_item("cleanup", "trash", "Limpeza")

        # Configuracoes virou tela (Frente K): item de navegacao com
        # estado ativo, nao mais acao modal. Sobre/Backups seguem acoes.
        sidebar.add_item("settings", "gear", "Configurações")
        for icon, label, cb in [
            ("info", "Sobre", self._open_about),
            ("archive", "Backups", self._open_backups),
        ]:
            sidebar.add_action(icon, label, cb)

        sidebar.item_selected.connect(self._router.navigate)
        self._sidebar = sidebar
        return sidebar

    def _apply_sidebar_metrics(self, animate: bool = False) -> None:
        from skinvault.ui.theme import SIZE_SIDEBAR_RAIL
        largura = (SIZE_SIDEBAR_RAIL if self._sidebar_rail
                   else self._sidebar_largura_expandida())
        # A sidebar NOVA (rail ou com rotulos) ja' nasce na largura final
        # -- so' o DOCK que a envolve anima, revelando/escondendo o
        # excedente aos poucos em vez de trocar seco.
        if self._sidebar is not None:
            self._sidebar.setFixedWidth(largura)
        if animate and self.isVisible():
            self._animar_largura_sidebar(largura)
        else:
            self._sidebar_dock.setMinimumWidth(largura)
            self._sidebar_dock.setMaximumWidth(largura)

    def _animar_largura_sidebar(self, alvo: int) -> None:
        from PyQt6.QtCore import QEasingCurve, QVariantAnimation
        dock = self._sidebar_dock
        anim = QVariantAnimation(dock)
        anim.setDuration(180)
        anim.setStartValue(dock.width())
        anim.setEndValue(alvo)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _tick(v) -> None:
            dock.setMinimumWidth(v)
            dock.setMaximumWidth(v)

        anim.valueChanged.connect(_tick)
        # Referencia guardada no dock: sem isto o objeto Python e' coletado
        # antes da animacao terminar e ela para no meio.
        dock._sidebar_width_anim = anim
        anim.start()

    def _sidebar_largura_expandida(self) -> int:
        """Largura escolhida em Configuracoes, no mesmo range do settings."""
        from skinvault.ui.theme import SIZE_SIDEBAR_W
        try:
            valor = int(load_settings().get("sidebar_width", SIZE_SIDEBAR_W))
        except (TypeError, ValueError):
            valor = SIZE_SIDEBAR_W
        return max(160, min(400, valor))

    def _toggle_sidebar(self) -> None:
        """Alterna rail <-> rotulos, preservando selecao."""
        self._sidebar_rail = not self._sidebar_rail
        anterior = self._sidebar
        nova = self._build_sidebar(self._sidebar_rail)
        self._sidebar_dock.setWidget(nova)
        if anterior is not None:
            anterior.setParent(None)
            anterior.deleteLater()
        self._apply_sidebar_metrics(animate=True)
        nova.select(self._sidebar_screen)
        s = load_settings()
        s["sidebar_collapsed"] = self._sidebar_rail
        save_settings(s)

        # estado inicial
        visible = self._router.sidebar_visible
        self._sidebar_dock.setVisible(visible)

    def _on_sidebar_visibility(self, visible: bool) -> None:
        self._sidebar_dock.setVisible(visible)

    def _on_navigated(self, screen: str) -> None:
        # Guardado pra sobreviver a um rebuild da barra (toggle rail).
        self._sidebar_screen = screen
        sidebar = self._sidebar_dock.widget()
        if sidebar and hasattr(sidebar, 'select'):
            sidebar.select(screen)

    # ── shortcuts ─────────────────────────────────────────────
    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self._focus_filter)
        QShortcut(QKeySequence("?"), self).activated.connect(
            self._show_shortcuts)
        QShortcut(QKeySequence("F5"), self).activated.connect(
            self._refresh_current)
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(
            self._open_settings)
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(
            self._open_settings)
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(
            self._open_palette)

    def _focus_filter(self) -> None:
        stack = getattr(self._router, '_stack', None)
        if stack is not None:
            w = stack.currentWidget()
            for attr in ("_filter_inp", "_search_inp"):
                inp = getattr(w, attr, None)
                if inp:
                    inp.setFocus()
                    inp.selectAll()
                    break

    def _refresh_current(self) -> None:
        stack = getattr(self._router, '_stack', None)
        if stack is not None:
            w = stack.currentWidget()
            refresh = getattr(w, 'refresh', None)
            if refresh:
                refresh()

    def _show_shortcuts(self) -> None:
        QMessageBox.information(
            self, "Atalhos de teclado",
            "<b>Atalhos:</b><br>"
            "F5 &nbsp;&nbsp; Recarregar tela atual<br>"
            "Ctrl+F &nbsp;&nbsp; Foco no filtro ou busca da tela<br>"
            "Esc &nbsp;&nbsp; Limpa a busca (Inventário, Watchlist, Histórico)<br>"
            "Delete &nbsp;&nbsp; Remove a linha selecionada (Trades, Watchlist)<br>"
            "Ctrl+L &nbsp;&nbsp; Foca a busca no Market<br>"
            "Ctrl+Enter &nbsp;&nbsp; Escaneia a categoria no Scanner<br>"
            "Ctrl+N / Ctrl+, &nbsp;&nbsp; Configurações<br>"
            "Ctrl+K &nbsp;&nbsp; Abre a paleta<br>"
            "? &nbsp;&nbsp; Mostra esta janela",
        )

    # ── tray ──────────────────────────────────────────────────
    def _init_tray(self) -> None:
        if QSystemTrayIcon is None:
            return
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
        except Exception:
            return
        icon = _make_tray_icon()
        self._tray_icon = QSystemTrayIcon(icon, self)
        menu = QMenu(self)
        if hasattr(QMenu, "setStyleSheet"):
            menu.setStyleSheet(
                f"QMenu {{ background: {t.BG_ELEVATED}; color: {t.TEXT};"
                f" border: 1px solid {t.BORDER}; padding: 4px; }}"
                "QMenu::item { padding: 6px 20px; }"
                f"QMenu::item:selected {{ background: {t.SURFACE_HOV}; }}"
            )
        restore_action = menu.addAction("Abrir SkinVault")
        restore_action.triggered.connect(self._restore_from_tray)
        menu.addSeparator()
        self._overlay_action = menu.addAction(
            "Modo overlay: ATIVO" if self._overlay_mode
            else "Modo overlay (CS fullscreen)"
        )
        self._overlay_action.setCheckable(True)
        self._overlay_action.setChecked(self._overlay_mode)
        self._overlay_action.setToolTip(
            "Liga 'stays on top' + 'no focus steal'. "
            "Permite a janela aparecer sobre o jogo fullscreen "
            "sem minimiza-lo. Persiste entre execucoes."
        )
        self._overlay_action.triggered.connect(
            lambda checked: self.set_overlay_mode(checked)
        )
        menu.addSeparator()
        quit_action = menu.addAction("Sair")
        quit_action.triggered.connect(QApplication.instance().quit)
        self._tray_icon.setContextMenu(menu)
        self._tray_icon.setToolTip("SkinVault - Gerenciador de portfolio CS2")
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_notification(self, title: str, body: str, severity: str) -> None:
        """Mostra notificacao via tray icon (Windows nativo)."""
        if not self._tray_icon:
            return
        # severity: opportunity (verde) | warning (amarelo) | info (azul)
        icon_type = QSystemTrayIcon.MessageIcon.Information
        if severity == "warning":
            icon_type = QSystemTrayIcon.MessageIcon.Warning
        try:
            self._tray_icon.showMessage(title, body, icon_type, 5000)
        except Exception:
            pass

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def activate(self) -> None:
        """Traz a janela pra frente. Chamado quando outra instancia tenta abrir.

        Escondida na bandeja ou minimizada: mesmo caminho da restauracao pelo
        tray. Ja' visivel: so' sobe o z-order -- `showNormal()` aqui
        desmaximizaria a janela so' porque o usuario clicou no atalho de novo.
        """
        if self.isMinimized() or not self.isVisible():
            self._restore_from_tray()
            return
        self.setWindowState(
            self.windowState() | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

    # ── gamedata watcher (updates do CS2 via GameTracking-CS2) ─
    _GAMEDATA_INTERVAL_MS = 6 * 3600 * 1000
    _GAMEDATA_FIRST_CHECK_MS = 20_000

    def _init_gamedata_watcher(self) -> None:
        """Polling do items_game.txt: 1 checagem 20s pos-boot + a cada 6h.

        Cada ciclo custa 1 request na API do GitHub (limite anonimo 60/h);
        downloads dos arquivos so acontecem quando o commit muda.
        """
        self._gamedata_checking = False
        self._gamedata_bridge = _GamedataBridge()
        self._gamedata_bridge.events_found.connect(self._on_gamedata_events)
        self._gamedata_timer = QTimer(self)
        self._gamedata_timer.setInterval(self._GAMEDATA_INTERVAL_MS)
        self._gamedata_timer.timeout.connect(self._check_gamedata_updates)
        self._gamedata_timer.start()
        QTimer.singleShot(
            self._GAMEDATA_FIRST_CHECK_MS, self._check_gamedata_updates,
        )

    def _check_gamedata_updates(self) -> None:
        if self._gamedata_checking:
            return
        self._gamedata_checking = True
        bridge = self._gamedata_bridge

        def _worker() -> None:
            try:
                from skinvault import gamedata
                result = gamedata.check_for_updates()
                events = result.get("events") or []
                if events:
                    gamedata.record_events_as_alerts(events)
                    bridge.events_found.emit(events)
            except Exception as e:
                print(f"WARNING: gamedata check failed: {e}",
                      file=__import__('sys').stderr)
            finally:
                self._gamedata_checking = False

        threading.Thread(target=_worker, daemon=True).start()

    def _on_gamedata_events(self, events: list) -> None:
        """Notifica via tray os eventos de update do jogo (agregado)."""
        if not load_settings().get("tray_notifications", True):
            return
        lines = [ev.get("summary", "") for ev in events[:3]]
        extra = len(events) - 3
        if extra > 0:
            lines.append(f"... e mais {extra} evento(s)")
        severity = "opportunity" if any(
            ev.get("type") in ("drop_pool_removed", "xpshop_removed")
            for ev in events
        ) else "info"
        self._on_notification(
            "SkinVault: update do CS2 detectado", "\n".join(lines), severity,
        )

    # ── geometry ──────────────────────────────────────────────
    def _save_geometry(self) -> None:
        s = load_settings()
        s["window_geometry"] = {"w": self.width(), "h": self.height()}
        s["window_position"] = {"x": self.x(), "y": self.y()}
        save_settings(s)

    def _debounce_save_geometry(self) -> None:
        try:
            self._geo_timer.timeout.disconnect()
        except Exception:
            pass
        self._geo_timer.timeout.connect(self._save_geometry)
        self._geo_timer.setSingleShot(True)
        self._geo_timer.start(300)

    def moveEvent(self, evt) -> None:  # noqa: N802
        super().moveEvent(evt)
        self._debounce_save_geometry()

    def resizeEvent(self, evt) -> None:  # noqa: N802
        super().resizeEvent(evt)
        self._debounce_save_geometry()

    def closeEvent(self, evt) -> None:  # noqa: N802
        self._save_geometry()
        s = load_settings()
        if self._tray_icon is not None and s.get(
            "minimize_to_tray_on_close", True
        ):
            self.hide()
            evt.ignore()
            return
        if self._tray_icon is not None:
            self._tray_icon.hide()
        evt.accept()
        QApplication.instance().quit()

    # ── dialogs ───────────────────────────────────────────────
    def _open_backups(self) -> None:
        dlg = BackupDialog(self)
        dlg.exec()

    def _open_settings(self) -> None:
        # Frente K: Configuracoes virou tela navegavel (era modal).
        self._router.navigate("settings")

    def _apply_sidebar_width(self, width: int) -> None:
        """Aplica a largura da sidebar ao vivo (chamado pela tela de
        Configuracoes). Clampa no mesmo range do settings.

        Sem efeito com a barra recolhida: o rail tem largura propria, e
        aplicar 220px nele so' produzia um rail largo com os icones
        boiando no meio -- que era o que a preferencia fazia antes de
        existir o modo com rotulos.
        """
        width = max(160, min(400, int(width)))
        if getattr(self, "_sidebar_rail", False):
            return
        dock = getattr(self, "_sidebar_dock", None)
        if dock is not None:
            dock.setMinimumWidth(width)
            dock.setMaximumWidth(width)
        sidebar = getattr(self, "_sidebar", None)
        if sidebar is not None:
            sidebar.setFixedWidth(width)

    def _apply_table_density(self, density: str) -> None:
        """Aplica a densidade de tabela ao vivo (chamado pela tela de
        Configuracoes) em toda tela ja construida que tenha uma `_table`.

        Mesmo padrao de `_apply_sidebar_width`/`_on_theme_changed`: as
        telas sao construidas uma vez so' no ScreenRouter.__init__, entao
        mudar o settings sozinho nao afeta quem ja' esta' de pe -- precisa
        de um passo explicito que ache cada tabela e reaplique.
        """
        from skinvault.ui import theme as t
        router = getattr(self, "_router", None)
        if router is None:
            return
        for attr in ("_account_screen", "_inventory_screen",
                     "_history_screen", "_scanner_screen",
                     "_market_screen", "_trades_screen",
                     "_watchlist_screen", "_cleanup_screen"):
            screen = getattr(router, attr, None)
            table = getattr(screen, "_table", None)
            if table is not None:
                t.set_table_density(table, density)

    def _on_theme_changed(self) -> None:
        s = load_settings()
        theme = s.get("theme", "dark")
        accent = s.get("accent_color") or DEFAULTS["accent_color"]
        if theme == self._current_theme and accent == self._current_accent:
            return
        self._current_theme = theme
        self._current_accent = accent
        if s.get("accent_color"):
            set_theme(theme, accent)
        else:
            set_theme(theme)
        self._apply_stylesheet()
        # O balao do tooltip e' janela propria e so' obedece o stylesheet
        # da aplicacao; sem reaplicar aqui ele ficaria com as cores do
        # tema anterior ate' o proximo start.
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(t.app_style())
        # Re-aplica sidebar dock style
        self._sidebar_dock.setStyleSheet(
            f"QDockWidget {{ background: {t.BG_ELEVATED}; }}"
        )
        # Seletor com objectName — sem ele o background propaga pros filhos
        # da sidebar (LineIcon/chip), reintroduzindo as tarjas (vide Frente M).
        self._sidebar_dock.widget().setStyleSheet(
            f"QWidget#Sidebar {{ background: {t.BG_ELEVATED}; }}"
        )
        # Os itens da sidebar embutem ACCENT_DIM/FOCUS_GREEN no QSS e a cor
        # do dot de sessao; reaplica pra refletir a nova cor de destaque.
        sidebar = getattr(self, "_sidebar", None)
        if sidebar is not None:
            sidebar.restyle()

    def _open_about(self) -> None:
        QMessageBox.about(
            self, "Sobre o SkinVault",
            "<b>SkinVault</b> v1.0<br><br>"
            "Avaliação de inventário CS2 sem login.<br>"
            "Preços públicos da Steam Community Market.<br><br>"
            "Lucro real apos taxa de 15% da Steam.<br>"
            "Nao preve futuro — so' dados factuais.<br><br>"
            "Feito por Pedro S. | 2026",
        )

    # ── command palette (Ctrl+K) ──────────────────────────────
    def _open_palette(self) -> None:
        from skinvault.ui.palette import CommandPalette
        CommandPalette(self._palette_commands(), self).exec()

    def _palette_commands(self) -> list[dict]:
        """Registro estatico de comandos (navegacao + acoes globais)."""
        nav = [
            ("account", "user", "Minha Conta"),
            ("inventory", "wallet", "Inventário"),
            ("history", "history", "Histórico"),
            ("scanner", "radar", "Scanner"),
            ("market", "chart", "Market"),
            ("trades", "swap", "Trades"),
            ("watchlist", "eye", "Watchlist"),
        ]
        cmds: list[dict] = [
            {"label": f"Ir: {label}", "category": "Navegar", "icon": icon,
             "run": (lambda k=key: self._router.navigate(k))}
            for key, icon, label in nav
        ]
        cmds += [
            {"label": "Consultar item no Market", "category": "Acao",
             "icon": "chart",
             "run": lambda: self._palette_nav_focus("market", "_search_inp")},
            {"label": "Adicionar trade", "category": "Acao", "icon": "swap",
             "run": lambda: self._router.navigate("trades")},
            {"label": "Adicionar a watchlist", "category": "Acao",
             "icon": "eye", "run": lambda: self._router.navigate("watchlist")},
            {"label": "Gerenciar backups", "category": "Acao",
             "icon": "archive", "run": self._open_backups},
            {"label": "Configurações", "category": "Ação", "icon": "gear",
             "run": self._open_settings},
        ]
        # "Exportar CSV" so' entra quando a tela atual suporta — evita
        # acao listada que nao faz nada (ex.: Account, Simulador).
        stack = getattr(self._router, "_stack", None)
        cur = stack.currentWidget() if stack is not None else None
        if callable(getattr(cur, "_on_export_csv", None)):
            cmds.append({"label": "Exportar CSV da tela atual",
                         "category": "Acao", "icon": "archive",
                         "run": self._palette_export_csv})
        return cmds

    def _palette_nav_focus(self, screen: str, attr: str) -> None:
        """Navega pra `screen` e foca o input `attr` da tela (se existir)."""
        self._router.navigate(screen)
        stack = getattr(self._router, "_stack", None)
        if stack is not None:
            inp = getattr(stack.currentWidget(), attr, None)
            if inp is not None:
                inp.setFocus()

    def _palette_export_csv(self) -> None:
        stack = getattr(self._router, "_stack", None)
        if stack is not None:
            fn = getattr(stack.currentWidget(), "_on_export_csv", None)
            if callable(fn):
                fn()

def _setup_logging() -> None:
    """Log em arquivo (data/skinvault.log) -- sob pythonw.exe nao ha console,
    entao sem isto todo logger.warning/info do app (incluindo o ciclo de
    sessao Steam) some sem deixar rastro.

    Idempotente: chamadas repetidas no mesmo processo (testes de launch)
    nao acumulam handlers — cada duplicata repetiria toda linha no arquivo.
    """
    log_path = DATA_DIR / "skinvault.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) \
                and getattr(h, "baseFilename", "") == str(log_path):
            return
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(
        log_path, maxBytes=512_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    root.addHandler(handler)


def _instalar_traducao_qt(app: QApplication) -> bool:
    """Botoes padrao do Qt em portugues (Fechar, Sim, Nao, Cancelar...).

    Sem isto QDialogButtonBox/QMessageBox mostravam "Close", "Yes", "No" --
    ingles no meio de um app todo em portugues. O .qm vem junto com o
    PyQt6. Falhar aqui nunca impede o app de abrir: fica em ingles.
    """
    from PyQt6.QtCore import QLibraryInfo, QTranslator
    try:
        # Sem parent: quem segura a referencia e' o proprio app (atributo
        # abaixo). Com parent=app quebrava com app de teste (FakeApp).
        tradutor = QTranslator()
        pasta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if not tradutor.load("qtbase_pt_BR", pasta):
            logging.getLogger(__name__).info(
                "Traducao pt_BR do Qt nao encontrada em %s", pasta)
            return False
        app.installTranslator(tradutor)
        app._sv_tradutor_qt = tradutor  # sem isto o GC descarta a traducao
        return True
    except Exception as e:  # nunca impedir o app de abrir
        logging.getLogger(__name__).info(
            "Traducao pt_BR do Qt nao instalada: %s", e)
        return False


def launch() -> int:
    ensure_data_dir()
    _setup_logging()
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication([])
    app.setWindowIcon(_app_icon())
    _instalar_traducao_qt(app)
    # Tooltip e message box abrem em janela propria: so' o stylesheet de
    # APLICACAO os alcanca, setStyleSheet no widget dono nao.
    app.setStyleSheet(t.app_style())

    # Antes de qualquer janela: com minimize_to_tray_on_close ligado, o X
    # esconde em vez de encerrar, e reabrir pelo atalho empilha processos
    # gravando nos mesmos JSON sem lock (ver single_instance).
    guard = SingleInstance()
    if not guard.try_acquire():
        logging.getLogger(__name__).info(
            "Ja' existe uma instancia rodando; trazendo pra frente.")
        return 0
    app.aboutToQuit.connect(guard.release)

    win = MainWindow()
    guard.set_activate_callback(win.activate)
    settings = load_settings()
    if settings.get("start_minimized", False) and win._tray_icon is not None:
        win.hide()
    elif settings.get("overlay_mode", False):
        # Overlay: show() em vez de showMaximized() pra nao se sobrepor
        # totalmente ao jogo, mantendo a janela em tamanho gerenciavel.
        win.show()
    else:
        win.showMaximized()
    return app.exec()
