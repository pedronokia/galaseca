"""Watchlist persistente -- {name, target_price, triggered}.

Usado pela UI pra monitorar precos em background e notificar
quando um item atinge o alvo. Tudo local, sem login.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR

_DEFAULT_PATH = DATA_DIR / "watchlist.json"


def load_watchlist(path: Path | str = _DEFAULT_PATH) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_watchlist(items: list[dict],
                   path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(items, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"WARNING: failed to save watchlist: {e}", file=__import__('sys').stderr)


def add_watch(name: str, target: float,
              path: Path | str = _DEFAULT_PATH) -> list[dict]:
    if target <= 0:
        raise ValueError("target deve ser > 0")
    items = load_watchlist(path)
    for it in items:
        if it["name"] == name:
            return items
    items.append({
        "name": name,
        "target": float(target),
        "triggered": False,
        "added_ts": time.time(),
    })
    save_watchlist(items, path)
    return items


def update_target(name: str, new_target: float,
                  path: Path | str = _DEFAULT_PATH) -> list[dict]:
    """Atualiza o preco alvo de um item na watchlist."""
    if new_target <= 0:
        raise ValueError("target deve ser > 0")
    items = load_watchlist(path)
    for it in items:
        if it["name"] == name:
            it["target"] = float(new_target)
            it["triggered"] = False
            break
    save_watchlist(items, path)
    return items


def remove_watch(index: int,
                 path: Path | str = _DEFAULT_PATH) -> list[dict]:
    items = load_watchlist(path)
    if 0 <= index < len(items):
        items.pop(index)
        save_watchlist(items, path)
    return items


def clear_watchlist(path: Path | str = _DEFAULT_PATH) -> None:
    """Remove todos os itens da watchlist."""
    save_watchlist([], path)


def reset_trigger(name: str,
                  path: Path | str = _DEFAULT_PATH) -> list[dict]:
    """Reseta o flag triggered pra um item (ex.: depois de notificar)."""
    items = load_watchlist(path)
    for it in items:
        if it["name"] == name:
            it["triggered"] = False
            break
    save_watchlist(items, path)
    return items
