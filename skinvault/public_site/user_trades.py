"""Trades pessoais (site público) -- mutação por usuário.

A matemática (lucro, custo, % retorno) continua 100% em `trades.py`
(`build_trade`/`trade_stats`/`monthly_pnl`) -- todas já recebem a lista
de trades direto, sem caminho de arquivo. Só a MUTAÇÃO (adicionar/
remover) é nova aqui, mesmo motivo do `user_portfolio.py`: `trades.
record_trade`/`remove_trade` usam `path: Path = _DEFAULT_PATH` (gotcha
#17 do AGENTS.md) e não dão pra redirecionar pra um usuário sem reescrever
a assinatura usada pelo app Qt.
"""
from __future__ import annotations

from pathlib import Path

from skinvault import trades as trades_mod
from skinvault.public_site import user_store

_KIND = "trades"


def load_trades(steamid: str, path: "Path | str | None" = None) -> list[dict]:
    return user_store.load_user_json(steamid, _KIND, [], path=path)


def add_trade(steamid: str, name: str, buy_cost: float, sell_price: float,
             quantity: int = 1, notes: str = "",
             path: "Path | str | None" = None) -> list[dict]:
    """Registra um trade encerrado (compra + venda já aconteceram)."""
    trade = trades_mod.build_trade(
        name, buy_cost, sell_price, quantity, notes=notes)
    registros = load_trades(steamid, path=path)
    registros.append(trade)
    user_store.save_user_json(steamid, _KIND, registros, path=path)
    return registros


def remove_trade(steamid: str, index: int,
                 path: "Path | str | None" = None) -> "list[dict] | None":
    """Remove o trade na posição `index`. None se o índice não existir."""
    registros = load_trades(steamid, path=path)
    if not (0 <= index < len(registros)):
        return None
    registros.pop(index)
    user_store.save_user_json(steamid, _KIND, registros, path=path)
    return registros
