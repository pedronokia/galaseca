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


def test_restore_de_verdade_preserva_dados_completos(tmp_path):
    """Round-trip completo: grava várias linhas, faz backup, "restaura"
    (copia o arquivo do backup pra um caminho novo, igual quem for
    restaurar via scp faria) e confere que TODAS as linhas sobrevivem
    -- não só uma fixture isolada (o que `test_primeiro_backup_cria_
    arquivo` já cobria, mas com um único valor fixo)."""
    import shutil

    db = tmp_path / "x.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE usuarios (steamid TEXT, nome TEXT)")
    linhas = [(f"7656119900000{i:02d}", f"jogador{i}") for i in range(20)]
    conn.executemany("INSERT INTO usuarios VALUES (?, ?)", linhas)
    conn.commit()
    conn.close()

    out = tmp_path / "backups"
    backup_path = db_backup.fazer_backup_se_necessario(db, out, now=1000.0)
    assert backup_path is not None

    restaurado = tmp_path / "restaurado.db"
    shutil.copy(backup_path, restaurado)

    conn = sqlite3.connect(str(restaurado))
    linhas_restauradas = conn.execute(
        "SELECT steamid, nome FROM usuarios ORDER BY steamid").fetchall()
    conn.close()
    assert linhas_restauradas == sorted(linhas)


# ── Backup dos JSON globais (scan_store/ranking) ────────────

def test_json_sem_nenhum_arquivo_nao_faz_nada(tmp_path):
    out = tmp_path / "backups"
    paths = {"scanner_last": tmp_path / "nao_existe.json"}
    assert db_backup.fazer_backup_json_se_necessario(paths, out) is None


def test_json_primeiro_backup_cria_zip_com_conteudo(tmp_path):
    import json
    import zipfile

    scan_path = tmp_path / "scanner_last.json"
    scan_path.write_text(json.dumps({"ts": 1, "results": []}), encoding="utf-8")
    out = tmp_path / "backups"
    resultado = db_backup.fazer_backup_json_se_necessario(
        {"scanner_last": scan_path}, out, now=1000.0)
    assert resultado is not None
    with zipfile.ZipFile(resultado) as zf:
        assert "scanner_last.json" in zf.namelist()
        conteudo = json.loads(zf.read("scanner_last.json"))
        assert conteudo["ts"] == 1


def test_json_nao_duplica_dentro_da_janela(tmp_path):
    scan_path = tmp_path / "scanner_last.json"
    scan_path.write_text("{}", encoding="utf-8")
    out = tmp_path / "backups"
    paths = {"scanner_last": scan_path}
    db_backup.fazer_backup_json_se_necessario(paths, out, now=1000.0)
    segundo = db_backup.fazer_backup_json_se_necessario(
        paths, out, now=1000.0 + 3600)
    assert segundo is None
    assert len(list(out.glob("json-*.zip"))) == 1


def test_json_mantem_apenas_os_7_mais_recentes(tmp_path):
    scan_path = tmp_path / "scanner_last.json"
    scan_path.write_text("{}", encoding="utf-8")
    out = tmp_path / "backups"
    paths = {"scanner_last": scan_path}
    for i in range(10):
        db_backup.fazer_backup_json_se_necessario(
            paths, out, now=1000.0 + i * 21 * 3600)
    assert len(list(out.glob("json-*.zip"))) == db_backup._MANTER
