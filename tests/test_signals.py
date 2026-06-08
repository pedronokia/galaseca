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
    """Preco acima da SMA curta soma 5 vs preco igual a' SMA.

    Note: rel_ath tambem aplica em ph >= 10. Testamos a DIFERENCA
    introduzida pelo momentum isolado.
    """
    v = {"verdict": "fair", "diff_pct": 0}
    ph_up = [{"price_median": 100.0}] * 14 + [{"price_median": 110.0}]
    ph_flat = [{"price_median": 100.0}] * 15
    delta = (signals.scan_score(v, price_history=ph_up)
              - signals.scan_score(v, price_history=ph_flat))
    assert delta == 5  # so' o fator momentum


def test_scan_score_momentum_negative():
    """Preco abaixo da SMA curta penaliza 5 vs preco igual a' SMA."""
    v = {"verdict": "fair", "diff_pct": 0}
    ph_down = [{"price_median": 100.0}] * 14 + [{"price_median": 90.0}]
    ph_flat = [{"price_median": 100.0}] * 15
    delta = (signals.scan_score(v, price_history=ph_down)
              - signals.scan_score(v, price_history=ph_flat))
    assert delta == -5


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


# ── Edge cases de persistencia ─────────────────────────
def test_record_item_price_corrupted_json(tmp_path):
    """Arquivo JSON corrompido e' tratado como vazio."""
    p = tmp_path / "ih.json"
    p.write_text("corrupt{json", encoding="utf-8")
    signals.record_item_price("AK", 100.0, path=p)
    h = signals.load_item_history("AK", path=p)
    assert len(h) == 1


def test_load_item_history_corrupted_json(tmp_path):
    """JSON corrompido retorna lista vazia."""
    p = tmp_path / "ih.json"
    p.write_text("corrupt", encoding="utf-8")
    assert signals.load_item_history("AK", path=p) == []


def test_record_item_price_oserror_ignored(tmp_path):
    """Erro de escrita no save e' silencioso."""
    file_path = tmp_path / "afile"
    file_path.write_text("", encoding="utf-8")
    bad = file_path / "ih.json"
    signals.record_item_price("AK", 100.0, path=bad)
    # nao crashou


def test_record_metric_corrupted_json(tmp_path, monkeypatch):
    """JSON corrompido em metrica e' tratado como vazio."""
    p = tmp_path / "m.json"
    p.write_text("corrupt{json", encoding="utf-8")
    monkeypatch.setattr(signals, "_VOLUME_PATH", p)
    signals.record_item_volume("AK", 500)
    h = signals.load_item_volume("AK")
    assert len(h) == 1


def test_record_metric_oserror_ignored(tmp_path, monkeypatch):
    """Erro de escrita em metrica e' silencioso."""
    file_path = tmp_path / "afile"
    file_path.write_text("", encoding="utf-8")
    bad = file_path / "m.json"
    monkeypatch.setattr(signals, "_VOLUME_PATH", bad)
    signals.record_item_volume("AK", 500)
    # nao crashou


def test_load_metric_corrupted_json(tmp_path, monkeypatch):
    """JSON corrompido em metrica retorna lista vazia."""
    p = tmp_path / "m.json"
    p.write_text("corrupt", encoding="utf-8")
    monkeypatch.setattr(signals, "_VOLUME_PATH", p)
    assert signals.load_item_volume("AK") == []


def test_record_metric_cap_200(tmp_path, monkeypatch):
    """_record_metric cap em 200 entradas."""
    p = tmp_path / "m.json"
    monkeypatch.setattr(signals, "_VOLUME_PATH", p)
    for i in range(205):
        signals.record_item_volume("Item", float(i))
    h = signals.load_item_volume("Item")
    assert len(h) == 200
    assert h[0]["value"] == 5.0


# ── Edge cases de analise ──────────────────────────────
def test_volume_anomaly_avg_zero():
    """Quando a media e' zero, nao ha anomalia."""
    h = [{"value": 0}] * 4 + [{"value": 100}]
    a = signals.volume_anomaly(h)
    assert a["is_anomaly"] is False


