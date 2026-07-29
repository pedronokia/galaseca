"""Testes do steam_api -- logica pura (sem rede)."""
from __future__ import annotations

import json

import pytest

from skinvault import steam_api
from skinvault.steam_api import (
    _extract_render_context,
    _find_query,
    _js_unescape,
    _skin_root_name,
    fair_value_verdict,
    get_market_page_data,
    parse_brl,
)


class TestFairValueVerdict:
    def test_both_none(self):
        v = fair_value_verdict(None, None)
        assert v["verdict"] == "unknown"

    def test_median_none(self):
        v = fair_value_verdict(100.0, None)
        assert v["verdict"] == "unknown"

    def test_lowest_none(self):
        v = fair_value_verdict(None, 100.0)
        assert v["verdict"] == "unknown"

    def test_median_zero(self):
        v = fair_value_verdict(100.0, 0)
        assert v["verdict"] == "unknown"

    def test_below_median(self):
        v = fair_value_verdict(90.0, 100.0)
        assert v["verdict"] == "below_median"
        assert v["diff_pct"] == pytest.approx(-10.0)

    def test_fair(self):
        v = fair_value_verdict(103.0, 100.0)
        assert v["verdict"] == "fair"

    def test_slightly_above(self):
        v = fair_value_verdict(115.0, 100.0)
        assert v["verdict"] == "slightly_above"

    def test_overpriced(self):
        v = fair_value_verdict(150.0, 100.0)
        assert v["verdict"] == "overpriced"

    def test_edge_below_negative(self):
        """diff_pct negativo (lowest < median) funciona."""
        v = fair_value_verdict(50.0, 100.0)
        assert v["diff_pct"] == -50.0
        assert v["verdict"] == "below_median"

    def test_with_tight_spread(self):
        v = fair_value_verdict(100.0, 100.0, spread=100, buy_count=100, sell_count=50)
        assert v["spread_verdict"] == "tight"
        assert v["book_verdict"] == "balanced"

    def test_with_wide_spread(self):
        v = fair_value_verdict(100.0, 100.0, spread=5000)
        assert v["spread_verdict"] == "wide"
        assert "pouca liquidez" in v["details"]["spread"]

    def test_with_buyer_dominant_book(self):
        v = fair_value_verdict(100.0, 100.0, buy_count=500, sell_count=10)
        assert v["book_verdict"] == "buyer_dominant"
        assert "Demanda aquecida" in v["message"]

    def test_with_seller_dominant_book(self):
        v = fair_value_verdict(100.0, 100.0, buy_count=10, sell_count=500)
        assert v["book_verdict"] == "seller_dominant"
        assert "Muitos vendedores" in v["message"]

    def test_with_rising_price_history(self):
        ph = [{"price_median": 100.0}] * 6 + [{"price_median": 115.0}]
        v = fair_value_verdict(100.0, 100.0, price_history=ph)
        assert v["trend_verdict"] == "rising"
        assert "Preco subindo" in v["message"]

    def test_with_falling_price_history(self):
        ph = [{"price_median": 115.0}] * 6 + [{"price_median": 100.0}]
        v = fair_value_verdict(100.0, 100.0, price_history=ph)
        assert v["trend_verdict"] == "falling"
        assert "Preco caindo" in v["message"]

    def test_insufficient_history_skips_trend(self):
        ph = [{"price_median": 100.0}] * 3
        v = fair_value_verdict(100.0, 100.0, price_history=ph)
        assert "trend_verdict" not in v

    def test_backward_compat_no_extra_keys(self):
        v = fair_value_verdict(90.0, 100.0)
        assert set(v.keys()) == {"diff_pct", "verdict", "label", "message"}

    def test_spread_must_be_int_not_dict(self):
        """Regression: chamar com spread=dict crashava com TypeError.

        Scanner e Market faziam spread=page['order_book'] (dict). O
        contrato espera int (centavos). Tests garantem que callers usem
        ob.get('spread') -- valor escalar -- e nao o dict inteiro.
        """
        with pytest.raises(TypeError):
            fair_value_verdict(100.0, 100.0, spread={"buy_count": 5})

    def test_order_book_dict_via_correct_keys(self):
        """Order book do get_market_page_data tem chaves buy_count/
        sell_count/spread. Callers devem extrair escalar antes de passar."""
        ob = {
            "best_bid": 9500,
            "best_ask": 10500,
            "buy_count": 100,
            "sell_count": 50,
            "spread": 1000,
        }
        v = fair_value_verdict(
            100.0, 100.0,
            spread=ob["spread"],
            buy_count=ob["buy_count"],
            sell_count=ob["sell_count"],
        )
        assert "spread_verdict" in v
        assert "book_verdict" in v


