"""Testes do steam_api -- logica pura + a camada de rede mockada em _http_get."""
from __future__ import annotations

import json

from skinvault import steam_api

# --- amostra no formato real do endpoint /inventory ---------------------------
_FAKE_INV = {
    "assets": [
        {"classid": "1", "instanceid": "0", "amount": "1"},
        {"classid": "2", "instanceid": "0", "amount": "1"},
        {"classid": "2", "instanceid": "0", "amount": "1"},  # duplicata -> agrega
        {"classid": "9", "instanceid": "0", "amount": "1"},  # sem description
    ],
    "descriptions": [
        {"classid": "1", "instanceid": "0", "market_hash_name": "AK-47 | Redline",
         "marketable": 1, "tradable": 1},
        {"classid": "2", "instanceid": "0", "market_hash_name": "Chroma 3 Case",
         "marketable": 1, "tradable": 1},
        {"classid": "3", "instanceid": "0", "market_hash_name": "Nao Marketavel",
         "marketable": 0, "tradable": 0},
    ],
}


def test_parse_brl_formats():
    assert steam_api.parse_brl("R$ 12,34") == 12.34
    assert steam_api.parse_brl("R$ 1.234,56") == 1234.56
    assert steam_api.parse_brl("R$ 0,03") == 0.03
    assert steam_api.parse_brl("") is None
    assert steam_api.parse_brl(None) is None


def test_parse_items_joins_and_aggregates():
    items = steam_api._parse_items(_FAKE_INV)
    by_name = {i["name"]: i for i in items}
    assert by_name["Chroma 3 Case"]["quantity"] == 2     # agregou duplicatas
    assert by_name["AK-47 | Redline"]["quantity"] == 1
    assert "Nao Marketavel" not in by_name               # filtrado
    assert len(items) == 2


def _mock_http(monkeypatch, code, body):
    monkeypatch.setattr(steam_api, "_http_get", lambda *a, **k: (code, body))


def test_fetch_inventory_ok(monkeypatch):
    _mock_http(monkeypatch, 200, json.dumps(_FAKE_INV))
    status, items = steam_api.fetch_inventory("123")
    assert status == steam_api.INV_OK
    assert len(items) == 2


def test_fetch_inventory_private(monkeypatch):
    # 400 e 403 = inventario com privacidade fechada (descoberto num teste real)
    for code in (400, 403):
        _mock_http(monkeypatch, code, None)
        status, items = steam_api.fetch_inventory("123")
        assert status == steam_api.INV_PRIVATE
        assert items == []


def test_fetch_inventory_rate_limited(monkeypatch):
    _mock_http(monkeypatch, 429, None)
    assert steam_api.fetch_inventory("123")[0] == steam_api.INV_RATE_LIMITED


def test_fetch_inventory_empty(monkeypatch):
    _mock_http(monkeypatch, 200, json.dumps({"assets": [], "descriptions": []}))
    assert steam_api.fetch_inventory("123")[0] == steam_api.INV_EMPTY


def test_fetch_inventory_network_error(monkeypatch):
    _mock_http(monkeypatch, 0, None)
    assert steam_api.fetch_inventory("123")[0] == steam_api.INV_ERROR


def test_public_wrapper_returns_items(monkeypatch):
    _mock_http(monkeypatch, 200, json.dumps(_FAKE_INV))
    assert len(steam_api.fetch_public_inventory("123")) == 2
