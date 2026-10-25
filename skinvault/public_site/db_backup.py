"""Backup rotativo do `public_site.db` -- local primeiro, "pra fora da
VM" é responsabilidade de quem opera (ver README: baixar via scp
periodicamente). Protege contra corrupção/bug de aplicação, não contra
perda da VM inteira -- isso precisaria de um destino externo (S3 etc.)
que exigiria credenciais que não temos como configurar sozinhos.

Usa a API de backup do próprio sqlite3 (não um `shutil.copy` cru) --
segura mesmo com o banco sendo escrito ao mesmo tempo por outro processo
(o `web`), sem lock nem corrupção de leitura parcial.
"""
from __future__ import annotations

import calendar
import sqlite3
import time
import zipfile
from pathlib import Path

from skinvault._paths import DATA_DIR

_DB_PATH = DATA_DIR / "public_site.db"
_BACKUP_DIR = DATA_DIR / "backups"
_MANTER = 7  # backups diários -- cobre uma semana de histórico
_INTERVALO_MIN_S = 20 * 3600  # não faz 2 backups no mesmo dia

# JSON globais do dashboard -- achado da 2a rodada (2026-10-25): só o
# SQLite (conta/portfolio pessoal) tinha backup; perder `scanner_last`/
# `rankings` sem isso significa perder o scan atual e o histórico de
# ciclos num crash de disco, sem nenhum jeito de recuperar sem esperar
# o próximo ciclo (que pode levar horas se a Steam estiver bloqueando).
_JSON_PATHS = {
    "scanner_last": DATA_DIR / "scanner_last.json",
    "scan_historico": DATA_DIR / "scan_historico.json",
    "rankings": DATA_DIR / "rankings.json",
}


def _timestamp_do_nome(caminho: Path, prefixo: str) -> float:
    """Hora embutida no NOME do arquivo (não `stat().st_mtime`, que é
    hora real do SO e não o `now` injetável do teste -- gotcha já
    documentado aqui mesmo, ver `fazer_backup_se_necessario`)."""
    ts_texto = caminho.stem.removeprefix(prefixo)
    try:
        # timegm (não mktime): o nome é gerado com gmtime (UTC).
        return calendar.timegm(time.strptime(ts_texto, "%Y%m%d-%H%M%S"))
    except ValueError:
        return caminho.stat().st_mtime


def _deve_pular(existentes: list[Path], prefixo: str, agora: float) -> bool:
    if not existentes:
        return False
    return (agora - _timestamp_do_nome(existentes[-1], prefixo)) < _INTERVALO_MIN_S


def fazer_backup_se_necessario(
        db_path: "Path | str | None" = None,
        backup_dir: "Path | str | None" = None,
        now: "float | None" = None) -> "Path | None":
    """Faz backup se o mais recente já existente tem mais de ~20h (ou
    não existe nenhum). Devolve o path criado, ou None se pulou/falhou.
    """
    src = Path(db_path) if db_path is not None else _DB_PATH
    if not src.exists():
        return None
    dest_dir = Path(backup_dir) if backup_dir is not None else _BACKUP_DIR
    agora = time.time() if now is None else now

    existentes = sorted(dest_dir.glob("public_site-*.db")) if dest_dir.exists() else []
    if _deve_pular(existentes, "public_site-", agora):
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    nome = time.strftime("public_site-%Y%m%d-%H%M%S.db", time.gmtime(agora))
    destino = dest_dir / nome
    try:
        origem_conn = sqlite3.connect(str(src))
        destino_conn = sqlite3.connect(str(destino))
        with destino_conn:
            origem_conn.backup(destino_conn)
        origem_conn.close()
        destino_conn.close()
    except sqlite3.Error:
        return None

    todos = sorted(dest_dir.glob("public_site-*.db"))
    for antigo in todos[:-_MANTER]:
        try:
            antigo.unlink()
        except OSError:
            pass
    return destino


def fazer_backup_json_se_necessario(
        paths: "dict[str, Path] | None" = None,
        backup_dir: "Path | str | None" = None,
        now: "float | None" = None) -> "Path | None":
    """Mesma cadência do backup do banco (1x/~20h, guarda os últimos
    `_MANTER`), pros JSON globais do dashboard (`_JSON_PATHS`) -- um
    .zip só por rodada, pra não multiplicar arquivo solto em
    `backups/`. None se nenhuma fonte existe, se já tem backup recente,
    ou se falhar gravando."""
    fontes = paths if paths is not None else _JSON_PATHS
    dest_dir = Path(backup_dir) if backup_dir is not None else _BACKUP_DIR
    agora = time.time() if now is None else now

    if not any(Path(p).exists() for p in fontes.values()):
        return None

    existentes = sorted(dest_dir.glob("json-*.zip")) if dest_dir.exists() else []
    if _deve_pular(existentes, "json-", agora):
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    nome = time.strftime("json-%Y%m%d-%H%M%S.zip", time.gmtime(agora))
    destino = dest_dir / nome
    try:
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
            for nome_arq, p in fontes.items():
                p = Path(p)
                if p.exists():
                    zf.write(p, arcname=f"{nome_arq}.json")
    except OSError:
        return None

    todos = sorted(dest_dir.glob("json-*.zip"))
    for antigo in todos[:-_MANTER]:
        try:
            antigo.unlink()
        except OSError:
            pass
    return destino