def test_multi_trend_tolerance_exceeded():
    """Entry muito distante do cutoff e' ignorado."""
    now = time.time()
    ph = [
        {"time": now - 100, "price_median": 100.0},       # muito perto
        {"time": now - 10, "price_median": 110.0},         # recente
    ]
    result = signals.multi_trend(ph, periods=[24])
    assert "24h" not in result  # nenhum entry perto de 24h atras


def test_multi_trend_first_price_zero():
    """Pulga entry com first_price == 0."""
    now = time.time()
    ph = [
        {"time": now - 90000, "price_median": 0.0},
        {"time": now - 1000, "price_median": 110.0},
    ]
    result = signals.multi_trend(ph, periods=[24])
    assert "24h" not in result


def test_find_support_resistance_with_resistance():
    """Detecta pontos de resistencia."""
    ph = []
    for i in range(20):
        ph.append({"price_median": 100.0 + (i % 5) * 5})
    sr = signals.find_support_resistance(ph, window=2)
    assert isinstance(sr["support"], list)
    assert isinstance(sr["resistance"], list)


def test_find_support_resistance_clustering_merge():
    """Niveis proximos sao agrupados em um unico nivel."""
    ph = [{"price_median": 100.0}] * 10
    ph[3] = {"price_median": 90.0}  # primeiro suporte
    ph[7] = {"price_median": 91.0}  # segundo suporte (proximo)
    sr = signals.find_support_resistance(ph, window=2, min_separation_pct=5.0)
    assert len(sr["support"]) >= 1


def test_find_support_resistance_clustering_keep_separate():
    """Niveis distantes mantem-se separados."""
    ph = [{"price_median": 100.0}] * 10
    ph[3] = {"price_median": 90.0}   # primeiro suporte
    ph[7] = {"price_median": 50.0}   # segundo suporte (distante)
    sr = signals.find_support_resistance(ph, window=2, min_separation_pct=5.0)
    assert len(sr["support"]) >= 2


def test_enhanced_score_delta_zero_skipped():
    """_add com delta=0 nao altera score nem breakdown."""
    v = {"verdict": "fair", "diff_pct": 0}
    score, breakdown = signals.enhanced_score(v)
    assert score == 50
    assert breakdown == []


# ---------- relative_to_ath ----------

def test_relative_to_ath_historico_curto():
    assert signals.relative_to_ath([]) == {}
    assert signals.relative_to_ath(
        [{"time": 0, "price_median": 10, "purchases": 1}] * 5
    ) == {}


def test_relative_to_ath_no_topo():
    # ATH e' o ultimo ponto
    ph = [{"time": i, "price_median": float(i), "purchases": 1}
          for i in range(20)]
    r = signals.relative_to_ath(ph)
    assert r["pct_of_ath"] == 1.0
    assert r["band"] == "at_ath"


def test_relative_to_ath_squeeze_inicial():
    # ATH historico 100, atual 3 -> 3% do ATH -> very_deep
    prices = [100.0] * 18 + [50.0] + [3.0]
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    r = signals.relative_to_ath(ph)
    assert r["band"] == "very_deep"
    assert r["pct_of_ath"] < 0.05


def test_relative_to_ath_squeeze_tardio():
    # ATH 100, atual 60 -> 60% -> near_ath (squeeze tardio)
    prices = [10.0, 100.0] + [60.0] * 18
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    r = signals.relative_to_ath(ph)
    assert r["band"] == "near_ath"
    assert 0.5 <= r["pct_of_ath"] < 0.9


def test_relative_to_ath_midrange():
    prices = [10.0, 100.0] + [30.0] * 18
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    r = signals.relative_to_ath(ph)
    assert r["band"] == "midrange"


def test_enhanced_score_rel_ath_aplica_universal():
    """rel_ath aplica para qualquer item (skin ou container)."""
    prices = [100.0] * 18 + [50.0] + [3.0]
    ph = [{"time": i, "price_median": p, "purchases": 5}
          for i, p in enumerate(prices)]
    v = {"verdict": "fair", "diff_pct": 0}
    # Sem is_container (skin)
    _, breakdown_skin = signals.enhanced_score(v, price_history=ph)
    assert "rel_ath" in [b["factor"] for b in breakdown_skin]
    # Com is_container=True (container)
    _, breakdown_cont = signals.enhanced_score(
        v, price_history=ph, is_container=True,
    )
    assert "rel_ath" in [b["factor"] for b in breakdown_cont]


