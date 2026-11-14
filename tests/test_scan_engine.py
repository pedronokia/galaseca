"""Testes do pipeline de coleta usado pelo worker do site."""
from __future__ import annotations

from lodout import scan_engine


def _mock_steam_ok(monkeypatch, price_history=None):
    monkeypatch.setattr(
        "lodout.steam_api.get_market_overview",
        lambda name: {"lowest": 100.0, "median": 120.0, "volume": 500})
    monkeypatch.setattr(
        "lodout.steam_api.get_market_page_data",
        lambda name: {
            "order_book": {"spread": 5, "buy_count": 10, "sell_count": 20},
            "price_history": price_history or [],
            "order_book_approx": False,
            "meta": {},
        })
    monkeypatch.setattr(
        "lodout.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {
            "label": "COMPRA", "diff_pct": -5,
            "spread_verdict": "tight", "book_verdict": "buyer_dominant",
            "trend_verdict": "rising",
        })
    monkeypatch.setattr("lodout.signals.record_item_price",
                        lambda *a, **kw: None)
    monkeypatch.setattr("lodout.signals.record_item_volume",
                        lambda *a, **kw: None)
    monkeypatch.setattr("lodout.signals.record_item_supply",
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
        "lodout.steam_api.get_market_page_data",
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
        "lodout.steam_api.get_market_overview",
        lambda name: (_ for _ in ()).throw(Exception("fail")))
    assert scan_engine.scan_item("X") is None


def test_scan_item_sem_overview_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "lodout.steam_api.get_market_overview", lambda name: None)
    monkeypatch.setattr(
        "lodout.steam_api.get_market_page_data", lambda name: None)
    assert scan_engine.scan_item("X") is None


def test_scan_item_sem_preco_nenhum_devolve_none(monkeypatch):
    monkeypatch.setattr(
        "lodout.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": None, "volume": None})
    monkeypatch.setattr(
        "lodout.steam_api.get_market_page_data",
        lambda name: {"order_book": None, "price_history": []})
    assert scan_engine.scan_item("X") is None


def test_scan_item_deriva_preco_do_historico(monkeypatch):
    monkeypatch.setattr(
        "lodout.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": 50.0, "volume": None})
    monkeypatch.setattr(
        "lodout.steam_api.get_market_page_data",
        lambda name: {
            "order_book": None,
            "price_history": [{"time": 1, "price_median": 42.0}],
        })
    monkeypatch.setattr(
        "lodout.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {"label": "—", "diff_pct": 0})
    monkeypatch.setattr("lodout.signals.record_item_price",
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

    monkeypatch.setattr("lodout.signals.pump_risk", _fake_pump_risk)
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
    from lodout import scan_targets

    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name) or {"name": name, "score": 1})
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
        "lodout.steam_api.get_market_overview",
        lambda name: {"lowest": 100.0, "median": None, "volume": None})
    monkeypatch.setattr(
        "lodout.steam_api.get_market_page_data",
        lambda name: {
            "order_book": None, "price_history": [],
            "order_book_approx": False, "meta": {},
        })
    monkeypatch.setattr(
        "lodout.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {
            "label": "—", "diff_pct": None, "verdict": "unknown",
            "spread_verdict": None, "book_verdict": None,
            "trend_verdict": None,
        })
    monkeypatch.setattr("lodout.signals.record_item_price",
                        lambda *a, **kw: None)
    monkeypatch.setattr("lodout.signals.record_item_volume",
                        lambda *a, **kw: None)
    monkeypatch.setattr("lodout.signals.record_item_supply",
                        lambda *a, **kw: None)

    resultado = scan_engine.scan_item("Item Sem Mediana")
    assert resultado is not None
    assert resultado["verdict_ok"] is True  # None tratado como 0 <= 0


