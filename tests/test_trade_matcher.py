"""Testes do pareamento BUY<->SELL de eventos do Steam Market."""
from __future__ import annotations

import time

import pytest

from skinvault import trade_matcher


# ── parse_steam_date ----------------------------------------------------

class TestParseSteamDate:
    def test_returns_none_for_empty(self):
        assert trade_matcher.parse_steam_date("") is None
        assert trade_matcher.parse_steam_date(None) is None  # type: ignore[arg-type]

    def test_returns_none_for_invalid_format(self):
        assert trade_matcher.parse_steam_date("garbage") is None
        assert trade_matcher.parse_steam_date("32 Foo") is None

    def test_invalid_calendar_dates_return_none(self):
        """Regression: time.mktime normalizava silenciosamente datas
        invalidas (31 Apr → 1 Mai, 29 Feb fora de bissexto → 1 Mar,
        99 Jan → ~8 Abr). Agora usamos datetime e essas viram None."""
        now = time.mktime((2025, 6, 15, 12, 0, 0, 0, 0, -1))
        assert trade_matcher.parse_steam_date("31 Apr", now=now) is None
        assert trade_matcher.parse_steam_date("99 Jan", now=now) is None
        # 29 Feb em ano nao bissexto vira None
        assert trade_matcher.parse_steam_date(
            "29 Feb, 2025", now=now
        ) is None

    def test_29_feb_valid_in_leap_year(self):
        now = time.mktime((2025, 6, 15, 12, 0, 0, 0, 0, -1))
        ts = trade_matcher.parse_steam_date("29 Feb, 2024", now=now)
        assert ts is not None
        lt = time.localtime(ts)
        assert (lt.tm_year, lt.tm_mon, lt.tm_mday) == (2024, 2, 29)

    def test_parses_day_month_with_implicit_year(self):
        # Em 15-Jun-2026: "10 Mar" deve cair em 2026
        now = time.mktime((2026, 6, 15, 12, 0, 0, 0, 0, -1))
        ts = trade_matcher.parse_steam_date("10 Mar", now=now)
        assert ts is not None
        lt = time.localtime(ts)
        assert (lt.tm_year, lt.tm_mon, lt.tm_mday) == (2026, 3, 10)

    def test_parses_explicit_year(self):
        now = time.mktime((2026, 6, 15, 12, 0, 0, 0, 0, -1))
        ts = trade_matcher.parse_steam_date("10 Mar, 2024", now=now)
        assert ts is not None
        lt = time.localtime(ts)
        assert (lt.tm_year, lt.tm_mon, lt.tm_mday) == (2024, 3, 10)

    def test_implicit_year_rolls_back_when_in_future(self):
        # Em 15-Mar-2026: "10 Dec" sem ano cai em 2025 (Dec/2026 e' futuro)
        now = time.mktime((2026, 3, 15, 12, 0, 0, 0, 0, -1))
        ts = trade_matcher.parse_steam_date("10 Dec", now=now)
        assert ts is not None
        assert time.localtime(ts).tm_year == 2025

    def test_parses_time_when_present(self):
        now = time.mktime((2026, 6, 15, 12, 0, 0, 0, 0, -1))
        ts = trade_matcher.parse_steam_date("10 Mar 18:30", now=now)
        assert ts is not None
        lt = time.localtime(ts)
        assert (lt.tm_hour, lt.tm_min) == (18, 30)


# ── match_events --------------------------------------------------------

def _ev(name, side, price, date_str):
    return {"name": name, "side": side, "price": price, "date_str": date_str}


