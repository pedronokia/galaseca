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


    def test_invalid_day_returns_none(self):
        """Dia nao numerico retorna None."""
        now = time.mktime((2026, 6, 15, 12, 0, 0, 0, 0, -1))
        assert trade_matcher.parse_steam_date("abc Jan", now=now) is None

    def test_invalid_time_format_returns_valid_date(self):
        """Time com formato invalido ignora a hora e retorna data valida."""
        now = time.mktime((2026, 6, 15, 12, 0, 0, 0, 0, -1))
        ts = trade_matcher.parse_steam_date("10 Mar xx:yy", now=now)
        assert ts is not None
        lt = time.localtime(ts)
        assert lt.tm_hour == 0

    def test_future_year_adjustment_fails_gracefully(self):
        """Ajuste de ano futuro que falha retorna None."""
        now = time.mktime((2024, 2, 15, 12, 0, 0, 0, 0, -1))
        # 29 Feb 2024 sem ano e' futuro (>1d), tenta 2023 — mas 29 Feb 2023 nao existe
        ts = trade_matcher.parse_steam_date("29 Feb", now=now)
        assert ts is None


# ── match_events --------------------------------------------------------

def _ev(name, side, price, date_str):
    return {"name": name, "side": side, "price": price, "date_str": date_str}


class TestMatchEvents:
    def test_empty_returns_empty(self):
        assert trade_matcher.match_events([]) == []

    def test_appid_filter_ignores_mismatch(self):
        events = [
            {"name": "AK", "side": "buy", "price": 10.0, "date_str": "1 Jan",
             "appid": 730},
            {"name": "AK", "side": "sell", "price": 20.0, "date_str": "5 Jan",
             "appid": 730},
            {"name": "AWP", "side": "buy", "price": 50.0, "date_str": "1 Jan",
             "appid": 740},
        ]
        result = trade_matcher.match_events(events, appid=730)
        assert len(result) == 1
        assert result[0].name == "AK"

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


def test_load_closed_trades(monkeypatch):
    """load_closed_trades carrega eventos do sync e pareia."""
    monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [
        {"name": "AK", "side": "buy", "price": 10.0, "date_str": "1 Jan"},
        {"name": "AK", "side": "sell", "price": 20.0, "date_str": "5 Jan"},
    ])
    result = trade_matcher.load_closed_trades()
    assert len(result) == 1
    assert result[0].pnl > 0


def test_load_open_buys(monkeypatch):
    """load_open_buys carrega eventos e retorna buys nao vendidos."""
    monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [
        {"name": "AK", "side": "buy", "price": 10.0, "date_str": "1 Jan"},
    ])
    result = trade_matcher.load_open_buys()
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


# ── buy_ts ─────────────────────────────────────────────────────────

def test_closed_trade_carrega_buy_ts():
    """O trade importado precisa do buy_ts pra alimentar avg_days e os
    filtros de periodo da tela."""
    now = trade_matcher.parse_steam_date("1 Jun, 2024")
    closed = trade_matcher.match_events([
        {"name": "AK", "side": "buy", "price": 10.0, "date_str": "1 Jan, 2024"},
        {"name": "AK", "side": "sell", "price": 20.0, "date_str": "5 Jan, 2024"},
    ], now=now)
    assert len(closed) == 1
    assert closed[0].buy_ts == trade_matcher.parse_steam_date(
        "1 Jan, 2024", now=now)
    assert closed[0].buy_ts < closed[0].sell_ts


def test_closed_trade_construcao_posicional_continua_valendo():
    """buy_ts entrou com default no fim justamente pra nao quebrar isso."""
    tr = trade_matcher.ClosedTrade("X", "1 Jan", 10.0, "5 Jan", 20.0,
                                   0.0, +5.0, 0.5)
    assert tr.buy_ts == 0.0


# ── chaves de dedupe ───────────────────────────────────────────────

class TestClosedTradeKey:
    def _tr(self, **kw):
        base = dict(name="AK", buy_date="1 Jan", buy_price=10.0,
                    sell_date="5 Jan", sell_price=20.0, sell_ts=0.0,
                    pnl=7.0, pnl_pct=70.0, buy_ts=0.0)
        base.update(kw)
        return trade_matcher.ClosedTrade(**base)

    def test_estavel(self):
        assert trade_matcher.closed_trade_key(self._tr()) == \
            trade_matcher.closed_trade_key(self._tr())

    def test_preco_diferente_muda_chave(self):
        assert trade_matcher.closed_trade_key(self._tr()) != \
            trade_matcher.closed_trade_key(self._tr(sell_price=21.0))

    def test_nome_diferente_muda_chave(self):
        assert trade_matcher.closed_trade_key(self._tr()) != \
            trade_matcher.closed_trade_key(self._tr(name="AWP"))

    def test_normaliza_html_do_nome(self):
        """Parsers diferentes dao '&amp;' vs '&' pro mesmo item."""
        assert trade_matcher.closed_trade_key(self._tr(name="A &amp; B")) == \
            trade_matcher.closed_trade_key(self._tr(name="A & B"))

    def test_data_vira_iso_quando_ha_timestamp(self):
        """AGENTS.md #4: o Steam omite o ano do ano corrente, entao '5 Jan'
        e '5 Jan, 2024' sao o MESMO evento visto em anos diferentes. Se a
        chave usasse a string crua, tudo seria reimportado na virada."""
        ts_2024 = trade_matcher.parse_steam_date("5 Jan, 2024")
        sem_ano = self._tr(sell_date="5 Jan", sell_ts=ts_2024)
        com_ano = self._tr(sell_date="5 Jan, 2024", sell_ts=ts_2024)
        assert trade_matcher.closed_trade_key(sem_ano) == \
            trade_matcher.closed_trade_key(com_ano)

    def test_pnl_nao_entra_na_chave(self):
        """Senao mudar a taxa da Steam reimportaria o historico inteiro."""
        assert trade_matcher.closed_trade_key(self._tr(pnl=7.0)) == \
            trade_matcher.closed_trade_key(self._tr(pnl=999.0))

    def test_repeticoes_ganham_sufixo(self):
        """3 compras+vendas iguais no mesmo dia sao 3 trades, nao 1."""
        iguais = [self._tr(), self._tr(), self._tr()]
        chaves = [k for k, _ in trade_matcher.assign_keys(iguais)]
        assert len(set(chaves)) == 3

    def test_sufixo_e_deterministico(self):
        iguais = [self._tr(), self._tr()]
        assert [k for k, _ in trade_matcher.assign_keys(iguais)] == \
            [k for k, _ in trade_matcher.assign_keys(iguais)]