def test_facas_e_luvas_usam_nome_de_mercado_com_estrela():
    # Sem o "★ " a listing page não existe: as 28 facas/luvas voltavam
    # vazias em todo ciclo e as categorias apareciam sem nenhum item.
    from lodout import scan_targets

    for cat in ("Facas", "Luvas"):
        for nome in scan_targets.SCAN_BY_CATEGORY[cat]:
            assert nome.startswith("★ "), nome


def test_dragon_king_usa_nome_de_mercado_real():
    from lodout import cases, scan_targets

    nome = "M4A4 | 龍王 (Dragon King) (Minimal Wear)"
    assert nome in scan_targets.SCAN_BY_CATEGORY["Rifles"]
    assert cases.case_status(nome)["case"] == "Chroma Case"


# ── disjuntor durante o ciclo (2026-11-13) ───────────────────

def _sleep_que_fecha_disjuntor(monkeypatch, dormidas):
    """time.sleep falso: registra e, se for a espera do disjuntor,
    "passa o tempo" fechando-o."""
    from lodout import steam_api

    def _sleep(s):
        dormidas.append(s)
        if s >= 30:  # espera do disjuntor (>= 1 min), não a pausa entre itens
            steam_api._rate_limit_state.clear()

    monkeypatch.setattr(scan_engine.time, "sleep", _sleep)


def test_run_full_scan_espera_disjuntor_em_vez_de_pular(monkeypatch):
    from lodout import steam_api
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
    from lodout import steam_api
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


def test_run_full_scan_relatorio_e_ritmo(monkeypatch):
    from lodout import steam_api
    monkeypatch.setattr(steam_api, "RATE_LIMIT_DELAY_S", 2.0)
    dormidas = []
    _sleep_que_fecha_disjuntor(monkeypatch, dormidas)

    def _fake(name, category=None, price_cache=None):
        if name == "Sem":
            return None
        if name == "Bloq":
            steam_api._registrar_rate_limit("priceoverview")
            return None
        return {"name": name, "score": 1,
                "_sombra": {"best_ask": 1000, "compras_24h": 10,
                            "lowest_overview": 10.0, "volume_overview": 10}}

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    rel = {}
    res = scan_engine.run_full_scan({"C": ["A", "Sem", "Bloq", "B"]},
                                    ritmo=1.5, relatorio=rel)
    assert all("_sombra" not in r for r in res)
    assert rel["sem_preco"] == ["Sem"]
    assert rel["pausas_429"] >= 1
    assert rel["comparacao_fontes"]["razao_preco"] == 0.01
    assert rel["comparacao_fontes"]["preco_concorda_pct"] == 100.0
    assert rel["comparacao_fontes"]["razao_volume"] == 1.0
    # Pausa entre itens multiplicada pelo ritmo.
    assert 3.0 in dormidas


def test_comparar_fontes_mede_discordancia():
    sombras = [
        {"best_ask": 100, "lowest_overview": 1.00},
        {"best_ask": 200, "lowest_overview": 2.00},
        {"best_ask": 300, "lowest_overview": 6.00},  # fora
        {"best_ask": None, "lowest_overview": 5.0},
    ]
    r = scan_engine.comparar_fontes(sombras)
    assert r["itens_preco"] == 3
    assert r["razao_preco"] == 0.01
    assert r["preco_concorda_pct"] == 66.7
    assert r["itens_volume"] == 0 and r["razao_volume"] is None
    assert scan_engine.comparar_fontes([]) is None


def test_fonte_pagina_soma_compras_das_ultimas_24h():
    page = {"price_history": [
        {"time": 1000, "price_median": 1, "purchases": 50},
        {"time": 100000, "price_median": 1, "purchases": 3},
        {"time": 103600, "price_median": 1, "purchases": 4},
    ]}
    f = scan_engine._fonte_pagina(page, {"best_ask": 123}, False)
    assert f == {"best_ask": 123, "compras_24h": 7, "mediana_24h": 1}
    assert scan_engine._fonte_pagina(page, {"best_ask": 1}, True) is None


