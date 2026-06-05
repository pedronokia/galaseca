from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from skinvault import backup


def test_make_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "DATA_DIR", tmp_path)
    (tmp_path / "portfolio.json").write_text("[]", encoding="utf-8")
    (tmp_path / "trades.json").write_text("[]", encoding="utf-8")

    path = backup.make_backup(keep=5)
    assert path is not None
    assert zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as z:
        assert "portfolio.json" in z.namelist()
        assert "trades.json" in z.namelist()


def test_backup_nonexistent_data(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "DATA_DIR", tmp_path / "empty")
    path = backup.make_backup(keep=5)
    assert path is None


def test_backup_prune(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "DATA_DIR", tmp_path)
    (tmp_path / "portfolio.json").write_text("[]", encoding="utf-8")

    for _ in range(5):
        backup.make_backup(keep=3)

    remaining = sorted(Path(backup._BACKUP_DIR).glob("*.zip"))
    assert len(remaining) <= 3