SAMPLE_RENDER_CONTEXT = json.dumps(
    {
        "localizationSettings": {"languages": []},
        "queryData": json.dumps(
            {
                "mutations": [],
                "queries": [
                    {
                        "state": {
                            "data": {
                                "prices": [
                                    {"time": 1392940800, "price_median": 209.86, "purchases": 198},
                                    {"time": 1780614000, "price_median": 233.07, "purchases": 3},
                                ]
                            },
                            "status": "success",
                        },
                        "queryKey": ["market", "pricehistory", 730, "AK-47 | Redline (Field-Tested)"],
                        "queryHash": '["market","pricehistory",730,"AK-47 | Redline (Field-Tested)"]',
                    },
                    {
                        "state": {
                            "data": {
                                "amtMaxBuyOrder": 103356,
                                "amtMinSellOrder": 106439,
                                "eCurrency": 7,
                                "cBuyOrders": 2744,
                                "cSellOrders": 65,
                                "rgCompactBuyOrders": [103356, 1, 103355, 1],
                                "rgCompactSellOrders": [106439, 1, 110164, 1],
                            },
                            "status": "success",
                        },
                        "queryKey": ["market", "orderbook", 730, "AK-47 | Redline (Field-Tested)"],
                        "queryHash": '["market","orderbook",730,"AK-47 | Redline (Field-Tested)"]',
                    },
                ],
            }
        ),
    }
)


def _build_mock_html(rc_json: str) -> str:
    """Gera HTML que simula a pagina de listagem do Steam Market."""
    escaped = rc_json.replace("\\", "\\\\").replace('"', '\\"')
    return (
        '<!DOCTYPE html><html><head></head><body>'
        '<script>window.SSR.renderContext = JSON.parse("'
        + escaped
        + '")</script>'
        '</body></html>'
    )


MOCK_HTML = _build_mock_html(SAMPLE_RENDER_CONTEXT)


class TestJsUnescape:
    def test_escaped_quotes(self):
        assert _js_unescape('{\\"a\\":1}') == '{"a":1}'

    def test_double_backslash(self):
        assert _js_unescape("a\\\\b") == "a\\b"

    def test_newline(self):
        assert _js_unescape("a\\nb") == "a\nb"


class TestExtractRenderContext:
    def test_extracts_from_valid_html(self):
        rc = _extract_render_context(MOCK_HTML)
        assert rc is not None
        assert "queryData" in rc

    def test_returns_none_for_no_parse(self):
        assert _extract_render_context("<html></html>") is None

    def test_returns_none_for_bad_json(self):
        html = '<script>window.SSR.renderContext = JSON.parse("{bad")</script>'
        assert _extract_render_context(html) is None


class TestFindQuery:
    def test_finds_by_key(self):
        queries = [
            {"queryKey": ["a", "b"], "state": {"data": "x"}},
            {"queryKey": ["market", "pricehistory"], "state": {"data": "y"}},
        ]
        assert _find_query(queries, "pricehistory") == "y"

    def test_returns_none_when_missing(self):
        assert _find_query([], "pricehistory") is None

    def test_exact_match_when_item_specified(self):
        queries = [
            {"queryKey": ["market", "orderbook", 730,
                          "AK-47 | Redline (Minimal Wear)"],
             "state": {"data": "mw"}},
            {"queryKey": ["market", "orderbook", 730,
                          "AK-47 | Redline (Field-Tested)"],
             "state": {"data": "ft"}},
        ]
        # Sem loose_match, exige substring match no nome cached
        assert _find_query(queries, "orderbook",
                           "AK-47 | Redline (Field-Tested)") == "ft"

    def test_loose_match_falls_back_to_skin_root(self):
        """Steam pre-carrega orderbook so' de um wear; loose_match pega
        do mesmo skin."""
        queries = [
            {"queryKey": ["market", "orderbook", 730,
                          "AK-47 | Redline (Minimal Wear)"],
             "state": {"data": "mw"}},
        ]
        # Pediu FT mas so' tem MW: loose_match resgata o MW
        assert _find_query(queries, "orderbook",
                           "AK-47 | Redline (Field-Tested)",
                           loose_match=True) == "mw"
        # Sem loose_match retorna None
        assert _find_query(queries, "orderbook",
                           "AK-47 | Redline (Field-Tested)") is None


class TestSkinRootName:
    def test_strips_wear(self):
        assert _skin_root_name(
            "AK-47 | Redline (Field-Tested)"
        ) == "ak-47 | redline"

    def test_strips_stattrak_prefix(self):
        assert _skin_root_name(
            "StatTrak™ AK-47 | Redline (Minimal Wear)"
        ) == "ak-47 | redline"

    def test_strips_souvenir_prefix(self):
        assert _skin_root_name(
            "Souvenir P250 | Sand Dune (Factory New)"
        ) == "p250 | sand dune"

    def test_strips_star_marker(self):
        assert _skin_root_name(
            "★ Karambit | Doppler (Factory New)"
        ) == "karambit | doppler"

    def test_no_wear_no_op(self):
        assert _skin_root_name("Operation Bravo Case") == "operation bravo case"


