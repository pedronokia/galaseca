"""Testes dos endpoints autenticados de steam_api (F10).

Os parsers sao puros (regex sobre HTML); fetches sao mockados via monkeypatch
em _http_get_auth, sem rede.
"""
from __future__ import annotations

import json

import pytest

from skinvault import steam_api
from skinvault.steam_api import (
    MarketEvent,
    TradeEvent,
    fetch_market_history,
    fetch_my_listings,
    fetch_trade_history_html,
    parse_market_history_html,
    parse_market_history_response,
    parse_trade_history_html,
)
from skinvault.steam_session import SteamSession


SAMPLE_STEAMID = "76561198000000001"


def _session() -> SteamSession:
    return SteamSession(
        steamid=SAMPLE_STEAMID,
        cookies={
            "sessionid": "abc",
            "steamLoginSecure": f"{SAMPLE_STEAMID}%7C%7Ctok",
        },
    )


# ── Fixtures de HTML --------------------------------------------------

MARKET_HISTORY_ROW_BUY = '''
<div class="market_listing_row market_recent_listing_row" id="history_row_730_2147483647_event">
    <div class="market_listing_left_cell market_listing_gainorloss_cell">
        <div class="market_listing_gainorloss">+</div>
    </div>
    <div class="market_listing_right_cell market_listing_my_price">
        <span class="market_table_value">
            <span class="market_listing_price">R$ 25,50</span>
        </span>
        <div class="market_listing_listed_date_combined">
            <div class="market_listing_listed_date">15 Mar</div>
        </div>
    </div>
    <div class="market_listing_item_name_block">
        <span class="market_listing_item_name">AK-47 | Redline (Field-Tested)</span>
    </div>
</div>
'''

MARKET_HISTORY_ROW_SELL = '''
<div class="market_listing_row market_recent_listing_row" id="history_row_730_42_event">
    <div class="market_listing_left_cell market_listing_gainorloss_cell">
        <div class="market_listing_gainorloss">-</div>
    </div>
    <div class="market_listing_right_cell market_listing_my_price">
        <span class="market_table_value">
            <span class="market_listing_price">R$ 130,00</span>
        </span>
        <div class="market_listing_listed_date_combined">
            <div class="market_listing_listed_date">14 Mar</div>
        </div>
    </div>
    <div class="market_listing_item_name_block">
        <span class="market_listing_item_name">AWP | Asiimov (FT)</span>
    </div>
</div>
'''

MARKET_HISTORY_ROW_WITH_ICON = '''
<div class="market_listing_row market_recent_listing_row" id="history_row_730_99887_event">
    <div class="market_listing_left_cell market_listing_gainorloss_cell">
        <div class="market_listing_gainorloss">-</div>
    </div>
    <div class="market_listing_left_cell market_listing_item_img_container">
        <img class="market_listing_item_img" src="https://community.cloudflare.steamstatic.com/economy/image/abc123def456:ghi789/62fx62f" />
    </div>
    <div class="market_listing_right_cell market_listing_my_price">
        <span class="market_table_value">
            <span class="market_listing_price">R$ 4,19</span>
        </span>
        <div class="market_listing_listed_date_combined">
            <div class="market_listing_listed_date">9 Oct</div>
        </div>
    </div>
    <div class="market_listing_item_name_block">
        <span class="market_listing_item_name">Kilowatt Case</span>
    </div>
</div>
'''

MARKET_HISTORY_ROW_LISTED = '''
<div class="market_listing_row market_recent_listing_row" id="history_row_listing_99_event">
    <div class="market_listing_left_cell market_listing_gainorloss_cell">
        <div class="market_listing_gainorloss"> </div>
    </div>
    <div class="market_listing_right_cell market_listing_my_price">
        <span class="market_table_value">
            <span class="market_listing_price">R$ 10,00</span>
        </span>
        <div class="market_listing_listed_date_combined">
            <div class="market_listing_listed_date">13 Mar</div>
        </div>
    </div>
    <div class="market_listing_item_name_block">
        <span class="market_listing_item_name">USP-S | Kill Confirmed (FT)</span>
    </div>
</div>
'''

TRADE_HISTORY_HTML = '''
<div class="tradehistoryrow">
    <div class="tradehistory_date">5 March 2026
        <div class="tradehistory_timestamp">14:32</div>
    </div>
    <div class="tradehistory_event_description">
        Traded with <a href="https://steamcommunity.com/profiles/76561198111111111/">SomeUser</a>
    </div>
    <div data-tradeofferid="987654321">
        <span class="history_item_name">AK-47 | Redline (Field-Tested)</span>
        <span class="history_item_name">USP-S | Kill Confirmed (FT)</span>
    </div>
</div>
<div class="tradehistoryrow">
    <div class="tradehistory_date">3 March 2026
        <div class="tradehistory_timestamp">09:10</div>
    </div>
    <div class="tradehistory_event_description">
        Traded with <a href="https://steamcommunity.com/profiles/76561198222222222/">Other</a>
    </div>
    <div data-tradeofferid="111222333">
        <span class="history_item_name">AWP | Asiimov (FT)</span>
    </div>
</div>
'''