# ── importacao ─────────────────────────────────────────────────────

class TestImportClosedTrades:
    def _closed(self, n=2):
        return [
            trade_matcher.ClosedTrade(
                name="AK-{}".format(i), buy_date="1 Jan, 2024", buy_price=10.0,
                sell_date="5 Jan, 2024", sell_price=20.0,
                sell_ts=1704412800.0, pnl=7.0, pnl_pct=70.0,
                buy_ts=1704067200.0,
            )
            for i in range(n)
        ]

    def test_grava_trades(self, tmp_path):
        from skinvault import trades as trades_mod
        p = tmp_path / "trades.json"
        res = trade_matcher.import_closed_trades(self._closed(2), path=p)
        assert res == {"imported": 2, "skipped": 0, "total": 2}
        gravados = trades_mod.load_trades(p)
        assert len(gravados) == 2
        assert all(tr["source"] == "steam_sync" for tr in gravados)
        assert all(tr["steam_event_id"] for tr in gravados)

    def test_reimportar_nao_duplica(self, tmp_path):
        """Idempotencia: e' o unico jeito de reimportar depois de um sync
        novo sem inflar o arquivo."""
        from skinvault import trades as trades_mod
        p = tmp_path / "trades.json"
        closed = self._closed(2)
        trade_matcher.import_closed_trades(closed, path=p)
        res = trade_matcher.import_closed_trades(closed, path=p)
        assert res == {"imported": 0, "skipped": 2, "total": 2}
        assert len(trades_mod.load_trades(p)) == 2

    def test_importa_so_o_que_e_novo(self, tmp_path):
        from skinvault import trades as trades_mod
        p = tmp_path / "trades.json"
        trade_matcher.import_closed_trades(self._closed(2), path=p)
        res = trade_matcher.import_closed_trades(self._closed(3), path=p)
        assert res["imported"] == 1
        assert res["skipped"] == 2
        assert len(trades_mod.load_trades(p)) == 3

    def test_nao_mexe_em_trade_manual(self, tmp_path):
        """Regra do sync (sync.py): source='manual' e' intocavel."""
        from skinvault import trades as trades_mod
        p = tmp_path / "trades.json"
        trades_mod.record_trade("AK-0", 5.0, 9.0, notes="minha nota", path=p)
        trade_matcher.import_closed_trades(self._closed(1), path=p)
        gravados = trades_mod.load_trades(p)
        manual = [tr for tr in gravados if tr["source"] == "manual"]
        assert len(manual) == 1
        assert manual[0]["notes"] == "minha nota"

    def test_preserva_datas_originais(self, tmp_path):
        """Sem isso todo trade importado teria a data da importacao e os
        filtros de periodo da tela ficariam inuteis."""
        from skinvault import trades as trades_mod
        p = tmp_path / "trades.json"
        trade_matcher.import_closed_trades(self._closed(1), path=p)
        tr = trades_mod.load_trades(p)[0]
        assert tr["buy_ts"] == 1704067200.0
        assert tr["sell_ts"] == 1704412800.0

    def test_pnl_recalculado_com_a_taxa(self, tmp_path):
        """O P&L gravado vem de net_proceeds, nao do campo do ClosedTrade."""
        from skinvault import portfolio, trades as trades_mod
        p = tmp_path / "trades.json"
        trade_matcher.import_closed_trades(self._closed(1), path=p)
        tr = trades_mod.load_trades(p)[0]
        esperado = portfolio.net_proceeds(20.0) - 10.0
        assert tr["pnl"] == pytest.approx(round(esperado, 2))

    def test_lista_vazia(self, tmp_path):
        p = tmp_path / "trades.json"
        res = trade_matcher.import_closed_trades([], path=p)
        assert res == {"imported": 0, "skipped": 0, "total": 0}

    def test_sem_argumento_carrega_do_sync(self, tmp_path, monkeypatch):
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [
            {"name": "AK", "side": "buy", "price": 10.0,
             "date_str": "1 Jan, 2024"},
            {"name": "AK", "side": "sell", "price": 20.0,
             "date_str": "5 Jan, 2024"},
        ])
        res = trade_matcher.import_closed_trades(path=tmp_path / "t.json")
        assert res["imported"] == 1

    def test_tres_trades_identicos_viram_tres_linhas(self, tmp_path):
        from skinvault import trades as trades_mod
        p = tmp_path / "trades.json"
        iguais = [
            trade_matcher.ClosedTrade(
                "AK", "1 Jan, 2024", 10.0, "5 Jan, 2024", 20.0,
                1704412800.0, 7.0, 70.0, 1704067200.0)
            for _ in range(3)
        ]
        res = trade_matcher.import_closed_trades(iguais, path=p)
        assert res["imported"] == 3
        assert len(trades_mod.load_trades(p)) == 3
        # E reimportar continua nao duplicando.
        assert trade_matcher.import_closed_trades(iguais, path=p)["imported"] == 0
