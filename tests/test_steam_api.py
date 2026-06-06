"""Testes do steam_api -- logica pura (sem rede)."""
from __future__ import annotations

import json

import pytest

from skinvault.steam_api import (
    _extract_render_context,
    _find_query,
    _js_unescape,
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
