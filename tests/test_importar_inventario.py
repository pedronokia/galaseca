"""Importar inventario publico pelo link do perfil + adicionar item manual."""
from __future__ import annotations

import pytest

from skinvault import portfolio, steam_api

ID = "76561198023414915"


# ── link do perfil -> SteamID64 ─────────────────────────────
@pytest.mark.parametrize("texto,esperado", [
    (ID, ("id64", ID)),
    (f"  {ID}  ", ("id64", ID)),
    (f"https://steamcommunity.com/profiles/{ID}/", ("id64", ID)),
    (f"steamcommunity.com/profiles/{ID}/inventory/#730", ("id64", ID)),
    ("https://steamcommunity.com/id/gabelogannewell/", ("vanity", "gabelogannewell")),
    ("https://steamcommunity.com/id/nick_123-x", ("vanity", "nick_123-x")),
    ("gabelogannewell", ("vanity", "gabelogannewell")),
    ("", ("invalid", "")),
    (None, ("invalid", "")),
    ("https://example.com/qualquer/coisa", ("invalid", "")),
    ("isto tem espaco", ("invalid", "")),
    ("123", ("vanity", "123")),
])
def test_parse_profile_input(texto, esperado):
    assert steam_api.parse_profile_input(texto) == esperado


def test_resolve_id64_nao_vai_na_rede(monkeypatch):
    monkeypatch.setattr(steam_api, "_http_get",
                        lambda url: pytest.fail("nao devia buscar"))
    assert steam_api.resolve_steam_id(ID) == (steam_api.RESOLVE_OK, ID)


def test_resolve_apelido_pelo_xml_publico(monkeypatch):
    urls = []

    def fake(url):
        urls.append(url)
        return 200, (f"<profile><steamID64>{ID}</steamID64>"
                     "<steamID>gaben</steamID></profile>")

    monkeypatch.setattr(steam_api, "_http_get", fake)
    assert steam_api.resolve_steam_id(
        "https://steamcommunity.com/id/gabelogannewell") == (
        steam_api.RESOLVE_OK, ID)
    assert urls == ["https://steamcommunity.com/id/gabelogannewell/?xml=1"]


@pytest.mark.parametrize("resposta,status", [
    ((200, "<response><error>The specified profile could not be found."
           "</error></response>"), steam_api.RESOLVE_NOT_FOUND),
    ((429, None), steam_api.RESOLVE_RATE_LIMITED),
    ((0, None), steam_api.RESOLVE_ERROR),
    ((500, None), steam_api.RESOLVE_ERROR),
])
def test_resolve_apelido_falhas(monkeypatch, resposta, status):
    monkeypatch.setattr(steam_api, "_http_get", lambda url: resposta)
    assert steam_api.resolve_steam_id("apelido") == (status, None)


def test_resolve_texto_invalido():
    assert steam_api.resolve_steam_id("nada a ver") == (
        steam_api.RESOLVE_INVALID, None)


# ── mescla na carteira ───────────────────────────────────────
@pytest.fixture
def arq(tmp_path):
    return tmp_path / "portfolio.json"


def _item(nome, qtd=1, icon=None):
    return {"name": nome, "quantity": qtd, "icon": icon, "type": "Rifle"}


def test_importacao_inicial_entra_com_custo_desconhecido(arq):
    r = portfolio.merge_steam_inventory(
        [_item("AK-47 | Alfa (FT)", 2, "h1"), _item("Kilowatt Case", 5)],
        path=arq)
    assert r == {"adicionados": 2, "atualizados": 0, "removidos": 0,
                 "manuais_mantidos": 0, "itens_no_inventario": 2}
    pos = portfolio.load_portfolio(arq)
    ak = next(p for p in pos if p["name"] == "AK-47 | Alfa (FT)")
    assert ak["quantity"] == 2 and ak["icon"] == "h1"
    assert ak["source"] == portfolio.SOURCE_STEAM
    assert portfolio.has_cost_basis(ak) is False  # custo desconhecido