# ── throttle silencioso e variantes ──────────────────────────

def _res(name, sem_hist=False):
    return {"name": name, "score": 1, "_sem_historico": sem_hist}


def test_tres_paginas_seguidas_sem_historico_viram_pausa(monkeypatch):
    from lodout import steam_api
    dormidas = []
    _sleep_que_fecha_disjuntor(monkeypatch, dormidas)
    tentativas = {}

    def _fake(name, category=None, price_cache=None):
        tentativas[name] = tentativas.get(name, 0) + 1
        # Primeira passada de B, C, D: throttle silencioso.
        return _res(name, sem_hist=name in "BCD" and tentativas[name] == 1)

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    rel = {}
    progresso = []
    res = scan_engine.run_full_scan(
        {"C": ["A", "B", "C", "D", "E"]}, relatorio=rel,
        on_progress=progresso.append,
        tinham_historico={"A", "B", "C", "D", "E"})
    assert rel["throttle_silencioso"] == 1
    assert tentativas == {"A": 1, "B": 2, "C": 2, "D": 2, "E": 1}
    assert sorted(r["name"] for r in res) == ["A", "B", "C", "D", "E"]
    assert all("_sem_historico" not in r for r in res)
    assert any("bloqueio silencioso" in m for m in progresso)
    assert any(s >= 30 for s in dormidas)


def test_sem_historico_isolado_e_genuino(monkeypatch):
    chamados = []

    def _fake(name, category=None, price_cache=None):
        chamados.append(name)
        return _res(name, sem_hist=name in ("B", "C"))

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    rel = {}
    res = scan_engine.run_full_scan({"C": ["A", "B", "C", "D"]},
                                    relatorio=rel,
                                    tinham_historico={"A", "B", "C", "D"})
    assert rel["throttle_silencioso"] == 0
    assert chamados == ["A", "B", "C", "D"]
    assert [r["name"] for r in res] == ["A", "B", "C", "D"]


def test_item_novo_sem_historico_nao_conta(monkeypatch):
    monkeypatch.setattr(scan_engine, "scan_item",
                        lambda name, category=None, price_cache=None:
                            _res(name, sem_hist=True))
    rel = {}
    res = scan_engine.run_full_scan({"C": ["N1", "N2", "N3", "N4"]},
                                    relatorio=rel, tinham_historico=set())
    assert rel["throttle_silencioso"] == 0 and len(res) == 4


def test_suspeitos_no_fim_da_lista_entram(monkeypatch):
    monkeypatch.setattr(scan_engine, "scan_item",
                        lambda name, category=None, price_cache=None:
                            _res(name, sem_hist=name != "A"))
    res = scan_engine.run_full_scan({"C": ["A", "B", "C"]},
                                    tinham_historico={"A", "B", "C"})
    assert [r["name"] for r in res] == ["A", "B", "C"]


def test_resumo_variantes_ordena_e_resume():
    page = {"variants": {
        "AK-47 | Redline (Field-Tested)": [{"time": 1, "price_median": 9}],
        "StatTrak™ AK-47 | Redline (Minimal Wear)": [
            {"time": 100000, "price_median": 80.0, "purchases": 2},
            {"time": 90000, "price_median": 70.0, "purchases": 5},
            {"time": 1000, "price_median": 50.0, "purchases": 99}],
        "AK-47 | Redline (Minimal Wear)": [
            {"time": 50, "price_median": 40.5, "purchases": 1}],
        "AK-47 | Redline (Battle-Scarred)": [{"time": 5, "price_median": None}],
    }}
    v = scan_engine._resumo_variantes("AK-47 | Redline (Field-Tested)", page)
    assert [x["name"] for x in v] == [
        "AK-47 | Redline (Minimal Wear)",
        "StatTrak™ AK-47 | Redline (Minimal Wear)"]
    assert v[1] == {"name": "StatTrak™ AK-47 | Redline (Minimal Wear)",
                    "mediana": 80.0, "ts": 100000, "compras_24h": 7}
    assert scan_engine._resumo_variantes("X", None) == []


