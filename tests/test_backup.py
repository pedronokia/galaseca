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


def test_restore_ignores_unknown_and_path_traversal_entries(tmp_path,
                                                             monkeypatch):
    """Regression: restore aceitava qualquer nome de entry no zip,
    abrindo Zip Slip se o backup viesse adulterado. Agora so' nomes
    em _DATA_FILES sao escritos.
    """
    monkeypatch.setattr(backup, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data").mkdir()
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as z:
        # Entry valida (whitelisted)
        z.writestr("portfolio.json", "[]")
        # Entries que NAO podem ser escritas
        z.writestr("hax.json", "owned")
        z.writestr("../escape.json", "escaped")

    count = backup.restore_backup(str(evil_zip))
    assert count == 1
    assert (tmp_path / "data" / "portfolio.json").exists()
    assert not (tmp_path / "data" / "hax.json").exists()
    # Path traversal nao escapou do data dir
    assert not (tmp_path / "escape.json").exists()
