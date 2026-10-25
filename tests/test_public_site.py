"""Testes do site público (Fase 1) -- servidor (Flask test client) + worker.

Sem rede: `server.py` só lê `scan_store`, nunca fala com a Steam. Os
testes de `worker.py` mockam `scan_engine.run_full_scan`.
"""
from __future__ import annotations

import pytest

from skinvault import ranking, scan_store
from skinvault.public_site import worker
from skinvault.public_site.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _salva_scan(tmp_path, monkeypatch, resultados, category="Facas"):
    # Captura a funcao ORIGINAL antes do monkeypatch -- referenciar
    # `scan_store.load_last_scan` de dentro do lambda, depois de
    # patcheado, chamaria o proprio lambda (auto-referencia infinita).
    original_load = scan_store.load_last_scan
    p = tmp_path / "scanner_last.json"
    scan_store.save_last_scan(category, resultados, path=p)
    monkeypatch.setattr(
        scan_store, "load_last_scan", lambda: original_load(path=p))


# ── server: / ────────────────────────────────────────────────

def test_index_sem_scan_mostra_vazio(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ainda não há nenhum scan".encode("utf-8") in resp.data


def test_index_com_scan_lista_candidato(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço baixo (+20)"}]},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Testada em Campo" in body  # localize_name traduziu
    assert "R$" in body
    assert "85" in body


def test_index_nunca_chama_rede(client, monkeypatch, tmp_path):
    """Garantia estrutural: nenhuma rota de server.py importa steam_api."""
    import skinvault.public_site.server as srv
    assert not hasattr(srv, "steam_api")


# ── server: /api/recommendations ────────────────────────────

def test_api_recommendations_sem_scan(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/api/recommendations")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidatos"] == []
    assert data["ultimo_scan"]["categoria"] is None


def test_api_recommendations_com_scan(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 90, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item Y", "score": 40, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "high"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados, category="Caixas")
    resp = client.get("/api/recommendations")
    data = resp.get_json()
    assert data["ultimo_scan"]["categoria"] == "Caixas"
    nomes = [c["name"] for c in data["candidatos"]]
    # Item Y tem pump_risk "high" -- filtrado por buy_candidates (default
    # max_pump_risk="medium")
    assert nomes == ["Item X"]


def test_api_recommendations_filtra_owned_vazio_sempre(client, monkeypatch,
                                                        tmp_path):
    """Site publico nao tem login: owned_names e' sempre vazio (ninguem
    'possui' nada), entao nenhum item e' descartado por posse."""
    resultados = [{"name": "Item Z", "score": 60, "price": 1.0,
                  "case_label": "", "pump_risk": {"level": "low"},
                  "breakdown": []}]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/api/recommendations")
    data = resp.get_json()
    assert [c["name"] for c in data["candidatos"]] == ["Item Z"]


# ── server: /healthz ─────────────────────────────────────────

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


# ── server: filtros/busca/ordenar/compacto ──────────────────

def test_index_busca_por_nome(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "AWP | Asiimov (Field-Tested)", "score": 70, "price": 100.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?q=redline")
    body = resp.data.decode("utf-8")
    assert "Redline" in body
    assert "Asiimov" not in body


def test_index_ordenar_por_preco(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caro", "score": 90, "price": 100.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Barato", "score": 50, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?ordenar=preco")
    body = resp.data.decode("utf-8")
    assert body.index("Barato") < body.index("Caro")


def test_index_nota_min_filtra(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Nota alta", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Nota baixa", "score": 30, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?nota_min=50")
    body = resp.data.decode("utf-8")
    assert "Nota alta" in body
    assert "Nota baixa" not in body


def test_index_preco_max_filtra(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caro", "score": 80, "price": 500.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Barato", "score": 50, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?preco_max=10")
    body = resp.data.decode("utf-8")
    assert "Barato" in body
    assert "Caro" not in body


def test_index_pagina_2(client, monkeypatch, tmp_path):
    resultados = [
        {"name": f"Item {i}", "score": 100 - i, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(25)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    pagina1 = client.get("/").data.decode("utf-8")
    pagina2 = client.get("/?pagina=2").data.decode("utf-8")
    assert "Item 0" in pagina1
    assert "Item 0" not in pagina2
    assert "Item 20" in pagina2


def test_index_descontinuada_ganha_selo(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caixa Velha", "score": 80, "price": 1.0,
         "case_label": "Alguma Caixa (descontinuada, 2018)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "selo-descontinuada" in body


def test_index_modo_compacto_aplica_classe(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [])
    body = client.get("/?compacto=1").data.decode("utf-8")
    assert "modo-compacto" in body


def test_index_mostra_contagem_por_categoria(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "A", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Facas"},
        {"name": "B", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Facas"},
        {"name": "C", "score": 60, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Luvas"},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "Facas (2)" in body
    assert "Luvas (1)" in body


def test_index_mostra_badge_proximo_scan(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "A", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "badge-cooldown" in body
    assert "Próxima atualização" in body


# ── server: robots/sitemap/404/cache ─────────────────────────

def test_robots_txt(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert b"Sitemap:" in resp.data
    assert b"Allow: /" in resp.data


def test_sitemap_xml(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/xml"
    assert b"<urlset" in resp.data
    assert b"/privacidade" in resp.data


def test_pagina_404_customizada(client):
    resp = client.get("/isso-nao-existe")
    assert resp.status_code == 404
    assert "não existe".encode("utf-8") in resp.data


def test_static_tem_cache_control(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "max-age" in resp.headers.get("Cache-Control", "")


# ── server: /status ──────────────────────────────────────────

def test_status_sem_historico(client, monkeypatch, tmp_path):
    from skinvault.public_site import uptime, visits
    monkeypatch.setattr(scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(uptime, "no_ar_desde", lambda: 0.0)
    monkeypatch.setattr(visits, "total", lambda: 0)
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "Ainda não há histórico".encode("utf-8") in resp.data


def test_status_mostra_ciclos_com_falha(client, monkeypatch, tmp_path):
    from skinvault.public_site import uptime, visits
    monkeypatch.setattr(scan_store, "load_historico_ciclos", lambda: [
        {"ts": 1000.0, "itens": 0, "duracao_min": 26.4, "sucesso": False},
        {"ts": 2000.0, "itens": 185, "duracao_min": 23.1, "sucesso": True},
    ])
    monkeypatch.setattr(uptime, "no_ar_desde", lambda: 0.0)
    monkeypatch.setattr(visits, "total", lambda: 7)
    resp = client.get("/status")
    body = resp.data.decode("utf-8")
    assert "Sem sucesso (bloqueado)" in body
    assert "Sucesso" in body


# ── server: /feed.xml ────────────────────────────────────────

def test_feed_sem_scan(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/feed.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/rss+xml"
    assert b"<rss" in resp.data


def test_feed_com_scan_lista_item(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/feed.xml")
    body = resp.data.decode("utf-8")
    assert "<item>" in body
    assert "nota 85" in body
    assert "steamcommunity.com/market/listings" in body


# ── worker ───────────────────────────────────────────────────

def test_categorias_padrao_exclui_adesivos():
    cats = worker.categorias_padrao()
    for pesada in worker._CATEGORIAS_PESADAS:
        assert pesada not in cats
    assert "Caixas" in cats


def test_run_once_grava_scan_store_e_ranking(monkeypatch, tmp_path):
    resultados = [{"name": "A", "score": 80}, {"name": "B", "score": 60}]
    original_save_scan = scan_store.save_last_scan
    original_save_snapshot = ranking.save_snapshot
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None: resultados)
    scan_path = tmp_path / "scanner_last.json"
    rank_path = tmp_path / "rankings.json"
    monkeypatch.setattr(
        worker.scan_store, "save_last_scan",
        lambda cat, res: original_save_scan(cat, res, path=scan_path))
    monkeypatch.setattr(
        worker.ranking, "save_snapshot",
        lambda res: original_save_snapshot(res, path=rank_path))

    out = worker.run_once({"Facas": ["A", "B"]})
    assert out == resultados
    saved = scan_store.load_last_scan(path=scan_path)
    assert saved["results"] == resultados
    snaps = ranking.load_snapshots(path=rank_path)
    assert len(snaps) == 1
    assert [it["name"] for it in snaps[0]["items"]] == ["A", "B"]


def test_run_once_sem_resultado_nao_grava_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None: [])
    chamado = {"save": False}

    def _boom(*a, **kw):
        chamado["save"] = True

    monkeypatch.setattr(worker.scan_store, "save_last_scan", _boom)
    monkeypatch.setattr(worker.ranking, "save_snapshot", _boom)
    out = worker.run_once({"Facas": ["A"]})
    assert out == []
    assert chamado["save"] is False


def test_run_once_default_usa_categorias_padrao(monkeypatch):
    recebido = {}

    def _fake(categories, on_progress=None):
        recebido["categories"] = categories
        return []

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    worker.run_once()
    for pesada in worker._CATEGORIAS_PESADAS:
        assert pesada not in recebido["categories"]


def _worker_main_uma_volta(monkeypatch):
    """Roda `main()` e para na 1a chamada de `time.sleep` (`while True`
    de verdade pararia a suite). Devolve os segundos passados pra sleep."""
    monkeypatch.setattr(worker, "run_once", lambda: [])
    chamadas = []

    def _fake_sleep(segundos):
        chamadas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    try:
        worker.main()
    except KeyboardInterrupt:
        pass
    return chamadas


def test_main_le_intervalo_do_env(monkeypatch):
    monkeypatch.setenv("SKINVAULT_WORKER_INTERVAL_HORAS", "2")
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [2 * 3600]


def test_main_sem_env_usa_default(monkeypatch):
    monkeypatch.delenv("SKINVAULT_WORKER_INTERVAL_HORAS", raising=False)
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [worker._INTERVALO_HORAS_DEFAULT * 3600]


def test_main_parametro_explicito_ignora_env(monkeypatch):
    monkeypatch.setenv("SKINVAULT_WORKER_INTERVAL_HORAS", "99")
    monkeypatch.setattr(worker, "run_once", lambda: [])
    chamadas = []

    def _fake_sleep(segundos):
        chamadas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    try:
        worker.main(intervalo_horas=1.0)
    except KeyboardInterrupt:
        pass
    assert chamadas == [3600]
