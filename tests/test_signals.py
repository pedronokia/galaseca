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


def test_record_and_load_volume(tmp_path, monkeypatch):
    p = tmp_path / "vol_history.json"
    monkeypatch.setattr(signals, "_VOLUME_PATH", p)
    signals.record_item_volume("AK-47 | Redline", 500)
    signals.record_item_volume("AK-47 | Redline", 600)
    h = signals.load_item_volume("AK-47 | Redline")
    assert len(h) == 2
    assert h[0]["value"] == 500.0
    assert h[1]["value"] == 600.0


def test_record_and_load_supply(tmp_path, monkeypatch):
    p = tmp_path / "sup_history.json"
    monkeypatch.setattr(signals, "_SUPPLY_PATH", p)
    signals.record_item_supply("AK-47 | Redline", 100)
    signals.record_item_supply("AK-47 | Redline", 90)
    h = signals.load_item_supply("AK-47 | Redline")
    assert len(h) == 2
    assert h[0]["value"] == 100


def test_supply_demand_ratio():
    r = signals.supply_demand_ratio(200, 100)
    assert r["ratio"] == 2.0
    assert "2.0" in r["label"]


def test_supply_demand_none():
    assert signals.supply_demand_ratio(None, 100)["ratio"] == 0
    assert signals.supply_demand_ratio(100, 0)["ratio"] == 0


def test_volume_anomaly_high():
    h = [{"value": 100}] * 5 + [{"value": 400}]
    a = signals.volume_anomaly(h, factor=2.0)
    assert a["is_anomaly"] is True
    assert "acima" in a["label"]


def test_volume_anomaly_normal():
    h = [{"value": 100}] * 5 + [{"value": 110}]
    a = signals.volume_anomaly(h, factor=2.0)
    assert a["is_anomaly"] is False


def test_volume_anomaly_short():
    assert signals.volume_anomaly([])["is_anomaly"] is False
    assert signals.volume_anomaly([{"value": 100}])["is_anomaly"] is False


def test_multi_trend_returns_empty_for_short_history():
    assert signals.multi_trend([]) == {}
    assert signals.multi_trend([{"time": 100, "price_median": 50.0}]) == {}


def test_multi_trend_basic():
    now = time.time()
    ph = [
        {"time": now - 90000, "price_median": 100.0},   # ~25h ago (within 20% tolerance)
        {"time": now - 1000, "price_median": 120.0},    # recente
    ]
    result = signals.multi_trend(ph, periods=[24])
    assert "24h" in result
    assert result["24h"]["direction"] == "subiu"


def test_multi_trend_period_labels():
    now = time.time()
    ph = [
        {"time": now - 700000, "price_median": 100.0},  # ~194h ago (dentro da tolerancia 7d)
        {"time": now - 86400, "price_median": 105.0},   # exatamente 24h ago
        {"time": now - 1000, "price_median": 110.0},    # recente
    ]
    result = signals.multi_trend(ph, periods=[24, 168])
    assert "24h" in result
    assert "7d" in result
    assert result["7d"]["direction"] == "subiu"


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


def test_scan_score_high_demand():
    """Alta demanda (>5x) soma 15 pontos."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v, volume=500, supply=50) == 65


def test_scan_score_good_demand():
    """Demanda moderada (>3x) soma 10 pontos."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v, volume=300, supply=80) == 60


def test_scan_score_low_demand():
    """Baixa demanda (<0.5x) penaliza 10 pontos."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v, volume=10, supply=50) == 40


def test_scan_score_skip_supply_none():
    """Sem dados de oferta, mantem score base."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v, volume=500, supply=None) == 50
    assert signals.scan_score(v, volume=None, supply=50) == 50


def test_scan_score_momentum_positive():
    """Preco acima da SMA curta soma 5."""
    v = {"verdict": "fair", "diff_pct": 0}
    ph = [{"price_median": 100.0}] * 14 + [{"price_median": 110.0}]
    assert signals.scan_score(v, price_history=ph) == 55


