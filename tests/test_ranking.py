"""Testes do snapshot de ranking."""
from __future__ import annotations

import time

from skinvault import ranking


def test_save_snapshot_basic(tmp_path):
    p = tmp_path / "r.json"
    results = [
        {"name": "A", "score": 80},
        {"name": "B", "score": 70},
        {"name": "C", "score": 60},
    ]
    snap = ranking.save_snapshot(results, path=p)
    assert len(snap["items"]) == 3
    assert snap["items"][0]["name"] == "A"
    assert snap["items"][0]["position"] == 1
    assert snap["items"][2]["position"] == 3


def test_save_snapshot_sorts_by_score(tmp_path):
    p = tmp_path / "r.json"
    results = [
        {"name": "Low", "score": 30},
        {"name": "High", "score": 90},
        {"name": "Mid", "score": 60},
    ]
    snap = ranking.save_snapshot(results, path=p)
    names = [it["name"] for it in snap["items"]]
    assert names == ["High", "Mid", "Low"]


def test_save_and_load_multiple(tmp_path):
    p = tmp_path / "r.json"
    ranking.save_snapshot([{"name": "A", "score": 50}], path=p)
    ranking.save_snapshot([{"name": "B", "score": 60}], path=p)
    snaps = ranking.load_snapshots(path=p)
    assert len(snaps) == 2


def test_snapshot_cap(tmp_path):
    p = tmp_path / "r.json"
    for i in range(ranking._SNAPSHOT_CAP + 10):
        ranking.save_snapshot([{"name": f"X{i}", "score": i}], path=p)
    snaps = ranking.load_snapshots(path=p)
    assert len(snaps) == ranking._SNAPSHOT_CAP


def test_previous_snapshot_none_when_single(tmp_path):
    p = tmp_path / "r.json"
    ranking.save_snapshot([{"name": "A", "score": 50}], path=p)
    assert ranking.previous_snapshot(path=p) is None


def test_previous_snapshot(tmp_path):
    p = tmp_path / "r.json"
    ranking.save_snapshot([{"name": "Old", "score": 50}], path=p)
    ranking.save_snapshot([{"name": "New", "score": 60}], path=p)
    prev = ranking.previous_snapshot(path=p)
    assert prev is not None
    assert prev["items"][0]["name"] == "Old"


def test_position_delta_no_previous():
    d = ranking.position_delta("A", 1, None)
    assert d["delta"] == 0
    assert d["prev_pos"] is None
    assert d["label"] == ""


def test_position_delta_subiu():
    prev = {"items": [{"name": "A", "position": 5}]}
    d = ranking.position_delta("A", 2, prev)
    assert d["delta"] == 3
    assert d["prev_pos"] == 5
    assert d["label"] == "+3"


def test_position_delta_caiu():
    prev = {"items": [{"name": "A", "position": 2}]}
    d = ranking.position_delta("A", 5, prev)
    assert d["delta"] == -3
    assert d["label"] == "-3"


def test_position_delta_igual():
    prev = {"items": [{"name": "A", "position": 3}]}
    d = ranking.position_delta("A", 3, prev)
    assert d["delta"] == 0
    assert d["label"] == "="


def test_position_delta_novo():
    prev = {"items": [{"name": "Other", "position": 1}]}
    d = ranking.position_delta("New", 5, prev)
    assert d["label"] == "NOVO"
    assert d["prev_pos"] is None


def test_latest_before(tmp_path):
    p = tmp_path / "r.json"
    ranking.save_snapshot([{"name": "old", "score": 10}], path=p)
    time.sleep(0.01)
    cutoff = time.time()
    time.sleep(0.01)
    ranking.save_snapshot([{"name": "new", "score": 20}], path=p)
    found = ranking.latest_before(cutoff, path=p)
    assert found is not None
    assert found["items"][0]["name"] == "old"


def test_latest_before_none_when_too_old(tmp_path):
    p = tmp_path / "r.json"
    ranking.save_snapshot([{"name": "a", "score": 0}], path=p)
    # cutoff anterior a qualquer snapshot
    assert ranking.latest_before(0, path=p) is None


def test_clear_rankings(tmp_path):
    p = tmp_path / "r.json"
    ranking.save_snapshot([{"name": "A", "score": 50}], path=p)
    assert len(ranking.load_snapshots(path=p)) == 1
    ranking.clear_rankings(path=p)
    assert ranking.load_snapshots(path=p) == []
