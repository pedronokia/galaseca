"""Testes da tela de Historico (web) -- Fase 7."""
from __future__ import annotations

import pytest

from skinvault import history as history_mod
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_historico_responde(client):
    resp = client.get("/historico")
    assert resp.status_code == 200


def _reset_history() -> None:
    """Zera data/history.json (o path de TESTE, ja isolado por
    SKINVAULT_DATA_DIR no conftest.py).

    NAO da' pra isolar via `monkeypatch.setattr(history_mod,
    "_DEFAULT_PATH", ...)` aqui: `record_snapshot`/`load_history` usam
    `path: Path | str = _DEFAULT_PATH` como default de PARAMETRO, que o
    Python resolve uma unica vez na definicao da funcao -- o mesmo
    AGENTS.md #13 (RATE_LIMIT_DELAY_S), so que pra history.py. A rota
    tambem chama sem `path=`, entao so' sobra resetar o arquivo de
    verdade, igual `trades_mod.save_trades([])` faz pras outras telas.
    """
    history_mod._DEFAULT_PATH.write_text("[]", encoding="utf-8")


def test_value_series_vazia(client):
    _reset_history()
    resp = client.get("/api/history/value")
    assert resp.get_json()["series"] == []


def test_value_series_mais_recente_primeiro(client):
    _reset_history()
    history_mod.record_snapshot(100.0, now=1000.0)
    history_mod.record_snapshot(200.0, now=2000.0)
    resp = client.get("/api/history/value")
    series = resp.get_json()["series"]
    assert [p["total"] for p in series] == [200.0, 100.0]


def test_simulate_calcula_pnl(client):
    resp = client.post("/api/history/simulate", json={
        "buy_price": 100, "sell_price": 150, "quantity": 2,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cost_total"] == 200.0
    assert data["is_profit"] is True
    assert data["pnl"] > 0


def test_simulate_rejeita_preco_invalido(client):
    resp = client.post("/api/history/simulate", json={
        "buy_price": "abc", "sell_price": 10,
    })
    assert resp.status_code == 400


def test_simulate_rejeita_quantidade_zero(client):
    resp = client.post("/api/history/simulate", json={
        "buy_price": 10, "sell_price": 10, "quantity": 0,
    })
    assert resp.status_code == 400


def test_simulate_default_quantidade_um(client):
    resp = client.post("/api/history/simulate", json={
        "buy_price": 10, "sell_price": 20,
    })
    assert resp.status_code == 200
    assert resp.get_json()["quantity"] == 1
