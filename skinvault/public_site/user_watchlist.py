"""Watchlist pessoal (site público) -- mutação por usuário.

A avaliação de regras (`alerts.evaluate_item`) e o resumo de regras
(`alerts.format_rules_summary`) continuam 100% em `alerts.py`, sem
alteração. Só a mutação (adicionar/editar regras/remover) é nova aqui,
mesmo motivo de `user_portfolio.py`/`user_trades.py` (as funções do app
local usam `path: Path = _DEFAULT_PATH`, gotcha #17 do AGENTS.md).
"""
from __future__ import annotations

import time
from pathlib import Path

from skinvault.public_site import user_store

_KIND = "watchlist"


def load_items(steamid: str, path: "Path | str | None" = None) -> list[dict]:
    return user_store.load_user_json(steamid, _KIND, [], path=path)


def add_item(steamid: str, name: str, target: float = 0.0,
            path: "Path | str | None" = None) -> list[dict]:
    """Adiciona um item novo. Não funde com um existente do mesmo nome."""
    items = load_items(steamid, path=path)
    items.append({
        "name": name, "target": target, "triggered": False,
        "added_ts": time.time(), "rules": {}, "triggered_rules": [],
    })
    user_store.save_user_json(steamid, _KIND, items, path=path)
    return items


def update_rules(steamid: str, name: str, rules: dict,
                 baseline_price: "float | None" = None,
                 path: "Path | str | None" = None) -> "list[dict] | None":
    """Substitui as regras do item. None se o nome não existir.

    Reseta `triggered_rules` -- regra nova precisa poder disparar de
    novo, mesmo que a antiga já tivesse disparado.
    """
    items = load_items(steamid, path=path)
    found = False
    for it in items:
        if it.get("name") == name:
            it["rules"] = rules
            if baseline_price is not None:
                it["baseline_price"] = baseline_price
            it["triggered_rules"] = []
            found = True
    if not found:
        return None
    user_store.save_user_json(steamid, _KIND, items, path=path)
    return items


def remove_item(steamid: str, name: str,
                path: "Path | str | None" = None) -> bool:
    items = load_items(steamid, path=path)
    remaining = [it for it in items if it.get("name") != name]
    changed = len(remaining) != len(items)
    if changed:
        user_store.save_user_json(steamid, _KIND, remaining, path=path)
    return changed