class TestGetMarketPageData:
    def test_parse_html_with_market_data(self, monkeypatch):
        """Integracao basica: mocka _http_get e verifica parse."""

        def mock_get(url: str, timeout: float = 15.0):
            return 200, MOCK_HTML

        monkeypatch.setattr("skinvault.steam_api._http_get", mock_get)
        result = get_market_page_data("AK-47 | Redline (Field-Tested)")
        assert result is not None
        assert "price_history" in result
        assert "order_book" in result
        assert len(result["price_history"]) == 2
        assert result["order_book"]["best_bid"] == 103356
        assert result["order_book"]["best_ask"] == 106439
        assert result["order_book"]["spread"] == 3083
        assert result["order_book"]["buy_count"] == 2744
        assert result["order_book"]["sell_count"] == 65

    def test_returns_none_on_http_error(self, monkeypatch):
        def mock_get(url: str, timeout: float = 15.0):
            return 404, None

        monkeypatch.setattr("skinvault.steam_api._http_get", mock_get)
        assert get_market_page_data("AK-47 | Redline") is None

    def test_returns_none_on_no_data(self, monkeypatch):
        def mock_get(url: str, timeout: float = 15.0):
            return 200, "<html></html>"

        monkeypatch.setattr("skinvault.steam_api._http_get", mock_get)
        assert get_market_page_data("AK-47 | Redline") is None


class TestParseBRL:
    def test_typical(self):
        assert parse_brl("R$ 1.234,56") == pytest.approx(1234.56)

    def test_small(self):
        assert parse_brl("R$ 50,00") == pytest.approx(50.0)

    def test_integer(self):
        assert parse_brl("R$ 100") == pytest.approx(100.0)

    def test_none(self):
        assert parse_brl(None) is None

    def test_empty(self):
        assert parse_brl("") is None

    def test_no_prefix(self):
        assert parse_brl("100,50") == pytest.approx(100.5)

    def test_garbage_returns_none(self):
        assert parse_brl("not a number") is None


# ── _http_get ──────────────────────────────────────────────────────


class MockResponse:
    """Simula resposta de urllib.request.urlopen."""
    def __init__(self, status=200, body=b"ok"):
        self.status = status
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        pass


def test_http_get_success(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=15: MockResponse())
    code, body = steam_api._http_get("http://x")
    assert code == 200
    assert body == "ok"


