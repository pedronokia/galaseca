"""UI do SkinVault (PyQt6).

F11 redesign: QMainWindow + QDockWidget sidebar + 3 telas.
Dialogs reutilizaveis aqui. Importada via 'python -m skinvault --ui'.
"""
from __future__ import annotations

import threading
import time

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
    QCheckBox,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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

from skinvault import backup, portfolio, prices, steam_api, steam_session, sync as steam_sync, trades
from skinvault._paths import DATA_DIR
from skinvault.settings import DEFAULTS, load_settings, save_settings
from skinvault.ui.components import FormRow, Sidebar, Toast

_BG = "#0E0E12"
_SURFACE = "#16161C"
_TEXT = "#E6E6EA"
_MUTED = "#9D9DA8"
_GREEN = "#22C55E"
_RED = "#EF4444"

THEMES = {
    "dark": {"bg": "#0E0E12", "surface": "#16161C", "text": "#E6E6EA", "muted": "#9D9DA8"},
    "light": {"bg": "#F5F5F5", "surface": "#FFFFFF", "text": "#1C1C1C", "muted": "#888888"},
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


def _input_style() -> str:
    return (
        f"QLineEdit {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
        " border-radius: 8px; padding: 10px 12px; font-size: 11pt;"
        f" color: {_TEXT}; }}"
        f"QLineEdit:focus {{ border: 1px solid {_GREEN}; }}"
    )


def _btn_primary(padding: str = "10px 22px", fs: str = "11pt",
                 disabled: bool = False) -> str:
    s = (
        "QPushButton { color: #DCFFE6; background: rgba(34,197,94,0.16);"
        f" border: 1px solid {_GREEN}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600; }}"
        "QPushButton:hover { background: rgba(34,197,94,0.26); }"
    )
    if disabled:
        s += (
            "QPushButton:disabled { color: #777; border-color: #333;"
            " background: #1a1a20; }"
        )
    return s


def _btn_danger(padding: str = "8px 18px", fs: str = "10pt") -> str:
    return (
        "QPushButton { color: #FFE6E6; background: rgba(239,68,68,0.16);"
        f" border: 1px solid {_RED}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600; }}"
        "QPushButton:hover { background: rgba(239,68,68,0.26); }"
    )


def _btn_secondary(padding: str = "8px 18px", fs: str = "10pt") -> str:
    return (
        "QPushButton { color: #E6E6EA; background: rgba(255,255,255,0.06);"
        " border: 1px solid #3A3A44; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600; }}"
        "QPushButton:hover { background: rgba(255,255,255,0.12); }"
    )


def _table_style() -> str:
    return (
        f"QTableWidget {{ background: {_SURFACE};"
        f" alternate-background-color: {_SURFACE};"
        " gridline-color: transparent; border: 1px solid #2A2A33;"
        f" border-radius: 10px; color: {_TEXT}; font-size: 10pt; }}"
        f"QHeaderView::section {{ background: {_SURFACE};"
        f" color: {_MUTED}; border: none; padding: 8px 10px;"
        " font-weight: 600; font-size: 9pt; }}"
        f"QTableWidget::item:selected {{ background: rgba(34,197,94,0.16);"
        f" color: {_TEXT}; }}"
    )


def set_theme(theme: str) -> None:
    global _BG, _SURFACE, _TEXT, _MUTED, _GREEN, _RED
    t = THEMES.get(theme, THEMES["dark"])
    _BG = t["bg"]
    _SURFACE = t["surface"]
    _TEXT = t["text"]
    _MUTED = t["muted"]
    from skinvault.ui.theme import _reload_palette
    _reload_palette(theme)


def _steam_market_url(name: str) -> str:
    import urllib.parse
    return f"https://steamcommunity.com/market/listings/730/{urllib.parse.quote(name)}"


def _make_tray_icon() -> QIcon:
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor(_GREEN)))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 16, 16)
    p.end()
    return QIcon(pix)


