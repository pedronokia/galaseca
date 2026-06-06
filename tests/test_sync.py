"""Testes do orquestrador de sync (F10)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skinvault import portfolio as portfolio_mod
from skinvault import steam_api, sync
from skinvault.steam_api import MarketEvent, TradeEvent
from skinvault.steam_session import SteamSession


SAMPLE_STEAMID = "76561198000000001"


def _session() -> SteamSession:
    return SteamSession(
        steamid=SAMPLE_STEAMID,
        cookies={
            "sessionid": "x",
            "steamLoginSecure": f"{SAMPLE_STEAMID}%7C%7Ctok",
        },
    )


# ── sync_inventory ----------------------------------------------------

class TestSyncInventory:
    def test_adds_new_items_with_source_steam(self, tmp_path: Path, monkeypatch):
        portfolio_path = tmp_path / "portfolio.json"

        def mock_fetch(session):
            return steam_api.INV_OK, [
                {"name": "AK-47 | Redline (FT)", "quantity": 1,
                 "tradable": True},
                {"name": "AWP | Asiimov (FT)", "quantity": 2,
                 "tradable": False},
            ]

        monkeypatch.setattr(steam_api, "fetch_inventory_authed", mock_fetch)
        result = sync.sync_inventory(_session(), path=portfolio_path)
        assert result["status"] == "ok"
        assert result["added"] == 2

        positions = portfolio_mod.load_portfolio(portfolio_path)
        assert len(positions) == 2
        assert all(p["source"] == "steam_sync" for p in positions)
        assert all(p["cost"] == 0.0 for p in positions)
        names = {p["name"] for p in positions}
        assert names == {"AK-47 | Redline (FT)", "AWP | Asiimov (FT)"}

    def test_preserves_manual_positions(self, tmp_path: Path, monkeypatch):
        portfolio_path = tmp_path / "portfolio.json"
        portfolio_mod.add_position(
            "AK-47 | Redline (FT)", cost=50.0, quantity=1,
            path=portfolio_path, source="manual",
        )

        def mock_fetch(session):
            return steam_api.INV_OK, [
                {"name": "AK-47 | Redline (FT)", "quantity": 1,
                 "tradable": True},
                {"name": "AWP | Asiimov (FT)", "quantity": 1,
                 "tradable": True},
            ]

        monkeypatch.setattr(steam_api, "fetch_inventory_authed", mock_fetch)
        result = sync.sync_inventory(_session(), path=portfolio_path)
        # AK manual ja existe, so AWP entra
        assert result["added"] == 1
        positions = portfolio_mod.load_portfolio(portfolio_path)
        assert len(positions) == 2
        ak = next(p for p in positions if "AK-47" in p["name"])
        assert ak["source"] == "manual"
        assert ak["cost"] == 50.0

    def test_idempotent(self, tmp_path: Path, monkeypatch):
        portfolio_path = tmp_path / "portfolio.json"

        def mock_fetch(session):
            return steam_api.INV_OK, [
                {"name": "X", "quantity": 1, "tradable": True},
            ]
        monkeypatch.setattr(steam_api, "fetch_inventory_authed", mock_fetch)
        sync.sync_inventory(_session(), path=portfolio_path)
        result2 = sync.sync_inventory(_session(), path=portfolio_path)
        # Segunda execucao nao deve adicionar nada
        assert result2["added"] == 0
        positions = portfolio_mod.load_portfolio(portfolio_path)
        assert len(positions) == 1

    def test_returns_error_status_on_private(self, tmp_path: Path, monkeypatch):
        portfolio_path = tmp_path / "portfolio.json"

        def mock_fetch(session):
            return steam_api.INV_PRIVATE, []
        monkeypatch.setattr(steam_api, "fetch_inventory_authed", mock_fetch)
        result = sync.sync_inventory(_session(), path=portfolio_path)
        assert result["status"] == "private"
        assert result["added"] == 0


# ── sync_market_history -----------------------------------------------

def _market_event_dict(name="AK-47", side="buy", price=25.0,
                       listing_id="730_1") -> dict:
    return {
        "name": name, "side": side, "price": price,
        "date_str": "15 Mar", "listing_id": listing_id,
    }


class TestSyncMarketHistory:
    def test_persists_new_events(self, tmp_path: Path, monkeypatch):
        events_path = tmp_path / "events.json"

        calls = [0]

        def mock_fetch(session, start=0, count=100, appid=None):
            calls[0] += 1
            if calls[0] == 1:
                return {"success": True, "total_count": 2,
                        "results_html": "_dummy_"}
            return None

        sample_events = [
            MarketEvent("AK-47", "buy", 25.0, "15 Mar", "730_1"),
            MarketEvent("AWP", "sell", 100.0, "14 Mar", "730_2"),
        ]
        monkeypatch.setattr(steam_api, "fetch_market_history", mock_fetch)
        monkeypatch.setattr(steam_api, "parse_market_history_response",
                            lambda r, default_appid=None: sample_events)
        # Pular sleep
        monkeypatch.setattr("skinvault.sync.time.sleep", lambda s: None)

        result = sync.sync_market_history(_session(), path=events_path,
                                          max_pages=2)
        assert result["new"] == 2
        assert result["total"] == 2

        stored = json.loads(events_path.read_text(encoding="utf-8"))
        assert len(stored) == 2
        assert {e["name"] for e in stored} == {"AK-47", "AWP"}

    def test_dedupe_via_listing_id(self, tmp_path: Path, monkeypatch):
        events_path = tmp_path / "events.json"
        # Pre-popula com um evento
        events_path.write_text(json.dumps([
            {"name": "AK-47", "side": "buy", "price": 25.0,
             "date_str": "15 Mar", "listing_id": "730_1"},
        ]), encoding="utf-8")

        def mock_fetch(session, start=0, count=100, appid=None):
            if start == 0:
                return {"success": True, "total_count": 2,
                        "results_html": "_dummy_"}
            return None

        sample_events = [
            MarketEvent("AK-47", "buy", 25.0, "15 Mar", "730_1"),  # dup
            MarketEvent("AWP", "sell", 100.0, "14 Mar", "730_2"),   # novo
        ]
        monkeypatch.setattr(steam_api, "fetch_market_history", mock_fetch)
        monkeypatch.setattr(steam_api, "parse_market_history_response",
                            lambda r, default_appid=None: sample_events)
        monkeypatch.setattr("skinvault.sync.time.sleep", lambda s: None)

        result = sync.sync_market_history(_session(), path=events_path,
                                          max_pages=1)
        assert result["new"] == 1
        assert result["total"] == 2

    def test_idempotent_consecutive_runs(self, tmp_path: Path, monkeypatch):
        events_path = tmp_path / "events.json"

        def mock_fetch(session, start=0, count=100, appid=None):
            if start == 0:
                return {"success": True, "total_count": 1,
                        "results_html": "_"}
            return None

        sample = [MarketEvent("AK-47", "buy", 25.0, "15 Mar", "730_1")]
        monkeypatch.setattr(steam_api, "fetch_market_history", mock_fetch)
        monkeypatch.setattr(steam_api, "parse_market_history_response",
                            lambda r, default_appid=None: sample)
        monkeypatch.setattr("skinvault.sync.time.sleep", lambda s: None)

        sync.sync_market_history(_session(), path=events_path, max_pages=1)
        result2 = sync.sync_market_history(_session(), path=events_path,
                                           max_pages=1)
        assert result2["new"] == 0
        assert result2["total"] == 1

    def test_no_fetch_returns_empty(self, tmp_path: Path, monkeypatch):
        events_path = tmp_path / "events.json"

        def mock_fetch(session, start=0, count=100, appid=None):
            return None

        monkeypatch.setattr(steam_api, "fetch_market_history", mock_fetch)
        result = sync.sync_market_history(_session(), path=events_path)
        assert result["new"] == 0


class TestMarketEventKey:
    def test_uses_listing_id_when_present(self):
        e = _market_event_dict(listing_id="730_42")
        assert sync.market_event_key(e) == "L:730_42"

    def test_falls_back_to_composite(self):
        e = _market_event_dict(listing_id=None)
        key = sync.market_event_key(e)
        assert "AK-47" in key
        assert "buy" in key

    def test_different_events_different_keys(self):
        e1 = _market_event_dict(name="AK-47", listing_id=None)
        e2 = _market_event_dict(name="AWP", listing_id=None)
        assert sync.market_event_key(e1) != sync.market_event_key(e2)

    def test_composite_key_stable_across_year_rollover(self):
        """Steam omite ano para o ano corrente e usa "5 Jan, 2024" depois.

        Sem normalizacao, o mesmo evento de Jan 2024 gerava chaves
        distintas em syncs feitos em 2024 ("5 Jan") vs 2025 ("5 Jan, 2024"),
        causando duplicacao anual quando listing_id estava ausente.
        """
        e_short = _market_event_dict(listing_id=None)
        e_short["date_str"] = "5 Jan"
        e_long = _market_event_dict(listing_id=None)
        e_long["date_str"] = "5 Jan, 2024"
        # Roda em 2025-06-15 (now fixo via monkey nao da pra usar aqui;
        # usamos uma data fixa que torna "5 Jan" → 2025-01-05 e "5 Jan, 2024"
        # → 2024-01-05). Em 2024-06+, ambos ainda mapeiam pra mesma data
        # quando "5 Jan" → 2024-01-05 e "5 Jan, 2024" → 2024-01-05.
        # Como nao temos controle de now nesse teste, validamos so que a
        # forma "5 Jan, 2024" produz a chave esperada (2024-01-05).
        k_long = sync.market_event_key(e_long)
        assert "2024-01-05" in k_long
        # E que "5 Jan" produz UMA data ISO (nao o date_str cru).
        k_short = sync.market_event_key(e_short)
        assert "5 Jan" not in k_short  # nao guarda mais o cru
        assert "-01-05" in k_short      # virou ISO


# ── sync_trade_offers -------------------------------------------------

class TestSyncTradeOffers:
    def test_persists_new_trades(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "trades.json"

        page_counter = [0]

        def mock_fetch(session, page=1):
            page_counter[0] += 1
            if page_counter[0] == 1:
                return "_html_"
            return None

        monkeypatch.setattr(steam_api, "fetch_trade_history_html", mock_fetch)
        sample_trades = [
            TradeEvent("999", "76561198000000002", "5 March", ["AK"], []),
            TradeEvent("888", "76561198000000003", "4 March", ["AWP"], []),
        ]
        monkeypatch.setattr(steam_api, "parse_trade_history_html",
                            lambda h: sample_trades)
        monkeypatch.setattr("skinvault.sync.time.sleep", lambda s: None)

        result = sync.sync_trade_offers(_session(), path=path, max_pages=2)
        assert result["new"] == 2
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert {t["tradeofferid"] for t in stored} == {"999", "888"}

    def test_dedupe_by_tradeofferid(self, tmp_path: Path, monkeypatch):
        path = tmp_path / "trades.json"
        path.write_text(json.dumps([
            {"tradeofferid": "999", "items_given": ["AK"]},
        ]), encoding="utf-8")

        def mock_fetch(session, page=1):
            return "_html_" if page == 1 else None

        monkeypatch.setattr(steam_api, "fetch_trade_history_html", mock_fetch)
        sample = [
            TradeEvent("999", None, "", ["AK"], []),       # dup
            TradeEvent("888", None, "", ["AWP"], []),      # novo
        ]
        monkeypatch.setattr(steam_api, "parse_trade_history_html",
                            lambda h: sample)
        monkeypatch.setattr("skinvault.sync.time.sleep", lambda s: None)

        result = sync.sync_trade_offers(_session(), path=path, max_pages=1)
        assert result["new"] == 1


# ── sync_all orquestrador --------------------------------------------

class TestSyncAll:
    def test_runs_all_four_and_collects_results(self, tmp_path: Path,
                                                monkeypatch):
        monkeypatch.setattr(sync, "sync_inventory",
                            lambda s: {"status": "ok", "added": 1, "skipped": 0})
        monkeypatch.setattr(sync, "sync_market_history",
                            lambda s: {"new": 5, "total": 5, "fetched": 5})
        monkeypatch.setattr(sync, "sync_listings",
                            lambda s: {"count": 3, "status": "ok"})
        monkeypatch.setattr(sync, "sync_trade_offers",
                            lambda s: {"new": 2, "total": 2, "fetched": 2})

        progress: list[tuple[str, dict]] = []
        result = sync.sync_all(_session(),
                               progress_cb=lambda step, r: progress.append((step, r)))
        assert set(result.keys()) == {"inventory", "market", "listings", "trades"}
        assert [step for step, _ in progress] == [
            "inventory", "market", "listings", "trades"
        ]

    def test_exception_in_step_is_caught(self, monkeypatch):
        def boom(s):
            raise RuntimeError("boom")

        monkeypatch.setattr(sync, "sync_inventory", boom)
        monkeypatch.setattr(sync, "sync_market_history",
                            lambda s: {"new": 0})
        monkeypatch.setattr(sync, "sync_listings", lambda s: {"count": 0})
        monkeypatch.setattr(sync, "sync_trade_offers", lambda s: {"new": 0})

        result = sync.sync_all(_session())
        assert "error" in result["inventory"]
        assert "boom" in result["inventory"]["error"]