def test_run_full_scan_pula_ja_coletados_e_avisa_resultado(monkeypatch):
    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name) or {"name": name, "score": 1,
                                      "_sombra": {"x": 1}})
    recebidos = []
    progresso = []
    scan_engine.run_full_scan({"C": ["A", "B", "C"]}, pular={"A"},
                              on_resultado=recebidos.append,
                              on_progress=progresso.append)
    assert chamados == ["B", "C"]
    assert [r["name"] for r in recebidos] == ["B", "C"]
    assert all("_sombra" not in r for r in recebidos)
    assert progresso == ["[1/2] B", "[2/2] C"]


def test_run_full_scan_aborta_quando_steam_fora(monkeypatch):
    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name) or None)
    nomes = [f"I{i}" for i in range(30)]
    rel, falhas, progresso = {}, [], []
    res = scan_engine.run_full_scan({"C": nomes}, relatorio=rel,
                                    falhas=falhas,
                                    on_progress=progresso.append)
    assert res == []
    assert chamados == nomes[:scan_engine._ABORTA_SEM_NADA]
    assert rel["abortado"] is True
    assert falhas == nomes
    assert any("Steam fora do ar" in m for m in progresso)


def test_run_full_scan_falhas_depois_de_um_sucesso_nao_abortam(monkeypatch):
    chamados = []

    def _fake(name, category=None, price_cache=None):
        chamados.append(name)
        return {"name": name, "score": 1} if name == "I0" else None

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    nomes = [f"I{i}" for i in range(15)]
    rel = {}
    scan_engine.run_full_scan({"C": nomes}, relatorio=rel)
    assert chamados == nomes
    assert rel["abortado"] is False


def test_run_full_scan_prioridade_ordena_entre_categorias(monkeypatch):
    chamados = []
    monkeypatch.setattr(
        scan_engine, "scan_item",
        lambda name, category=None, price_cache=None:
            chamados.append(name) or {"name": name, "score": 1})
    scan_engine.run_full_scan(
        {"A": ["a1", "a2"], "B": ["b1", "b2"]},
        prioridade={"b2": -90, "a2": -80, "b1": -10})
    assert chamados == ["b2", "a2", "b1", "a1"]


# ── modo 1 requisição por item (fonte="pagina") ──────────────

def _pagina(approx=False, ask=12345):
    return {
        "order_book": {"best_ask": ask},
        "order_book_approx": approx,
        "price_history": [
            {"time": 1000, "price_median": 999.0, "purchases": 50},  # >24h
            {"time": 100000, "price_median": 120.0, "purchases": 1},
            {"time": 100500, "price_median": 100.0, "purchases": 5},
            {"time": 101000, "price_median": 110.0, "purchases": 2},
        ],
    }


def test_overview_da_pagina_converte_e_resume_24h():
    o = scan_engine._overview_da_pagina(_pagina(), 0.01)
    assert o == {"lowest": 123.45, "median": 100.0, "volume": 8}
    assert scan_engine._overview_da_pagina(_pagina(approx=True), 0.01) is None
    assert scan_engine._overview_da_pagina(_pagina(ask=None), 0.01) is None
    assert scan_engine._overview_da_pagina(None, 0.01) is None


def test_scan_item_modo_pagina_faz_uma_requisicao(monkeypatch):
    _mock_steam_ok(monkeypatch)
    chamadas = []
    monkeypatch.setattr("lodout.steam_api.get_market_overview",
                        lambda name: chamadas.append("overview") or None)
    monkeypatch.setattr("lodout.steam_api.get_market_page_data",
                        lambda name: chamadas.append("pagina") or _pagina())
    r = scan_engine.scan_item("X", fonte="pagina", fator_preco=0.01)
    assert chamadas == ["pagina"]
    assert r["price"] == 123.45 and r["volume"] == 8