# ── Tests: parse_market_history_html ---------------------------------

class TestParseMarketHistory:
    def test_parses_buy_event(self):
        events = parse_market_history_html(MARKET_HISTORY_ROW_BUY)
        assert len(events) == 1
        e = events[0]
        assert e.name == "AK-47 | Redline (Field-Tested)"
        assert e.side == "buy"
        assert e.price == pytest.approx(25.50)
        assert e.date_str == "15 Mar"
        assert e.listing_id == "730_2147483647"

    def test_parses_sell_event(self):
        events = parse_market_history_html(MARKET_HISTORY_ROW_SELL)
        assert len(events) == 1
        assert events[0].side == "sell"
        assert events[0].price == pytest.approx(130.0)

    def test_parses_listed_event(self):
        events = parse_market_history_html(MARKET_HISTORY_ROW_LISTED)
        assert len(events) == 1
        assert events[0].side == "listed"

    def test_parses_multiple_rows(self):
        combined = MARKET_HISTORY_ROW_BUY + MARKET_HISTORY_ROW_SELL + MARKET_HISTORY_ROW_LISTED
        events = parse_market_history_html(combined)
        assert len(events) == 3
        assert [e.side for e in events] == ["buy", "sell", "listed"]

    def test_empty_html(self):
        assert parse_market_history_html("") == []

    def test_html_without_rows(self):
        assert parse_market_history_html("<div>nothing</div>") == []

    def test_response_wrapper(self):
        resp = {"success": True, "results_html": MARKET_HISTORY_ROW_BUY,
                "total_count": 1}
        events = parse_market_history_response(resp)
        assert len(events) == 1
        assert events[0].side == "buy"

    def test_response_wrapper_invalid(self):
        assert parse_market_history_response(None) == []
        assert parse_market_history_response({}) == []

    def test_parses_icon_url_from_html(self):
        """Quando o HTML traz <img src=.../economy/image/<hash>/...>, captura."""
        events = parse_market_history_html(MARKET_HISTORY_ROW_WITH_ICON)
        assert len(events) == 1
        assert events[0].icon_url == "abc123def456:ghi789"

    def test_icon_url_none_quando_html_sem_img(self):
        """Sem <img economy/image/...>, icon_url fica None (compat antigo)."""
        events = parse_market_history_html(MARKET_HISTORY_ROW_BUY)
        assert events[0].icon_url is None


# ── Tests: parse_trade_history_html ----------------------------------

class TestParseTradeHistory:
    def test_parses_trade_offer(self):
        events = parse_trade_history_html(TRADE_HISTORY_HTML)
        assert len(events) == 2
        first = events[0]
        assert first.tradeofferid == "987654321"
        assert first.partner_steamid == "76561198111111111"
        assert "5 March 2026" in first.date_str
        assert "14:32" in first.date_str
        assert "AK-47 | Redline (Field-Tested)" in first.items_given
        assert "USP-S | Kill Confirmed (FT)" in first.items_given

    def test_parses_second_trade(self):
        events = parse_trade_history_html(TRADE_HISTORY_HTML)
        second = events[1]
        assert second.tradeofferid == "111222333"
        assert second.partner_steamid == "76561198222222222"
        assert second.items_given == ["AWP | Asiimov (FT)"]

    def test_empty_html(self):
        assert parse_trade_history_html("") == []

    def test_no_trade_rows(self):
        assert parse_trade_history_html("<html>nada</html>") == []


# ── Tests: fetch wrappers (mock _http_get_auth) ----------------------

class TestFetchMarketHistory:
    def test_returns_parsed_json(self, monkeypatch):
        payload = {"success": True, "total_count": 1,
                   "results_html": MARKET_HISTORY_ROW_BUY}

        def mock_get(url, session, timeout=20.0, extra_headers=None):
            assert "myhistory/render" in url
            return 200, json.dumps(payload)

        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        result = fetch_market_history(_session())
        assert result == payload

    def test_returns_none_on_http_error(self, monkeypatch):
        def mock_get(url, session, timeout=20.0, extra_headers=None):
            return 401, None
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        assert fetch_market_history(_session()) is None

    def test_returns_none_on_invalid_json(self, monkeypatch):
        def mock_get(url, session, timeout=20.0, extra_headers=None):
            return 200, "<html>not json</html>"
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        assert fetch_market_history(_session()) is None

    def test_paginates_via_start_count(self, monkeypatch):
        captured: dict = {}

        def mock_get(url, session, timeout=20.0, extra_headers=None):
            captured["url"] = url
            return 200, "{}"

        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        fetch_market_history(_session(), start=200, count=50)
        assert "start=200" in captured["url"]
        assert "count=50" in captured["url"]


