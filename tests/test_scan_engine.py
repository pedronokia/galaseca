"""Testes do pipeline de coleta usado pelo worker do site."""
from __future__ import annotations

from galaseca import scan_engine


def _mock_steam_ok(monkeypatch, price_history=None):
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_overview",
        lambda name: {"lowest": 100.0, "median": 120.0, "volume": 500})
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_page_data",
        lambda name: {
            "order_book": {"spread": 5, "buy_count": 10, "sell_count": 20},
            "price_history": price_history or [],
            "order_book_approx": False,
            "meta": {},
        })
    monkeypatch.setattr(
        "galaseca.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {
            "label": "COMPRA", "diff_pct": -5,
            "spread_verdict": "tight", "book_verdict": "buyer_dominant",
            "trend_verdict": "rising",
        })
    monkeypatch.setattr("galaseca.signals.record_item_price",
                        lambda *a, **kw: None)
    monkeypatch.setattr("galaseca.signals.record_item_volume",
                        lambda *a, **kw: None)
    monkeypatch.setattr("galaseca.signals.record_item_supply",
                        lambda *a, **kw: None)


# ── scan_item ────────────────────────────────────────────────

def test_scan_item_sucesso(monkeypatch):
    _mock_steam_ok(monkeypatch)
    r = scan_engine.scan_item("AK-47 | Redline (Field-Tested)")
    assert r is not None
    assert r["name"] == "AK-47 | Redline (Field-Tested)"
    assert r["price"] == 100.0
    assert r["verdict"] == "COMPRA"
    assert r["verdict_ok"] is True
    assert r["derived_price"] is False
    assert isinstance(r["score"], int)
    assert isinstance(r["breakdown"], list)
    # texto traduzido, nao o codigo cru
    assert r["spread"] == "Pequena"
    assert r["book"] == "Mais compradores"
    assert r["trend"] == "Subindo"
    assert r["trend_code"] == "rising"


def test_scan_item_preserva_hash_do_icone(monkeypatch):
    _mock_steam_ok(monkeypatch)
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_page_data",
        lambda name: {
            "order_book": {"spread": 5, "buy_count": 10, "sell_count": 20},
            "price_history": [],
            "order_book_approx": False,
            "meta": {"icon_url": "skin-icon-hash"},
        },
    )

    resultado = scan_engine.scan_item("AK-47 | Redline (Field-Tested)")

    assert resultado["icon"] == "skin-icon-hash"


def test_scan_item_excecao_de_rede_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_overview",
        lambda name: (_ for _ in ()).throw(Exception("fail")))
    assert scan_engine.scan_item("X") is None


def test_scan_item_sem_overview_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_overview", lambda name: None)
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_page_data", lambda name: None)
    assert scan_engine.scan_item("X") is None


def test_scan_item_sem_preco_nenhum_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": None, "volume": None})
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_page_data",
        lambda name: {"order_book": None, "price_history": []})
    assert scan_engine.scan_item("X") is None


