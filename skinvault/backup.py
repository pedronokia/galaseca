from __future__ import annotations

import json
import time
import zipfile
from datetime import datetime
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_bytes
from skinvault.settings import load_settings

_BACKUP_DIR = DATA_DIR / "backups"
_DATA_FILES = [
    "prices.json",
    "portfolio.json",
    "history.json",
    "item_history.json",
    "volume_history.json",
    "supply_history.json",
    "watchlist.json",
    "trades.json",
    "steamids.json",
    "settings.json",
    "alerts_log.json",
    "rankings.json",
    # Market buscas recentes
    "market_recent.json",
    # Historico deixado pela sincronizacao de conta (F10, revertida em
    # 2026-08-07 -- ver ROADMAP.md). steam_session.json saiu da lista: era
    # a sessao viva, que nao existe mais. Estes 3 continuam cobertos: sao
    # dado historico local que o usuario decidiu manter.
    "steam_market_events.json",
    "active_listings.json",
    "trade_history.json",
    # Watcher de arquivos do jogo (gamedata.py)
    "gamedata_state.json",
    "gamedata_events.json",
    # Datas de aposentadoria de caixa (retirements.py). Dado acumulado ao
    # longo do tempo pelo watcher -- nao e' regeneravel.
    "case_retirements.json",
    # Caches de dados da Steam. Sao regeneraveis em teoria, mas na pratica
    # custam horas: os endpoints sao agressivamente rate-limited (medido em
    # 2026-07-28, bloqueio de dezenas de minutos). Reconstruir do zero e'
    # bem mais caro que carregar no backup.
    "ssr_cache.json",
    "discovery_cache.json",
    # Precos de mercado fora da Steam + cambio (markets.py)
    "market_prices.json",
    "fx_rate.json",
]


def make_backup(keep: int | None = None) -> str | None:
    if keep is None:
        keep = load_settings().get("keep_backups", 10)
    if keep == 0:
        _prune_backups(0)
        return None
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"skinvault_backup_{ts}.zip"
    path = _BACKUP_DIR / name
    count = 0
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for fname in _DATA_FILES:
                fp = DATA_DIR / fname
                if fp.exists():
                    z.write(fp, fname)
                    count += 1
        if count == 0:
            path.unlink(missing_ok=True)
            return None
        _prune_backups(keep)
        return str(path)
    except Exception:
        return None


def _prune_backups(keep: int) -> None:
    if not _BACKUP_DIR.exists():
        return
    backups = sorted(
        p for p in _BACKUP_DIR.iterdir()
        if p.suffix == ".zip" and p.name.startswith("skinvault_backup_")
    )
    for old in backups[:-keep] if keep else backups:
        try:
            old.unlink()
        except Exception:
            pass


def list_backups() -> list[dict]:
    if not _BACKUP_DIR.exists():
        return []
    backups = sorted(
        (p for p in _BACKUP_DIR.iterdir()
         if p.suffix == ".zip" and p.name.startswith("skinvault_backup_")),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    return [
        {"name": p.name, "path": str(p), "size": p.stat().st_size,
         "mtime": p.stat().st_mtime}
        for p in backups
    ]


def delete_backup(path: str) -> bool:
    try:
        Path(path).unlink(missing_ok=True)
        return True
    except Exception:
        return False


def restore_backup(path: str) -> int:
    """Restaura backup .zip para DATA_DIR.

    Aceita apenas nomes presentes em _DATA_FILES (whitelist) — protege
    contra Zip Slip (entry com path traversal como ../../etc/passwd)
    caso o usuario tente restaurar um backup adulterado.
    """
    allowed = frozenset(_DATA_FILES)
    count = 0
    try:
        with zipfile.ZipFile(path, "r") as z:
            for fname in z.namelist():
                if fname not in allowed:
                    continue
                data = z.read(fname)
                atomic_write_bytes(DATA_DIR / fname, data)
                count += 1
        return count
    except Exception:
        return 0