class TestFetchMyListings:
    def test_returns_parsed_json(self, monkeypatch):
        payload = {"success": True, "num_active_listings": 3}

        def mock_get(url, session, timeout=20.0, extra_headers=None):
            assert "mylistings/render" in url
            return 200, json.dumps(payload)

        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        result = fetch_my_listings(_session())
        assert result == payload

    def test_returns_none_when_unauth(self, monkeypatch):
        def mock_get(url, session, timeout=20.0, extra_headers=None):
            return 401, None
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        assert fetch_my_listings(_session()) is None


class TestFetchTradeHistoryHtml:
    def test_returns_html_body(self, monkeypatch):
        def mock_get(url, session, timeout=20.0, extra_headers=None):
            assert "/tradehistory" in url
            assert SAMPLE_STEAMID in url
            return 200, TRADE_HISTORY_HTML

        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        html = fetch_trade_history_html(_session())
        assert html is not None
        assert "tradehistoryrow" in html

    def test_returns_none_without_steamid(self, monkeypatch):
        s = SteamSession(steamid="", cookies={"sessionid": "x"})
        assert fetch_trade_history_html(s) is None

    def test_uses_page_param(self, monkeypatch):
        captured: dict = {}

        def mock_get(url, session, timeout=20.0, extra_headers=None):
            captured["url"] = url
            return 200, ""

        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        fetch_trade_history_html(_session(), page=3)
        assert "p=3" in captured["url"]


# ── Tests: fetch_inventory_authed -----------------------------------------

INV_OK = "ok"
INV_PRIVATE = "private"
INV_RATE_LIMITED = "rate_limited"
INV_EMPTY = "empty"
INV_ERROR = "error"


class TestFetchInventoryAuthed:
    def test_private_403(self, monkeypatch):
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (403, None)
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_PRIVATE
        assert items == []

    def test_rate_limited_429(self, monkeypatch):
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (429, None)
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_RATE_LIMITED
        assert items == []

    def test_error_on_non_200(self, monkeypatch):
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (500, None)
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_ERROR
        assert items == []

    def test_error_on_none_body_with_200(self, monkeypatch):
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (200, None)
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_ERROR
        assert items == []

    def test_invalid_json(self, monkeypatch):
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (200, "not-json")
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_ERROR
        assert items == []

    def test_empty_no_assets(self, monkeypatch):
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (200, "{}")
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_EMPTY
        assert items == []

    def test_empty_no_marketable(self, monkeypatch):
        data = json.dumps({"assets": [], "descriptions": []})
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (200, data)
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_EMPTY
        assert items == []

    def test_returns_items(self, monkeypatch):
        payload = {
            "assets": [
                {"classid": "1", "instanceid": "0", "amount": "1"}
            ],
            "descriptions": [
                {"classid": "1", "instanceid": "0",
                 "marketable": 1, "market_hash_name": "AK-47 | Redline (FT)"}
            ],
        }
        mock_get = lambda url, session, timeout=20.0, extra_headers=None: (200, json.dumps(payload))
        monkeypatch.setattr(steam_api, "_http_get_auth", mock_get)
        status, items = steam_api.fetch_inventory_authed(_session())
        assert status == INV_OK
        assert len(items) == 1
        assert items[0]["name"] == "AK-47 | Redline (FT)"


# ── Tests: _http_get_auth (real urllib) ----------------------------------


class TestHttpGetAuth:
    """Testa _http_get_auth mockando urllib diretamente."""

    def test_success(self, monkeypatch):
        class MockResp:
            status = 200
            def read(self):
                return b'{"ok": true}'

        class MockUrlOpen:
            def __enter__(self):
                return MockResp()
            def __exit__(self, *a):
                pass

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=20.0: MockUrlOpen())
        code, body = steam_api._http_get_auth("https://example.com", _session())
        assert code == 200
        assert body == '{"ok": true}'

    def test_success_with_extra_headers(self, monkeypatch):
        class MockResp:
            status = 200
            def read(self):
                return b"ok"

        class MockUrlOpen:
            def __enter__(self):
                return MockResp()
            def __exit__(self, *a):
                pass

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=20.0: MockUrlOpen())

        def check_headers(url, session, timeout=20.0, extra_headers=None):
            # Verifica que o Referer foi passado
            assert extra_headers == {"Referer": "https://steamcommunity.com/profiles/x"}
            return steam_api._http_get_auth(url, session, timeout, extra_headers)

        code, body = check_headers(
            "https://example.com", _session(),
            extra_headers={"Referer": "https://steamcommunity.com/profiles/x"}
        )
        assert code == 200

    def test_http_error_returns_code(self, monkeypatch):
        def raiser(*a, **k):
            import urllib.error
            try:
                raise urllib.error.HTTPError(
                    "https://example.com", 429, "Too Many", {},
                    None
                )
            except urllib.error.HTTPError:
                raise
        monkeypatch.setattr("urllib.request.urlopen", raiser)
        code, body = steam_api._http_get_auth("https://example.com", _session())
        assert code == 429
        assert body is None

    def test_generic_exception_returns_zero(self, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda req, timeout=20.0: (_ for _ in ()).throw(ValueError("boom"))
        )
        code, body = steam_api._http_get_auth("https://example.com", _session())
        assert code == 0
        assert body is None
