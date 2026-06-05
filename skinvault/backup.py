from __future__ import annotations

import json
import time
import zipfile
from datetime import datetime
from pathlib import Path

from skinvault._paths import DATA_DIR
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
    # F10 -- sync da conta Steam
    "steam_session.json",
    "steam_market_events.json",
    "active_listings.json",
    "trade_history.json",
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
    count = 0
    try:
        with zipfile.ZipFile(path, "r") as z:
            for fname in z.namelist():
                data = z.read(fname)
                (DATA_DIR / fname).write_bytes(data)
                count += 1
        return count
    except Exception:
        return 0