def test_enhanced_score_rel_ath_squeeze_inicial_bonifica():
    """Squeeze inicial (atual << ATH) recebe +5."""
    # ATH 100, atual 3
    prices = [100.0] * 18 + [50.0] + [3.0]
    ph = [{"time": i, "price_median": p, "purchases": 5}
          for i, p in enumerate(prices)]
    v = {"verdict": "fair", "diff_pct": 0}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    rel = next((b for b in breakdown if b["factor"] == "rel_ath"), None)
    assert rel is not None
    assert rel["delta"] == 5


def test_enhanced_score_rel_ath_squeeze_tardio_penaliza():
    """Preco perto do ATH recebe -8 (squeeze tardio)."""
    # ATH 100, atual 60
    prices = [10.0, 100.0] + [60.0] * 18
    ph = [{"time": i, "price_median": p, "purchases": 5}
          for i, p in enumerate(prices)]
    v = {"verdict": "fair", "diff_pct": 0}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    rel = next((b for b in breakdown if b["factor"] == "rel_ath"), None)
    assert rel is not None
    assert rel["delta"] == -8


# ---------- price_zscore ----------

def _mk_ph(prices, start_ts=0, step=86400):
    return [{"time": start_ts + i * step,
             "price_median": p, "purchases": 5}
            for i, p in enumerate(prices)]


def test_zscore_historico_curto():
    assert signals.price_zscore([]) == {}
    assert signals.price_zscore(_mk_ph([100.0] * 10)) == {}


def test_zscore_preco_estavel_neutral():
    # 30 dias de preco constante => std=0 => retorna {}
    assert signals.price_zscore(_mk_ph([100.0] * 30)) == {}


def test_zscore_extremo_baixo():
    # 29 dias em 100, ultimo dia em 50 (queda forte)
    prices = [100.0] * 29 + [50.0]
    z = signals.price_zscore(_mk_ph(prices))
    assert z["band"] == "extreme_low"
    assert z["z"] < -2


def test_zscore_extremo_alto():
    prices = [100.0] * 29 + [200.0]
    z = signals.price_zscore(_mk_ph(prices))
    assert z["band"] == "extreme_high"
    assert z["z"] > 2


def test_zscore_neutral_dentro_da_banda():
    # leve variacao -> z proximo de 0
    import random
    random.seed(42)
    prices = [100.0 + random.uniform(-1, 1) for _ in range(30)]
    z = signals.price_zscore(_mk_ph(prices))
    assert -1 < z["z"] < 1
    assert z["band"] == "neutral"


def test_zscore_label_format():
    prices = [100.0] * 29 + [50.0]
    z = signals.price_zscore(_mk_ph(prices))
    assert "Z=" in z["label"]
    assert "extreme_low" in z["label"]


def test_zscore_window_respeitada():
    # janela 10 com 30 pontos -> usa so os ultimos 10
    prices = [100.0] * 20 + [50.0] * 9 + [40.0]
    z = signals.price_zscore(_mk_ph(prices), window=10)
    assert z["window_used"] == 10
    # mean perto de 49 (9*50 + 40)/10
    assert 47 < z["mean"] < 51


# ---------- data_quality ----------

def test_data_quality_vazio():
    r = signals.data_quality([])
    assert r["confidence"] == 0.0
    assert r["level"] == "none"
    assert r["n"] == 0


def test_data_quality_alta_confianca():
    """Historico grande e recente => high confidence."""
    now = time.time()
    ph = [{"time": now - i * 86400, "price_median": 100.0, "purchases": 5}
          for i in range(200)]
    r = signals.data_quality(ph)
    assert r["confidence"] >= 0.9
    assert r["level"] == "high"
    assert r["n"] == 200


def test_data_quality_baixa_n():
    """N pequeno reduz confidence."""
    now = time.time()
    ph = [{"time": now - i * 86400, "price_median": 100.0, "purchases": 5}
          for i in range(20)]
    r = signals.data_quality(ph)
    # 20/200 = 0.1 * recencia ~1 = 0.1
    assert r["confidence"] < 0.2
    assert r["level"] == "very_low"