def test_http_get_httperror_returns_code(monkeypatch):
    """HTTPError retorna o codigo do erro."""
    import urllib.error

    def _raise(url, *a, **kw):
        raise urllib.error.HTTPError("http://x", 429, "rate", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    code, body = steam_api._http_get("http://x")
    assert code == 429
    assert body is None


def test_http_get_network_error_returns_zero(monkeypatch):
    """Erro generico de rede retorna 0."""

    def _raise(url, *a, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    code, body = steam_api._http_get("http://x")
    assert code == 0
    assert body is None


# ── _get_json ──────────────────────────────────────────────────────


def test_get_json_non_200_returns_none(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (404, b"{}"))
    assert steam_api._get_json("http://x") is None


def test_get_json_invalid_json_returns_none(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, "not json"))
    assert steam_api._get_json("http://x") is None


# ── _parse_volume ──────────────────────────────────────────────────


def test_parse_volume_none():
    assert steam_api._parse_volume(None) is None


def test_parse_volume_empty():
    assert steam_api._parse_volume("") is None


def test_parse_volume_garbage():
    assert steam_api._parse_volume("abc") is None


def test_parse_volume_with_commas():
    assert steam_api._parse_volume("1,234") == 1234


# ── get_market_price / get_market_overview ─────────────────────────


# get_market_price virou wrapper de get_market_price_status, que precisa do
# STATUS HTTP pra distinguir 429 de "item sem preco" -- entao ele le' o
# _http_get direto, que e' o ponto de mock canonico (AGENTS.md).
def _fake_http(code, body):
    return lambda url, timeout=15.0: (code, body)


def test_get_market_price_no_data(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", _fake_http(500, None))
    assert steam_api.get_market_price("AK") is None


def test_get_market_price_not_successful(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        _fake_http(200, '{"success": false}'))
    assert steam_api.get_market_price("AK") is None


def test_get_market_price_falls_back_to_median(monkeypatch):
    """Sem lowest_price, usa median_price."""
    monkeypatch.setattr(
        "skinvault.steam_api._http_get",
        _fake_http(200, '{"success": true, "median_price": "R$ 200,00"}'))
    assert steam_api.get_market_price("AK") == 200.0


# ── status do priceoverview ────────────────────────────────────────

def test_price_status_ok(monkeypatch):
    monkeypatch.setattr(
        "skinvault.steam_api._http_get",
        _fake_http(200, '{"success": true, "lowest_price": "R$ 150,00"}'))
    assert steam_api.get_market_price_status("AK") == (
        steam_api.PRICE_OK, 150.0)


def test_price_status_429_e_rate_limited(monkeypatch):
    """O caso que antes virava 'sem preco' e envenenava o cache por 1h."""
    monkeypatch.setattr("skinvault.steam_api._http_get", _fake_http(429, None))
    assert steam_api.get_market_price_status("AK") == (
        steam_api.PRICE_RATE_LIMITED, None)


def test_price_status_sem_mercado(monkeypatch):
    """Steam respondeu: o item nao tem preco. Isso e' fato sobre o item."""
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        _fake_http(200, '{"success": false}'))
    assert steam_api.get_market_price_status("AK") == (
        steam_api.PRICE_NO_PRICE, None)


def test_price_status_erro_de_rede(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", _fake_http(0, None))
    assert steam_api.get_market_price_status("AK") == (
        steam_api.PRICE_ERROR, None)


def test_price_status_json_quebrado(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        _fake_http(200, "{nao e json"))
    assert steam_api.get_market_price_status("AK") == (
        steam_api.PRICE_ERROR, None)


def test_price_status_sucesso_sem_preco_parseavel(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        _fake_http(200, '{"success": true}'))
    assert steam_api.get_market_price_status("AK") == (
        steam_api.PRICE_NO_PRICE, None)


def test_apenas_ok_e_no_price_sao_cacheaveis():
    """A lista que separa fato sobre o ITEM de estado da REDE."""
    assert steam_api.PRICE_OK in steam_api.PRICE_CACHEABLE
    assert steam_api.PRICE_NO_PRICE in steam_api.PRICE_CACHEABLE
    assert steam_api.PRICE_RATE_LIMITED not in steam_api.PRICE_CACHEABLE
    assert steam_api.PRICE_ERROR not in steam_api.PRICE_CACHEABLE


def test_get_market_overview_no_data(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._get_json", lambda url: None)
    assert steam_api.get_market_overview("AK") is None


def test_get_market_overview_not_successful(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._get_json", lambda url: {"success": False})
    assert steam_api.get_market_overview("AK") is None


def test_get_market_overview_parse(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._get_json", lambda url: {
        "success": True,
        "lowest_price": "R$ 100,00",
        "median_price": "R$ 110,00",
        "volume": "1,234",
    })
    r = steam_api.get_market_overview("AK")
    assert r["lowest"] == 100.0
    assert r["median"] == 110.0
    assert r["volume"] == 1234


# ── _parse_items ───────────────────────────────────────────────────


def test_parse_items_non_marketable_skipped():
    data = {
        "assets": [{"classid": "1", "instanceid": "1", "amount": 1}],
        "descriptions": [{"classid": "1", "instanceid": "1", "marketable": False}],
    }
    assert steam_api._parse_items(data) == []


def test_parse_items_empty_name_skipped():
    data = {
        "assets": [{"classid": "1", "instanceid": "1", "amount": 1}],
        "descriptions": [{
            "classid": "1", "instanceid": "1", "marketable": True,
            "market_hash_name": "",
        }],
    }
    assert steam_api._parse_items(data) == []


def test_parse_items_aggregates_quantity():
    data = {
        "assets": [
            {"classid": "1", "instanceid": "1", "amount": 2},
            {"classid": "1", "instanceid": "1", "amount": 3},
        ],
        "descriptions": [{
            "classid": "1", "instanceid": "1", "marketable": True,
            "market_hash_name": "AK-47 | Redline",
            "tradable": True,
        }],
    }
    result = steam_api._parse_items(data)
    assert len(result) == 1
    assert result[0]["quantity"] == 5


# ── fetch_inventory status codes ───────────────────────────────────


def test_fetch_inventory_private(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (400, None))
    status, items = steam_api.fetch_inventory("123")
    assert status == "private"
    assert items == []


def test_fetch_inventory_rate_limited(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (429, None))
    status, items = steam_api.fetch_inventory("123")
    assert status == "rate_limited"


def test_fetch_inventory_error_on_non_200(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (500, None))
    status, items = steam_api.fetch_inventory("123")
    assert status == "error"


def test_fetch_inventory_invalid_json(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, "not json"))
    status, items = steam_api.fetch_inventory("123")
    assert status == "error"


def test_fetch_inventory_empty_no_assets(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, "{}"))
    status, items = steam_api.fetch_inventory("123")
    assert status == "empty"


def test_fetch_inventory_empty_no_marketable(monkeypatch):
    body = json.dumps({
        "assets": [{"classid": "1", "instanceid": "1", "amount": 1}],
        "descriptions": [{
            "classid": "1", "instanceid": "1", "marketable": False,
        }],
    })
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, body))
    status, items = steam_api.fetch_inventory("123")
    assert status == "empty"


# ── fetch_public_inventory wrapper ─────────────────────────────────


def test_fetch_public_inventory_returns_items_list(monkeypatch):
    monkeypatch.setattr(
        "skinvault.steam_api.fetch_inventory",
        lambda sid: ("ok", [{"name": "AK", "quantity": 1}]),
    )
    assert steam_api.fetch_public_inventory("123") == [{"name": "AK", "quantity": 1}]


# ── _js_unescape adicional ─────────────────────────────────────────


class TestJsUnescapeExtended:
    def test_carriage_return(self):
        assert _js_unescape("a\\rb") == "a\rb"

    def test_tab(self):
        assert _js_unescape("a\\tb") == "a\tb"

    def test_slash(self):
        assert _js_unescape("a\\/b") == "a/b"

    def test_unicode(self):
        assert _js_unescape("\\u0041") == "A"

    def test_unescaped_char(self):
        # \x -> "x", entao a\xb = "axb"
        assert _js_unescape("a\\xb") == "axb"

    def test_plain_string_no_changes(self):
        assert _js_unescape("hello") == "hello"


# ── _find_query com args extras ────────────────────────────────────


def test_find_query_key_not_in_querykey():
    """queryKey que nao contem a key e' ignorado."""
    queries = [{"queryKey": ["market", "other"], "state": {"data": "x"}}]
    assert steam_api._find_query(queries, "pricehistory") is None


