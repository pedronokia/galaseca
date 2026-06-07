"""Testes do engine de backtest do enhanced_score."""
from __future__ import annotations

import time

import pytest

from skinvault import backtest


def _mk_history(prices: list[float], start_ts: float | None = None,
                day_step: float = 86400.0,
                purchases: int = 10) -> list[dict]:
    """Constroi price_history sintetico com 1 entry por dia."""
    if start_ts is None:
        start_ts = time.time() - len(prices) * day_step
    return [
        {"time": start_ts + i * day_step,
         "price_median": p,
         "purchases": purchases}
        for i, p in enumerate(prices)
    ]


# ---------- _slice_history ----------

def test_slice_history_cuts_at_cutoff():
    hist = _mk_history([10, 11, 12, 13, 14], start_ts=1000, day_step=100)
    sliced = backtest._slice_history(hist, cutoff_ts=1200)
    assert len(sliced) == 3
    assert sliced[-1]["price_median"] == 12


def test_slice_history_empty():
    assert backtest._slice_history([], 1000) == []


def test_slice_history_inclusive_at_boundary():
    hist = _mk_history([10, 20], start_ts=1000, day_step=100)
    sliced = backtest._slice_history(hist, cutoff_ts=1000)
    assert len(sliced) == 1


# ---------- _mock_verdict_from_history ----------

def test_mock_verdict_too_short():
    hist = _mk_history([10, 11, 12])
    assert backtest._mock_verdict_from_history(hist) == {}


def test_mock_verdict_below_median():
    # Preco final bem abaixo da mediana 30d
    prices = [100.0] * 25 + [80.0] * 5
    hist = _mk_history(prices)
    v = backtest._mock_verdict_from_history(hist)
    assert v["verdict"] == "below_median"
    assert v["diff_pct"] < -5


def test_mock_verdict_fair():
    prices = [100.0] * 30
    hist = _mk_history(prices)
    v = backtest._mock_verdict_from_history(hist)
    assert v["verdict"] == "fair"
    assert v["diff_pct"] == 0.0


def test_mock_verdict_overpriced():
    prices = [100.0] * 25 + [150.0] * 5
    hist = _mk_history(prices)
    v = backtest._mock_verdict_from_history(hist)
    assert v["verdict"] == "overpriced"


def test_mock_verdict_trend_rising():
    # 23 dias estaveis em 100, 7 dias subindo pra 110
    prices = [100.0] * 23 + [110.0] * 7
    hist = _mk_history(prices)
    v = backtest._mock_verdict_from_history(hist)
    assert v.get("trend_verdict") == "rising"


def test_mock_verdict_trend_falling():
    prices = [100.0] * 23 + [85.0] * 7
    hist = _mk_history(prices)
    v = backtest._mock_verdict_from_history(hist)
    assert v.get("trend_verdict") == "falling"


def test_mock_verdict_median_zero_returns_empty():
    hist = _mk_history([0.0] * 30)
    assert backtest._mock_verdict_from_history(hist) == {}


# ---------- _future_return ----------

def test_future_return_positive():
    hist = _mk_history([100.0, 100.0, 100.0, 110.0],
                       start_ts=1000, day_step=86400)
    # de t=1000 (100) a t=1000+2d ~ ainda nao tem +30d, vamos sintetizar maior
    hist = _mk_history([100.0] * 35 + [120.0] * 35,
                       start_ts=0, day_step=86400)
    ret = backtest._future_return(hist, from_ts=10 * 86400, horizon_days=30)
    assert ret is not None
    assert ret > 0.15  # ~20% de subida


def test_future_return_negative():
    hist = _mk_history([100.0] * 35 + [80.0] * 35,
                       start_ts=0, day_step=86400)
    ret = backtest._future_return(hist, from_ts=10 * 86400, horizon_days=30)
    assert ret is not None
    assert ret < -0.15


def test_future_return_no_data():
    hist = _mk_history([100.0] * 5, start_ts=0, day_step=86400)
    # horizon estoura o fim do historico
    ret = backtest._future_return(hist, from_ts=0, horizon_days=30)
    assert ret is None


def test_future_return_zero_start_price():
    hist = _mk_history([0.0] * 5 + [100.0] * 35, start_ts=0, day_step=86400)
    ret = backtest._future_return(hist, from_ts=0, horizon_days=30)
    assert ret is None


# ---------- simulate_item ----------

def test_simulate_item_short_history():
    hist = _mk_history([100.0] * 10)
    assert backtest.simulate_item("X", hist) == []


def test_simulate_item_produces_samples():
    # 200 dias de historico com leve trend
    prices = [100.0 + i * 0.1 for i in range(200)]
    hist = _mk_history(prices, start_ts=0, day_step=86400)
    samples = backtest.simulate_item("AK | X", hist,
                                      horizon_days=30, step_days=14,
                                      min_history_days=60)
    assert len(samples) >= 5
    for s in samples:
        assert s["item"] == "AK | X"
        assert 0 <= s["score"] <= 100
        assert isinstance(s["return_pct"], float)


def test_simulate_item_inclui_confidence_e_level():
    """Cada sample carrega confidence e level (contexto temporal correto)."""
    prices = [100.0 + i * 0.1 for i in range(200)]
    hist = _mk_history(prices, start_ts=0, day_step=86400)
    samples = backtest.simulate_item("X", hist,
                                      horizon_days=30, step_days=14,
                                      min_history_days=60)
    assert len(samples) > 0
    for s in samples:
        assert "confidence" in s
        assert "level" in s
        assert 0.0 <= s["confidence"] <= 1.0
        assert s["level"] in ("high", "medium", "low", "very_low", "none")


