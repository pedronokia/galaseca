"""Testes do historico de valor (roundtrip em arquivo temporario)."""
from __future__ import annotations

from skinvault import history


def test_record_and_load_roundtrip(tmp_path):
    p = tmp_path / "h.json"
    history.record_snapshot(100.0, path=p, now=1000)
    history.record_snapshot(150.0, path=p, now=2000)
    series = history.load_history(path=p)
    assert [s["total"] for s in series] == [100.0, 150.0]
    assert [s["ts"] for s in series] == [1000, 2000]


def test_load_missing_returns_empty(tmp_path):
    assert history.load_history(path=tmp_path / "nao_existe.json") == []


def test_history_caps_length(tmp_path):
    p = tmp_path / "h.json"
    for i in range(520):
        history.record_snapshot(float(i), path=p, now=i)
    series = history.load_history(path=p)
    assert len(series) == 500                 # capou
    assert series[-1]["total"] == 519.0       # manteve os mais recentes
