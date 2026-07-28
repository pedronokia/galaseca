"""InventoryScreen -- a aba propria do inventario.

Saiu de dentro da "Minha Conta" em 28/07/2026: la' o inventario dividia a
janela com perfil, quatro cartoes de valor, cinco de desempenho e um
grafico, e sobrava rodape pro conteudo que da' nome a tela.
"""
from __future__ import annotations

import pytest

from skinvault.ui.inventory_screen import InventoryScreen


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


@pytest.fixture
def tela(monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {"Kilowatt Case": 0.24})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    return InventoryScreen()


ROWS = [
    {"name": "AK-47 | Redline (Battle-Scarred)", "quantity": 1,
     "price": 175.71, "market": 175.71, "net_if_sold": 149.35, "pnl": None},
    {"name": "Kilowatt Case", "quantity": 21,
     "price": 1.22, "market": 25.62, "net_if_sold": 1.04, "pnl": None},
]
POS = [{"source": "steam_sync", "icon": "abc", "type": "Rifle"},
       {"source": "steam_sync", "icon": "def", "type": "Container"}]


# ── estado vazio ───────────────────────────────────────────────────


def test_comeca_vazia(tela):
    assert tela._views.isVisibleTo(tela) is False
    assert tela._empty.isVisibleTo(tela) is True


def test_dados_escondem_o_empty_state(tela):
    tela.set_data(ROWS, POS)
    assert tela._views.isVisibleTo(tela) is True
    assert tela._empty.isVisibleTo(tela) is False


def test_lista_vazia_volta_pro_empty_state(tela):
    tela.set_data(ROWS, POS)
    tela.set_data([], [])
    assert tela._empty.isVisibleTo(tela) is True
    assert tela._status.text() == ""


# ── as duas visoes ─────────────────────────────────────────────────


def test_popula_grade_e_tabela(tela):
    tela.set_data(ROWS, POS)
    assert tela._grid.count() == 2
    assert tela._table.rowCount() == 2


def test_grade_traz_as_duas_avaliacoes(tela):
    tela.set_data(ROWS, POS)
    kilo = next(x.item for x in tela._grid._tiles
                if "Kilowatt" in x.item["raw_name"])
    assert kilo["steam_net"] == 1.04
    assert kilo["market_net"] is not None
    assert kilo["premium_pct"] is not None


def test_item_sem_cotacao_fora_fica_none(tela, monkeypatch):
    """Nao inventa numero: sem cotacao, o campo fica vazio."""
    monkeypatch.setattr("skinvault.markets.cached_market", lambda *a, **k: {})
    tela.set_data(ROWS, POS)
    for tile in tela._grid._tiles:
        assert tile.item["market_net"] is None
        assert tile.item["steam_net"] is not None


def test_falha_de_rede_nao_derruba_a_tela(tela, monkeypatch):
    def boom(*a, **k):
        raise OSError("sem rede")
    monkeypatch.setattr("skinvault.markets.cached_market", boom)
    tela.set_data(ROWS, POS)
    assert tela._grid.count() == 2


def test_usa_icone_e_tipo_da_posicao(tela):
    tela.set_data(ROWS, POS)
    assert {x.item["icon"] for x in tela._grid._tiles} == {"abc", "def"}


def test_sem_posicoes_nao_quebra(tela):
    tela.set_data(ROWS, [])
    assert tela._grid.count() == 2


# ── alternancia e filtro ───────────────────────────────────────────


def test_comeca_na_grade(tela):
    assert tela._views.currentIndex() == 0
    assert tela._view_btn.text() == "Ver em tabela"
    assert tela._filter.isEnabled() is False


def test_toggle_vai_e_volta(tela):
    tela._toggle_view()
    assert tela._views.currentIndex() == 1
    assert tela._filter.isEnabled() is True
    tela._toggle_view()
    assert tela._views.currentIndex() == 0
    assert tela._filter.isEnabled() is False


def test_filtro_esconde_linhas(tela):
    tela.set_data(ROWS, POS)
    tela._apply_filter("kilowatt")
    escondidas = [tela._table.isRowHidden(i)
                  for i in range(tela._table.rowCount())]
    assert escondidas.count(False) == 1


def test_filtro_vazio_mostra_tudo(tela):
    tela.set_data(ROWS, POS)
    tela._apply_filter("kilowatt")
    tela._apply_filter("")
    assert all(not tela._table.isRowHidden(i)
               for i in range(tela._table.rowCount()))


def test_status_conta_itens(tela):
    tela.set_data(ROWS, POS)
    assert "2" in tela._status.text()


# ── integracao com o router ────────────────────────────────────────


def test_router_liga_account_ao_inventario(tmp_path):
    """A AccountScreen avalia; a InventoryScreen so' exibe."""
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    r = ScreenRouter(PriceCache(tmp_path / "p.json", ttl=3600))
    r._account_screen.inventory_ready.emit(ROWS, POS)
    assert r._inventory_screen._grid.count() == 2


def test_router_navega_pro_inventario(tmp_path):
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import SCREEN_INVENTORY, ScreenRouter
    r = ScreenRouter(PriceCache(tmp_path / "p.json", ttl=3600))
    r.navigate(SCREEN_INVENTORY)
    assert r._stack.currentWidget() is r._inventory_screen
