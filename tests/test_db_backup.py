"""Testes do backup rotativo do public_site.db (db_backup.py)."""
from __future__ import annotations

import sqlite3

from skinvault.public_site import db_backup


def _cria_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()


def test_sem_db_nao_faz_nada(tmp_path):
    db = tmp_path / "nao_existe.db"
    out = tmp_path / "backups"
    assert db_backup.fazer_backup_se_necessario(db, out) is None


def test_primeiro_backup_cria_arquivo(tmp_path):
    db = tmp_path / "x.db"
    _cria_db(db)
    out = tmp_path / "backups"
    resultado = db_backup.fazer_backup_se_necessario(db, out, now=1000.0)
    assert resultado is not None
    assert resultado.exists()
    # Conteudo de verdade (backup via API do sqlite, nao arquivo vazio)
    conn = sqlite3.connect(str(resultado))
    assert conn.execute("SELECT x FROM t").fetchone() == (1,)
    conn.close()


def test_nao_duplica_dentro_da_janela(tmp_path):
    db = tmp_path / "x.db"
    _cria_db(db)
    out = tmp_path / "backups"
    db_backup.fazer_backup_se_necessario(db, out, now=1000.0)
    segundo = db_backup.fazer_backup_se_necessario(db, out, now=1000.0 + 3600)
    assert segundo is None
    assert len(list(out.glob("public_site-*.db"))) == 1


def test_faz_novo_apos_a_janela(tmp_path):
    db = tmp_path / "x.db"
    _cria_db(db)
    out = tmp_path / "backups"
    db_backup.fazer_backup_se_necessario(db, out, now=1000.0)
    segundo = db_backup.fazer_backup_se_necessario(db, out, now=1000.0 + 21 * 3600)
    assert segundo is not None
    assert len(list(out.glob("public_site-*.db"))) == 2


def test_mantem_apenas_os_7_mais_recentes(tmp_path):
    db = tmp_path / "x.db"
    _cria_db(db)
    out = tmp_path / "backups"
    for i in range(10):
        db_backup.fazer_backup_se_necessario(db, out, now=1000.0 + i * 21 * 3600)
    assert len(list(out.glob("public_site-*.db"))) == db_backup._MANTER