def test_score_from_history_vazio_retorna_none():
    assert backtest.score_from_history("X", []) is None
    assert backtest.score_from_history("X", [{"time": 0}]) is None


def test_score_from_history_retorna_int_em_range():
    import time as _t
    ph = [{"time": _t.time() - i * 86400,
           "price_median": 100.0 + i * 0.1, "purchases": 5}
          for i in range(60)]
    score = backtest.score_from_history("AK-47 | X", ph)
    assert isinstance(score, int)
    assert 0 <= score <= 100


def test_score_from_history_container_squeeze_inicial_alto():
    import time as _t
    prices = [100.0] * 25 + [50.0, 30.0, 10.0, 5.0, 3.0]
    ph = [{"time": _t.time() - (30 - i) * 86400,
           "price_median": p, "purchases": 5}
          for i, p in enumerate(prices)]
    score = backtest.score_from_history("Clutch Case", ph)
    assert score is not None
    assert score >= 50


def test_simulate_item_confidence_cresce_com_prefix():
    """Samples tardios tem mais historico, logo confidence >= dos primeiros."""
    prices = [100.0 + i * 0.1 for i in range(300)]
    hist = _mk_history(prices, start_ts=0, day_step=86400)
    samples = backtest.simulate_item("X", hist,
                                      horizon_days=30, step_days=14,
                                      min_history_days=60)
    assert len(samples) >= 5
    # Confidence nunca diminui ao longo do tempo (size_factor cresce)
    first_conf = samples[0]["confidence"]
    last_conf = samples[-1]["confidence"]
    assert last_conf >= first_conf


def test_simulate_item_empty():
    assert backtest.simulate_item("X", []) == []


# ---------- aggregate_by_bucket ----------

def test_aggregate_buckets_empty():
    out = backtest.aggregate_by_bucket([])
    assert len(out) == 5
    assert all(b["n"] == 0 for b in out)


def test_aggregate_buckets_distribuicao():
    samples = [
        {"item": "X", "ts": 0, "score": 20, "return_pct": -5.0,
         "breakdown_count": 0},
        {"item": "X", "ts": 0, "score": 25, "return_pct": -3.0,
         "breakdown_count": 0},
        {"item": "X", "ts": 0, "score": 60, "return_pct": 2.0,
         "breakdown_count": 0},
        {"item": "X", "ts": 0, "score": 90, "return_pct": 10.0,
         "breakdown_count": 0},
        {"item": "X", "ts": 0, "score": 100, "return_pct": 15.0,
         "breakdown_count": 0},
    ]
    out = backtest.aggregate_by_bucket(samples)
    by_label = {b["bucket"]: b for b in out}
    assert by_label["0-29"]["n"] == 2
    assert by_label["50-69"]["n"] == 1
    # 90 cai em 85-100 e 100 tambem (high=101)
    assert by_label["85-100"]["n"] == 2
    assert by_label["85-100"]["hit_rate"] == 100.0
    assert by_label["0-29"]["hit_rate"] == 0.0


def test_aggregate_hit_rate_calculo():
    samples = [
        {"item": "X", "ts": 0, "score": 75, "return_pct": 5.0,
         "breakdown_count": 0},
        {"item": "X", "ts": 0, "score": 75, "return_pct": -1.0,
         "breakdown_count": 0},
    ]
    out = backtest.aggregate_by_bucket(samples)
    bucket_70 = next(b for b in out if b["bucket"] == "70-84")
    assert bucket_70["n"] == 2
    assert bucket_70["hit_rate"] == 50.0
    assert bucket_70["avg_return_pct"] == 2.0


# ---------- correlation ----------

def test_correlation_positiva_perfeita():
    samples = [
        {"item": "X", "ts": 0, "score": s, "return_pct": float(s),
         "breakdown_count": 0}
        for s in [10, 20, 30, 40, 50, 60, 70, 80, 90]
    ]
    corr = backtest.correlation(samples)
    assert corr == 1.0


def test_correlation_negativa():
    samples = [
        {"item": "X", "ts": 0, "score": s, "return_pct": -float(s),
         "breakdown_count": 0}
        for s in [10, 30, 50, 70, 90]
    ]
    corr = backtest.correlation(samples)
    assert corr == -1.0


def test_correlation_insufficient():
    assert backtest.correlation([]) is None
    assert backtest.correlation([{"item": "X", "ts": 0, "score": 50,
                                   "return_pct": 5.0,
                                   "breakdown_count": 0}]) is None


def test_correlation_zero_variance():
    samples = [
        {"item": "X", "ts": 0, "score": 50, "return_pct": float(i),
         "breakdown_count": 0}
        for i in range(5)
    ]
    # Todos com mesmo score -> variancia 0 -> None
    assert backtest.correlation(samples) is None


# ---------- format_report ----------

def test_format_report_basico():
    buckets = backtest.aggregate_by_bucket([])
    out = backtest.format_report(buckets, correlation_value=0.1234,
                                  horizon_days=30, total_samples=0)
    assert "Backtest enhanced_score" in out
    assert "Bucket" in out
    assert "0.1234" in out


def test_format_report_sem_correlacao():
    buckets = backtest.aggregate_by_bucket([])
    out = backtest.format_report(buckets, horizon_days=30, total_samples=0)
    assert "Correlacao" not in out