def test_scan_item_deriva_preco_do_historico(monkeypatch):
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": 50.0, "volume": None})
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_page_data",
        lambda name: {
            "order_book": None,
            "price_history": [{"time": 1, "price_median": 42.0}],
        })
    monkeypatch.setattr(
        "galaseca.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {"label": "—", "diff_pct": 0})
    monkeypatch.setattr("galaseca.signals.record_item_price",
                        lambda *a, **kw: None)
    r = scan_engine.scan_item("X")
    assert r is not None
    assert r["price"] == 42.0
    assert r["derived_price"] is True


def test_scan_item_grava_no_price_cache(monkeypatch):
    _mock_steam_ok(monkeypatch)

    class _FakeCache:
        def __init__(self):
            self.puts = []

        def put(self, name, price):
            self.puts.append((name, price))

    cache = _FakeCache()
    scan_engine.scan_item("X", price_cache=cache)
    assert cache.puts == [("X", 100.0)]


def test_scan_item_sem_price_cache_nao_quebra(monkeypatch):
    _mock_steam_ok(monkeypatch)
    assert scan_engine.scan_item("X", price_cache=None) is not None


def test_scan_item_usa_categoria_no_pump_risk(monkeypatch):
    """category e' passado pra pump_risk (exclusao de eventos da Valve)."""
    _mock_steam_ok(monkeypatch)
    recebido = {}

    def _fake_pump_risk(price_history=None, volume_history=None,
                        category=None):
        recebido["category"] = category
        return {"level": "low", "flags": 0, "reasons": []}

    monkeypatch.setattr("galaseca.signals.pump_risk", _fake_pump_risk)
    scan_engine.scan_item("X", category="Facas")
    assert recebido["category"] == "Facas"


# ── run_full_scan ────────────────────────────────────────────

def test_run_full_scan_chama_scan_item_por_categoria(monkeypatch):
    chamados = []

    def _fake_scan_item(name, category=None, price_cache=None):
        chamados.append((name, category))
        return {"name": name, "score": 50}

    monkeypatch.setattr(scan_engine, "scan_item", _fake_scan_item)
    categorias = {"Facas": ["A", "B"], "Luvas": ["C"]}
    resultados = scan_engine.run_full_scan(categorias)
    assert sorted(chamados) == [("A", "Facas"), ("B", "Facas"), ("C", "Luvas")]
    assert len(resultados) == 3


def test_run_full_scan_dedupe_item_em_duas_categorias(monkeypatch):
    chamados = []

    def _fake_scan_item(name, category=None, price_cache=None):
        chamados.append(name)
        return {"name": name, "score": 50}

    monkeypatch.setattr(scan_engine, "scan_item", _fake_scan_item)
    categorias = {"Facas": ["A"], "Luvas": ["A"]}
    scan_engine.run_full_scan(categorias)
    assert chamados == ["A"]


def test_run_full_scan_ignora_item_sem_resultado(monkeypatch):
    monkeypatch.setattr(scan_engine, "scan_item",
                        lambda name, category=None, price_cache=None: None)
    resultados = scan_engine.run_full_scan({"Facas": ["A", "B"]})
    assert resultados == []


def test_run_full_scan_chama_on_progress(monkeypatch):
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None: {"name": name,
                                                        "score": 1})
    progresso = []
    scan_engine.run_full_scan({"Facas": ["A", "B"]},
                              on_progress=progresso.append)
    assert progresso == ["[1/2] A", "[2/2] B"]


def test_run_full_scan_respeita_cancelled(monkeypatch):
    chamados = []

    def _fake_scan_item(name, category=None, price_cache=None):
        chamados.append(name)
        return {"name": name, "score": 1}

    monkeypatch.setattr(scan_engine, "scan_item", _fake_scan_item)
    # `cancelled()` e' checado tanto no laco de descoberta (1x, por
    # categoria) quanto no laco de itens (1x por item) -- a 1a chamada e'
    # a checagem da categoria "Facas", a 2a e' o item A, a 3a e' o item B.
    estado = {"n": 0}

    def _cancelled():
        estado["n"] += 1
        return estado["n"] > 2

    scan_engine.run_full_scan({"Facas": ["A", "B", "C"]},
                              cancelled=_cancelled)
    assert chamados == ["A"]


def test_run_full_scan_default_usa_scan_targets(monkeypatch):
    """Sem `categories`, usa scan_targets.SCAN_BY_CATEGORY (lista real)."""
    from galaseca import scan_targets

    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name))
    scan_engine.run_full_scan()
    esperados = {n for items in scan_targets.SCAN_BY_CATEGORY.values()
                for n in items}
    assert set(chamados) == esperados


def test_run_full_scan_categories_vazio_nao_chama_nada(monkeypatch):
    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name))
    scan_engine.run_full_scan({})
    assert chamados == []


def test_scan_item_nao_quebra_com_diff_pct_none(monkeypatch):
    """Achado ao vivo (2026-10-26): quando a mediana não vem (item sem
    histórico suficiente), `fair_value_verdict` devolve `diff_pct: None`
    de propósito (não ausente -- a CHAVE existe com valor None).
    `.get("diff_pct", 0)` sozinho não pega esse caso (o default só vale
    pra chave ausente) e `None <= 0` derrubava o scan inteiro do item
    com TypeError. Trava a correção de scan_engine.py:125."""
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_overview",
        lambda name: {"lowest": 100.0, "median": None, "volume": None})
    monkeypatch.setattr(
        "galaseca.steam_api.get_market_page_data",
        lambda name: {
            "order_book": None, "price_history": [],
            "order_book_approx": False, "meta": {},
        })
    monkeypatch.setattr(
        "galaseca.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {
            "label": "—", "diff_pct": None, "verdict": "unknown",
            "spread_verdict": None, "book_verdict": None,
            "trend_verdict": None,
        })
    monkeypatch.setattr("galaseca.signals.record_item_price",
                        lambda *a, **kw: None)
    monkeypatch.setattr("galaseca.signals.record_item_volume",
                        lambda *a, **kw: None)
    monkeypatch.setattr("galaseca.signals.record_item_supply",
                        lambda *a, **kw: None)

    resultado = scan_engine.scan_item("Item Sem Mediana")
    assert resultado is not None
    assert resultado["verdict_ok"] is True  # None tratado como 0 <= 0


