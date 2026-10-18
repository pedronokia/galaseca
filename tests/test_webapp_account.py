"""Testes da tela de Conta (web) -- Fase 2 da migracao pra Flask.

`account_data` e' logica pura (sem Flask); testada direto. As rotas sao
testadas via Flask test client, sem subir servidor de verdade.
"""
from __future__ import annotations

import time

import pytest

from skinvault import portfolio as portfolio_mod
from skinvault.prices import PriceCache
from skinvault.webapp import account_data
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_summary_payload_carteira_vazia():
    payload = account_data.summary_payload()
    assert payload["rows"] == []
    assert payload["totals"]["positions"] == 0
    assert payload["rate_limited"] is False


def test_summary_payload_usa_so_cache(tmp_path):
    """summary_payload nunca bate na rede -- so' lê o que já está em cache."""
    cache = PriceCache(path=tmp_path / "prices.json")
    cache.put("AK-47 | Redline (Field-Tested)", 100.0)
    portfolio_mod.save_portfolio([
        {"name": "AK-47 | Redline (Field-Tested)", "cost": 80.0, "quantity": 1},
    ])

    payload = account_data.summary_payload(cache=cache)

    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["price"] == 100.0
    assert row["has_cost"] is True
    assert payload["totals"]["pnl"] is not None
    assert payload["totals"]["pnl"] > 0


def test_summary_payload_item_sem_cache_fica_sem_preco(tmp_path):
    cache = PriceCache(path=tmp_path / "prices.json")
    portfolio_mod.save_portfolio([
        {"name": "Item Nao Cacheado", "cost": 10.0, "quantity": 1},
    ])

    payload = account_data.summary_payload(cache=cache)

    assert payload["rows"][0]["price"] is None
    assert payload["totals"]["pnl"] is None


def test_rota_summary_retorna_json(client):
    resp = client.get("/api/account/summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rows" in data
    assert "totals" in data


def test_rota_refresh_recusa_concorrente(client, monkeypatch):
    monkeypatch.setattr(account_data, "_refreshing", True)
    resp = client.post("/api/account/refresh")
    assert resp.status_code == 409
    assert resp.get_json()["started"] is False


def test_rota_refresh_dispara_e_termina_sozinha(client):
    portfolio_mod.save_portfolio([])
    resp = client.post("/api/account/refresh")
    assert resp.status_code == 200
    assert resp.get_json()["started"] is True
    for _ in range(100):
        if not account_data.is_refreshing():
            break
        time.sleep(0.02)
    assert not account_data.is_refreshing()


def test_start_refresh_publica_progresso_e_resultado(tmp_path):
    cache = PriceCache(path=tmp_path / "prices.json")
    portfolio_mod.save_portfolio([
        {"name": "Item A", "cost": 10.0, "quantity": 1},
    ])
    progresso: list[tuple[int, int]] = []
    resultado: list[dict] = []

    started = account_data.start_refresh(
        on_progress=lambda done, total: progresso.append((done, total)),
        on_done=lambda payload: resultado.append(payload),
        cache=cache,
    )
    assert started is True

    for _ in range(100):
        if resultado:
            break
        time.sleep(0.02)

    assert resultado, "on_done nunca foi chamado"
    assert progresso, "on_progress nunca foi chamado"
    assert "rows" in resultado[0]
