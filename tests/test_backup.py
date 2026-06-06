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


def test_make_backup_keep_zero(tmp_path, monkeypatch):
    """keep=0: prune tudo e retorna None."""
    monkeypatch.setattr(backup, "DATA_DIR", tmp_path)
    bdir = tmp_path / "backups"
    monkeypatch.setattr(backup, "_BACKUP_DIR", bdir)
    bdir.mkdir(parents=True)
    # enche de zips
    for i in range(3):
        (bdir / f"skinvault_backup_20250101_{i:02d}.zip").write_text("x")
    path = backup.make_backup(keep=0)
    assert path is None
    assert not list(bdir.glob("*.zip"))


def test_make_backup_exception_returns_none(tmp_path, monkeypatch):
    """Falha ao criar zip retorna None."""
    monkeypatch.setattr(backup, "DATA_DIR", tmp_path)
    (tmp_path / "portfolio.json").write_text("[]", encoding="utf-8")
    import zipfile
    original = zipfile.ZipFile
    def bad_zip(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(zipfile, "ZipFile", bad_zip)
    path = backup.make_backup(keep=5)
    assert path is None


def test_prune_backups_nonexistent_dir(tmp_path, monkeypatch):
    """_prune_backups nao quebra se _BACKUP_DIR nao existe."""
    monkeypatch.setattr(backup, "_BACKUP_DIR", tmp_path / "noexist")
    backup._prune_backups(5)  # nao deve levantar


def test_prune_backups_unlink_error(tmp_path, monkeypatch):
    """_prune_backups nao quebra se unlink falhar."""
    bdir = tmp_path / "backups"
    monkeypatch.setattr(backup, "_BACKUP_DIR", bdir)
    bdir.mkdir()
    zp = bdir / "skinvault_backup_20250101_000000.zip"
    zp.write_text("x")

    def _fail(*a, **kw):
        raise PermissionError("denied")
    monkeypatch.setattr(Path, "unlink", _fail)
    backup._prune_backups(0)  # nao deve levantar


def test_list_backups_nonexistent_dir(tmp_path, monkeypatch):
    """list_backups retorna [] se _BACKUP_DIR nao existe."""
    monkeypatch.setattr(backup, "_BACKUP_DIR", tmp_path / "noexist")
    assert backup.list_backups() == []


def test_delete_backup_success(tmp_path):
    """delete_backup deleta arquivo e retorna True."""
    p = tmp_path / "backup.zip"
    p.write_text("x")
    assert backup.delete_backup(str(p)) is True
    assert not p.exists()


def test_delete_backup_nonexistent(tmp_path):
    """delete_backup de arquivo inexistente retorna True (missing_ok)."""
    assert backup.delete_backup(str(tmp_path / "noexist.zip")) is True


def test_delete_backup_on_directory_returns_false(tmp_path):
    """delete_backup em diretorio retorna False."""
    d = tmp_path / "mydir"
    d.mkdir()
    assert backup.delete_backup(str(d)) is False


def test_restore_backup_bad_zip(tmp_path):
    """restore_backup com zip invalido retorna 0."""
    p = tmp_path / "bad.zip"
    p.write_text("not a zip")
    assert backup.restore_backup(str(p)) == 0
