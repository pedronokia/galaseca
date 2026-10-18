"""Testes do Scanner (web) -- Fase 11.

Rede mockada via `steam_api._http_get` (ponto canonico, AGENTS.md),
com o mesmo MOCK_HTML que tests/test_steam_api.py usa. A lista de
categorias e' trocada por uma fixture pequena via monkeypatch em
`scanner_data.SCAN_BY_CATEGORY` -- e' global simples referenciada no
corpo das funcoes (nao default de parametro), entao o monkeypatch
alcanca `categories()`/`start_scan()` sem a armadilha do AGENTS.md #13.
"""
from __future__ import annotations

import json
import time

import pytest

from skinvault.webapp import scanner_data
from skinvault.webapp.server import create_app
from tests.test_steam_api import MOCK_HTML

_OVERVIEW_BODY = json.dumps({
    "success": True, "lowest_price": "R$ 100,00",
    "median_price": "R$ 120,00", "volume": "42",
})
_FAKE_CATEGORIES = {
    "Teste A": ["Item Um", "Item Dois"],
    "Teste B": ["Item Três"],
}


def _fake_http_get(url: str, timeout: float = 15.0):
    if "priceoverview" in url:
        return 200, _OVERVIEW_BODY
    if "listings" in url:
        return 200, MOCK_HTML
    return 404, None


@pytest.fixture(autouse=True)
def mock_network_and_categories(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", _fake_http_get)
    monkeypatch.setattr(scanner_data, "SCAN_BY_CATEGORY", _FAKE_CATEGORIES)
    # Garante que nenhum teste comeca com um scan "preso" de um teste
    # anterior que nao deu tempo de terminar.
    scanner_data._scanning = False
    scanner_data._cancel_requested = False
    yield
    scanner_data._scanning = False
    scanner_data._cancel_requested = False


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_scanner_responde(client):
    resp = client.get("/scanner")
    assert resp.status_code == 200


def test_categories_lista_todas_e_cada_uma(client):
    resp = client.get("/api/scanner/categories")
    data = resp.get_json()["categories"]
    assert data[0] == "Todas as categorias"
    assert "Teste A" in data
    assert "Teste B" in data


def test_scan_rejeita_categoria_invalida(client):
    resp = client.post("/api/scanner/scan", json={"category": "Não Existe"})
    assert resp.status_code == 400


def test_scan_recusa_concorrente(client, monkeypatch):
    monkeypatch.setattr(scanner_data, "_scanning", True)
    resp = client.post("/api/scanner/scan", json={"category": "Teste A"})
    assert resp.status_code == 409


def _wait_until_idle(timeout_s: float = 5.0) -> None:
    deadline = time.time() + timeout_s
    while scanner_data.is_scanning() and time.time() < deadline:
        time.sleep(0.02)


def test_start_scan_processa_itens_e_chama_callbacks():
    progress_calls = []
    items = []
    done = []

    started = scanner_data.start_scan(
        "Teste A",
        on_progress=lambda done_n, total, name: progress_calls.append(
            (done_n, total, name)),
        on_item=lambda item: items.append(item),
        on_done=lambda result: done.append(result),
    )
    assert started is True
    _wait_until_idle()

    assert len(progress_calls) == 2  # "Teste A" tem 2 itens
    assert len(items) == 2
    assert all(0 <= it["score"] <= 100 for it in items)
    assert all(it["price"] == pytest.approx(100.0) for it in items)
    assert done == [{"cancelled": False}]
    assert scanner_data.is_scanning() is False


def test_start_scan_todas_as_categorias_junta_sem_duplicar():
    items = []
    scanner_data.start_scan(
        "Todas as categorias",
        on_progress=lambda *a: None,
        on_item=lambda item: items.append(item),
        on_done=lambda result: None,
    )
    _wait_until_idle()
    nomes = {it["name"] for it in items}
    assert nomes == {"Item Um", "Item Dois", "Item Três"}


def test_start_scan_recusa_concorrente_na_propria_funcao():
    scanner_data.start_scan(
        "Teste A", on_progress=lambda *a: None,
        on_item=lambda *a: None, on_done=lambda *a: None,
    )
    started_again = scanner_data.start_scan(
        "Teste B", on_progress=lambda *a: None,
        on_item=lambda *a: None, on_done=lambda *a: None,
    )
    assert started_again is False
    _wait_until_idle()


def test_cancel_scan_marca_cancelado():
    # Chamar cancel_scan() da thread principal LOGO apos start_scan() e'
    # uma corrida (RATE_LIMIT_DELAY_S=0 na suite -- o worker pode
    # terminar os 3 itens antes do cancelamento ser visto). Em vez
    # disso, o proprio `on_progress` (que roda DENTRO da thread do
    # worker, sincrono) cancela ao ver o primeiro item -- determinístico.
    done = []

    def _cancel_on_first(done_n, _total, _name):
        if done_n == 1:
            scanner_data.cancel_scan()

    scanner_data.start_scan(
        "Todas as categorias", on_progress=_cancel_on_first,
        on_item=lambda *a: None, on_done=lambda result: done.append(result),
    )
    _wait_until_idle()
    assert done and done[0]["cancelled"] is True


def test_rota_scan_fim_a_fim(client):
    resp = client.post("/api/scanner/scan", json={"category": "Teste A"})
    assert resp.status_code == 200
    assert resp.get_json()["started"] is True
    _wait_until_idle()

    status_resp = client.get("/api/scanner/status")
    assert status_resp.get_json()["scanning"] is False


def test_rota_cancel(client):
    resp = client.post("/api/scanner/cancel")
    assert resp.status_code == 200