def test_find_query_item_name_mismatch_skips():
    """Item name especificado mas queryKey nome difere, sem loose_match."""
    queries = [
        {"queryKey": ["market", "orderbook", 730, "AWP | Dragon Lore"],
         "state": {"data": "dl"}},
    ]
    assert steam_api._find_query(queries, "orderbook", "AK-47 | Redline") is None


def test_find_query_not_enough_key_length():
    """queryKey com len <= 3 ignora check de nome."""
    queries = [
        {"queryKey": ["market", "pricehistory"], "state": {"data": "ph"}},
    ]
    assert steam_api._find_query(queries, "pricehistory", "AK") == "ph"


# ── get_market_page_data edge cases ────────────────────────────────


def test_get_market_page_data_no_render_context(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, "<html>"))
    assert steam_api.get_market_page_data("AK") is None


def test_get_market_page_data_no_queries(monkeypatch):
    rc = json.dumps({"queryData": json.dumps({"queries": []})})
    html = '<script>window.SSR.renderContext = JSON.parse("' + rc.replace('"', '\\"') + '")</script>'
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, html))
    assert steam_api.get_market_page_data("AK") is None


def test_get_market_page_data_loose_match_orderbook(monkeypatch):
    """Quando orderbook exato nao existe, tenta loose_match."""
    rc = json.dumps({
        "queryData": json.dumps({
            "queries": [
                {
                    "state": {"data": {"prices": [{"time": 100, "price_median": 10, "purchases": 1}]}},
                    "queryKey": ["market", "pricehistory", 730, "AK-47 | Redline"],
                },
                {
                    "state": {"data": {"amtMaxBuyOrder": 500, "amtMinSellOrder": 600,
                                        "cBuyOrders": 10, "cSellOrders": 5,
                                        "rgCompactBuyOrders": [], "rgCompactSellOrders": []}},
                    "queryKey": ["market", "orderbook", 730, "AK-47 | Redline (Minimal Wear)"],
                },
            ],
        }),
    })
    html = '<script>window.SSR.renderContext = JSON.parse("' + rc.replace('"', '\\"') + '")</script>'
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, html))
    result = steam_api.get_market_page_data("AK-47 | Redline (Field-Tested)")
    assert result is not None
    assert result["order_book_approx"] is True
    assert result["order_book"]["best_bid"] == 500


def test_get_market_page_data_invalid_query_data_json(monkeypatch):
    """queryData com JSON invalido retorna None."""
    rc = json.dumps({"queryData": "not-a-json-string"})
    html = '<script>window.SSR.renderContext = JSON.parse("' + rc.replace('"', '\\"') + '")</script>'
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, html))
    assert steam_api.get_market_page_data("AK") is None


def test_get_market_page_data_query_data_not_string(monkeypatch):
    """queryData que nao e' string retorna None."""
    rc = json.dumps({"queryData": 123})
    html = '<script>window.SSR.renderContext = JSON.parse("' + rc.replace('"', '\\"') + '")</script>'
    monkeypatch.setattr("skinvault.steam_api._http_get", lambda url: (200, html))
    assert steam_api.get_market_page_data("AK") is None


# ── fetch_my_listings / fetch_market_history JSON error ────────────


def test_fetch_my_listings_invalid_json_returns_none(monkeypatch):
    """fetch_my_listings com JSON invalido retorna None."""

    class FakeSession:
        steamid = "123"
        def cookie_header(self):
            return ""

    monkeypatch.setattr("skinvault.steam_api._http_get_auth", lambda *a, **kw: (200, "bad json"))
    assert steam_api.fetch_my_listings(FakeSession()) is None


# ── parse_market_history_html ──────────────────────────────────────


def test_parse_market_history_html_empty():
    assert steam_api.parse_market_history_html("") == []


def test_parse_market_history_html_no_anchors():
    assert steam_api.parse_market_history_html("<div>no rows</div>") == []


def test_parse_market_history_html_skip_no_name():
    """Nome em branco ou sem regex de nome continua (name fica '')."""
    html = (
        '<div class="market_listing_row">'
        '<div class="market_listing_item_name">   </div>'
        "<div>extra</div>"
        "</div>"
    )
    result = steam_api.parse_market_history_html(html)
    assert len(result) == 1
    assert result[0].name == ""


def test_parse_market_history_html_no_name_div_skips_row():
    """Row sem div de nome (regex nao encontra) e' pulado."""
    html = (
        '<div class="market_listing_row">'
        "<div>no name here</div>"
        "</div>"
    )
    result = steam_api.parse_market_history_html(html)
    assert len(result) == 0


def test_parse_market_history_html_with_name_but_no_price():
    html = (
        '<div class="market_listing_row" id="history_row_lid1_lid1">'
        '<div class="market_listing_gainorloss">+</div>'
        '<div class="market_listing_item_name">AK-47</div>'
        '<div class="market_listing_listed_date">1 Jan</div>'
        "</div>"
    )
    result = steam_api.parse_market_history_html(html)
    assert len(result) == 1
    assert result[0].name == "AK-47"
    assert result[0].side == "buy"  # + → buy
    assert result[0].price is None  # no price div