def test_data_quality_antigo_decai():
    """Histórico antigo (>180d) zera recência => confidence 0."""
    now = time.time()
    ph = [{"time": now - 200 * 86400 - i * 86400,
           "price_median": 100.0, "purchases": 5}
          for i in range(200)]
    r = signals.data_quality(ph)
    assert r["confidence"] == 0.0
    assert r["age_days"] > 180


def test_data_quality_medio_decay():
    """Histórico em 90d (na rampa) gera medium ou low."""
    now = time.time()
    # Histórico denso mas com ultimo ponto 90d atras
    ph = [{"time": now - 90 * 86400 - i * 86400,
           "price_median": 100.0, "purchases": 5}
          for i in range(200)]
    r = signals.data_quality(ph)
    # size_factor=1, recency=(180-90)/150=0.6 => confidence ~0.6
    assert 0.4 <= r["confidence"] <= 0.7
    assert r["level"] in ("medium", "low")


def test_data_quality_level_thresholds():
    """Levels separados por confidence."""
    now = time.time()
    # Construir histórias com confidence-alvo
    # n=160, recencia=1 => 0.8 -> high
    ph_high = [{"time": now - i * 86400, "price_median": 1.0, "purchases": 1}
               for i in range(160)]
    assert signals.data_quality(ph_high)["level"] == "high"
    # n=100, recencia=1 => 0.5 -> medium
    ph_med = [{"time": now - i * 86400, "price_median": 1.0, "purchases": 1}
              for i in range(100)]
    assert signals.data_quality(ph_med)["level"] == "medium"
    # n=50, recencia=1 => 0.25 -> low
    ph_low = [{"time": now - i * 86400, "price_median": 1.0, "purchases": 1}
              for i in range(50)]
    assert signals.data_quality(ph_low)["level"] == "low"


def test_data_quality_now_parametro():
    """Passar now no futuro reduz confidence pra historico velho."""
    now = time.time()
    ph = [{"time": now - i * 86400, "price_median": 100.0, "purchases": 5}
          for i in range(200)]
    r_now = signals.data_quality(ph)
    r_future = signals.data_quality(ph, now=now + 365 * 86400)
    assert r_now["confidence"] > r_future["confidence"]
    assert r_future["level"] in ("very_low", "none")


def test_data_quality_now_no_passado():
    """now no passado pode tornar historico futuro 'recente' (sanity check)."""
    now = time.time()
    ph = [{"time": now + i * 86400, "price_median": 100.0, "purchases": 5}
          for i in range(200)]
    # Com now=now (real), o ultimo ponto e' 200d no futuro, age negativo -> recente
    # Mais util: now no futuro real == ultimo ponto => age=0 => recencia=1
    r = signals.data_quality(ph, now=now + 200 * 86400)
    assert r["confidence"] >= 0.9


def test_data_quality_label_contem_info():
    now = time.time()
    ph = [{"time": now - i * 86400, "price_median": 100.0, "purchases": 5}
          for i in range(50)]
    r = signals.data_quality(ph)
    assert "n=50" in r["label"]
    assert r["level"] in r["label"]


# ---------- drawdown ----------

def test_drawdown_historico_curto():
    assert signals.drawdown([]) == {}
    assert signals.drawdown(_mk_ph([100.0] * 3)) == {}


def test_drawdown_at_high():
    # preco no maximo da janela
    prices = [80.0, 90.0, 100.0, 95.0, 100.0]
    dd = signals.drawdown(_mk_ph(prices, step=86400), window_days=90)
    assert dd["band"] == "at_high"
    assert dd["drawdown_pct"] == 0


def test_drawdown_deep():
    # max 200, atual 100 = 50% DD
    prices = [100.0, 150.0, 200.0, 150.0, 100.0]
    dd = signals.drawdown(_mk_ph(prices, step=86400), window_days=90)
    assert dd["band"] == "deep"
    assert dd["drawdown_pct"] == 50.0
    assert dd["max_price"] == 200.0


def test_drawdown_moderate():
    # max 100, atual 80 = 20% DD => moderate
    prices = [80.0, 90.0, 100.0, 95.0, 80.0]
    dd = signals.drawdown(_mk_ph(prices, step=86400), window_days=90)
    assert dd["band"] == "moderate"


