"""Testes da tela de Watchlist (web) -- Fase 8.

`watchlist.py`/`alerts.py` usam `path=_DEFAULT_PATH` como default de
PARAMETRO (congelado na definicao da funcao -- AGENTS.md #13, mesma
armadilha de test_webapp_history.py). Reseta-se chamando as proprias
funcoes de save sem `path=`, nunca via monkeypatch no atributo do
modulo.
"""
from __future__ import annotations

import pytest

from skinvault import alerts as alerts_mod
from skinvault import watchlist as watchlist_mod
from skinvault.prices import PriceCache
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    watchlist_mod.save_watchlist([])
    alerts_mod.clear_alerts_log()
    return app.test_client()


def test_pagina_watchlist_responde(client):
    resp = client.get("/watchlist")
    assert resp.status_code == 200


def test_lista_vazia(client):
    resp = client.get("/api/watchlist")
    assert resp.get_json()["items"] == []


def test_adiciona_item(client):
    resp = client.post("/api/watchlist", json={
        "name": "AK-47 | Redline (Field-Tested)", "target": 100,
    })
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["index"] == 0
    assert items[0]["target"] == 100.0
    assert items[0]["muted"] is False
    assert items[0]["triggered"] is False


def test_adiciona_rejeita_nome_vazio(client):
    resp = client.post("/api/watchlist", json={"name": "  "})
    assert resp.status_code == 400


def test_adiciona_rejeita_target_negativo(client):
    resp = client.post("/api/watchlist", json={"name": "X", "target": -5})
    assert resp.status_code == 400


def test_remove_item(client):
    watchlist_mod.add_watch("Item A", 10)
    watchlist_mod.add_watch("Item B", 20)
    resp = client.delete("/api/watchlist/0")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Item B"


def test_remove_item_inexistente(client):
    resp = client.delete("/api/watchlist/9")
    assert resp.status_code == 404


def test_update_rules(client):
    watchlist_mod.add_watch("Item A", 0)
    resp = client.patch("/api/watchlist/0/rules", json={
        "price_below": 50, "price_drop_pct": 10, "baseline_price": 80,
    })
    assert resp.status_code == 200
    item = resp.get_json()["items"][0]
    assert item["rules"]["price_below"] == 50.0
    assert item["rules"]["price_drop_pct"] == 10.0
    assert item["baseline_price"] == 80.0
    assert "nenhuma regra" not in item["rules_summary"]


def test_update_rules_item_inexistente(client):
    resp = client.patch("/api/watchlist/9/rules", json={"price_below": 1})
    assert resp.status_code == 404


def test_update_rules_rejeita_valor_negativo(client):
    watchlist_mod.add_watch("Item A", 0)
    resp = client.patch("/api/watchlist/0/rules", json={"price_below": -1})
    assert resp.status_code == 400


def test_mute_e_desmute(client):
    watchlist_mod.add_watch("Item A", 0)
    resp = client.post("/api/watchlist/0/mute", json={"hours": 24})
    assert resp.get_json()["items"][0]["muted"] is True

    resp = client.post("/api/watchlist/0/mute", json={"hours": None})
    assert resp.get_json()["items"][0]["muted"] is False


def test_check_dispara_alerta_price_below(client):
    watchlist_mod.add_watch("Item Barato", 0)
    items = watchlist_mod.load_watchlist()
    items[0]["rules"] = {"price_below": 20}
    watchlist_mod.save_watchlist(items)

    # A rota le' preco de PriceCache() no path DEFAULT (mesmo truque de
    # path=_DEFAULT_PATH congelado -- grava no MESMO arquivo que ela le').
    PriceCache().put("Item Barato", 10.0)

    resp = client.post("/api/watchlist/check")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["fired"]) == 1
    assert data["fired"][0]["rule"] == "price_below"
    assert data["items"][0]["triggered"] is True

    log_resp = client.get("/api/watchlist/log")
    assert len(log_resp.get_json()["entries"]) == 1


def test_check_nao_dispara_de_novo_item_silenciado(client):
    default_cache = PriceCache()
    default_cache.put("Item Mudo", 10.0)
    watchlist_mod.add_watch("Item Mudo", 0)
    items = watchlist_mod.load_watchlist()
    items[0]["rules"] = {"price_below": 20}
    watchlist_mod.save_watchlist(items)
    watchlist_mod.set_muted("Item Mudo", 24)

    resp = client.post("/api/watchlist/check")
    assert resp.get_json()["fired"] == []


def test_log_vazio(client):
    resp = client.get("/api/watchlist/log")
    assert resp.get_json()["entries"] == []
