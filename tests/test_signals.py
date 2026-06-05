"""Testes dos sinais honestos -- tendencia, liquidez, descontinuada."""
from __future__ import annotations

import json
import time

import pytest

from skinvault import signals


def test_record_and_load(tmp_path):
    p = tmp_path / "ih.json"
    signals.record_item_price("AK-47 | Redline", 100.0, path=p)
    signals.record_item_price("AK-47 | Redline", 110.0, path=p)
    h = signals.load_item_history("AK-47 | Redline", path=p)
    assert len(h) == 2
    assert h[0]["price"] == 100.0
    assert h[1]["price"] == 110.0


def test_record_cap_at_100(tmp_path):
    p = tmp_path / "ih.json"
    for i in range(105):
        signals.record_item_price("Item", float(i), path=p)
    h = signals.load_item_history("Item", path=p)
    assert len(h) == 100
    assert h[0]["price"] == 5.0
    assert h[-1]["price"] == 104.0


def test_trend_subiu():
    now = time.time()
    h = [{"ts": now - 86400 * 10, "price": 100.0},
         {"ts": now, "price": 120.0}]
    t = signals.trend(h)
    assert t is not None
    assert t["direction"] == "subiu"
    assert t["change_pct"] == 20.0
    assert "20.0%" in t["label"]


def test_trend_caiu():
    now = time.time()
    h = [{"ts": now - 86400 * 5, "price": 200.0},
         {"ts": now, "price": 150.0}]
    t = signals.trend(h)
    assert t["direction"] == "caiu"
    assert t["change_pct"] == -25.0


def test_trend_insuficiente():
    assert signals.trend([]) is None
    assert signals.trend([{"ts": 0, "price": 100.0}]) is None


def test_trend_zero_first():
    assert signals.trend([{"ts": 0, "price": 0},
                          {"ts": 1, "price": 100}]) is None


def test_trend_estavel():
    now = time.time()
    h = [{"ts": now - 86400 * 7, "price": 150.0},
         {"ts": now, "price": 150.0}]
    t = signals.trend(h)
    assert t is not None
    assert t["direction"] == "estavel"
    assert t["change_pct"] == 0.0
    assert "estavel" in t["label"]


def test_liquidity_liquid():
    assert signals.liquidity_flag(100)["level"] == "liquid"


def test_liquidity_low():
    assert signals.liquidity_flag(10)["level"] == "low"


def test_liquidity_unknown():
    assert signals.liquidity_flag(None)["level"] == "unknown"


def test_discontinued_case():
    r = signals.discontinued_flag("Operation Bravo Case")
    assert r["is_discontinued"] is True
    assert "descontinuada" in r["flag"]


def test_discontinued_not():
    r = signals.discontinued_flag("AK-47 | Redline (Field-Tested)")
    assert r["is_discontinued"] is False
    assert r["flag"] == ""


def test_discontinued_case_partial_match():
    r = signals.discontinued_flag("Clutch Case")
    assert r["is_discontinued"] is True
    r = signals.discontinued_flag("clutch case")
    assert r["is_discontinued"] is True


def test_sma_basic():
    result = signals.sma([1, 2, 3, 4, 5, 6, 7], period=3)
    assert result[:2] == [None, None]
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(3.0)
    assert result[6] == pytest.approx(6.0)


def test_sma_short():
    assert signals.sma([1, 2], period=5) == [None, None]


def test_sma_empty():
    assert signals.sma([], period=3) == []


def test_find_support_resistance():
    # Trough at middle: point 90 is < both sides
    ph = [{"price_median": 105.0}, {"price_median": 100.0}, {"price_median": 105.0},
          {"price_median": 90.0},
          {"price_median": 105.0}, {"price_median": 100.0}, {"price_median": 105.0}]
    sr = signals.find_support_resistance(ph, window=2)
    assert len(sr["support"]) >= 1
    assert 88 <= sr["support"][0] <= 92


def test_find_support_resistance_empty():
    assert signals.find_support_resistance([], window=2) == {"support": [], "resistance": []}
    assert signals.find_support_resistance([{"price_median": 100.0}], window=2) == {"support": [], "resistance": []}


def test_scan_score_below_median():
    v = {"verdict": "below_median", "diff_pct": -15, "spread_verdict": "tight",
         "book_verdict": "buyer_dominant", "trend_verdict": "rising"}
    assert signals.scan_score(v) == 100


def test_scan_score_overpriced():
    v = {"verdict": "overpriced", "diff_pct": 30, "spread_verdict": "wide",
         "book_verdict": "seller_dominant", "trend_verdict": "falling"}
    assert signals.scan_score(v) == 0


def test_scan_score_neutral():
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v) == 50