def test_parse_market_history_html_gainloss_minus():
    """Sinal '-' marca como sell."""
    html = (
        '<div class="market_listing_row" id="history_row_lid1_lid1">'
        '<div class="market_listing_gainorloss">-</div>'
        '<div class="market_listing_item_name">AWP</div>'
        '<div class="market_listing_listed_date">5 Jan</div>'
        "</div>"
    )
    result = steam_api.parse_market_history_html(html)
    assert result[0].side == "sell"


# ── parse_market_history_response ──────────────────────────────────


def test_parse_market_history_response_non_dict():
    assert steam_api.parse_market_history_response("not dict") == []


# ── parse_trade_history_html ───────────────────────────────────────


def test_parse_trade_history_html_empty():
    assert steam_api.parse_trade_history_html("") == []


def test_parse_trade_history_html_no_anchors():
    assert steam_api.parse_trade_history_html("<div>no rows</div>") == []


def test_parse_trade_history_html_no_offerid_no_items_skipped():
    """Row sem tradeofferid e sem items e' pulado."""
    html = (
        '<div class="tradehistoryrow">'
        "<div>stuff</div>"
        "</div>"
    )
    assert steam_api.parse_trade_history_html(html) == []


def test_parse_trade_history_html_with_date_and_time():
    html = (
        '<div class="tradehistoryrow">'
        ' tradeofferid_12345 '
        '<div class="tradehistory_date">1 Jan, 2024</div>'
        '<div class="tradehistory_timestamp">12:30</div>'
        '<span class="history_item_name">AK-47</span>'
        "</div>"
    )
    result = steam_api.parse_trade_history_html(html)
    assert len(result) == 1
    assert result[0].tradeofferid == "12345"
    assert "12:30" in result[0].date_str


# ── Fixture real: myhistory_sample.html ──────────────────────────────

def test_parse_myhistory_fixture():
    """Parseia fixture sintetica com formato real de IDs (sem trailing _).

    O fixture tem 5 rows, cada uma com listing_id diferente, para
    validar que _ROW_ID_RE captura corretamente o ID sem exigir
    underscore final.
    """
    import pathlib
    fixture_path = pathlib.Path(__file__).resolve().parent / "fixtures" / "myhistory_sample.html"
    html = fixture_path.read_text(encoding="utf-8")
    events = steam_api.parse_market_history_html(html)
    assert len(events) == 5, f"Esperado 5, parseou {len(events)}"
    for i, ev in enumerate(events):
        assert ev.listing_id is not None, (
            f"Evento {i} ({ev.name}): listing_id=None"
        )
        assert "_" in ev.listing_id, (
            f"Evento {i}: listing_id '{ev.listing_id}' sem underscore"
        )
    # Verifica dedup: 3 Kilowatt Case no mesmo dia/preco com IDs distintos
    kilowatts = [ev for ev in events if "Kilowatt" in ev.name]
    assert len(kilowatts) == 3
    lids = {ev.listing_id for ev in kilowatts}
    assert len(lids) == 3, (
        f"3 Kilowatt Case com listing_ids colapsados: {lids}"
    )


# ── search_market: camada de descoberta ────────────────────────────


def _search_body(results, total=0, success=True):
    return json.dumps(
        {"success": success, "total_count": total, "results": results})


def test_search_url_monta_facetas_e_prefixo_tag():
    """Chave da faceta vira category_730_X[] e ganha prefixo tag_."""
    url = steam_api._search_url(
        "", {"type": "CSGO_Type_Rifle", "exterior": ["WearCategory2"]},
        "quantity", True, 0, 100, 7)
    assert "category_730_Type%5B%5D=tag_CSGO_Type_Rifle" in url
    assert "category_730_Exterior%5B%5D=tag_WearCategory2" in url
    assert "currency=7" in url and "norender=1" in url


def test_search_url_nao_duplica_prefixo_tag():
    """Tag que ja' vem com tag_ nao vira tag_tag_."""
    url = steam_api._search_url(
        "", {"type": "tag_CSGO_Type_Knife"}, "price", False, 0, 100, 7)
    assert "tag_CSGO_Type_Knife" in url
    assert "tag_tag_" not in url
    assert "sort_dir=asc" in url


def test_search_url_par_invertido_quality_rarity():
    """A Steam inverte: 'category' -> _Quality, 'rarity' -> _Rarity.

    Trocar os dois nao gera erro, so' resultado errado -- por isso o teste.
    """
    url = steam_api._search_url(
        "", {"category": "strange", "rarity": "Rarity_Ancient_Weapon"},
        "quantity", True, 0, 100, 7)
    assert "category_730_Quality%5B%5D=tag_strange" in url
    assert "category_730_Rarity%5B%5D=tag_Rarity_Ancient_Weapon" in url


def test_search_url_ignora_faceta_desconhecida_e_sort_invalido():
    url = steam_api._search_url(
        "ak", {"nao_existe": "x"}, "bogus", True, 0, 100, 7)
    assert "nao_existe" not in url
    assert "sort_column=quantity" in url
    assert "query=ak" in url


def test_parse_search_results_usa_centavos():
    """sell_price vem em centavos da moeda pedida."""
    rows = steam_api._parse_search_results({"results": [
        {"name": "AK-47 | Redline (FT)", "hash_name": "AK-47 | Redline (FT)",
         "sell_price": 12345, "sell_listings": 42},
    ]})
    assert rows[0]["price"] == pytest.approx(123.45)
    assert rows[0]["listings"] == 42


