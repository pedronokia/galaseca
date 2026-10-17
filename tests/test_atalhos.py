"""Atalhos de teclado (bloco 4 da revisao de UI, 2026-10-17).

O bug que motivou: a janela registrava Ctrl+F (e Ctrl+N) e as telas
tambem. Duas QShortcut com a mesma tecla ativas ao mesmo tempo sao
ambiguas pro Qt -- ele emite activatedAmbiguously e NENHUMA dispara.
Ctrl+F nao fazia nada justamente nas telas que tinham busca.
"""
from __future__ import annotations

import pytest
from PyQt6.QtGui import QShortcut


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _teclas(widget, so_filhos_diretos=True):
    opts = ({"options": __import__("PyQt6.QtCore", fromlist=["Qt"])
             .Qt.FindChildOption.FindDirectChildrenOnly}
            if so_filhos_diretos else {})
    return [s.key().toString() for s in widget.findChildren(QShortcut,
                                                            **opts)]


def _janela(monkeypatch):
    from tests.test_ui_smoke import _make_mw
    return _make_mw(monkeypatch)


def test_janela_sem_tecla_duplicada_com_as_telas(monkeypatch):
    """Nenhuma tecla da janela pode repetir a de uma tela."""
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    win = _janela(monkeypatch)
    da_janela = _teclas(win)
    assert len(da_janela) == len(set(da_janela))

    router = ScreenRouter(PriceCache(ttl=3600))
    for i in range(router._stack.count()):
        tela = router._stack.widget(i)
        comuns = set(da_janela) & set(_teclas(tela, False))
        assert not comuns, (type(tela).__name__, comuns)


def test_ctrl_numero_navega_na_ordem_da_barra(monkeypatch):
    win = _janela(monkeypatch)
    atalhos = {s.key().toString(): s for s in win.findChildren(QShortcut)}
    for i, (key, _icon, _label) in enumerate(win._SIDEBAR_ITENS, 1):
        atalhos[f"Ctrl+{i}"].activated.emit()
        assert win._router._screen == key


def test_ajuda_lista_troca_de_tela(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    textos = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: textos.append(a[2]))
    win = _janela(monkeypatch)
    win._show_shortcuts()
    assert "Ctrl+1" in textos[0] and "Inventário" in textos[0]


def test_market_ctrl_f_e_f5(monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui.market_screen import MarketScreen
    tela = MarketScreen(PriceCache(ttl=3600))
    assert {"Ctrl+F", "Ctrl+L"} <= set(_teclas(tela))
    buscas = []
    monkeypatch.setattr(tela, "_on_search", lambda: buscas.append(1))
    tela.refresh()                      # campo vazio: nada a refazer
    assert buscas == []
    tela._search_inp.setText("AK-47 | Redline (Field-Tested)")
    tela.refresh()
    assert buscas == [1]


def test_inventario_f5_pede_reavaliacao(monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {})
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda *a, **k: None)
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: {})
    from skinvault.ui.inventory_screen import InventoryScreen
    tela = InventoryScreen()
    pedidos = []
    tela.request_reeval.connect(lambda: pedidos.append(1))
    tela.refresh()                      # vazio: nao reavalia o nada
    assert pedidos == []
    tela.set_data([{"name": "Kilowatt Case", "quantity": 1, "price": 1.2,
                    "market": 1.2, "net_if_sold": 1.04, "pnl": None}],
                  [{"name": "Kilowatt Case", "source": "steam_sync"}], False)
    tela.refresh()
    assert pedidos == [1]
