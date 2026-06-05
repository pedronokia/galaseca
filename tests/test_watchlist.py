"""Testes da watchlist."""
from __future__ import annotations

from skinvault import watchlist


def test_add_and_load(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("AK-47 | Redline", 200.0, path=p)
    items = watchlist.load_watchlist(path=p)
    assert len(items) == 1
    assert items[0]["name"] == "AK-47 | Redline"
    assert items[0]["target"] == 200.0
    assert items[0]["triggered"] is False


def test_remove(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("A", 100.0, path=p)
    watchlist.add_watch("B", 200.0, path=p)
    watchlist.remove_watch(0, path=p)
    items = watchlist.load_watchlist(path=p)
    assert len(items) == 1
    assert items[0]["name"] == "B"


def test_clear_watchlist(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("A", 100.0, path=p)
    watchlist.add_watch("B", 200.0, path=p)
    watchlist.clear_watchlist(path=p)
    assert watchlist.load_watchlist(path=p) == []


def test_load_empty(tmp_path):
    assert watchlist.load_watchlist(tmp_path / "empty.json") == []


def test_remove_invalid_index(tmp_path):
    items = watchlist.remove_watch(99, path=tmp_path / "w.json")
    assert items == []
