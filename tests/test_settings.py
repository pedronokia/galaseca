from __future__ import annotations

from skinvault import settings


def test_defaults():
    s = settings.load_settings(path="nonexistent.json")
    assert s["cache_ttl_hours"] == 6
    assert s["fee_rate"] == 0.15
    assert s["auto_backup"] is True
    assert s["keep_backups"] == 10


def test_save_and_load(tmp_path):
    p = tmp_path / "settings.json"
    data = {"cache_ttl_hours": 12, "fee_rate": 0.10, "keep_backups": 5}
    settings.save_settings(data, path=p)
    loaded = settings.load_settings(path=p)
    assert loaded["cache_ttl_hours"] == 12
    assert loaded["fee_rate"] == 0.10
    assert loaded["keep_backups"] == 5
    assert loaded["auto_backup"] is True


def test_partial_update(tmp_path):
    p = tmp_path / "settings.json"
    settings.save_settings({"cache_ttl_hours": 3}, path=p)
    loaded = settings.load_settings(path=p)
    assert loaded["cache_ttl_hours"] == 3
    assert loaded["fee_rate"] == 0.15