def test_scan_item_modo_pagina_book_aproximado_usa_overview(monkeypatch):
    _mock_steam_ok(monkeypatch)
    chamadas = []
    monkeypatch.setattr(
        "lodout.steam_api.get_market_overview",
        lambda name: chamadas.append("overview") or {
            "lowest": 50.0, "median": 55.0, "volume": 3})
    monkeypatch.setattr(
        "lodout.steam_api.get_market_page_data",
        lambda name: chamadas.append("pagina") or _pagina(approx=True))
    r = scan_engine.scan_item("X", fonte="pagina", fator_preco=0.01)
    assert chamadas == ["pagina", "overview"]
    assert r["price"] == 50.0


def test_run_full_scan_repassa_fonte_so_quando_pagina(monkeypatch):
    recebidos = []

    def _fake(name, category=None, price_cache=None, **kw):
        recebidos.append(kw)
        return {"name": name, "score": 1}

    monkeypatch.setattr(scan_engine, "scan_item", _fake)
    scan_engine.run_full_scan({"C": ["A"]})
    scan_engine.run_full_scan({"C": ["B"]}, fonte="pagina", fator_preco=0.01)
    assert recebidos == [{}, {"fonte": "pagina", "fator_preco": 0.01}]


def test_comparar_fontes_mede_mediana():
    sombras = [
        {"median_overview": 100.0, "mediana_24h": 101.0},
        {"median_overview": 50.0, "mediana_24h": 50.0},
        {"median_overview": 10.0, "mediana_24h": 20.0},  # fora
    ]
    r = scan_engine.comparar_fontes(sombras)
    assert r["itens_mediana"] == 3
    assert r["razao_mediana"] == 1.01
    assert r["mediana_concorda_pct"] == 66.7


def test_fonte_pagina_inclui_mediana_24h():
    f = scan_engine._fonte_pagina(_pagina(), {"best_ask": 1}, False)
    assert f["mediana_24h"] == 100.0


def test_comparar_fontes_separa_mediana_por_liquidez():
    sombras = [
        {"name": "Liquido", "median_overview": 10.0, "mediana_24h": 10.1,
         "volume_overview": 500},
        {"name": "Medio", "median_overview": 10.0, "mediana_24h": 10.0,
         "volume_overview": 40},
        {"name": "Parado", "median_overview": 10.0, "mediana_24h": 14.0,
         "volume_overview": 2},
        {"name": "Parado2", "median_overview": 10.0, "mediana_24h": 10.0,
         "volume_overview": 3},
    ]
    r = scan_engine.comparar_fontes(sombras)
    faixas = r["mediana_por_liquidez"]
    assert faixas["alta"] == {"itens": 1, "concorda_pct": 100.0}
    assert faixas["media"] == {"itens": 1, "concorda_pct": 100.0}
    assert faixas["baixa"] == {"itens": 2, "concorda_pct": 50.0}
    assert r["mediana_divergentes"] == [
        {"name": "Parado", "vendas_24h": 2, "razao": 1.386}]


def test_comparar_tendencia_conta_mudancas_e_efeito_na_nota():
    sombras = [
        {"name": "A", "trend_antigo": "rising", "trend_7d": "falling"},
        {"name": "B", "trend_antigo": "rising", "trend_7d": "rising"},
        {"name": "C", "trend_antigo": "stable", "trend_7d": "rising"},
        {"name": "D", "trend_antigo": "falling", "trend_7d": None},
    ]
    r = scan_engine.comparar_tendencia(sombras)
    assert r["itens"] == 3 and r["mudariam"] == 2
    assert r["transicoes"] == {"rising->falling": 1, "stable->rising": 1}
    assert r["maiores"][0] == {"name": "A", "de": "rising", "para": "falling",
                               "nota_delta": -25}
    assert scan_engine.comparar_tendencia([]) is None