def test_facas_e_luvas_usam_nome_de_mercado_com_estrela():
    # Sem o "★ " a listing page não existe: as 28 facas/luvas voltavam
    # vazias em todo ciclo e as categorias apareciam sem nenhum item.
    from galaseca import scan_targets

    for cat in ("Facas", "Luvas"):
        for nome in scan_targets.SCAN_BY_CATEGORY[cat]:
            assert nome.startswith("★ "), nome


def test_dragon_king_usa_nome_de_mercado_real():
    from galaseca import cases, scan_targets

    nome = "M4A4 | 龍王 (Dragon King) (Minimal Wear)"
    assert nome in scan_targets.SCAN_BY_CATEGORY["Rifles"]
    assert cases.case_status(nome)["case"] == "Chroma Case"


# ── disjuntor durante o ciclo (2026-11-13) ───────────────────

def _sleep_que_fecha_disjuntor(monkeypatch, dormidas):
    """time.sleep falso: registra e, se for uma espera de verdade (> 0),
    "passa o tempo" fechando o disjuntor."""
    from galaseca import steam_api

    def _sleep(s):
        dormidas.append(s)
        if s > 0:
            steam_api._rate_limit_state.clear()

    monkeypatch.setattr(scan_engine.time, "sleep", _sleep)


def test_run_full_scan_espera_disjuntor_em_vez_de_pular(monkeypatch):
    from galaseca import steam_api
    dormidas = []
    _sleep_que_fecha_disjuntor(monkeypatch, dormidas)
    chamados = []
    tentativas = {"B": 0}

    def _fake(name, category=None, price_cache=None):
        chamados.append(name)
        if name == "B" and tentativas["B"] == 0:
            tentativas["B"] += 1
            steam_api._registrar_rate_limit("market_listings")
            return None
        return {"name": name, "score": 50}

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    falhas = []
    progresso = []
    res = scan_engine.run_full_scan({"Facas": ["A", "B", "C"]},
                                    on_progress=progresso.append,
                                    falhas=falhas)
    # C não foi pulado; B voltou no fim, depois da pausa.
    assert chamados == ["A", "B", "C", "B"]
    assert sorted(r["name"] for r in res) == ["A", "B", "C"]
    assert falhas == []
    assert any(s >= 50 for s in dormidas)
    assert any("Steam pediu pausa" in m for m in progresso)
    assert "Repetindo depois da pausa: B" in progresso


def test_run_full_scan_item_que_falha_de_novo_vira_falha(monkeypatch):
    from galaseca import steam_api
    _sleep_que_fecha_disjuntor(monkeypatch, [])

    def _fake(name, category=None, price_cache=None):
        if name == "B":
            steam_api._registrar_rate_limit("priceoverview")
            return None
        return {"name": name, "score": 50}

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    falhas = []
    scan_engine.run_full_scan({"Facas": ["A", "B"]}, falhas=falhas)
    assert falhas == ["B"]


def test_run_full_scan_sem_resultado_sem_429_nao_repete(monkeypatch):
    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name) or None)
    falhas = []
    scan_engine.run_full_scan({"Facas": ["A", "B"]}, falhas=falhas)
    assert chamados == ["A", "B"]
    assert falhas == ["A", "B"]


def test_run_full_scan_bloqueio_longo_encerra_ciclo(monkeypatch):
    monkeypatch.setattr(scan_engine, "_cooldown_scan_s",
                        lambda: scan_engine._ESPERA_DISJUNTOR_MAX_S + 1)
    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name) or {"name": name, "score": 1})
    monkeypatch.setattr(scan_engine.time, "sleep",
                        lambda s: (_ for _ in ()).throw(
                            AssertionError("não devia dormir o bloqueio")))
    falhas = []
    progresso = []
    res = scan_engine.run_full_scan({"Facas": ["A", "B"]},
                                    on_progress=progresso.append,
                                    falhas=falhas)
    assert res == [] and chamados == []
    assert falhas == ["A", "B"]
    assert any("ciclo encerrado" in m for m in progresso)


def test_scan_item_marca_momento_da_coleta(monkeypatch):
    _mock_steam_ok(monkeypatch)
    r = scan_engine.scan_item("X")
    assert r is not None and r["coletado_em"] > 0
