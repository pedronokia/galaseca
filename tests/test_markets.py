"""Precos multi-mercado: parse, cache, cambio e comparacao."""
from __future__ import annotations

import json

import pytest

from skinvault import markets


# ── _parse_prices: o formato varia por fonte ───────────────────────


def test_parse_aceita_starting_at():
    d = markets._parse_prices(
        {"AK-47 | Redline (FT)": {"starting_at": 12.5,
                                  "suggested_price": None}})
    assert d == {"AK-47 | Redline (FT)": 12.5}


def test_parse_aceita_numero_direto():
    assert markets._parse_prices({"X": 3.25}) == {"X": 3.25}


def test_parse_aceita_campos_alternativos():
    d = markets._parse_prices({"A": {"price": 7.0}, "B": {"lowest_price": 2.0}})
    assert d == {"A": 7.0, "B": 2.0}


def test_parse_descarta_zero_e_nulo():
    d = markets._parse_prices(
        {"A": {"starting_at": 0}, "B": {"starting_at": None},
         "C": None, "D": {"starting_at": 1.0}})
    assert d == {"D": 1.0}


def test_parse_tolera_lixo():
    assert markets._parse_prices(None) == {}
    assert markets._parse_prices([1, 2]) == {}


# ── fetch_market ───────────────────────────────────────────────────


def test_fetch_ok(monkeypatch):
    body = json.dumps({"Kilowatt Case": {"starting_at": 0.24}})
    monkeypatch.setattr(markets, "_http_get", lambda url, **kw: (200, body))
    status, precos = markets.fetch_market("skinport")
    assert status == markets.OK
    assert precos["Kilowatt Case"] == 0.24


def test_fetch_usa_a_fonte_na_url(monkeypatch):
    vistos = []

    def fake(url, **kw):
        vistos.append(url)
        return 200, json.dumps({"X": 1.0})

    monkeypatch.setattr(markets, "_http_get", fake)
    markets.fetch_market("buff163")
    assert "buff163.json" in vistos[0]


def test_fetch_erros(monkeypatch):
    monkeypatch.setattr(markets, "_http_get", lambda url, **kw: (403, None))
    assert markets.fetch_market()[0] == markets.ERROR
    monkeypatch.setattr(markets, "_http_get", lambda url, **kw: (200, "{"))
    assert markets.fetch_market()[0] == markets.ERROR
    monkeypatch.setattr(markets, "_http_get", lambda url, **kw: (200, "{}"))
    assert markets.fetch_market()[0] == markets.ERROR


# ── cache ──────────────────────────────────────────────────────────


def test_cache_guarda_e_le(tmp_path):
    c = markets.MarketPriceCache(path=tmp_path / "m.json", ttl=3600)
    c.put("skinport", {"A": 1.0}, now=1000)
    assert c.get("skinport", now=1500) == {"A": 1.0}


def test_cache_expira(tmp_path):
    c = markets.MarketPriceCache(path=tmp_path / "m.json", ttl=100)
    c.put("skinport", {"A": 1.0}, now=1000)
    assert c.get("skinport", now=2000) is None


def test_cache_separa_fontes(tmp_path):
    c = markets.MarketPriceCache(path=tmp_path / "m.json", ttl=3600)
    c.put("skinport", {"A": 1.0}, now=1000)
    assert c.get("buff163", now=1000) is None


def test_cache_persiste(tmp_path):
    p = tmp_path / "m.json"
    markets.MarketPriceCache(path=p, ttl=3600).put("skinport", {"A": 2.0},
                                                   now=1000)
    assert markets.MarketPriceCache(path=p, ttl=3600).get(
        "skinport", now=1100) == {"A": 2.0}


