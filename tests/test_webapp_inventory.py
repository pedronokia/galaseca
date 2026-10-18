"""Testes da tela de Inventario (web) -- Fase 3 da migracao pra Flask.

So' a API: custo editavel (`/api/inventory/cost`) e "+ Adicionar item"
(`/api/inventory/add`). Nenhuma das duas bate na rede -- so' o preco
muda isso, e aqui so' o custo/posicao muda.
"""
from __future__ import annotations

import pytest

from skinvault import portfolio as portfolio_mod
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_inventario_responde(client):
    resp = client.get("/inventario")
    assert resp.status_code == 200
    assert b"Invent\xc3\xa1rio" in resp.data


def test_rota_list_retorna_mesma_forma_que_account_summary(client):
    resp = client.get("/api/inventory")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rows" in data and "totals" in data


def test_set_cost_atualiza_posicao_existente(client):
    portfolio_mod.save_portfolio([
        {"name": "AK-47 | Redline (Field-Tested)", "cost": None, "quantity": 1},
    ])
    resp = client.post("/api/inventory/cost", json={
        "name": "AK-47 | Redline (Field-Tested)", "cost": 150.5,
    })
    assert resp.status_code == 200
    rows = resp.get_json()["rows"]
    assert rows[0]["cost"] == 150.5
    assert rows[0]["has_cost"] is True

    positions = portfolio_mod.load_portfolio()
    assert positions[0]["cost"] == 150.5


def test_set_cost_cria_posicao_quando_nome_nao_existe(client):
    portfolio_mod.save_portfolio([])
    resp = client.post("/api/inventory/cost", json={
        "name": "Item Novo", "cost": 10,
    })
    assert resp.status_code == 200
    positions = portfolio_mod.load_portfolio()
    assert len(positions) == 1
    assert positions[0]["name"] == "Item Novo"
    assert positions[0]["cost"] == 10.0


def test_set_cost_rejeita_custo_negativo(client):
    portfolio_mod.save_portfolio([
        {"name": "Item X", "cost": None, "quantity": 1},
    ])
    resp = client.post("/api/inventory/cost", json={
        "name": "Item X", "cost": -5,
    })
    assert resp.status_code == 400


def test_set_cost_rejeita_nome_vazio(client):
    resp = client.post("/api/inventory/cost", json={"name": "", "cost": 10})
    assert resp.status_code == 400


def test_add_item_cria_posicao_sem_custo(client):
    portfolio_mod.save_portfolio([])
    resp = client.post("/api/inventory/add", json={
        "name": "Item Drop", "quantity": 2,
    })
    assert resp.status_code == 200
    positions = portfolio_mod.load_portfolio()
    assert len(positions) == 1
    assert positions[0]["cost"] is None
    assert positions[0]["quantity"] == 2
    rows = resp.get_json()["rows"]
    assert rows[0]["has_cost"] is False


def test_add_item_rejeita_quantidade_invalida(client):
    resp = client.post("/api/inventory/add", json={
        "name": "Item Y", "quantity": 0,
    })
    assert resp.status_code == 400


def test_add_item_rejeita_nome_vazio(client):
    resp = client.post("/api/inventory/add", json={"name": "   "})
    assert resp.status_code == 400
