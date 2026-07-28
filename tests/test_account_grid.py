"""AccountScreen: alternancia grade/tabela e as duas avaliacoes."""
from __future__ import annotations

import pytest

from skinvault.prices import PriceCache


@pytest.fixture(autouse=True)
def app():
    """Mesmo ciclo de vida do test_ui_smoke.

    Sem QApplication, instanciar QWidget derruba o processo (exit 9). E com
    ciclo de vida DIFERENTE do outro arquivo, a suite inteira crasha --
    o teardown de la' encerra a instancia que estes testes reusariam.
    """
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
def screen(app, tmp_path):
    from skinvault.ui.account_screen import AccountScreen
    return AccountScreen(PriceCache(tmp_path / "p.json", ttl=3600))


ROWS = [
    {"name": "AK-47 | Redline (Battle-Scarred)", "quantity": 1,
     "price": 175.71, "market": 175.71, "net_if_sold": 149.35, "pnl": 10.0},
    {"name": "Kilowatt Case", "quantity": 21,
     "price": 1.22, "market": 25.62, "net_if_sold": 1.04, "pnl": -2.0},
]
POS = [{"source": "steam_sync", "icon": "abc", "type": "Classified Rifle"},
       {"source": "steam_sync", "icon": "def", "type": "Container"}]


# ── alternancia ────────────────────────────────────────────────────


def test_comeca_na_grade(screen):
    assert screen._views.currentIndex() == 0
    assert screen._view_btn.text() == "Ver em tabela"


def test_toggle_vai_e_volta(screen):
    screen._toggle_view()
    assert screen._views.currentIndex() == 1
    assert screen._view_btn.text() == "Ver em grade"
    screen._toggle_view()
    assert screen._views.currentIndex() == 0
    assert screen._view_btn.text() == "Ver em tabela"


def test_filtro_seque_a_visao_ativa(screen):
    """O filtro so' age na tabela; ativo na grade so' confundiria.

    Regressao: a primeira versao olhava o estado ANTES do clique e deixava
    o filtro invertido nas duas direcoes.
    """
    assert screen._filter_inp.isEnabled() is False   # nasce na grade
    screen._toggle_view()                            # -> tabela
    assert screen._filter_inp.isEnabled() is True
    screen._toggle_view()                            # -> grade
    assert screen._filter_inp.isEnabled() is False


# ── populacao da grade ─────────────────────────────────────────────


def test_grade_recebe_os_itens(screen, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {"Kilowatt Case": 0.24})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    screen._populate_grid(ROWS, POS)
    assert screen._grid.count() == 2


def test_grade_traz_as_duas_avaliacoes(screen, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {"Kilowatt Case": 0.24})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    screen._populate_grid(ROWS, POS)
    kilo = next(t.item for t in screen._grid._tiles
                if "Kilowatt" in t.item["raw_name"])
    assert kilo["steam_net"] == 1.04          # saldo Steam
    assert kilo["market_net"] is not None      # dinheiro real
    assert kilo["premium_pct"] is not None


def test_item_sem_cotacao_fora_fica_none(screen, monkeypatch):
    """Nao inventa numero: sem cotacao, o campo fica vazio."""
    monkeypatch.setattr("skinvault.markets.cached_market", lambda *a, **k: {})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    screen._populate_grid(ROWS, POS)
    for tile in screen._grid._tiles:
        assert tile.item["market_net"] is None
        assert tile.item["steam_net"] is not None


def test_falha_de_rede_nao_derruba_a_tela(screen, monkeypatch):
    def boom(*a, **k):
        raise OSError("sem rede")

    monkeypatch.setattr("skinvault.markets.cached_market", boom)
    screen._populate_grid(ROWS, POS)
    assert screen._grid.count() == 2
    assert all(t.item["market_net"] is None for t in screen._grid._tiles)


def test_grade_usa_icone_e_tipo_da_posicao(screen, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market", lambda *a, **k: {})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    screen._populate_grid(ROWS, POS)
    icones = {t.item["icon"] for t in screen._grid._tiles}
    assert icones == {"abc", "def"}


def test_grade_sem_posicoes_nao_quebra(screen, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market", lambda *a, **k: {})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    screen._populate_grid(ROWS, [])
    assert screen._grid.count() == 2


def test_grade_vazia(screen, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market", lambda *a, **k: {})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    screen._populate_grid([], [])
    assert screen._grid.count() == 0