def test_cached_market_evita_rede_no_hit(tmp_path, monkeypatch):
    c = markets.MarketPriceCache(path=tmp_path / "m.json", ttl=3600)
    c.put("skinport", {"A": 1.0})
    chamadas = []
    monkeypatch.setattr(markets, "_http_get",
                        lambda *a, **k: chamadas.append(1) or (200, "{}"))
    assert markets.cached_market("skinport", cache=c) == {"A": 1.0}
    assert chamadas == []


def test_cached_market_falha_devolve_vazio(tmp_path, monkeypatch):
    c = markets.MarketPriceCache(path=tmp_path / "m.json", ttl=3600)
    monkeypatch.setattr(markets, "_http_get", lambda *a, **k: (500, None))
    assert markets.cached_market("skinport", cache=c) == {}


# ── cambio ─────────────────────────────────────────────────────────


def test_fx_usa_cache_valido(tmp_path, monkeypatch):
    p = tmp_path / "fx.json"
    p.write_text(json.dumps({"ts": 1000, "rate": 5.5}), encoding="utf-8")
    monkeypatch.setattr(markets, "_http_get",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("nao devia chamar a rede")))
    assert markets.usd_brl(path=p, now=1100) == 5.5


def test_fx_busca_quando_expirado(tmp_path, monkeypatch):
    p = tmp_path / "fx.json"
    p.write_text(json.dumps({"ts": 0, "rate": 5.5}), encoding="utf-8")
    monkeypatch.setattr(
        markets, "_http_get",
        lambda *a, **k: (200, json.dumps({"rates": {"BRL": 5.2}})))
    assert markets.usd_brl(path=p, now=10 ** 9) == 5.2


def test_fx_cai_no_cache_velho_se_a_rede_falhar(tmp_path, monkeypatch):
    p = tmp_path / "fx.json"
    p.write_text(json.dumps({"ts": 0, "rate": 5.7}), encoding="utf-8")
    monkeypatch.setattr(markets, "_http_get", lambda *a, **k: (0, None))
    assert markets.usd_brl(path=p, now=10 ** 9) == 5.7


def test_fx_fallback_sem_cache_nem_rede(tmp_path, monkeypatch):
    monkeypatch.setattr(markets, "_http_get", lambda *a, **k: (0, None))
    assert markets.usd_brl(path=tmp_path / "nao_existe.json") == \
        markets._FX_FALLBACK


# ── compare: o coracao do achado ───────────────────────────────────


def test_compare_mede_o_premio_da_steam():
    """Caso real: Steam pede ~36% mais que o mercado com dinheiro real."""
    r = markets.compare(steam_brl=13.6, market_usd=1.956, fx=5.11)
    assert 34 <= r["premium_pct"] <= 38


def test_compare_wallet_vs_cash_sao_direcoes_opostas():
    r = markets.compare(steam_brl=13.6, market_usd=1.956, fx=5.11)
    assert r["to_wallet_pct"] > 0, "comprar fora e vender na Steam rende"
    assert r["to_cash_pct"] < 0, "comprar na Steam pra sacar perde"


def test_compare_desconta_a_taxa_certa_por_mercado():
    r_sp = markets.compare(10.0, 2.0, 5.0, source="skinport")
    r_buff = markets.compare(10.0, 2.0, 5.0, source="buff163")
    assert r_buff["market_net"] > r_sp["market_net"]


def test_compare_sem_preco_de_mercado_ainda_da_o_lado_steam():
    r = markets.compare(10.0, None, 5.0)
    assert r["steam_net"] == 8.5
    assert r["market_net"] is None
    assert r["premium_pct"] is None


# ── compare_all / best_market ──────────────────────────────────────
#
# A taxa varia muito entre plataformas: 5% na CSGOTM contra 12% no
# Skinport. Medido na AK-47 Redline FT em 2026-07-30, a CSGOTM pagava
# R$ 155,75 liquidos contra R$ 135,85 do Skinport -- entao o maior bruto
# nao e' necessariamente o melhor negocio, e ordenar por bruto enganaria.


