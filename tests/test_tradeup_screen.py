"""Testes da tela de Trade-up (skinvault/ui/tradeup_screen.py)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import pytest

from skinvault import tradeup

from tests.test_tradeup import CRATES, SKINS


@pytest.fixture(autouse=True)
def _qapp():
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


class _InlineThread:
    """Thread falsa: executa no ato, no processo do teste."""

    def __init__(self, target=None, daemon=None, **kw):
        self._target = target

    def start(self):
        if self._target is not None:
            self._target()


class _Pricer:
    """Substitui SsrPricer: precos fixos, sem disco e sem rede."""

    PRECOS = {"AWP | Restrito A1 (Minimal Wear)": 23.0,
              "P90 | Restrito A2 (Field-Tested)": 5.75}

    def __init__(self, *a, **kw):
        self.fetches = 0
        self.blocked = False

    def pending(self, names):
        return 0

    def __call__(self, name):
        return self.PRECOS.get(name)


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setattr("threading.Thread", _InlineThread)
    cat = tradeup.build_catalog(SKINS, CRATES)
    monkeypatch.setattr(tradeup, "refresh_catalog",
                        lambda force=False: (tradeup.CATALOG_CACHED, cat))
    monkeypatch.setattr(tradeup, "SsrPricer", _Pricer)
    from skinvault.ui.tradeup_screen import TradeUpScreen
    s = TradeUpScreen()
    s.refresh()
    return s


def _add(screen, name, qty, f="", cost=0.0):
    screen._name_inp.setText(name)
    screen._qty_inp.setValue(qty)
    screen._float_inp.setText(f)
    screen._cost_inp.setValue(cost)
    screen._on_add()


def test_carrega_catalogo_e_autocomplete(screen):
    assert screen._catalog is not None
    assert "2 coleções" in screen._catalog_lbl.text() or \
        "coleções" in screen._catalog_lbl.text()
    assert screen._name_inp.completer() is not None


def test_calcula_ev_e_preenche_tabela(screen):
    _add(screen, "AK-47 | Alfa (Field-Tested)", 10, f="0,20", cost=1.0)
    assert screen._inputs.rowCount() == 1
    assert "10 item(ns)" in screen._count_lbl.text()
    screen._on_calculate()
    assert screen._outputs.rowCount() == 2
    assert screen._card_ev._value.text() == "R$ 12,50"
    assert "R$ 2,50" in screen._card_profit._value.text()
    assert screen._card_chance._value.text() == "50,0%"
    assert screen._calc_btn.isEnabled()


def test_contrato_invalido_nao_dispara_worker(screen, monkeypatch):
    chamado = []
    monkeypatch.setattr(screen._eval_worker, "start",
                        lambda plan: chamado.append(plan))
    _add(screen, "AK-47 | Alfa (Field-Tested)", 3)
    screen._on_calculate()
    assert not chamado
    assert screen._status_lbl.isVisibleTo(screen)
    assert "10 itens" in screen._status_lbl.text()


def test_limite_de_itens_e_remover(screen):
    _add(screen, "AK-47 | Alfa (Field-Tested)", 8)
    _add(screen, "M4A4 | Alfa (Field-Tested)", 3)  # passaria de 10
    assert len(screen._entries) == 1
    screen._inputs.selectRow(0)
    screen._on_remove()
    assert screen._entries == [] and screen._inputs.rowCount() == 0


def test_router_navega_para_tradeup(monkeypatch):
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr(tradeup, "refresh_catalog",
                        lambda force=False: (tradeup.CATALOG_UNAVAILABLE, None))
    from skinvault.prices import PriceCache
    from skinvault.ui import screen_router as sr
    router = sr.ScreenRouter(PriceCache())
    router.navigate(sr.SCREEN_TRADEUP)
    assert router._stack.currentWidget() is router._tradeup_screen
    assert "indisponível" in router._tradeup_screen._catalog_lbl.text()
