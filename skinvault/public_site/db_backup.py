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
from pathlib import Path

from skinvault._paths import DATA_DIR

_DB_PATH = DATA_DIR / "public_site.db"
_BACKUP_DIR = DATA_DIR / "backups"
_MANTER = 7  # backups diários -- cobre uma semana de histórico
_INTERVALO_MIN_S = 20 * 3600  # não faz 2 backups no mesmo dia


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
    if existentes:
        # Lê a hora do NOME do arquivo (não `stat().st_mtime`): mtime é
        # hora real do SO, não o `now` injetável do teste -- misturar os
        # dois fazia a comparação dar sempre "recente demais" em teste
        # (achado ao escrever o teste, 2026-10-25).
        ts_texto = existentes[-1].stem.removeprefix("public_site-")
        try:
            # timegm (não mktime): o nome foi gerado com gmtime (UTC) --
            # mktime interpretaria como hora LOCAL e deslocaria pelo fuso.
            ts_mais_recente = calendar.timegm(
                time.strptime(ts_texto, "%Y%m%d-%H%M%S"))
        except ValueError:
            ts_mais_recente = existentes[-1].stat().st_mtime
        if agora - ts_mais_recente < _INTERVALO_MIN_S:
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
