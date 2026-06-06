"""Testes do feed de atividade recente."""
from __future__ import annotations

import time

from skinvault import activity


def test_load_recent_activity_empty(monkeypatch):
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
    monkeypatch.setattr("skinvault.alerts.load_alerts_log", lambda: [])
    monkeypatch.setattr("skinvault.ranking.load_snapshots", lambda: [])
    assert activity.load_recent_activity() == []


def test_load_recent_activity_orders_by_ts_desc(monkeypatch):
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
        {"name": "Older trade", "sell_ts": 100, "pnl": 10, "pnl_pct": 5},
        {"name": "Newer trade", "sell_ts": 300, "pnl": -20, "pnl_pct": -10},
    ])
    monkeypatch.setattr("skinvault.alerts.load_alerts_log", lambda: [
        {"ts": 200, "name": "AK", "label": "Volume 3x", "rule": "volume_spike"},
    ])
    monkeypatch.setattr("skinvault.ranking.load_snapshots", lambda: [
        {"ts": 250, "items": [{"name": "AWP", "score": 90}]},
    ])
    events = activity.load_recent_activity(limit=10)
    assert [e["title"] for e in events] == [
        "Newer trade", "Ranking Top 20", "AK", "Older trade",
    ]


def test_load_recent_activity_respects_limit(monkeypatch):
    trades_list = [
        {"name": f"Trade {i}", "sell_ts": i, "pnl": 1, "pnl_pct": 1}
        for i in range(20)
    ]
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: trades_list)
    monkeypatch.setattr("skinvault.alerts.load_alerts_log", lambda: [])
    monkeypatch.setattr("skinvault.ranking.load_snapshots", lambda: [])
    events = activity.load_recent_activity(limit=5)
    assert len(events) == 5


def test_load_recent_activity_limit_zero(monkeypatch):
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
        {"name": "x", "sell_ts": 100, "pnl": 1, "pnl_pct": 1}])
    monkeypatch.setattr("skinvault.alerts.load_alerts_log", lambda: [])
    monkeypatch.setattr("skinvault.ranking.load_snapshots", lambda: [])
    assert activity.load_recent_activity(limit=0) == []


def test_trade_event_profit():
    ev = activity._trade_event({
        "name": "AK-47", "sell_ts": 1000, "pnl": 50, "pnl_pct": 25,
    })
    assert ev["type"] == "trade"
    assert ev["color"] == "green"
    assert ev["icon"] == "↑"
    assert "+50" in ev["subtitle"]


def test_trade_event_loss():
    ev = activity._trade_event({
        "name": "AK-47", "sell_ts": 1000, "pnl": -30, "pnl_pct": -15,
    })
    assert ev["color"] == "red"
    assert ev["icon"] == "↓"


def test_trade_event_uses_buy_ts_fallback():
    ev = activity._trade_event({
        "name": "x", "buy_ts": 500, "pnl": 0, "pnl_pct": 0,
    })
    assert ev["ts"] == 500.0


def test_trade_event_no_ts_returns_none():
    assert activity._trade_event({"name": "x"}) is None


def test_trade_event_missing_name():
    ev = activity._trade_event({"sell_ts": 100, "pnl": 0, "pnl_pct": 0})
    assert ev["title"] == "Trade"


def test_alert_event_basic():
    ev = activity._alert_event({
        "ts": 100, "name": "AK", "label": "Volume 3x", "rule": "volume_spike",
    })
    assert ev["type"] == "alert"
    assert ev["color"] == "accent"
    assert ev["icon"] == "★"
    assert ev["subtitle"] == "Volume 3x"


def test_alert_event_falls_back_to_rule():
    ev = activity._alert_event({
        "ts": 100, "name": "AK", "rule": "volume_spike",
    })
    assert ev["subtitle"] == "volume_spike"


def test_alert_event_missing_name():
    ev = activity._alert_event({"ts": 100})
    assert ev["title"] == "Alerta"
    assert ev["subtitle"] == ""


def test_alert_event_no_ts():
    assert activity._alert_event({"name": "x"}) is None


def test_ranking_event_with_leader():
    ev = activity._ranking_event({
        "ts": 100,
        "items": [{"name": "AWP | Asiimov", "score": 95},
                  {"name": "AK-47", "score": 80}],
    })
    assert ev["type"] == "ranking"
    assert "Asiimov" in ev["subtitle"]


def test_ranking_event_empty_items():
    ev = activity._ranking_event({"ts": 100, "items": []})
    assert "vazio" in ev["subtitle"]


def test_ranking_event_no_items_key():
    ev = activity._ranking_event({"ts": 100})
    assert "vazio" in ev["subtitle"]


def test_ranking_event_item_missing_name():
    ev = activity._ranking_event({"ts": 100, "items": [{"score": 50}]})
    assert "?" in ev["subtitle"]


def test_ranking_event_no_ts():
    assert activity._ranking_event({"items": []}) is None


def test_format_relative_ts_now():
    now = 10000.0
    assert activity.format_relative_ts(now - 30, now=now) == "agora"


def test_format_relative_ts_minutes():
    now = 10000.0
    assert activity.format_relative_ts(now - 600, now=now) == "10m"


def test_format_relative_ts_hours():
    now = 100000.0
    assert activity.format_relative_ts(now - 7200, now=now) == "2h"


def test_format_relative_ts_days():
    now = 1_000_000.0
    assert activity.format_relative_ts(now - 3 * 86400, now=now) == "3d"


def test_format_relative_ts_old_uses_date():
    import datetime as dt
    ts = dt.datetime(2024, 5, 15).timestamp()
    now = dt.datetime(2024, 6, 1).timestamp()
    out = activity.format_relative_ts(ts, now=now)
    assert "mai" in out
    assert "15" in out


def test_format_relative_ts_default_now_uses_time(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 10000.0)
    assert activity.format_relative_ts(9999.0) == "agora"