def test_parse_search_results_ignora_sem_nome():
    rows = steam_api._parse_search_results(
        {"results": [{"sell_price": 100}, {"hash_name": "X", "sell_price": 0,
                                           "sell_listings": "nao-numero"}]})
    assert len(rows) == 1
    assert rows[0]["hash_name"] == "X"
    assert rows[0]["listings"] == 0


def test_search_market_ok(monkeypatch):
    body = _search_body(
        [{"hash_name": "Kilowatt Case", "sell_price": 122,
          "sell_listings": 1000}], total=611)
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (200, body))
    status, items, total = steam_api.search_market()
    assert status == steam_api.SEARCH_OK
    assert total == 611
    assert items[0]["hash_name"] == "Kilowatt Case"


def test_search_market_rate_limited(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (429, None))
    status, items, total = steam_api.search_market()
    assert status == steam_api.SEARCH_RATE_LIMITED
    assert items == [] and total == 0


def test_search_market_success_false_vira_erro(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (200, _search_body([], success=False)))
    status, _, _ = steam_api.search_market()
    assert status == steam_api.SEARCH_ERROR


def test_search_market_json_invalido(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (200, "nao json"))
    status, _, _ = steam_api.search_market()
    assert status == steam_api.SEARCH_ERROR


def test_search_market_all_pagina_ate_o_total(monkeypatch):
    """Avanca por len(resultados) e para ao alcancar total_count."""
    def fake(url):
        start = int(url.split("start=")[1].split("&")[0])
        if start >= 20:
            return 200, _search_body([], total=20)
        rows = [{"hash_name": f"item{start + i}", "sell_price": 100,
                 "sell_listings": 1} for i in range(10)]
        return 200, _search_body(rows, total=20)

    monkeypatch.setattr("skinvault.steam_api._http_get", fake)
    status, items, total = steam_api.search_market_all()
    assert status == steam_api.SEARCH_OK
    assert total == 20
    assert len(items) == 20
    assert items[0]["hash_name"] == "item0"
    assert items[-1]["hash_name"] == "item19"


def test_search_market_all_respeita_max_items(monkeypatch):
    rows = [{"hash_name": f"i{i}", "sell_price": 100, "sell_listings": 1}
            for i in range(10)]
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (200, _search_body(rows, total=9999)))
    status, items, _ = steam_api.search_market_all(max_items=25)
    assert status == steam_api.SEARCH_OK
    assert len(items) == 25


def test_search_market_all_para_em_pagina_vazia(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (200, _search_body([], total=500)))
    status, items, _ = steam_api.search_market_all()
    assert status == steam_api.SEARCH_OK
    assert items == []


# ── _find_query: exato tem que vencer substring ────────────────────


def _q(nome, data):
    return {"queryKey": ["market", "pricehistory", 730, nome],
            "state": {"data": data}}


AK_FT = "AK-47 | Redline (Field-Tested)"


def test_find_query_exato_vence_souvenir_que_vem_antes():
    """Caso real do SSR: Souvenir aparece antes e CONTEM o nome pedido.

    Medido em 28/07/2026 numa listing page real -- a Souvenir tinha 1 ponto
    de historico e a correta 5188, na mesma resposta.
    """
    queries = [
        _q("Souvenir AK-47 | Redline (Field-Tested)", "souvenir"),
        _q(AK_FT, "correto"),
        _q("StatTrak™ AK-47 | Redline (Field-Tested)", "stattrak"),
    ]
    assert _find_query(queries, "pricehistory", AK_FT) == "correto"


def test_find_query_exato_vence_mesmo_sendo_o_ultimo():
    """A escolha nao pode depender da ordem de iteracao do SSR."""
    queries = [
        _q("StatTrak™ AK-47 | Redline (Field-Tested)", "stattrak"),
        _q("Souvenir AK-47 | Redline (Field-Tested)", "souvenir"),
        _q(AK_FT, "correto"),
    ]
    assert _find_query(queries, "pricehistory", AK_FT) == "correto"


def test_find_query_substring_ainda_funciona_sem_exato():
    """Compatibilidade: nome parcial do chamador continua casando."""
    queries = [_q(AK_FT, "ak_ft")]
    assert _find_query(queries, "pricehistory", "AK-47 | Redline") == "ak_ft"


def test_find_query_loose_nao_ganha_do_exato():
    """Com exato disponivel, loose_match nao deve desviar pra outro wear."""
    queries = [
        _q("AK-47 | Redline (Minimal Wear)", "outro_wear"),
        _q(AK_FT, "correto"),
    ]
    assert _find_query(
        queries, "pricehistory", AK_FT, loose_match=True) == "correto"


def test_find_query_loose_so_quando_nao_ha_exato_nem_substring():
    """Comportamento do orderbook: SSR so' traz um wear, aceita o root."""
    queries = [_q("AK-47 | Redline (Minimal Wear)", "mw")]
    assert _find_query(queries, "orderbook", AK_FT) is None
    assert _find_query(
        queries, "pricehistory", AK_FT, loose_match=True) == "mw"


