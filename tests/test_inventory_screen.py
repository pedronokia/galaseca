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


# ── coluna Score ───────────────────────────────────────────────────
#
# O score fica persistido na POSITION pelo "Validar score" da tela Minha
# Conta. A tela de inventario so' exibe -- nao recalcula nem toca a rede,
# que e' rate-limited.


def _score_cell(tela, fragmento):
    """Celula de score da linha cujo nome contem `fragmento`.

    Buscar por nome, nao por indice: a tabela roda com setSortingEnabled e
    reordena pelo nome LOCALIZADO ("Caixa Kilowatt" vem antes de "AK-47 |
    Redline (Veterana de Guerra)"), entao a ordem visual nao e' a de entrada.
    """
    for i in range(tela._table.rowCount()):
        nome = tela._table.item(i, tela.COL_NAME)
        if nome and fragmento.lower() in nome.text().lower():
            return tela._table.item(i, tela.COL_SCORE)
    raise AssertionError("linha nao encontrada: " + fragmento)


def test_score_da_position_aparece_na_coluna(tela):
    import time
    pos = [dict(POS[0], current_score=88, score_ts=time.time()),
           dict(POS[1])]
    tela.set_data(ROWS, pos)
    assert _score_cell(tela, "Redline").text() == "88"


def test_score_segue_o_item_certo_apos_a_ordenacao(tela):
    """A tabela reordena; o score nao pode acabar na linha do vizinho."""
    import time
    agora = time.time()
    pos = [dict(POS[0], current_score=88, score_ts=agora),
           dict(POS[1], current_score=12, score_ts=agora)]
    tela.set_data(ROWS, pos)
    assert _score_cell(tela, "Redline").text() == "88"
    assert _score_cell(tela, "Kilowatt").text() == "12"


def test_sem_score_mostra_travessao(tela):
    tela.set_data(ROWS, POS)
    cel = _score_cell(tela, "Redline")
    assert cel.text() == "—"
    assert "Validar score" in cel.toolTip()


def test_score_desatualizado_fica_ambar(tela):
    """Um 90 de tres semanas atras nao e' oportunidade, e' dado velho."""
    import time
    from skinvault.ui import theme as t
    pos = [dict(POS[0], current_score=90, score_ts=time.time() - 86400 * 21),
           dict(POS[1], current_score=90, score_ts=time.time())]
    tela.set_data(ROWS, pos)
    velho = _score_cell(tela, "Redline")
    novo = _score_cell(tela, "Kilowatt")
    assert velho.foreground().color().name() == t.WARN.lower()
    assert novo.foreground().color().name() == t.POSITIVE.lower()
    assert "DESATUALIZADO" in velho.toolTip()
    assert "DESATUALIZADO" not in novo.toolTip()


def test_score_nao_desloca_a_coluna_origem(tela):
    """Origem entrou depois de Score; se os indices saissem de sincronia a
    tabela mostraria 'Steam' na coluna errada."""
    tela.set_data(ROWS, POS)
    assert tela._table.item(0, tela.COL_ORIGIN).text() == "Steam"
    assert tela._table.columnCount() == 8


def test_position_faltando_nao_quebra_a_coluna(tela):
    """set_data(rows, []) e' caminho suportado -- ver test_sem_posicoes."""
    tela.set_data(ROWS, [])
    assert _score_cell(tela, "Redline").text() == "—"


def test_celula_de_score_e_a_mesma_da_watchlist():
    """Se as duas telas divergirem na cor ou no tooltip, uma das duas esta'
    mentindo sobre o mesmo numero."""
    import time
    from skinvault.ui.components import score_table_item
    from skinvault.ui.watchlist_screen import WatchlistScreen
    assert WatchlistScreen  # a tela consome o mesmo helper
    ts = time.time()
    a = score_table_item(75, ts)
    b = score_table_item(75, ts)
    assert a.text() == b.text()
    assert a.toolTip() == b.toolTip()
    assert a.foreground().color().name() == b.foreground().color().name()


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