def test_reimportacao_atualiza_quantidade_e_remove_o_que_saiu(arq):
    portfolio.merge_steam_inventory(
        [_item("A", 1), _item("B", 1)], path=arq)
    r = portfolio.merge_steam_inventory(
        [_item("A", 3, "novo-icone")], path=arq)
    assert r["atualizados"] == 1 and r["removidos"] == 1
    assert r["adicionados"] == 0
    pos = portfolio.load_portfolio(arq)
    assert [(p["name"], p["quantity"]) for p in pos] == [("A", 3)]
    assert pos[0]["icon"] == "novo-icone"


def test_sem_remover_mantem_o_que_saiu(arq):
    portfolio.merge_steam_inventory([_item("A"), _item("B")], path=arq)
    r = portfolio.merge_steam_inventory([_item("A")], remove_missing=False,
                                        path=arq)
    assert r["removidos"] == 0
    assert {p["name"] for p in portfolio.load_portfolio(arq)} == {"A", "B"}


def test_posicao_manual_nunca_e_tocada(arq):
    portfolio.add_position("A", 150.0, 1, path=arq)          # manual, com custo
    portfolio.add_position("Fora do inventario", 20.0, 1, path=arq)
    r = portfolio.merge_steam_inventory([_item("A", 4), _item("C")],
                                        path=arq)
    assert r["manuais_mantidos"] == 1 and r["adicionados"] == 1
    pos = {p["name"]: p for p in portfolio.load_portfolio(arq)}
    assert pos["A"]["quantity"] == 1 and pos["A"]["cost"] == 150.0
    assert pos["A"]["source"] == "manual"
    assert "Fora do inventario" in pos  # manual sobrevive mesmo sumindo
    assert pos["C"]["source"] == portfolio.SOURCE_STEAM


def test_posicao_manual_ganha_icone_do_inventario_real(arq):
    """Achado real (2026-10-20): item colado via CSV (manual pra sempre)
    que por acaso E' o mesmo item do inventario Steam real nao devia
    ficar sem imagem ate' o fim dos tempos -- so' custo/quantidade/origem
    ficam intocados, o icone backfilla do mesmo jeito."""
    portfolio.add_position("A", 150.0, 1, path=arq)  # manual, sem icone
    r = portfolio.merge_steam_inventory([_item("A", 4, "hash-real")],
                                        path=arq)
    pos = portfolio.load_portfolio(arq)[0]
    assert pos["icon"] == "hash-real"
    # custo/quantidade/origem continuam intocados -- so' o icone muda.
    assert pos["cost"] == 150.0 and pos["quantity"] == 1
    assert pos["source"] == "manual"
    assert r["manuais_mantidos"] == 1


def test_custo_definido_depois_vira_manual_e_e_preservado(arq):
    portfolio.merge_steam_inventory([_item("A", 1)], path=arq)
    portfolio.update_position_cost("A", 99.9, path=arq)
    portfolio.merge_steam_inventory([_item("A", 7)], path=arq)
    pos = portfolio.load_portfolio(arq)
    assert len(pos) == 1
    assert pos[0]["cost"] == 99.9 and pos[0]["quantity"] == 1


def test_duplicata_da_steam_de_item_manual_nao_conta_como_removida(arq):
    portfolio.add_position("A", 10.0, 1, path=arq)
    portfolio.add_position("A", 0.0, 1, path=arq,
                           source=portfolio.SOURCE_STEAM)
    r = portfolio.merge_steam_inventory([_item("A")], path=arq)
    assert r["removidos"] == 0
    assert [p["source"] for p in portfolio.load_portfolio(arq)] == ["manual"]


# ── adicionar item sem custo ─────────────────────────────────
def test_add_position_sem_custo_fica_fora_do_lucro(arq):
    portfolio.add_position("Fever Case", None, 3, path=arq)
    pos = portfolio.load_portfolio(arq)[0]
    assert pos["cost"] is None and pos["source"] == "manual"
    assert portfolio.has_cost_basis(pos) is False
    res = portfolio.evaluate_portfolio([pos], lambda n: 10.0)
    assert res["totals"]["unknown_cost"] == 1
    assert res["totals"]["pnl"] is None


def test_add_position_custo_zero_e_drop(arq):
    portfolio.add_position("Drop", 0.0, 1, path=arq)
    assert portfolio.has_cost_basis(portfolio.load_portfolio(arq)[0])
