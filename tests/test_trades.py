"""Testes do trade analyzer -- lucro realizado."""
from __future__ import annotations

import pytest

from galaseca import trades


def test_record_trade_pnl_pct_is_0_100(tmp_path):
    """record_trade.pnl_pct retorna 0-100, nao fracao."""
    t = trades.record_trade("AK-47 | Redline", 100.0, 150.0, 1,
                            path=tmp_path / "t.json")
    assert t["pnl_pct"] == pytest.approx(30.43, abs=0.01)


def test_trade_stats_win_rate_is_0_100(tmp_path):
    """trade_stats.win_rate retorna 0-100, nao fracao."""
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 150.0, 1, path=p)
    s = trades.trade_stats(path=p)
    assert s["win_rate"] == 100.0 if s["total"] else 0.0


def test_record_trade_profit(tmp_path):
    p = tmp_path / "trades.json"
    t = trades.record_trade("AK-47 | Redline", 200.0, 350.0, 1, path=p)
    assert t["pnl"] == pytest.approx(104.35, abs=0.02)
    assert t["name"] == "AK-47 | Redline"


def test_record_trade_loss(tmp_path):
    p = tmp_path / "trades.json"
    t = trades.record_trade("AWP | Asiimov", 700.0, 600.0, 1, path=p)
    assert t["pnl"] < 0
    assert t["pnl"] == pytest.approx(-178.26, abs=0.02)


def test_record_trade_multiple_qty(tmp_path):
    p = tmp_path / "trades.json"
    t = trades.record_trade("Item", 100.0, 150.0, 3, path=p)
    assert t["cost_total"] == 300.0
    assert t["pnl"] == pytest.approx(91.30, abs=0.02)


def test_record_trade_buy_ts(tmp_path):
    p = tmp_path / "t.json"
    t = trades.record_trade("A", 100.0, 200.0, 1, buy_ts=1000000, path=p)
    assert t["buy_ts"] == 1000000
    assert t["sell_ts"] > 1000000
    days = (t["sell_ts"] - 1000000) / 86400
    assert days > 0


def test_record_trade_notes_tags(tmp_path):
    p = tmp_path / "t.json"
    t = trades.record_trade("Item", 100.0, 200.0, 1,
                            notes="Bom negocio", tags=["profit", "skin"],
                            path=p)
    assert t["notes"] == "Bom negocio"
    assert t["tags"] == ["profit", "skin"]


def test_load_empty(tmp_path):
    assert trades.load_trades(tmp_path / "empty.json") == []


def test_stats_empty(tmp_path):
    s = trades.trade_stats([], path=tmp_path / "x.json")
    assert s["total"] == 0
    assert s["fees_total"] == 0.0
    assert s["avg_days"] == 0


