"""Testes da tela de Inventario (web) -- Fase 3 da migracao pra Flask.

So' a API: custo editavel (`/api/inventory/cost`) e remover item
(`/api/inventory/remove`). Nenhuma das duas bate na rede -- so' o preco
muda isso, e aqui so' o custo/posicao muda. "+ Adicionar item" e
"Colar lista" saíram da tela (2026-10-20, a pedido do usuario) -- so'
a Steam entra com item agora.

Importar da Steam (`/api/inventory/import`) bate em rede publica --
mockada via `steam_api.resolve_steam_id`/`fetch_inventory` direto
(ponto de entrada de `inventory_data.start_import`), nunca `_http_get`
cru: o resolve faz uma requisicao XML separada que nao vale a pena
simular aqui.
"""
from __future__ import annotations

import time

import pytest

from skinvault import portfolio as portfolio_mod
from skinvault import steam_api
from skinvault.webapp import inventory_data
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


def test_remove_item_remove_posicao_existente(client):
    portfolio_mod.save_portfolio([
        {"name": "AK-47 | Redline (Field-Tested)", "cost": 150.0, "quantity": 1},
        {"name": "AWP | Asiimov (Field-Tested)", "cost": 650.0, "quantity": 1},
    ])
    resp = client.post("/api/inventory/remove", json={
        "name": "AK-47 | Redline (Field-Tested)",
    })
    assert resp.status_code == 200
    rows = resp.get_json()["rows"]
    assert len(rows) == 1
    assert rows[0]["name"] == "AWP | Asiimov (Field-Tested)"
    assert len(portfolio_mod.load_portfolio()) == 1


def test_remove_item_nome_inexistente(client):
    portfolio_mod.save_portfolio([])
    resp = client.post("/api/inventory/remove", json={"name": "Nao Existe"})
    assert resp.status_code == 404


def test_remove_item_rejeita_nome_vazio(client):
    resp = client.post("/api/inventory/remove", json={"name": ""})
    assert resp.status_code == 400


def _wait_until_idle(timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while inventory_data.is_importing() and time.time() < deadline:
        time.sleep(0.02)


def test_import_status_cooldown_zero_por_padrao(client):
    resp = client.get("/api/inventory/import/status")
    assert resp.status_code == 200
    assert resp.get_json()["cooldown_s"] == 0.0


def test_import_status_expoe_cooldown_do_disjuntor(client):
    steam_api._registrar_rate_limit("inventory")
    try:
        resp = client.get("/api/inventory/import/status")
        assert resp.get_json()["cooldown_s"] > 0.0
    finally:
        steam_api._limpar_rate_limit("inventory")


def test_import_rejeita_perfil_vazio(client):
    resp = client.post("/api/inventory/import", json={"profile": ""})
    assert resp.status_code == 400


def test_import_recusa_concorrente(client, monkeypatch):
    monkeypatch.setattr(inventory_data, "_importing", True)
    resp = client.post("/api/inventory/import", json={"profile": "alguem"})
    assert resp.status_code == 409
    inventory_data._importing = False


def test_import_perfil_invalido_nao_mexe_na_carteira(monkeypatch):
    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda texto: (steam_api.RESOLVE_INVALID, None))
    portfolio_mod.save_portfolio([])
    resultados = []
    assert inventory_data.start_import("lixo", False, resultados.append)
    _wait_until_idle()
    assert len(resultados) == 1
    assert "error" in resultados[0]
    assert portfolio_mod.load_portfolio() == []


def test_import_tenta_de_novo_sozinho_apos_bloqueio_passageiro(monkeypatch):
    # Pedido do usuario: "so existe essa forma [de importar]?" -- a
    # automatica ja' existia, so' faltava nao exigir reclique manual
    # pra um bloqueio curto (o caso comum: 1 usuario, 1 clique, topa
    # com um 429 passageiro). 2 falhas seguidas, acerta na 3a tentativa.
    chamadas = []

    def fake_fetch(steam_id):
        chamadas.append(steam_id)
        if len(chamadas) < 3:
            return steam_api.INV_RATE_LIMITED, []
        return steam_api.INV_OK, [
            {"name": "AK-47 | Redline (Field-Tested)", "quantity": 1}]

    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda texto: (steam_api.RESOLVE_OK, "7656119"))
    monkeypatch.setattr(steam_api, "fetch_inventory", fake_fetch)
    portfolio_mod.save_portfolio([])
    resultados = []
    inventory_data.start_import("alguem", False, resultados.append)
    _wait_until_idle()
    assert len(chamadas) == 3
    assert resultados[0]["ok"] is True
    assert len(portfolio_mod.load_portfolio()) == 1