def test_drawdown_mild():
    # max 100, atual 92 = 8% DD => mild
    prices = [85.0, 90.0, 100.0, 95.0, 92.0]
    dd = signals.drawdown(_mk_ph(prices, step=86400), window_days=90)
    assert dd["band"] == "mild"


def test_drawdown_window_respeitada():
    # janela menor que historico => so' usa parte recente
    # primeiros 30 dias: pico 200. ultimos 20 dias: pico 100
    prices = [200.0] + [100.0] * 49
    import time
    now = time.time()
    hist = [{"time": now - (50 - i) * 86400,
             "price_median": p, "purchases": 5}
            for i, p in enumerate(prices)]
    dd = signals.drawdown(hist, window_days=20)
    # janela so' pega ultimos 20 dias -> pico = 100, atual = 100 -> at_high
    assert dd["band"] == "at_high"


def test_drawdown_days_since_max():
    prices = [200.0, 100.0, 100.0, 100.0, 100.0]
    dd = signals.drawdown(_mk_ph(prices, step=86400), window_days=90)
    assert dd["days_since_max"] == 4.0


def test_enhanced_score_drawdown_at_high_rising():
    """At high + trend rising => bonus +5."""
    # cria historico com preco subindo terminando no maximo
    prices = [80.0] * 25 + [85.0, 90.0, 95.0, 98.0, 100.0]
    ph = _mk_ph(prices)
    v = {"verdict": "fair", "diff_pct": 2.0, "trend_verdict": "rising"}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    factors = [b["factor"] for b in breakdown]
    assert "drawdown" in factors
    dd_f = next(b for b in breakdown if b["factor"] == "drawdown")
    assert dd_f["delta"] == 5


def test_enhanced_score_drawdown_deep_falling():
    """Deep DD + falling => penalidade -5."""
    prices = [200.0] * 5 + [100.0] * 25
    ph = _mk_ph(prices)
    v = {"verdict": "fair", "diff_pct": 0, "trend_verdict": "falling"}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    dd_f = next(b for b in breakdown if b["factor"] == "drawdown")
    assert dd_f["delta"] == -5


def test_enhanced_score_drawdown_deep_rising():
    """Deep DD + rising => bonus de recuperacao +5."""
    prices = [200.0] * 5 + [100.0] * 25
    ph = _mk_ph(prices)
    v = {"verdict": "fair", "diff_pct": 0, "trend_verdict": "rising"}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    dd_f = next(b for b in breakdown if b["factor"] == "drawdown")
    assert dd_f["delta"] == 5


def test_enhanced_score_drawdown_sem_trend_sem_fator():
    """Sem trend_verdict => drawdown nao entra."""
    prices = [80.0] * 25 + [100.0] * 5
    ph = _mk_ph(prices)
    v = {"verdict": "fair", "diff_pct": 0}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    assert "drawdown" not in [b["factor"] for b in breakdown]


def test_enhanced_score_nao_inclui_zscore():
    """Z-score nao entra no enhanced_score (varios experimentos negativos).

    A funcao price_zscore() continua disponivel como sinal standalone.
    """
    prices = [100.0] * 28 + [85.0, 80.0]
    ph = _mk_ph(prices)
    v = {"verdict": "fair", "diff_pct": -10.0, "trend_verdict": "rising"}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    assert "zscore" not in [b["factor"] for b in breakdown]


# ---------- cases.is_container ----------

def test_is_container_caixa_conhecida():
    from skinvault import cases
    assert cases.is_container("Clutch Case") is True
    assert cases.is_container("Prisma Case") is True


def test_is_container_skin_de_arma():
    from skinvault import cases
    assert cases.is_container("AK-47 | Redline (Field-Tested)") is False
    assert cases.is_container("AWP | Asiimov (Field-Tested)") is False


def test_is_container_capsula():
    from skinvault import cases
    assert cases.is_container("Stockholm 2021 Legends Sticker Capsule") is True


def test_is_container_vazio():
    from skinvault import cases
    assert cases.is_container("") is False
    assert cases.is_container(None) is False