def test_remove_trade(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    trades.record_trade("B", 150.0, 300.0, 1, path=p)
    assert len(trades.load_trades(path=p)) == 2
    trades.remove_trade(0, path=p)
    remaining = trades.load_trades(path=p)
    assert len(remaining) == 1
    assert remaining[0]["name"] == "B"


def test_update_trade(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    trades.update_trade(0, notes="Nota atualizada", tags=["spec"], path=p)
    t = trades.load_trades(path=p)[0]
    assert t["notes"] == "Nota atualizada"
    assert t["tags"] == ["spec"]


def test_filter_keyword(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("AK-47 Redline", 100.0, 200.0, 1, path=p)
    trades.record_trade("AWP Asiimov", 200.0, 180.0, 1, path=p)
    r = trades.filter_trades(keyword="AK", path=p)
    assert len(r) == 1
    assert r[0]["name"] == "AK-47 Redline"


def test_filter_tags(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, tags=["skin"], path=p)
    trades.record_trade("B", 200.0, 180.0, 1, tags=["case"], path=p)
    r = trades.filter_trades(tags=["skin"], path=p)
    assert len(r) == 1
    assert r[0]["name"] == "A"


def test_filter_profit_loss(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    trades.record_trade("B", 200.0, 180.0, 1, path=p)
    assert len(trades.filter_trades(profit_only=True, path=p)) == 1
    assert len(trades.filter_trades(loss_only=True, path=p)) == 1


def test_stats_with_best_worst(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    trades.record_trade("B", 200.0, 180.0, 1, path=p)
    s = trades.trade_stats(path=p)
    assert s["total"] == 2
    assert s["win_count"] == 1
    assert s["loss_count"] == 1
    assert s["win_rate"] == 50.0
    assert s["best"]["name"] == "A"
    assert s["worst"]["name"] == "B"
    assert len(s["monthly"]) == 1
    assert s["monthly"][0]["trades"] == 2
    assert s["fees_total"] > 0
    assert s["avg_days"] == 0


def test_stats_fees_and_days(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 2,
                        buy_ts=1000000, path=p)
    s = trades.trade_stats(path=p)
    assert s["fees_total"] == pytest.approx(52.17, abs=0.02)
    assert s["avg_days"] > 0


def test_stats_with_trades(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)  # profit
    trades.record_trade("B", 200.0, 180.0, 1, path=p)  # loss
    s = trades.trade_stats(path=p)
    assert s["total"] == 2
    assert s["win_count"] == 1
    assert s["loss_count"] == 1
    assert s["win_rate"] == 50.0


def test_clear_trades(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    assert len(trades.load_trades(path=p)) == 1
    trades.clear_trades(path=p)
    assert trades.load_trades(path=p) == []
    s = trades.trade_stats(path=p)
    assert s["total"] == 0


def test_save_trades_oserror_ignored(tmp_path):
    p = tmp_path / "t.json"
    trades.save_trades([{"name": "A"}], path=p)
    p.unlink()
    p.mkdir()
    trades.save_trades([{"name": "B"}], path=p)  # nao crashou


def test_update_trade_invalid_index(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    assert trades.update_trade(99, cost=150.0, path=p) is None


def test_update_trade_cost_only(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    t = trades.update_trade(0, cost=150.0, path=p)
    assert t["buy_cost"] == 150.0
    assert t["cost_total"] == 150.0
    assert t["pnl"] > 0


def test_update_trade_sell_price_only(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    t = trades.update_trade(0, sell_price=300.0, path=p)
    assert t["sell_price"] == 300.0
    assert t["pnl"] > 0
    assert t["net_received"] > 0


def test_update_trade_cost_and_sell(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)
    t = trades.update_trade(0, cost=50.0, sell_price=300.0, path=p)
    assert t["pnl"] > 0


def test_filter_trades_pnl_profit(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)  # profit
    trades.record_trade("B", 200.0, 180.0, 1, path=p)  # loss
    r = trades.filter_trades(pnl="profit", path=p)
    assert len(r) == 1
    assert r[0]["name"] == "A"


def test_filter_trades_pnl_loss(tmp_path):
    p = tmp_path / "t.json"
    trades.record_trade("A", 100.0, 200.0, 1, path=p)  # profit
    trades.record_trade("B", 200.0, 180.0, 1, path=p)  # loss
    r = trades.filter_trades(pnl="loss", path=p)
    assert len(r) == 1
    assert r[0]["name"] == "B"


def test_monthly_pnl_agrupa_e_ordena():
    """monthly_pnl agrega por mes gmtime, ordenado, com count e soma."""
    import calendar
    ts_jan = calendar.timegm((2025, 1, 10, 0, 0, 0))
    ts_fev = calendar.timegm((2025, 2, 10, 0, 0, 0))
    data = [
        {"sell_ts": ts_fev, "pnl": -3.0},
        {"sell_ts": ts_jan, "pnl": 10.0},
        {"sell_ts": ts_jan, "pnl": 2.5},
    ]
    out = trades.monthly_pnl(data)
    assert out == [
        {"month": "2025-01", "trades": 2, "pnl": 12.5},
        {"month": "2025-02", "trades": 1, "pnl": -3.0},
    ]


def test_monthly_pnl_tolera_trade_legado():
    """Trade sem net_received/buy_ts nao quebra (so usa sell_ts/pnl)."""
    out = trades.monthly_pnl([{"sell_ts": 0, "pnl": 1.0}, {}])
    assert out[0]["month"] == "1970-01"
    assert out[0]["trades"] == 2
    assert out[0]["pnl"] == 1.0
