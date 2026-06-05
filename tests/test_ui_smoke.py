"""Smoke tests para UI (F11).

Instancia MainWindow e cada tela individualmente sem rede.
Nao usa rede; mocka session e tray nos testes que precisam.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

import pytest


@pytest.fixture(autouse=True)
def _qapp():
    """Cria/descarta QApplication por teste."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    for w in list(app.topLevelWidgets()):
        w.deleteLater()
    app.processEvents()
    app.quit()


def test_mainwindow_instantiation(monkeypatch):
    """Cria MainWindow sem erros, mockando session e tray."""
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: False)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.gui import MainWindow
    win = MainWindow()
    assert win.windowTitle() == "SkinVault"


def test_login_gate():
    """LoginGate instancia sem erro."""
    from skinvault.ui.login_gate import LoginGate
    gate = LoginGate()
    assert gate is not None


def test_account_screen():
    """AccountScreen instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    cache = PriceCache(ttl=3600)
    screen = AccountScreen(cache)
    assert screen is not None


def test_history_screen():
    """HistoryScreen instancia sem erro."""
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    assert screen is not None


def test_scanner_screen():
    """ScannerScreen (mockup) instancia sem erro."""
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen()
    assert screen is not None


def test_screen_router_builds(monkeypatch):
    """ScreenRouter instancia e mostra LoginGate (sem sessao)."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    cache = PriceCache(ttl=3600)
    router = ScreenRouter(cache)
    assert router._stack.currentWidget() == router._login_gate


def test_price_worker():
    """PriceWorker bridge instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import PriceWorker, SinglePriceWorker
    cache = PriceCache(ttl=3600)
    assert PriceWorker(cache) is not None
    assert SinglePriceWorker(cache) is not None


def test_components_instantiation():
    """Componentes da UI instanciam sem erro."""
    from skinvault.ui.components import (
        Avatar, Breadcrumb, Card, Footer, Sidebar,
        StatCard, SegmentedControl, LockOverlay,
    )
    assert Card() is not None
    assert StatCard("label", "value") is not None
    assert Sidebar() is not None
    assert Breadcrumb() is not None
    assert Footer() is not None
    assert Avatar() is not None
    assert SegmentedControl() is not None
    assert LockOverlay() is not None


def test_dialogs_instantiation(monkeypatch):
    """SettingsDialog, BackupDialog e SteamSyncDialog instanciam."""
    monkeypatch.setattr("skinvault.sync.sync_all",
                        lambda *a, **kw: {})
    from skinvault.gui import BackupDialog, SettingsDialog, SteamSyncDialog
    from skinvault.steam_session import SteamSession
    assert SettingsDialog() is not None
    assert BackupDialog() is not None
    assert SteamSyncDialog(SteamSession("key", "sid")) is not None
