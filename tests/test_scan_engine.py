"""Testes de scan_engine.py (nucleo de scan sem Qt)."""
from __future__ import annotations

from skinvault import scan_engine


def _mock_steam_ok(monkeypatch, price_history=None):
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": 100.0, "median": 120.0, "volume": 500})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: {
            "order_book": {"spread": 5, "buy_count": 10, "sell_count": 20},
            "price_history": price_history or [],
            "order_book_approx": False,
            "meta": {},
        })
    monkeypatch.setattr(
        "skinvault.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {
            "label": "COMPRA", "diff_pct": -5,
            "spread_verdict": "tight", "book_verdict": "buyer_dominant",
            "trend_verdict": "rising",
        })
    monkeypatch.setattr("skinvault.signals.record_item_price",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_volume",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_supply",
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


def test_scan_item_excecao_de_rede_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: (_ for _ in ()).throw(Exception("fail")))
    assert scan_engine.scan_item("X") is None


def test_scan_item_sem_overview_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview", lambda name: None)
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data", lambda name: None)
    assert scan_engine.scan_item("X") is None


def test_scan_item_sem_preco_nenhum_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": None, "volume": None})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: {"order_book": None, "price_history": []})
    assert scan_engine.scan_item("X") is None


def test_scan_item_deriva_preco_do_historico(monkeypatch):
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": 50.0, "volume": None})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: {
            "order_book": None,
            "price_history": [{"time": 1, "price_median": 42.0}],
        })
    monkeypatch.setattr(
        "skinvault.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {"label": "—", "diff_pct": 0})
    monkeypatch.setattr("skinvault.signals.record_item_price",
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

    monkeypatch.setattr("skinvault.signals.pump_risk", _fake_pump_risk)
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
    from skinvault import scan_targets

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
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": 100.0, "median": None, "volume": None})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: {
            "order_book": None, "price_history": [],
            "order_book_approx": False, "meta": {},
        })
    monkeypatch.setattr(
        "skinvault.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {
            "label": "—", "diff_pct": None, "verdict": "unknown",
            "spread_verdict": None, "book_verdict": None,
            "trend_verdict": None,
        })
    monkeypatch.setattr("skinvault.signals.record_item_price",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_volume",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_supply",
                        lambda *a, **kw: None)

    resultado = scan_engine.scan_item("Item Sem Mediana")
    assert resultado is not None
    assert resultado["verdict_ok"] is True  # None tratado como 0 <= 0