def test_find_query_ignora_case_no_exato():
    queries = [_q("ak-47 | redline (field-tested)", "case_diff")]
    assert _find_query(queries, "pricehistory", AK_FT) == "case_diff"


# ── _collect_variants: colher as irmas da mesma pagina ─────────────


def test_collect_variants_pega_todas_as_series():
    queries = [
        _q(AK_FT, {"prices": [1, 2, 3]}),
        _q("AK-47 | Redline (Minimal Wear)", {"prices": [1, 2]}),
        _q("StatTrak™ AK-47 | Redline (Field-Tested)", {"prices": [1]}),
    ]
    v = steam_api._collect_variants(queries)
    assert set(v) == {
        AK_FT,
        "AK-47 | Redline (Minimal Wear)",
        "StatTrak™ AK-47 | Redline (Field-Tested)",
    }
    assert v[AK_FT] == [1, 2, 3]


def test_collect_variants_omite_series_vazias():
    queries = [
        _q(AK_FT, {"prices": []}),
        _q("AK-47 | Redline (Well-Worn)", {"prices": [1]}),
    ]
    v = steam_api._collect_variants(queries)
    assert AK_FT not in v
    assert v == {"AK-47 | Redline (Well-Worn)": [1]}


def test_collect_variants_ignora_outras_chaves_e_querykey_curta():
    queries = [
        {"queryKey": ["market", "orderbook", 730, AK_FT],
         "state": {"data": {"prices": [1, 2]}}},
        {"queryKey": ["market", "pricehistory"],
         "state": {"data": {"prices": [1, 2]}}},
        {"queryKey": "nao e' lista", "state": {"data": {"prices": [1]}}},
    ]
    assert steam_api._collect_variants(queries) == {}


def test_collect_variants_aceita_data_como_lista_crua():
    queries = [_q(AK_FT, [{"t": 1}])]
    assert steam_api._collect_variants(queries) == {AK_FT: [{"t": 1}]}


# ── facetas: catalogo ao vivo ──────────────────────────────────────


_FACETS_RAW = {
    "Rarity": {
        "appid": 730, "name": "Rarity", "localized_name": "Quality",
        "tags": {"Rarity_Ancient_Weapon": {"localized_name": "Covert"}},
    },
    "Quality": {
        "appid": 730, "name": "Quality", "localized_name": "Category",
        "tags": {"normal": {"localized_name": "Normal"},
                 "strange": {"localized_name": "StatTrak™"}},
    },
}


def test_normalize_facets_usa_name_como_chave():
    """A chave e' `name` (vai na URL), nao o localized_name (rotulo de UI)."""
    f = steam_api._normalize_facets(_FACETS_RAW)
    assert set(f) == {"Rarity", "Quality"}
    # O par invertido da Steam preservado: chave Rarity, rotulo "Quality".
    assert f["Rarity"]["label"] == "Quality"
    assert f["Quality"]["label"] == "Category"
    assert f["Quality"]["tags"]["strange"] == "StatTrak™"


def test_normalize_facets_tolera_lixo():
    assert steam_api._normalize_facets(None) == {}
    assert steam_api._normalize_facets({"a": "nao e' dict"}) == {}
    assert steam_api._normalize_facets({"a": {"sem_name": 1}}) == {}


def test_normalize_facets_tag_sem_metadata():
    f = steam_api._normalize_facets(
        {"T": {"name": "Type", "tags": {"CSGO_Type_Rifle": None}}})
    assert f["Type"]["tags"]["CSGO_Type_Rifle"] == "CSGO_Type_Rifle"


def test_collect_facets_acha_no_ssr():
    queries = [
        {"queryKey": ["market", "pricehistory", 730, AK_FT],
         "state": {"data": {"prices": [1]}}},
        {"queryKey": ["market", "app_facets", 730],
         "state": {"data": _FACETS_RAW}},
    ]
    f = steam_api._collect_facets(queries)
    assert f["Quality"]["tags"]["normal"] == "Normal"


def test_collect_facets_ausente_devolve_vazio():
    assert steam_api._collect_facets([]) == {}


def test_fetch_market_facets_ok(monkeypatch):
    body = json.dumps({"success": True, "facets": _FACETS_RAW})
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (200, body))
    f = steam_api.fetch_market_facets()
    assert f["Rarity"]["tags"]["Rarity_Ancient_Weapon"] == "Covert"


def test_fetch_market_facets_falha_devolve_vazio(monkeypatch):
    monkeypatch.setattr("skinvault.steam_api._http_get",
                        lambda url: (500, None))
    assert steam_api.fetch_market_facets() == {}
    monkeypatch.setattr(
        "skinvault.steam_api._http_get",
        lambda url: (200, json.dumps({"success": False})))
    assert steam_api.fetch_market_facets() == {}


def test_market_facets_bate_com_as_chaves_do_catalogo():
    """MARKET_FACETS so' pode apontar pra chaves que a Steam expoe."""
    f = steam_api._normalize_facets(_FACETS_RAW)
    for chave in ("Rarity", "Quality"):
        assert chave in f
    assert steam_api.MARKET_FACETS["rarity"] == "Rarity"
    assert steam_api.MARKET_FACETS["category"] == "Quality"
