"""Testes de recommendations.py (candidatos de compra + vigia de venda)."""
from __future__ import annotations

from skinvault import recommendations as rec


def _scan_row(name, score, pump_level="low", breakdown=None, **extra):
    row = {
        "name": name,
        "score": score,
        "pump_risk": {"level": pump_level, "flags": 0, "reasons": []},
        "breakdown": breakdown or [],
    }
    row.update(extra)
    return row


# ── buy_candidates ──────────────────────────────────────────────

def test_buy_candidates_ordena_por_score():
    rows = [_scan_row("A", 60), _scan_row("B", 90), _scan_row("C", 75)]
    out = rec.buy_candidates(rows)
    assert [r["name"] for r in out] == ["B", "C", "A"]


def test_buy_candidates_exclui_owned():
    rows = [_scan_row("A", 90), _scan_row("B", 80)]
    out = rec.buy_candidates(rows, owned_names={"a"})
    assert [r["name"] for r in out] == ["B"]


def test_buy_candidates_owned_case_insensitive_e_strip():
    rows = [_scan_row("AK-47 | Redline", 90)]
    out = rec.buy_candidates(rows, owned_names={" ak-47 | redline "})
    assert out == []


def test_buy_candidates_filtra_pump_risk_high_por_default():
    rows = [_scan_row("A", 95, pump_level="high"), _scan_row("B", 70)]
    out = rec.buy_candidates(rows)
    assert [r["name"] for r in out] == ["B"]


def test_buy_candidates_max_pump_risk_high_nao_filtra():
    rows = [_scan_row("A", 95, pump_level="high")]
    out = rec.buy_candidates(rows, max_pump_risk="high")
    assert [r["name"] for r in out] == ["A"]


def test_buy_candidates_limit():
    rows = [_scan_row(str(i), i) for i in range(20)]
    out = rec.buy_candidates(rows, limit=3)
    assert len(out) == 3
    assert [r["name"] for r in out] == ["19", "18", "17"]


def test_buy_candidates_reasons_so_fatores_positivos():
    breakdown = [
        {"factor": "mediana", "delta": 20, "label": "Preço baixo (+20)"},
        {"factor": "trend", "delta": -10, "label": "Caindo (-10)"},
        {"factor": "spread", "delta": 15, "label": "Fácil de vender (+15)"},
    ]
    rows = [_scan_row("A", 80, breakdown=breakdown)]
    out = rec.buy_candidates(rows)
    assert out[0]["reasons"] == ["Preço baixo (+20)", "Fácil de vender (+15)"]


def test_buy_candidates_reasons_cap_em_3():
    breakdown = [{"factor": f"f{i}", "delta": 1, "label": f"r{i}"}
                 for i in range(5)]
    rows = [_scan_row("A", 80, breakdown=breakdown)]
    out = rec.buy_candidates(rows)
    assert len(out[0]["reasons"]) == 3


def test_buy_candidates_vazio():
    assert rec.buy_candidates([]) == []


def test_buy_candidates_ignora_linha_sem_name():
    rows = [{"score": 90}, _scan_row("A", 80)]
    out = rec.buy_candidates(rows)
    assert [r["name"] for r in out] == ["A"]


# ── sell_watch ──────────────────────────────────────────────────

def _ctx(pct, ath=100.0, current=None, at_launch=False):
    return {"pct_of_ath": pct, "ath": ath,
            "current": current if current is not None else ath * pct,
            "at_launch": at_launch}


def test_sell_watch_inclui_posicao_no_topo():
    positions = [{"name": "A", "quantity": 2, "exit_ctx": _ctx(0.95)}]
    out = rec.sell_watch(positions)
    assert len(out) == 1
    assert out[0]["name"] == "A"
    assert out[0]["exit_context"]["level"] == "topo"


def test_sell_watch_exclui_posicao_no_meio_sem_pump_risk():
    positions = [{"name": "A", "exit_ctx": _ctx(0.35)}]
    out = rec.sell_watch(positions)
    assert out == []


def test_sell_watch_inclui_por_pump_risk_mesmo_com_exit_context_baixo():
    positions = [{"name": "A", "exit_ctx": _ctx(0.10)}]
    out = rec.sell_watch(
        positions, pump_risk_by_name={"A": {"level": "high", "reasons": []}})
    assert len(out) == 1


def test_sell_watch_sem_exit_ctx_e_sem_pump_risk_fica_fora():
    positions = [{"name": "A"}]
    out = rec.sell_watch(positions)
    assert out == []


def test_sell_watch_ordena_topo_antes_de_alto():
    positions = [
        {"name": "Alto", "exit_ctx": _ctx(0.55)},
        {"name": "Topo", "exit_ctx": _ctx(0.92)},
    ]
    out = rec.sell_watch(positions)
    assert [r["name"] for r in out] == ["Topo", "Alto"]


def test_sell_watch_min_level_baixo_inclui_tudo_com_contexto():
    positions = [{"name": "A", "exit_ctx": _ctx(0.10)}]
    out = rec.sell_watch(positions, min_level="baixo")
    assert len(out) == 1


def test_sell_watch_preserva_quantity_e_score():
    positions = [{"name": "A", "quantity": 3, "current_score": 72,
                  "score_ts": 123.0, "exit_ctx": _ctx(0.95)}]
    out = rec.sell_watch(positions)
    assert out[0]["quantity"] == 3
    assert out[0]["current_score"] == 72
    assert out[0]["score_ts"] == 123.0


def test_sell_watch_ctx_invalido_nao_quebra():
    positions = [{"name": "A", "exit_ctx": {"pct_of_ath": "x"}}]
    out = rec.sell_watch(positions)
    assert out == []


# ── missing_validation ───────────────────────────────────────────

def test_missing_validation():
    positions = [
        {"name": "A", "exit_ctx": _ctx(0.5)},
        {"name": "B"},
        {"name": "C", "exit_ctx": None},
    ]
    assert rec.missing_validation(positions) == ["B", "C"]


def test_missing_validation_vazio():
    assert rec.missing_validation([]) == []