def test_scan_score_momentum_negative():
    """Preco abaixo da SMA curta penaliza 5."""
    v = {"verdict": "fair", "diff_pct": 0}
    ph = [{"price_median": 100.0}] * 14 + [{"price_median": 90.0}]
    assert signals.scan_score(v, price_history=ph) == 45


def test_scan_score_momentum_insuficiente():
    """Historico curto ignora momentum."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v, price_history=[{"price_median": 100}]) == 50


def test_scan_score_multi_trend_all_rising():
    """Todos os periodos subindo somam 10."""
    v = {"verdict": "fair", "diff_pct": 0}
    mt = {"24h": {"change_pct": 2.0}, "7d": {"change_pct": 5.0},
          "30d": {"change_pct": 8.0}}
    assert signals.scan_score(v, multi_trend=mt) == 60


def test_scan_score_multi_trend_all_falling():
    """Todos os periodos caindo penalizam 10."""
    v = {"verdict": "fair", "diff_pct": 0}
    mt = {"24h": {"change_pct": -2.0}, "7d": {"change_pct": -5.0},
          "30d": {"change_pct": -8.0}}
    assert signals.scan_score(v, multi_trend=mt) == 40


def test_scan_score_volume_liquidity_bonus():
    """Volume > 2000 soma 5."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v, volume=3000) == 55


def test_enhanced_score_returns_tuple():
    v = {"verdict": "fair", "diff_pct": 0}
    score, breakdown = signals.enhanced_score(v)
    assert score == 50
    assert breakdown == []


def test_enhanced_score_below_median_breakdown():
    v = {"verdict": "below_median", "diff_pct": -15, "spread_verdict": "tight",
         "book_verdict": "buyer_dominant", "trend_verdict": "rising"}
    score, breakdown = signals.enhanced_score(v)
    assert score == 100
    factors = {b["factor"] for b in breakdown}
    assert "mediana" in factors
    assert "spread" in factors
    assert "book" in factors
    assert "trend" in factors
    assert "verdict" in factors


def test_enhanced_score_breakdown_sorted_by_abs_delta():
    v = {"verdict": "below_median", "diff_pct": -10, "spread_verdict": "tight",
         "trend_verdict": "rising"}
    _, breakdown = signals.enhanced_score(v)
    # Spread tight (+25) deve vir antes de mediana (-10 * 1.2 = +12)
    assert breakdown[0]["factor"] == "spread"
    assert breakdown[0]["delta"] == 25


def test_enhanced_score_case_status_discontinued():
    v = {"verdict": "fair", "diff_pct": 0}
    score, breakdown = signals.enhanced_score(
        v, case_status={"is_discontinued": True}
    )
    assert score == 55
    assert any(b["factor"] == "case" and b["delta"] == 5 for b in breakdown)


def test_enhanced_score_case_status_rare():
    v = {"verdict": "fair", "diff_pct": 0}
    score, breakdown = signals.enhanced_score(
        v, case_status={"is_rare": True}
    )
    assert score == 53
    assert any(b["factor"] == "case" and b["delta"] == 3 for b in breakdown)


def test_format_breakdown_empty():
    assert "Sem fatores" in signals.format_breakdown([])


def test_format_breakdown_groups_positive_negative():
    breakdown = [
        {"factor": "spread", "delta": 25, "label": "Spread apertado (+25)"},
        {"factor": "trend", "delta": -10, "label": "Tendencia: caindo (-10)"},
    ]
    text = signals.format_breakdown(breakdown)
    assert "Positivos:" in text
    assert "Negativos:" in text
    assert "Spread apertado" in text
    assert "Tendencia: caindo" in text


def test_scan_score_wrapper_returns_int():
    """scan_score deve continuar retornando apenas int (backward compat)."""
    v = {"verdict": "fair", "diff_pct": 0}
    assert signals.scan_score(v) == 50
    assert isinstance(signals.scan_score(v), int)
