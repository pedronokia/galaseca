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