@pytest.fixture
def _mercados(monkeypatch):
    dados = {
        "skinport": {"AK": 30.0},    # bruto 150, taxa 12% -> 132
        "buff163": {"AK": 29.0},     # bruto 145, taxa 2.5% -> 141.375
        "csgotm": {"AK": 28.0},      # bruto 140, taxa 5% -> 133
    }
    monkeypatch.setattr(markets, "cached_market",
                        lambda src, cache=None: dados.get(src, {}))
    monkeypatch.setattr(markets, "usd_brl", lambda *a, **k: 5.0)
    return dados


def test_compare_all_ordena_pelo_liquido(_mercados):
    r = markets.compare_all("AK")
    assert [x["source"] for x in r] == ["buff163", "csgotm", "skinport"]


def test_compare_all_maior_bruto_nao_vence(_mercados):
    """Skinport tem o maior BRUTO e mesmo assim fica em ultimo."""
    r = markets.compare_all("AK")
    assert max(r, key=lambda x: x["gross_brl"])["source"] == "skinport"
    assert r[0]["source"] != "skinport"


def test_best_market_e_o_primeiro(_mercados):
    assert markets.best_market("AK")["source"] == "buff163"


def test_compare_all_pula_fonte_sem_cotacao(_mercados):
    r = markets.compare_all("Item Que So Existe No Skinport")
    assert r == []


def test_compare_all_calcula_premio_da_steam(_mercados):
    r = markets.compare_all("AK", steam_brl=180.0)
    sp = next(x for x in r if x["source"] == "skinport")
    assert sp["premium_pct"] == pytest.approx(20.0, abs=0.1)  # 180/150


def test_compare_all_sem_preco_steam_nao_inventa_premio(_mercados):
    for x in markets.compare_all("AK"):
        assert x["premium_pct"] is None


def test_compare_all_fx_invalido_devolve_vazio(monkeypatch, _mercados):
    monkeypatch.setattr(markets, "usd_brl", lambda *a, **k: 0.0)
    assert markets.compare_all("AK") == []


def test_best_market_sem_nenhuma_cotacao(_mercados):
    assert markets.best_market("Nao Existe") is None


def test_compare_all_aceita_lista_de_fontes(_mercados):
    r = markets.compare_all("AK", sources=["skinport"])
    assert [x["source"] for x in r] == ["skinport"]


def test_compare_sem_preco_steam_e_seguro():
    r = markets.compare(None, 2.0, 5.0)
    assert r["steam_net"] is None and r["premium_pct"] is None


def test_compare_sem_preco_steam_ainda_da_o_lado_do_mercado():
    """Simetrico do teste acima, e o que faltava.

    Os dois lados sao independentes: a cotacao do Skinport nao precisa da
    Steam pra existir. Ate' 2026-07-30 a funcao desistia inteira sem o
    preco da Steam, e com o priceoverview em 429 o inventario mostrava
    "sem cotacao" em 30 das 31 posicoes que TINHAM cotacao em cache.
    """
    r = markets.compare(None, 2.0, 5.0, source="skinport")
    assert r["market_net"] is not None
    assert r["market_net"] == round(2.0 * 5.0 * (1 - 0.12), 2)
    # as comparativas seguem exigindo os dois lados
    assert r["premium_pct"] is None
    assert r["to_wallet_pct"] is None
    assert r["to_cash_pct"] is None


def test_compare_sem_nenhum_dos_dois():
    r = markets.compare(None, None, 5.0)
    assert r["steam_net"] is None and r["market_net"] is None


def test_compare_fx_invalido_nao_inventa_valor_de_mercado():
    """fx zero nao pode virar mercado gratis."""
    r = markets.compare(None, 2.0, 0)
    assert r["market_net"] is None


def test_compare_fx_invalido_nao_explode():
    r = markets.compare(10.0, 2.0, 0)
    assert r["steam_net"] == 8.5 and r["market_net"] is None
