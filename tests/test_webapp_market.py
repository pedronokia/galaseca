"""Testes da Consulta de Mercado (web) -- Fase 10.

So' esta tela bate na Steam sincronamente dentro do request (uma busca
sao 2 chamadas, nao um lote). `steam_api._http_get` e' o ponto de mock
canonico (AGENTS.md) -- dispatcha por URL pra servir priceoverview e a
listing page com o MESMO fixture que tests/test_steam_api.py ja usa.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skinvault.webapp import market_data
from skinvault.webapp.server import create_app
from tests.test_steam_api import MOCK_HTML

_NAME = "AK-47 | Redline (Field-Tested)"
_OVERVIEW_BODY = json.dumps({
    "success": True, "lowest_price": "R$ 100,00",
    "median_price": "R$ 120,00", "volume": "42",
})


def _fake_http_get(url: str, timeout: float = 15.0):
    if "priceoverview" in url:
        return 200, _OVERVIEW_BODY
    if "listings" in url:
        return 200, MOCK_HTML
    return 404, None


@pytest.fixture(autouse=True)
def mock_network(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", _fake_http_get)


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_market_responde(client):
    resp = client.get("/mercado")
    assert resp.status_code == 200


def test_recent_vazio(client, tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "_RECENT_PATH", tmp_path / "recent.json")
    resp = client.get("/api/market/recent")
    assert resp.get_json()["recent"] == []


def test_search_rejeita_nome_vazio(client):
    resp = client.post("/api/market/search", json={"name": "  "})
    assert resp.status_code == 400


def test_search_encontrado(client, tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "_RECENT_PATH", tmp_path / "recent.json")
    resp = client.post("/api/market/search", json={"name": _NAME})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["found"] is True
    assert data["overview"]["lowest"] == pytest.approx(100.0)
    assert data["overview"]["median"] == pytest.approx(120.0)
    assert data["overview"]["volume"] == 42
    assert data["verdict"]["verdict"] in (
        "below_median", "fair", "slightly_above", "overpriced")
    assert data["order_book"]["buy_count"] == 2744
    assert len(data["price_history_tail"]) == 2
    assert data["recent"] == [_NAME]


def test_search_grava_no_recente_sem_duplicar(client, tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "_RECENT_PATH", tmp_path / "recent.json")
    client.post("/api/market/search", json={"name": "Item A"})
    client.post("/api/market/search", json={"name": "Item B"})
    resp = client.post("/api/market/search", json={"name": "Item A"})
    recent = resp.get_json()["recent"]
    assert recent[0] == "Item A"
    assert recent.count("Item A") == 1


def test_search_nao_encontrado(client, monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                         lambda url, timeout=15.0: (404, None))
    resp = client.post("/api/market/search", json={"name": "Item Inexistente"})
    assert resp.status_code == 200
    assert resp.get_json()["found"] is False


def test_search_grava_preco_no_cache(client, tmp_path, monkeypatch):
    from skinvault.prices import PriceCache
    monkeypatch.setattr(market_data, "_RECENT_PATH", tmp_path / "recent.json")
    cache = PriceCache(path=tmp_path / "prices.json")
    result = market_data.search(_NAME, cache=cache)
    assert result["found"] is True
    assert cache.get(_NAME) == pytest.approx(100.0)


def test_runsearch_js_descarta_resposta_superada():
    """runSearch() em market.js nao tinha nenhuma guarda contra busca
    concorrente -- searchBtn.disabled nao desabilita o CAMPO de texto,
    entao buscar um item lento e apertar Enter de novo com outro nome
    antes da resposta voltar disparava uma segunda busca em paralelo.
    Se a resposta da busca antiga chegasse depois da nova, a tela
    acabava mostrando o preco do item ERRADO. Mesma familia de bug ja'
    corrigida nesta sessao em market_screen.py (Qt), inventory.js e
    _price_worker.py (contador de geracao). O cliente de teste do
    Flask nao executa JS -- a rede de seguranca e' garantir que a
    correcao (incrementar `searchGen` em runSearch() e conferir em
    ambos os `.then`/`.catch`) nao regrida, lendo o codigo-fonte."""
    js = Path(__file__).parent.parent / "skinvault" / "webapp" \
        / "static" / "js" / "market.js"
    src = js.read_text(encoding="utf-8")
    assert "searchGen" in src, (
        "contador de geracao (searchGen) sumiu de market.js -- buscas "
        "concorrentes voltam a poder sobrescrever o resultado mais "
        "novo com um mais antigo")
    # Recorte exato do corpo de runSearch() -- do nome da funcao ate' a
    # proxima declarada logo abaixo dela no arquivo (`function render`).
    # Sem regex guloso: um `.*` com DOTALL procurando o fechamento `}`
    # mais parecido transbordava pro corpo de render() tambem.
    inicio = src.index("function runSearch() {")
    fim = src.index("function render(data) {")
    assert inicio < fim, "runSearch() precisa vir antes de render() no arquivo"
    corpo = src[inicio:fim]
    assert corpo.count("gen !== searchGen") == 2, (
        "runSearch() precisa conferir `gen !== searchGen` nos dois "
        "callbacks (.then de sucesso E .catch de erro) antes de tocar "
        "no estado da tela")
