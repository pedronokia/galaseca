"""Portfólio pessoal (site público) -- mutação por usuário.

A matemática (valor, lucro, breakeven) continua 100% em `portfolio.py`,
sem alteração -- `evaluate_portfolio(positions, price_fn)` já recebe a
lista direto, não um caminho de arquivo. Só a MUTAÇÃO (adicionar/editar/
remover) é nova aqui, porque `portfolio.add_position`/etc. do app local
usam `path: Path = _DEFAULT_PATH` (gotcha #17 do AGENTS.md) e não dão pra
redirecionar pra um usuário sem reescrever a assinatura usada pelo app Qt.

Mesma forma de posição que `portfolio.json` já usa: {name, cost, quantity,
added_ts, source}.
"""
from __future__ import annotations

import time
from pathlib import Path

from skinvault.public_site import user_store

_KIND = "portfolio"


def load_positions(steamid: str,
                   path: "Path | str | None" = None) -> list[dict]:
    return user_store.load_user_json(steamid, _KIND, [], path=path)


def add_position(steamid: str, name: str, cost: "float | None",
                 quantity: int = 1,
                 path: "Path | str | None" = None) -> list[dict]:
    """Adiciona uma posição nova (não funde com uma existente do mesmo
    nome -- igual ao `portfolio.add_position` do app local, cada adição é
    uma linha própria)."""
    positions = load_positions(steamid, path=path)
    positions.append({
        "name": name,
        "cost": cost,
        "quantity": quantity,
        "added_ts": time.time(),
        "source": "manual",
    })
    user_store.save_user_json(steamid, _KIND, positions, path=path)
    return positions


def update_position_cost(steamid: str, name: str, cost: float,
                         path: "Path | str | None" = None) -> "list[dict] | None":
    """Atualiza o custo de toda posição com esse nome. None se nenhuma
    posição desse nome existir (nada pra atualizar)."""
    positions = load_positions(steamid, path=path)
    found = False
    for pos in positions:
        if pos.get("name") == name:
            pos["cost"] = cost
            found = True
    if not found:
        return None
    user_store.save_user_json(steamid, _KIND, positions, path=path)
    return positions


def remove_position(steamid: str, name: str,
                    path: "Path | str | None" = None) -> bool:
    """Remove TODAS as posições com esse nome. True se algo foi removido."""
    positions = load_positions(steamid, path=path)
    remaining = [p for p in positions if p.get("name") != name]
    changed = len(remaining) != len(positions)
    if changed:
        user_store.save_user_json(steamid, _KIND, remaining, path=path)
    return changed