class TestMatchEvents:
    def test_empty_returns_empty(self):
        assert trade_matcher.match_events([]) == []

    def test_unmatched_buy_or_sell_does_not_produce_trade(self):
        events = [
            _ev("AK", "buy", 10.0, "1 Jan"),
            _ev("AWP", "sell", 50.0, "1 Jan"),  # sem buy correspondente
        ]
        result = trade_matcher.match_events(events)
        assert result == []

    def test_simple_pair_calculates_pnl(self):
        # buy 10, sell 15 -> net 15/1.15 = 13.04, pnl = 3.04
        events = [
            _ev("AK", "buy", 10.0, "1 Jan"),
            _ev("AK", "sell", 15.0, "10 Jan"),
        ]
        result = trade_matcher.match_events(events)
        assert len(result) == 1
        c = result[0]
        assert c.name == "AK"
        assert c.buy_price == 10.0
        assert c.sell_price == 15.0
        assert c.pnl == pytest.approx(15.0 / 1.15 - 10.0, abs=0.01)

    def test_fifo_matches_oldest_first(self):
        # Em 15-Jun-2026: 1 Jan, 5 Feb e 10 Mar todas em 2026
        now = time.mktime((2026, 6, 15, 0, 0, 0, 0, 0, -1))
        events = [
            _ev("AK", "buy", 10.0, "1 Jan"),
            _ev("AK", "buy", 12.0, "5 Feb"),
            _ev("AK", "sell", 20.0, "10 Mar"),
            _ev("AK", "sell", 25.0, "20 Mar"),
        ]
        result = trade_matcher.match_events(events, now=now)
        assert len(result) == 2
        # Mais recente primeiro (sort desc por sell_ts)
        # FIFO: buy 10 com sell 20, buy 12 com sell 25
        pairs = {(c.buy_price, c.sell_price) for c in result}
        assert pairs == {(10.0, 20.0), (12.0, 25.0)}

    def test_sell_before_buy_is_skipped(self):
        now = time.mktime((2026, 6, 15, 0, 0, 0, 0, 0, -1))
        events = [
            _ev("AK", "sell", 20.0, "1 Jan"),  # antes do unico buy
            _ev("AK", "buy", 10.0, "5 Feb"),
            _ev("AK", "sell", 25.0, "10 Mar"),
        ]
        result = trade_matcher.match_events(events, now=now)
        assert len(result) == 1
        assert result[0].buy_price == 10.0
        assert result[0].sell_price == 25.0

    def test_invalid_events_ignored(self):
        events = [
            _ev("AK", "buy", None, "1 Jan"),       # sem preco
            _ev("", "buy", 10.0, "1 Jan"),         # sem nome
            _ev("AK", "listed", 10.0, "1 Jan"),    # side desconhecido
            _ev("AK", "buy", 10.0, "1 Jan"),
            _ev("AK", "sell", 15.0, "5 Jan"),
        ]
        result = trade_matcher.match_events(events)
        assert len(result) == 1

    def test_isolates_by_name(self):
        events = [
            _ev("AK", "buy", 10.0, "1 Jan"),
            _ev("AWP", "sell", 50.0, "10 Jan"),
            _ev("AWP", "buy", 40.0, "5 Jan"),
            _ev("AK", "sell", 15.0, "20 Jan"),
        ]
        result = trade_matcher.match_events(events)
        assert len(result) == 2
        by_name = {c.name: c for c in result}
        assert by_name["AK"].buy_price == 10.0
        assert by_name["AWP"].buy_price == 40.0


# ── summarize -----------------------------------------------------------

class TestFindOpenBuys:
    def test_empty_returns_empty(self):
        assert trade_matcher.find_open_buys([]) == []

    def test_returns_buy_when_no_sell(self):
        events = [_ev("AK", "buy", 10.0, "1 Jan")]
        result = trade_matcher.find_open_buys(events)
        assert len(result) == 1
        assert result[0].name == "AK"
        assert result[0].buy_price == 10.0

    def test_returns_only_unpaired_buys_fifo(self):
        # 3 buys, 1 sell -> 1 par fechado, 2 abertos (os mais novos)
        now = time.mktime((2026, 6, 15, 0, 0, 0, 0, 0, -1))
        events = [
            _ev("AK", "buy", 10.0, "1 Jan"),    # pareado com sell 1 Feb
            _ev("AK", "buy", 12.0, "5 Jan"),    # aberto
            _ev("AK", "buy", 14.0, "10 Jan"),   # aberto
            _ev("AK", "sell", 20.0, "1 Feb"),
        ]
        result = trade_matcher.find_open_buys(events, now=now)
        assert len(result) == 2
        prices = sorted(o.buy_price for o in result)
        assert prices == [12.0, 14.0]

    def test_isolates_by_name(self):
        events = [
            _ev("AK", "buy", 10.0, "1 Jan"),    # aberto
            _ev("AWP", "buy", 50.0, "1 Jan"),
            _ev("AWP", "sell", 60.0, "1 Feb"),  # AWP fechado
        ]
        result = trade_matcher.find_open_buys(events)
        assert len(result) == 1
        assert result[0].name == "AK"


class TestSummarize:
    def test_win_rate_is_0_100(self):
        """summarize.win_rate retorna 0-100, nao fracao."""
        trades = [
            trade_matcher.ClosedTrade("X", "1 Jan", 10.0, "5 Jan", 20.0,
                                      0.0, +5.0, 0.5),
        ]
        s = trade_matcher.summarize(trades)
        assert s["win_rate"] == 100.0

    def test_empty(self):
        s = trade_matcher.summarize([])
        assert s == {"count": 0, "total_pnl": 0.0, "winners": 0,
                     "losers": 0, "win_rate": 0.0}

    def test_mixed_results(self):
        trades = [
            trade_matcher.ClosedTrade("X", "1 Jan", 10.0, "5 Jan", 20.0,
                                      0.0, +5.0, 0.5),
            trade_matcher.ClosedTrade("Y", "1 Jan", 10.0, "5 Jan", 5.0,
                                      0.0, -5.0, -0.5),
            trade_matcher.ClosedTrade("Z", "1 Jan", 10.0, "5 Jan", 20.0,
                                      0.0, +3.0, 0.3),
        ]
        s = trade_matcher.summarize(trades)
        assert s["count"] == 3
        assert s["winners"] == 2
        assert s["losers"] == 1
        assert s["total_pnl"] == pytest.approx(3.0)
        assert s["win_rate"] == pytest.approx(200 / 3)
