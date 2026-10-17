"""Testes da calculadora de trade-up (skinvault/tradeup.py)."""
from __future__ import annotations

import json

import pytest

from skinvault import tradeup


# ── dataset sintetico no formato ByMykel/CSGO-API ────────────
def _skin(name, rarity, col=None, mn=0.0, mx=1.0, st=True, cat="rifles"):
    return {
        "name": name,
        "rarity": {"id": rarity},
        "collections": [{"name": col}] if col else [],
        "min_float": mn, "max_float": mx, "stattrak": st,
        "category": {"id": cat},
    }


SKINS = [
    # Colecao A (de caixa): 2 Mil-Spec, 2 Restricted, 1 Covert
    _skin("AK-47 | Alfa", "rarity_rare_weapon", "Col A"),
    _skin("M4A4 | Alfa", "rarity_rare_weapon", "Col A"),
    _skin("AWP | Restrito A1", "rarity_mythical_weapon", "Col A", 0.0, 0.5),
    _skin("P90 | Restrito A2", "rarity_mythical_weapon", "Col A", 0.1, 0.7),
    _skin("M4A1-S | Covert A", "rarity_ancient_weapon", "Col A"),
    # Colecao B (de caixa de luvas): 1 Mil-Spec, 1 Restricted, 1 Covert
    _skin("Glock-18 | Beta", "rarity_rare_weapon", "Col B"),
    _skin("USP-S | Restrito B", "rarity_mythical_weapon", "Col B"),
    _skin("AK-47 | Covert B", "rarity_ancient_weapon", "Col B"),
    # Colecao de mapa (sem caixa)
    _skin("MP9 | Mapa", "rarity_ancient_weapon", "Col Mapa"),
    # Facas (duas fases de Doppler = 1 nome de mercado) e luva
    _skin("★ Karambit | Doppler", "rarity_ancient_weapon", None, 0.0, 0.08,
          cat="sfui_invpanel_filter_melee"),
    _skin("★ Karambit | Doppler", "rarity_ancient_weapon", None, 0.0, 0.08,
          cat="sfui_invpanel_filter_melee"),
    _skin("★ Karambit | Fade", "rarity_ancient_weapon", None, 0.0, 0.08,
          cat="sfui_invpanel_filter_melee"),
    _skin("★ Karambit", "rarity_ancient_weapon", None,
          cat="sfui_invpanel_filter_melee"),
    _skin("★ Sport Gloves | Vice", "rarity_ancient", None, 0.06, 0.8,
          st=False, cat="sfui_invpanel_filter_gloves"),
]

CRATES = [
    {"name": "Caixa A",
     "contains": [{"name": "AK-47 | Alfa"}, {"name": "M4A1-S | Covert A"}],
     "contains_rare": [{"name": "★ Karambit | Doppler"},
                       {"name": "★ Karambit | Doppler"},
                       {"name": "★ Karambit | Fade"},
                       {"name": "★ Karambit"}]},
    {"name": "Caixa B",
     "contains": [{"name": "Glock-18 | Beta"}],
     "contains_rare": [{"name": "★ Sport Gloves | Vice"}]},
    {"name": "Capsula", "contains": [{"name": "AK-47 | Alfa"}]},
]


@pytest.fixture
def cat():
    return tradeup.build_catalog(SKINS, CRATES, now=1000.0)


def _n(name, k, **extra):
    return [dict({"name": name}, **extra) for _ in range(k)]


# ── nomes ────────────────────────────────────────────────────
@pytest.mark.parametrize("name,base,wear,st,sv", [
    ("AK-47 | Redline (Field-Tested)", "AK-47 | Redline", "Field-Tested",
     False, False),
    ("StatTrak™ AK-47 | Redline (Minimal Wear)", "AK-47 | Redline",
     "Minimal Wear", True, False),
    ("Souvenir AWP | Dragon Lore (Factory New)", "AWP | Dragon Lore",
     "Factory New", False, True),
    ("★ StatTrak™ Karambit | Fade (Factory New)", "★ Karambit | Fade",
     "Factory New", True, False),
    ("★ Karambit", "★ Karambit", None, False, False),
])
def test_parse_market_name(name, base, wear, st, sv):
    p = tradeup.parse_market_name(name)
    assert (p["base"], p["wear"], p["stattrak"], p["souvenir"]) == (
        base, wear, st, sv)


def test_market_name_roundtrip():
    assert tradeup.market_name("★ Karambit | Fade", "Factory New", True) == \
        "★ StatTrak™ Karambit | Fade (Factory New)"
    assert tradeup.market_name("AK-47 | Alfa", "Well-Worn", True) == \
        "StatTrak™ AK-47 | Alfa (Well-Worn)"
    # faca vanilla nao tem wear no nome de mercado
    assert tradeup.market_name("★ Karambit", "Factory New", True) == \
        "★ StatTrak™ Karambit"