def test_enhanced_score_sem_zscore_se_historico_curto():
    """Historico < 30 nao deve incluir fator zscore."""
    ph = _mk_ph([100.0] * 15 + [50.0] * 5)
    v = {"verdict": "fair", "diff_pct": 0}
    _, breakdown = signals.enhanced_score(v, price_history=ph)
    assert "zscore" not in [b["factor"] for b in breakdown]


# ---------- is_score_stale / score_age_text ----------

def test_is_score_stale_none():
    assert signals.is_score_stale(None) is True


def test_is_score_stale_fresh():
    ts = time.time() - 3600  # 1h atras
    assert signals.is_score_stale(ts) is False


def test_is_score_stale_old():
    ts = time.time() - 8 * 86400  # 8d atras
    assert signals.is_score_stale(ts) is True


def test_is_score_stale_boundary():
    ts = time.time() - 7 * 86400  # exatos 7d
    assert signals.is_score_stale(ts) is False


def test_is_score_stale_custom_max_age():
    ts = time.time() - 3 * 86400  # 3d
    assert signals.is_score_stale(ts, max_age_days=2) is True
    assert signals.is_score_stale(ts, max_age_days=5) is False


def test_score_age_text_none():
    assert "nunca calculado" in signals.score_age_text(None)


def test_score_age_text_fresh():
    assert signals.score_age_text(time.time()) == "agora"


def test_score_age_text_minutes():
    ts = time.time() - 300  # 5min
    txt = signals.score_age_text(ts)
    assert "min" in txt


def test_score_age_text_hours():
    ts = time.time() - 7200  # 2h
    txt = signals.score_age_text(ts)
    assert "h" in txt


def test_score_age_text_days():
    ts = time.time() - 5 * 86400  # 5d
    txt = signals.score_age_text(ts)
    assert "d" in txt


# === pump_risk ===

def test_pump_risk_low_estavel():
    # Preço estável em ~30% do ATH (midrange), sem rally, sem volume anômalo
    prices = [100.0] + [30.0] * 19
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    r = signals.pump_risk(ph, volume_history=None)
    assert r["level"] == "low"
    assert r["flags"] == 0


def test_pump_risk_high_pump_pattern():
    # Preço subiu de 10 -> 100 nos ultimos 14d (rally +900%) e está no ATH
    prices = [10.0] * 15 + [20.0, 40.0, 60.0, 80.0, 100.0]
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    r = signals.pump_risk(ph, volume_history=None)
    # ATH (1 flag) + Rally +30% (1 flag) -> high
    assert r["level"] == "high"
    assert r["flags"] == 2
    assert any("ATH" in reason for reason in r["reasons"])
    assert any("Rally" in reason for reason in r["reasons"])


def test_pump_risk_medium_near_ath_sem_rally():
    # No ATH mas sem rally recente (estável há tempo)
    prices = [100.0] * 20
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    r = signals.pump_risk(ph, volume_history=None)
    # at_ath (1 flag) — sem rally (mesma faixa)
    assert r["level"] == "medium"
    assert r["flags"] == 1


def test_pump_risk_high_com_volume():
    # Near ATH + volume sustentado 7d 3x acima da media 30d
    prices = [50.0] * 15 + [55.0, 60.0, 70.0, 80.0, 90.0]
    ph = [{"time": i, "price_median": p, "purchases": 1}
          for i, p in enumerate(prices)]
    # 30 entries de volume: baseline ~100, recent 7d ~300
    vol = [{"ts": i, "value": 100.0} for i in range(23)]
    vol += [{"ts": i + 23, "value": 300.0} for i in range(7)]
    r = signals.pump_risk(ph, volume_history=vol)
    # rally (90/50 = +80%) + at_ath + volume = 3 flags -> high
    assert r["level"] == "high"
    assert r["flags"] >= 2


def test_pump_risk_historico_curto_retorna_low():
    ph = [{"time": i, "price_median": 50.0, "purchases": 1}
          for i in range(5)]
    r = signals.pump_risk(ph, volume_history=None)
    assert r["level"] == "low"
    assert r["flags"] == 0


def test_pump_risk_sem_inputs():
    r = signals.pump_risk(None, None)
    assert r["level"] == "low"
    assert r["flags"] == 0
    assert r["reasons"] == []