def test_import_desiste_apos_bloqueio_persistente(monkeypatch):
    chamadas = []
    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda texto: (steam_api.RESOLVE_OK, "7656119"))
    monkeypatch.setattr(
        steam_api, "fetch_inventory",
        lambda steam_id: (chamadas.append(1), (steam_api.INV_RATE_LIMITED, []))[1])
    resultados = []
    inventory_data.start_import("alguem", False, resultados.append)
    _wait_until_idle()
    # 1 tentativa inicial + 2 retentativas (steam_api.RATE_LIMIT_RETRY_BACKOFF_MULT) = 3
    assert len(chamadas) == 3
    assert "error" in resultados[0]


def test_import_mescla_inventario_publico(monkeypatch):
    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda texto: (steam_api.RESOLVE_OK, "7656119"))
    monkeypatch.setattr(
        steam_api, "fetch_inventory",
        lambda steam_id: (steam_api.INV_OK, [
            {"name": "AK-47 | Redline (Field-Tested)", "quantity": 2},
        ]))
    portfolio_mod.save_portfolio([])
    resultados = []
    assert inventory_data.start_import(
        "https://steamcommunity.com/id/teste", False, resultados.append)
    _wait_until_idle()
    assert len(resultados) == 1
    payload = resultados[0]
    assert payload["ok"] is True
    assert payload["resumo"]["adicionados"] == 1
    positions = portfolio_mod.load_portfolio()
    assert len(positions) == 1
    assert positions[0]["quantity"] == 2
    assert positions[0]["source"] == portfolio_mod.SOURCE_STEAM


def test_import_pausa_entre_resolve_e_fetch(monkeypatch):
    # Achado real (2026-10): resolve_steam_id (link personalizado bate
    # na rede) seguido de fetch_inventory sem pausa nenhuma -- mesma
    # lacuna do _collect_inventory, so' que entre as duas chamadas em
    # vez de entre paginas.
    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda texto: (steam_api.RESOLVE_OK, "7656119"))
    monkeypatch.setattr(steam_api, "fetch_inventory",
                         lambda steam_id: (steam_api.INV_OK, []))
    # time.sleep e' o mesmo modulo global em todo o processo -- patchar
    # via inventory_data.time.sleep tambem pegaria o poll abaixo, que
    # usa a MESMA funcao. Guarda a referencia original antes de patchar
    # e usa so' ela pra esperar o worker terminar.
    real_sleep = time.sleep
    sonos = []
    monkeypatch.setattr("skinvault.webapp.inventory_data.time.sleep",
                         sonos.append)
    inventory_data.start_import("alguem", False, lambda r: None)
    deadline = time.time() + 5.0
    while inventory_data.is_importing() and time.time() < deadline:
        real_sleep(0.02)
    assert sonos == [steam_api.RATE_LIMIT_DELAY_S]


def test_import_preserva_custo_manual(monkeypatch):
    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda texto: (steam_api.RESOLVE_OK, "7656119"))
    monkeypatch.setattr(
        steam_api, "fetch_inventory",
        lambda steam_id: (steam_api.INV_OK, [
            {"name": "AK-47 | Redline (Field-Tested)", "quantity": 1},
        ]))
    portfolio_mod.save_portfolio([
        {"name": "AK-47 | Redline (Field-Tested)", "cost": 150.0,
         "quantity": 1, "source": "manual"},
    ])
    resultados = []
    inventory_data.start_import("alguem", False, resultados.append)
    _wait_until_idle()
    positions = portfolio_mod.load_portfolio()
    assert len(positions) == 1
    assert positions[0]["cost"] == 150.0


def test_import_rede_fora_nao_recusa_proxima_tentativa(monkeypatch):
    def _explode(texto):
        raise RuntimeError("rede fora")
    monkeypatch.setattr(steam_api, "resolve_steam_id", _explode)
    resultados = []
    inventory_data.start_import("alguem", False, resultados.append)
    _wait_until_idle()
    assert "error" in resultados[0]
    assert inventory_data.is_importing() is False
