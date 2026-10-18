"""Testes da tela de Trades (web) -- Fase 4. CRUD puro, sem rede."""
from __future__ import annotations

import pytest

from skinvault import trades as trades_mod
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    trades_mod.save_trades([])
    return app.test_client()


def test_pagina_trades_responde(client):
    resp = client.get("/trades")
    assert resp.status_code == 200
    assert b"Trades" in resp.data


def test_lista_vazia(client):
    resp = client.get("/api/trades")
    data = resp.get_json()
    assert data["trades"] == []
    assert data["stats"]["total"] == 0


def test_adiciona_trade(client):
    resp = client.post("/api/trades", json={
        "name": "AK-47 | Redline", "buy_cost": 100, "sell_price": 150,
        "quantity": 2, "notes": "lote de teste",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["trades"]) == 1
    t = data["trades"][0]
    assert t["index"] == 0
    assert t["quantity"] == 2
    assert t["notes"] == "lote de teste"
    assert data["stats"]["total"] == 1


def test_adiciona_rejeita_nome_vazio(client):
    resp = client.post("/api/trades", json={
        "name": "  ", "buy_cost": 1, "sell_price": 1,
    })
    assert resp.status_code == 400


def test_adiciona_rejeita_preco_invalido(client):
    resp = client.post("/api/trades", json={
        "name": "X", "buy_cost": "abc", "sell_price": 1,
    })
    assert resp.status_code == 400


def test_adiciona_rejeita_quantidade_zero(client):
    resp = client.post("/api/trades", json={
        "name": "X", "buy_cost": 1, "sell_price": 1, "quantity": 0,
    })
    assert resp.status_code == 400


def test_edita_trade_recalcula_pnl(client):
    trades_mod.record_trade("Item", 100, 120, 1)
    resp = client.patch("/api/trades/0", json={"sell_price": 200})
    assert resp.status_code == 200
    t = resp.get_json()["trades"][0]
    assert t["sell_price"] == 200
    assert t["pnl"] > 0


def test_edita_trade_inexistente(client):
    resp = client.patch("/api/trades/9", json={"sell_price": 10})
    assert resp.status_code == 404


def test_remove_trade(client):
    trades_mod.record_trade("Item A", 10, 20, 1)
    trades_mod.record_trade("Item B", 10, 20, 1)
    resp = client.delete("/api/trades/0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["trades"]) == 1
    assert data["trades"][0]["name"] == "Item B"
    assert data["trades"][0]["index"] == 0


def test_remove_trade_inexistente(client):
    resp = client.delete("/api/trades/9")
    assert resp.status_code == 404