# ── SettingsDialog ──────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._settings = load_settings()
        self.setWindowTitle("Configuracoes")
        self.resize(420, 300)
        self.setStyleSheet(
            f"QDialog {{ background: {_BG}; }}"
            f"* {{ color: {_TEXT}; font-family: 'Segoe UI'; }}"
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

        title = QLabel("Configuracoes")
        title.setStyleSheet(f"color: {_TEXT}; font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        self._cache_ttl = QLineEdit(str(self._settings.get("cache_ttl_hours", 6)))
        self._cache_ttl.setPlaceholderText("Horas")
        self._cache_ttl.setStyleSheet(_input_style())
        layout.addWidget(FormRow("Cache TTL (h):", self._cache_ttl))

        self._fee_rate = QLineEdit(str(self._settings.get("fee_rate", 0.15)))
        self._fee_rate.setPlaceholderText("Ex.: 0.15")
        self._fee_rate.setStyleSheet(_input_style())
        layout.addWidget(FormRow("Taxa Steam:", self._fee_rate))

        self._auto_backup = QCheckBox("Ativar backup automatico")
        self._auto_backup.setChecked(self._settings.get("auto_backup", True))
        self._auto_backup.setStyleSheet(
            f"QCheckBox {{ color: {_TEXT}; font-size: 10pt; font-family: 'Segoe UI'; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._auto_backup)

        self._keep_backups = QLineEdit(str(self._settings.get("keep_backups", 10)))
        self._keep_backups.setPlaceholderText("Numero de backups")
        self._keep_backups.setStyleSheet(_input_style())
        layout.addWidget(FormRow("Manter backups:", self._keep_backups))

        self._sidebar_width = QLineEdit(str(self._settings.get("sidebar_width", 220)))
        self._sidebar_width.setPlaceholderText("Largura em px")
        self._sidebar_width.setStyleSheet(_input_style())
        layout.addWidget(FormRow("Largura sidebar:", self._sidebar_width))

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["Escuro", "Claro"])
        current = self._settings.get("theme", "dark")
        self._theme_combo.setCurrentIndex(0 if current == "dark" else 1)
        self._theme_combo.setStyleSheet(
            f"QComboBox {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px 10px; font-size: 10pt;"
            f" color: {_TEXT}; }}"
            "QComboBox::drop-down { border: none; width: 24px; }"
            f"QComboBox QAbstractItemView {{ background: {_SURFACE};"
            f" color: {_TEXT}; selection-background-color: #2A2A33; }}"
        )
        layout.addWidget(FormRow("Tema:", self._theme_combo))

        self._start_min = QCheckBox("Iniciar minimizado (na bandeja)")
        self._start_min.setChecked(self._settings.get("start_minimized", False))
        self._start_min.setStyleSheet(
            f"QCheckBox {{ color: {_TEXT}; font-size: 10pt; font-family: 'Segoe UI'; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        layout.addWidget(self._start_min)

        self._min_to_tray = QCheckBox(
            "Minimizar para bandeja ao fechar (X nao encerra o app)"
        )
        self._min_to_tray.setChecked(
            self._settings.get("minimize_to_tray_on_close", True)
        )
        self._min_to_tray.setStyleSheet(self._start_min.styleSheet())
        layout.addWidget(self._min_to_tray)

        layout.addStretch()

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Salvar")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(_btn_primary())
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("Cancelar")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(_btn_secondary())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _save(self) -> None:
        try:
            ttl = int(self._cache_ttl.text().strip())
        except ValueError:
            ttl = 6
        try:
            fee = float(self._fee_rate.text().strip().replace(",", "."))
        except ValueError:
            fee = 0.15
        try:
            keep = int(self._keep_backups.text().strip())
        except ValueError:
            keep = 10
        try:
            sw = int(self._sidebar_width.text().strip())
        except ValueError:
            sw = 220
        theme = "dark" if self._theme_combo.currentIndex() == 0 else "light"
        existing = load_settings()
        existing.update({
            "cache_ttl_hours": max(1, ttl),
            "fee_rate": max(0, min(1, fee)),
            "auto_backup": self._auto_backup.isChecked(),
            "keep_backups": max(0, keep),
            "sidebar_width": max(160, min(400, sw)),
            "theme": theme,
            "start_minimized": self._start_min.isChecked(),
            "minimize_to_tray_on_close": self._min_to_tray.isChecked(),
        })
        save_settings(existing)
        # Live theme reload via parent
        parent = self.parent()
        if parent and hasattr(parent, '_on_theme_changed'):
            parent._on_theme_changed()
        self.accept()


# ── BackupDialog ────────────────────────────────────────────────
class BackupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar Backups")
        self.resize(520, 360)
        self.setStyleSheet(
            f"QDialog {{ background: {_BG}; }}"
            f"* {{ color: {_TEXT}; font-family: 'Segoe UI'; }}"
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
        title.setStyleSheet(f"color: {_TEXT}; font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 8px; font-size: 10pt;"
            f" color: {_TEXT}; }}"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #2A2A33; }"
        )
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(_btn_secondary())
        refresh_btn.clicked.connect(self._refresh)
        btn_row.addWidget(refresh_btn)

        restore_btn = QPushButton("Restaurar")
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setStyleSheet(_btn_primary("8px 18px", "10pt"))
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(restore_btn)

        delete_btn = QPushButton("Deletar")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(_btn_danger())
        delete_btn.clicked.connect(self._delete)
        btn_row.addWidget(delete_btn)

        btn_row.addStretch()
        close_btn = QPushButton("Fechar")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(_btn_secondary())
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


# ── Steam Sync (F10) ────────────────────────────────────────────
class _SyncBridge(QObject):
    step_done = pyqtSignal(str, dict)
    all_done = pyqtSignal(dict)
    failed = pyqtSignal(str)


class SteamSyncDialog(QDialog):
    _STEPS = (
        ("inventory", "Inventario CS2"),
        ("market", "Historico do Steam Market"),
        ("listings", "Listagens ativas"),
        ("trades", "Trade offers"),
    )

    def __init__(self, session: steam_session.SteamSession,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session = session
        self._bridge = _SyncBridge()
        self._bridge.step_done.connect(self._on_step)
        self._bridge.all_done.connect(self._on_done)
        self._bridge.failed.connect(self._on_failed)
        self._labels: dict[str, QLabel] = {}
        self.setWindowTitle("Sincronizando com Steam")
        self.resize(520, 320)
        self._build()
        self._start()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("Sincronizando dados da conta Steam")
        title.setStyleSheet(f"color: {_TEXT}; font-size: 13pt; font-weight: 600;")
        root.addWidget(title)

        warn = QLabel(
            "Mantenha esta janela aberta. O Steam limita requisicoes; "
            "pode levar ate 1 minuto."
        )
        warn.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        warn.setWordWrap(True)
        root.addWidget(warn)

        for key, label in self._STEPS:
            row = QHBoxLayout()
            tag = QLabel(f"o  {label}")
            tag.setStyleSheet(f"color: {_TEXT}; font-size: 10pt;")
            row.addWidget(tag, 1)
            status = QLabel("aguardando…")
            status.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
            row.addWidget(status)
            self._labels[key] = tag
            self._labels[key + "_status"] = status
            root.addLayout(row)

        self._progress = QProgressBar()
        self._progress.setRange(0, len(self._STEPS))
        self._progress.setValue(0)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {_SURFACE};"
            f" border: 1px solid #3A3A44; border-radius: 6px;"
            f" color: {_TEXT}; text-align: center; }}"
            f"QProgressBar::chunk {{ background: {_GREEN};"
            " border-radius: 5px; }}"
        )
        root.addWidget(self._progress)

        self._close_btn = QPushButton("Fechar")
        self._close_btn.setEnabled(False)
        self._close_btn.setStyleSheet(_btn_secondary())
        self._close_btn.clicked.connect(self.accept)
        root.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _start(self) -> None:
        def worker() -> None:
            try:
                results = steam_sync.sync_all(
                    self._session,
                    progress_cb=lambda step, r: self._bridge.step_done.emit(step, r),
                )
                self._bridge.all_done.emit(results)
            except Exception as exc:
                self._bridge.failed.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_step(self, step: str, result: dict) -> None:
        label = self._labels.get(step)
        status = self._labels.get(step + "_status")
        if label is not None:
            label.setText("● " + label.text()[3:])
            label.setStyleSheet(f"color: {_GREEN}; font-size: 10pt; font-weight: 600;")
        if status is not None:
            status.setText(_format_sync_result(step, result))
        self._progress.setValue(self._progress.value() + 1)

    def _on_done(self, results: dict) -> None:
        self._close_btn.setEnabled(True)
        self._close_btn.setText("Concluido — fechar")

    def _on_failed(self, msg: str) -> None:
        self._close_btn.setEnabled(True)
        self._close_btn.setText("Fechar")
        QMessageBox.warning(self, "Falha no sync",
                            f"Erro durante a sincronizacao:\n{msg}")


def _format_sync_result(step: str, result: dict) -> str:
    if "error" in result:
        return "erro: " + str(result["error"])[:40]
    if step == "inventory":
        added = result.get("added", 0)
        total = added + result.get("skipped", 0)
        return f"{added} novos / {total} no inventario"
    if step == "market":
        return f"{result.get('new', 0)} novos / {result.get('total', 0)} total"
    if step == "listings":
        return f"{result.get('count', 0)} ativas"
    if step == "trades":
        return f"{result.get('new', 0)} novos / {result.get('total', 0)} total"
    return "ok"


# ── MainWindow (QMainWindow) ────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        settings = load_settings()
        theme = settings.get("theme", "dark")
        set_theme(theme)
        self._current_theme = theme
        self.setWindowTitle("SkinVault")

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
        self._router.sync_requested.connect(self._on_sync_requested)
        self._router.notification_requested.connect(self._on_notification)
        self.setCentralWidget(self._router)

        self._create_sidebar_dock(settings)

        self._router.navigated.connect(self._on_navigated)
        self._router.sidebar_visibility_changed.connect(self._on_sidebar_visibility)
        self._router.session_changed.connect(self._sidebar.set_session)
        self._router.start()

        self._setup_shortcuts()

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
            FONT_FAMILY, SCROLL_THUMB, SCROLL_THUMB_HOV,
        )
        self.setStyleSheet(
            f"QMainWindow {{ background: {BG}; }}"
            f"* {{ color: {TEXT};"
            f" font-family: '{FONT_FAMILY}', 'Segoe UI', system-ui; }}"
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

        sw = settings.get("sidebar_width", 220)
        self._sidebar_dock.setMinimumWidth(sw)
        self._sidebar_dock.setMaximumWidth(sw)

        sidebar = Sidebar(width=sw)
        # Icones de linha (QPainter) por nome — vide components.LineIcon
        for key, icon, label in [
            ("account", "user", "Minha Conta"),
            ("history", "history", "Historico"),
            ("scanner", "radar", "Scanner"),
            ("market", "chart", "Market"),
            ("trades", "swap", "Trades"),
            ("simulador", "calc", "Simulador"),
            ("watchlist", "eye", "Watchlist"),
        ]:
            sidebar.add_item(key, icon, label)
        sidebar.add_stretch()

        for icon, label, cb in [
            ("gear", "Configuracoes", self._open_settings),
            ("info", "Sobre", self._open_about),
            ("archive", "Backups", self._open_backups),
        ]:
            sidebar.add_action(icon, label, cb)

        sidebar.add_session_chip()

        sidebar.item_selected.connect(self._router.navigate)
        self._sidebar = sidebar
        self._sidebar_dock.setWidget(sidebar)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                           self._sidebar_dock)

        # estado inicial
        visible = self._router.sidebar_visible
        self._sidebar_dock.setVisible(visible)

    def _on_sidebar_visibility(self, visible: bool) -> None:
        self._sidebar_dock.setVisible(visible)

    def _on_navigated(self, screen: str) -> None:
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
            "Ctrl+F &nbsp;&nbsp; Foco no filtro<br>"
            "Ctrl+N &nbsp;&nbsp; Nova posicao (Settings)<br>"
            "Ctrl+, &nbsp;&nbsp; Configuracoes<br>"
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
                f"QMenu {{ background: {_SURFACE}; color: {_TEXT};"
                " border: 1px solid #3A3A44; padding: 4px; }"
                "QMenu::item { padding: 6px 20px; }"
                "QMenu::item:selected { background: #2A2A33; }"
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

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._restore_from_tray()

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

    def _on_sync_requested(self, session) -> None:
        dlg = SteamSyncDialog(session, self)
        dlg.exec()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.exec()

    def _on_theme_changed(self) -> None:
        s = load_settings()
        theme = s.get("theme", "dark")
        if theme == self._current_theme:
            return
        self._current_theme = theme
        set_theme(theme)
        self._apply_stylesheet()
        # Re-aplica sidebar dock style
        self._sidebar_dock.setStyleSheet(
            f"QDockWidget {{ background: {_SURFACE}; }}"
        )
        self._sidebar_dock.widget().setStyleSheet(
            f"background: {_SURFACE};"
        )

    def _open_about(self) -> None:
        QMessageBox.about(
            self, "Sobre o SkinVault",
            "<b>SkinVault</b> v1.0<br><br>"
            "Avaliacao de inventario CS2 sem login.<br>"
            "Precos publicos da Steam Community Market.<br><br>"
            "Lucro real apos taxa de 15% da Steam.<br>"
            "Nao preve futuro — so' dados factuais.<br><br>"
            "Feito por Pedro S. | 2026",
        )


def launch() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication([])
    win = MainWindow()
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
