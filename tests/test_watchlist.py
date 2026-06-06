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


def test_add_duplicate_ignored(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("AK", 100.0, path=p)
    items = watchlist.add_watch("AK", 200.0, path=p)
    assert len(items) == 1
    assert items[0]["target"] == 100.0  # original mantido


def test_add_negative_target_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        watchlist.add_watch("AK", -1.0, path=tmp_path / "w.json")


def test_add_zero_target_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        watchlist.add_watch("AK", 0, path=tmp_path / "w.json")


def test_update_target(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("AK", 100.0, path=p)
    items = watchlist.update_target("AK", 150.0, path=p)
    assert items[0]["target"] == 150.0
    assert items[0]["triggered"] is False


def test_update_target_inexistent(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("AK", 100.0, path=p)
    items = watchlist.update_target("AWP", 200.0, path=p)
    assert len(items) == 1  # nao adicionou


def test_update_target_negative_raises(tmp_path):
    import pytest
    p = tmp_path / "w.json"
    watchlist.add_watch("AK", 100.0, path=p)
    with pytest.raises(ValueError):
        watchlist.update_target("AK", -5.0, path=p)


def test_reset_trigger(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("AK", 100.0, path=p)
    items = watchlist.load_watchlist(path=p)
    items[0]["triggered"] = True
    watchlist.save_watchlist(items, path=p)
    items = watchlist.reset_trigger("AK", path=p)
    assert items[0]["triggered"] is False


def test_reset_trigger_inexistent(tmp_path):
    p = tmp_path / "w.json"
    watchlist.add_watch("AK", 100.0, path=p)
    items = watchlist.reset_trigger("AWP", path=p)
    assert len(items) == 1  # nao crashou


def test_load_invalid_json(tmp_path):
    p = tmp_path / "w.json"
    p.write_text("corrupt", encoding="utf-8")
    assert watchlist.load_watchlist(path=p) == []


def test_save_watchlist_oserror_ignored(tmp_path):
    p = tmp_path / "w.json"
    watchlist.save_watchlist([{"name": "AK"}], path=p)
    p.unlink()
    p.mkdir()  # agora e' diretorio
    watchlist.save_watchlist([{"name": "AK"}], path=p)  # nao crashou