@pytest.mark.parametrize("f,wear", [
    (0.0, "Factory New"), (0.0699, "Factory New"), (0.07, "Minimal Wear"),
    (0.15, "Field-Tested"), (0.3799, "Field-Tested"), (0.38, "Well-Worn"),
    (0.45, "Battle-Scarred"), (1.0, "Battle-Scarred"),
])
def test_wear_for_float(f, wear):
    assert tradeup.wear_for_float(f) == wear


def test_default_float_recorta_pelo_range_do_skin():
    redline = {"min": 0.10, "max": 0.70}
    assert tradeup.default_float(redline, "Factory New") is None
    assert tradeup.default_float(redline, "Minimal Wear") == pytest.approx(0.125)
    assert tradeup.default_float(redline, "Field-Tested") == pytest.approx(0.265)


# ── catalogo ─────────────────────────────────────────────────
def test_build_catalog_tiers_e_pools(cat):
    a = cat["collections"]["Col A"]
    assert a["tiers"]["rare"] == ["AK-47 | Alfa", "M4A4 | Alfa"]
    assert a["tiers"]["mythical"] == ["AWP | Restrito A1", "P90 | Restrito A2"]
    # fases de Doppler colapsam num nome so'
    assert a["rare"] == ["★ Karambit", "★ Karambit | Doppler",
                         "★ Karambit | Fade"]
    assert a["rare_st"] == a["rare"]
    b = cat["collections"]["Col B"]
    assert b["rare"] == ["★ Sport Gloves | Vice"]
    assert b["rare_st"] == []  # luva nao tem StatTrak
    assert cat["collections"]["Col Mapa"]["rare"] == []
    assert cat["skins"]["★ Sport Gloves | Vice"]["glove"] is True
    assert cat["ts"] == 1000.0


def test_input_suggestions_respeita_range_e_stattrak(cat):
    sug = tradeup.input_suggestions(cat)
    assert "AWP | Restrito A1 (Factory New)" in sug
    assert "P90 | Restrito A2 (Factory New)" not in sug  # range comeca em 0.1
    assert "StatTrak™ AK-47 | Alfa (Field-Tested)" in sug
    assert not any(s.startswith("★") for s in sug)  # faca nao e' input


def test_catalog_persistencia_e_refresh(tmp_path, cat, monkeypatch):
    p = tmp_path / "tradeup_catalog.json"
    tradeup.save_catalog(cat, p)
    assert tradeup.load_catalog(p)["collections"].keys() == cat["collections"].keys()

    chamadas = []
    monkeypatch.setattr(tradeup, "fetch_catalog",
                        lambda: chamadas.append(1) or None)
    # fresco: nao bate na rede
    st, c = tradeup.refresh_catalog(p, now=1000.0 + 60)
    assert st == tradeup.CATALOG_CACHED and c and not chamadas
    # expirado + rede falhou: usa o velho
    st, c = tradeup.refresh_catalog(p, now=1000.0 + tradeup.CATALOG_TTL_S + 1)
    assert st == tradeup.CATALOG_STALE and c and chamadas
    # sem nada em disco e sem rede
    st, c = tradeup.refresh_catalog(tmp_path / "nada.json")
    assert (st, c) == (tradeup.CATALOG_UNAVAILABLE, None)


