"""Metas financeiras — lógica pura (goals.py).

Persistência mockada via monkeypatch do _settings (nada toca disco real).
"""
from __future__ import annotations

import pytest

from skinvault import goals


class _FakeSettings:
    def __init__(self, data: dict):
        self.data = data

    def load_settings(self):
        return self.data

    def save_settings(self, data: dict):
        self.data = data


@pytest.fixture
def st(monkeypatch):
    fake = _FakeSettings({"goals": []})
    monkeypatch.setattr(goals, "_settings", fake)
    return fake


TOTALS = {
    "market": 1200.0,
    "net_if_sold": 1000.0,
    "pnl": 200.0,
    "cost_known": 800.0,
    "positions": 12,
}


# ── current_value ─────────────────────────────────────────────


def test_current_value_por_metrica():
    assert goals.current_value("market", TOTALS) == 1200.0
    assert goals.current_value("net", TOTALS) == 1000.0
    assert goals.current_value("pnl", TOTALS) == 200.0
    assert goals.current_value("items", TOTALS) == 12


def test_current_value_pnl_none_vira_zero():
    assert goals.current_value("pnl", {"pnl": None}) == 0.0


def test_current_value_metrica_desconhecida():
    assert goals.current_value("nada", TOTALS) == 0.0


def test_current_value_totals_vazio():
    assert goals.current_value("market", {}) == 0.0


# ── progress ──────────────────────────────────────────────────


def test_progress_parcial():
    p = goals.progress(500.0, 1000.0)
    assert p["pct"] == 50.0
    assert p["done"] is False
    assert p["remaining"] == 500.0


def test_progress_atingida():
    p = goals.progress(1000.0, 1000.0)
    assert p["pct"] == 100.0
    assert p["done"] is True
    assert p["remaining"] == 0.0


def test_progress_transborda_nao():
    p = goals.progress(2000.0, 1000.0)
    assert p["pct"] == 100.0
    assert p["done"] is True


def test_progress_alvo_invalido():
    p = goals.progress(500.0, 0.0)
    assert p["pct"] == 0.0
    assert p["done"] is False


def test_progress_negativo_clamp_zero():
    p = goals.progress(-10.0, 1000.0)
    assert p["pct"] == 0.0
    assert p["done"] is False


# ── persistência ──────────────────────────────────────────────


def test_load_goals_vazio(st):
    assert goals.load_goals() == []


def test_upsert_cria_e_normaliza(st):
    metas = goals.upsert_goal("Meta", 5000.0, "market")
    assert len(metas) == 1
    g = metas[0]
    assert g["label"] == "Meta"
    assert g["metric"] == "market"
    assert g["target"] == 5000.0
    assert g["enabled"] is True
    assert g["id"] == "g1"


def test_upsert_mesmo_rotulo_atualiza(st):
    goals.upsert_goal("Meta", 5000.0, "market")
    metas = goals.upsert_goal("Meta", 9000.0, "net")
    assert len(metas) == 1
    assert metas[0]["target"] == 9000.0
    assert metas[0]["metric"] == "net"


def test_remove_goal(st):
    metas = goals.upsert_goal("A", 100.0, "market")
    metas = goals.upsert_goal("B", 200.0, "items")
    rest = goals.remove_goal(metas[0]["id"])
    assert [g["label"] for g in rest] == ["B"]


def test_save_goals_ids_deterministicos(st):
    goals.save_goals([{"label": "X", "metric": "market", "target": 1.0},
                      {"label": "Y", "metric": "items", "target": 5}])
    data = st.load_settings()
    assert [g["id"] for g in data["goals"]] == ["g1", "g2"]


def test_normalize_metrica_invalida_cai_default(st):
    goals.save_goals([{"label": "X", "metric": "zzz", "target": 10.0}])
    assert goals.load_goals()[0]["metric"] == "market"


def test_normalize_alvo_invalido_vira_zero(st):
    goals.save_goals([{"label": "X", "metric": "market", "target": "abc"}])
    assert goals.load_goals()[0]["target"] == 0.0


def test_load_goals_nao_lista_vira_vazio(monkeypatch):
    fake = _FakeSettings({"goals": {"nao_e_lista": 1}})
    monkeypatch.setattr(goals, "_settings", fake)
    assert goals.load_goals() == []


# ── goal_rows (o que a UI renderiza) ──────────────────────────


def test_goal_rows_computa_progresso(st):
    goals.upsert_goal("Meta", 1000.0, "net")
    rows = goals.goal_rows(TOTALS)
    assert len(rows) == 1
    r = rows[0]
    assert r["current"] == 1000.0
    assert r["pct"] == 100.0
    assert r["done"] is True


def test_goal_rows_pula_desabilitada(st):
    goals.save_goals([{"label": "Off", "metric": "market",
                       "target": 100.0, "enabled": False},
                      {"label": "On", "metric": "items",
                       "target": 10.0, "enabled": True}])
    rows = goals.goal_rows(TOTALS)
    assert [r["label"] for r in rows] == ["On"]


def test_goal_rows_sem_metas(st):
    assert goals.goal_rows(TOTALS) == []


# ── parse_target ──────────────────────────────────────────────


def test_parse_target_formatos():
    assert goals.parse_target("5000") == 5000.0
    assert goals.parse_target("5.000") == 5000.0
    assert goals.parse_target("R$ 5.000,50") == 5000.5
    assert goals.parse_target("1234,56") == 1234.56


def test_parse_target_invalido_levanta():
    with pytest.raises(ValueError):
        goals.parse_target("")
    with pytest.raises(ValueError):
        goals.parse_target("abc")


def test_metric_label():
    assert goals.metric_label("market") == "Valor de mercado"
    assert goals.metric_label("x") == "x"
