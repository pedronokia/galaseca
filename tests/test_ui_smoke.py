"""Smoke tests para UI (F11).

Instancia MainWindow e cada tela individualmente sem rede.
Nao usa rede; mocka session e tray nos testes que precisam.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

import pytest


@pytest.fixture(autouse=True)
def _qapp():
    """Cria/descarta QApplication por teste."""
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
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
    """ScannerScreen (real) instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    assert screen is not None


def test_screen_router_builds(monkeypatch):
    """ScreenRouter instancia e mostra LoginGate (sem sessao)."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    cache = PriceCache(ttl=3600)
    router = ScreenRouter(cache)
    assert router._stack.currentWidget() == router._login_gate


def test_price_worker_instantiation():
    """PriceWorker bridge instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import BatchPriceWorker, PriceWorker, SinglePriceWorker
    cache = PriceCache(ttl=3600)
    assert PriceWorker(cache) is not None
    assert SinglePriceWorker(cache) is not None
    assert BatchPriceWorker(cache) is not None


class _InlineThread:
    """Thread fake que executa o target em start() (nao async)."""
    def __init__(self, target=None, daemon=False):
        self._target = target
    def start(self):
        if self._target:
            self._target()


def test_price_worker_start(monkeypatch):
    """PriceWorker.start() emite eval_done com dados corretos."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import PriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio",
                        lambda: [{"name": "AK", "cost": 100.0, "quantity": 1}])
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: 150.0)

    cache = PriceCache(ttl=3600)
    worker = PriceWorker(cache)
    results = []
    worker.eval_done.connect(results.append)
    worker.start()
    QApplication.processEvents()

    assert len(results) == 1
    d = results[0]
    assert d["totals"]["pnl"] == pytest.approx(30.43, abs=0.01)
    assert len(d["rows"]) == 1


def test_price_worker_start_error(monkeypatch):
    """PriceWorker.start() engole excecao e emite eval_done com error."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import PriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio",
                        lambda: (_ for _ in ()).throw(ValueError("boom")))

    cache = PriceCache(ttl=3600)
    worker = PriceWorker(cache)
    results = []
    worker.eval_done.connect(results.append)
    worker.start()
    QApplication.processEvents()

    assert len(results) == 1
    assert "error" in results[0]
    assert "boom" in results[0]["error"]


def test_batch_price_worker(monkeypatch):
    """BatchPriceWorker.start() emite progress e batch_done."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import BatchPriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: 50.0)

    cache = PriceCache(ttl=3600)
    worker = BatchPriceWorker(cache)
    progress_log = []
    worker.progress.connect(lambda d, t: progress_log.append((d, t)))
    done_log = []
    worker.batch_done.connect(lambda: done_log.append(True))
    worker.start(["AK", "AWP", "AK"])
    QApplication.processEvents()

    assert done_log == [True]
    assert progress_log == [(1, 2), (2, 2)]  # deduped to 2 unique


def test_single_price_worker(monkeypatch):
    """SinglePriceWorker.start() emite done com preco."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import SinglePriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: 200.0 if n == "AK" else None)

    cache = PriceCache(ttl=3600)
    worker = SinglePriceWorker(cache)
    results = []
    worker.done.connect(lambda n, p: results.append((n, p)))
    worker.start("AK")
    QApplication.processEvents()

    assert len(results) == 1
    assert results[0] == ("AK", 200.0)


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


def test_market_screen():
    """MarketScreen instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.market_screen import MarketScreen
    screen = MarketScreen(PriceCache(ttl=3600))
    assert screen is not None


def test_trades_screen():
    """TradesScreen instancia sem erro."""
    from skinvault.ui.trades_screen import TradesScreen
    screen = TradesScreen()
    assert screen is not None


def test_simulador_screen():
    """SimuladorScreen instancia sem erro."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    assert screen is not None


def test_watchlist_screen():
    """WatchlistScreen instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    assert screen is not None


def test_dialogs_instantiation(monkeypatch):
    """SettingsDialog, BackupDialog e SteamSyncDialog instanciam."""
    monkeypatch.setattr("skinvault.sync.sync_all",
                        lambda *a, **kw: {})
    from skinvault.gui import BackupDialog, SettingsDialog, SteamSyncDialog
    from skinvault.steam_session import SteamSession
    assert SettingsDialog() is not None
    assert BackupDialog() is not None
    assert SteamSyncDialog(SteamSession("key", "sid")) is not None