def test_load_catalog_ilegivel_vira_none(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{nao e json", encoding="utf-8")
    assert tradeup.load_catalog(p) is None
    p.write_text(json.dumps({"version": 999, "skins": {}, "collections": {}}),
                 encoding="utf-8")
    assert tradeup.load_catalog(p) is None


def test_fetch_catalog_via_http_get(monkeypatch):
    respostas = {tradeup._SKINS_URL: json.dumps(SKINS),
                 tradeup._CRATES_URL: json.dumps(CRATES)}
    monkeypatch.setattr(tradeup, "_http_get",
                        lambda url: (200, respostas[url]))
    cat = tradeup.fetch_catalog()
    assert "Col A" in cat["collections"]

    monkeypatch.setattr(tradeup, "_http_get", lambda url: (429, None))
    assert tradeup.fetch_catalog() is None


# ── plano ────────────────────────────────────────────────────
def test_contrato_normal_probabilidade_por_colecao(cat):
    inputs = (_n("AK-47 | Alfa (Field-Tested)", 7)
              + _n("Glock-18 | Beta (Field-Tested)", 3))
    plan = tradeup.plan_contract(inputs, cat)
    assert plan["errors"] == [] and plan["mode"] == tradeup.MODE_STANDARD
    probs = {o["base"]: o["prob"] for o in plan["outcomes"]}
    # Col A: 7/10 dividido entre 2 Restricted; Col B: 3/10 num so'
    assert probs == pytest.approx({"AWP | Restrito A1": 0.35,
                                   "P90 | Restrito A2": 0.35,
                                   "USP-S | Restrito B": 0.30})
    assert sum(probs.values()) == pytest.approx(1.0)


def test_float_de_saida_normalizado_pelo_range(cat):
    inputs = _n("AK-47 | Alfa (Field-Tested)", 10, float=0.20)
    plan = tradeup.plan_contract(inputs, cat)
    out = {o["base"]: o for o in plan["outcomes"]}
    # input range 0-1 -> norm 0.20; AWP 0-0.5 -> 0.10 (MW); P90 0.1-0.7 -> 0.22
    assert out["AWP | Restrito A1"]["float"] == pytest.approx(0.10)
    assert out["AWP | Restrito A1"]["name"] == "AWP | Restrito A1 (Minimal Wear)"
    assert out["P90 | Restrito A2"]["float"] == pytest.approx(0.22)
    assert out["P90 | Restrito A2"]["wear"] == "Field-Tested"
    assert not plan["warnings"]  # float informado: nada assumido


def test_contrato_faca(cat):
    plan = tradeup.plan_contract(_n("M4A1-S | Covert A (Field-Tested)", 5),
                                 cat)
    assert plan["mode"] == tradeup.MODE_RARE and not plan["errors"]
    nomes = sorted(o["name"] for o in plan["outcomes"])
    assert nomes == ["★ Karambit", "★ Karambit | Doppler (Factory New)",
                     "★ Karambit | Fade (Factory New)"]
    assert all(o["prob"] == pytest.approx(1 / 3) for o in plan["outcomes"])


def test_contrato_faca_stattrak_e_luva_sem_stattrak(cat):
    plan = tradeup.plan_contract(
        _n("StatTrak™ M4A1-S | Covert A (Minimal Wear)", 5), cat)
    assert "★ StatTrak™ Karambit | Fade (Factory New)" in {
        o["name"] for o in plan["outcomes"]}

    plan = tradeup.plan_contract(
        _n("StatTrak™ AK-47 | Covert B (Minimal Wear)", 5), cat)
    assert plan["errors"] and "StatTrak" in plan["errors"][0]
    plan = tradeup.plan_contract(_n("AK-47 | Covert B (Minimal Wear)", 5), cat)
    assert [o["name"] for o in plan["outcomes"]] == [
        "★ Sport Gloves | Vice (Minimal Wear)"]  # norm .11 -> .06+.11*.74=.141


@pytest.mark.parametrize("inputs,trecho", [
    ([], "Adicione"),
    (_n("AK-47 | Alfa (Field-Tested)", 9), "10 itens"),
    (_n("M4A1-S | Covert A (Field-Tested)", 10), "5 Covert"),
    (_n("AK-47 | Alfa (Field-Tested)", 9)
     + _n("AWP | Restrito A1 (Factory New)", 1), "mesma raridade"),
    (_n("AK-47 | Alfa (Field-Tested)", 9)
     + _n("StatTrak™ M4A4 | Alfa (Field-Tested)", 1), "tudo-ou-nada"),
    (_n("MP9 | Mapa (Field-Tested)", 5), "sem faca/luva"),
    (_n("★ Karambit | Fade (Factory New)", 5), "colecao"),
    (_n("Nao Existe | X (Field-Tested)", 10), "catalogo"),
    (_n("AK-47 | Alfa", 10), "wear"),
    (_n("AK-47 | Alfa (Field-Tested)", 10, float=0.5), "nao corresponde"),
    (_n("AWP | Restrito A1 (Battle-Scarred)", 10, float=0.9), "fora do range"),
])
def test_contratos_invalidos(cat, inputs, trecho):
    plan = tradeup.plan_contract(inputs, cat)
    assert plan["errors"] and trecho in plan["errors"][0]
    assert plan["outcomes"] == []


def test_souvenir_mistura_e_avisa(cat):
    inputs = (_n("Souvenir AK-47 | Alfa (Field-Tested)", 5)
              + _n("AK-47 | Alfa (Field-Tested)", 5))
    plan = tradeup.plan_contract(inputs, cat)
    assert not plan["errors"]
    assert any("Souvenir" in w for w in plan["warnings"])
    assert all(not o["name"].startswith("Souvenir") for o in plan["outcomes"])


# ── EV ───────────────────────────────────────────────────────
def test_evaluate_ev_liquido_da_taxa_steam(cat):
    plan = tradeup.plan_contract(
        _n("AK-47 | Alfa (Field-Tested)", 10, float=0.20, cost=1.0), cat)
    precos = {"AWP | Restrito A1 (Minimal Wear)": 23.0,
              "P90 | Restrito A2 (Field-Tested)": 5.75}
    res = tradeup.evaluate(plan, precos.get)
    assert res["cost"] == pytest.approx(10.0)
    # liquido = preco / 1.15 -> 20 e 5; EV = .5*20 + .5*5
    assert res["ev_net"] == pytest.approx(12.5)
    assert res["profit"] == pytest.approx(2.5)
    assert res["roi"] == pytest.approx(0.25)
    assert res["prob_profit"] == pytest.approx(0.5)
    assert res["coverage"] == pytest.approx(1.0)
    assert res["outcomes"][0]["name"] == "AWP | Restrito A1 (Minimal Wear)"


def test_evaluate_preco_parcial_e_input_sem_preco(cat):
    plan = tradeup.plan_contract(
        _n("AK-47 | Alfa (Field-Tested)", 10, float=0.20, cost=1.0), cat)
    res = tradeup.evaluate(
        plan, {"AWP | Restrito A1 (Minimal Wear)": 23.0}.get)
    assert res["coverage"] == pytest.approx(0.5)
    assert res["ev_net"] == pytest.approx(10.0)
    assert any("parcial" in w for w in res["warnings"])

    plan = tradeup.plan_contract(
        _n("AK-47 | Alfa (Field-Tested)", 10, float=0.20), cat)
    res = tradeup.evaluate(plan, lambda n: None)
    assert res["ev_net"] is None and res["missing_inputs"] == 10


def test_evaluate_repassa_erro_do_plano(cat):
    res = tradeup.evaluate(tradeup.plan_contract([], cat), lambda n: 1.0)
    assert res["errors"] and res["ev_net"] is None


def test_price_names_agrupa_e_deduplica(cat):
    plan = tradeup.plan_contract(
        _n("AK-47 | Alfa (Field-Tested)", 10, float=0.20), cat)
    nomes = tradeup.price_names(plan)
    assert nomes.count("AK-47 | Alfa (Field-Tested)") == 1
    assert len(nomes) == 3


# ── preco de referencia / SSR ────────────────────────────────
def test_reference_price_mediana_7_dias():
    dia = 86400
    ph = [{"time": i * dia, "price_median": float(i), "purchases": 1}
          for i in range(1, 21)]
    # ultimos 7 dias: 14..20 -> mediana 17
    assert tradeup.reference_price(ph) == pytest.approx(17.0)
    assert tradeup.reference_price([]) is None


class _FakeCache:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, name):
        return self.data.get(name)

    def has(self, name):
        return name in self.data

    def put_many(self, mapping):
        self.data.update(mapping)
        return len(mapping)


def _ph(preco):
    return [{"time": 86400, "price_median": preco, "purchases": 3}]


def test_ssr_pricer_semeia_variantes_e_so_usa_nome_exato(monkeypatch):
    from skinvault import steam_api
    chamadas = []

    def fake_page(name):
        chamadas.append(name)
        return {"variants": {"X | Y (Field-Tested)": _ph(10.0),
                             "X | Y (Minimal Wear)": _ph(20.0)},
                # substring fallback de outra variante: nao pode ser usado
                "price_history": _ph(999.0)}

    monkeypatch.setattr(steam_api, "get_market_page_data", fake_page)
    sono = []
    pricer = tradeup.SsrPricer(cache=_FakeCache(), sleep=sono.append)
    assert pricer.pending(["X | Y (Field-Tested)", "X | Y (Minimal Wear)"]) == 1
    assert pricer("X | Y (Field-Tested)") == pytest.approx(10.0)
    assert pricer("X | Y (Minimal Wear)") == pytest.approx(20.0)  # cache hit
    assert pricer("X | Y (Factory New)") is None  # pagina veio, wear nao
    assert len(chamadas) == 2 and len(sono) == 1
    assert not pricer.blocked


def test_ssr_pricer_para_apos_falhas_seguidas(monkeypatch):
    from skinvault import steam_api
    chamadas = []
    monkeypatch.setattr(steam_api, "get_market_page_data",
                        lambda n: chamadas.append(n) or None)
    pricer = tradeup.SsrPricer(cache=_FakeCache(), sleep=lambda s: None)
    for i in range(6):
        assert pricer(f"Item {i} | Z (Field-Tested)") is None
    assert pricer.blocked and len(chamadas) == tradeup.SsrPricer.MAX_FALHAS
