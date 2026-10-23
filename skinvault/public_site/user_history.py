"""Histórico de valor da carteira (site público) -- por usuário.

Mesma forma de ponto que `history.json` do app local usa: {ts, total}.
`record_if_changed` espelha o dedup de `AccountScreen._record_value_snapshot`
(Qt): pular quando o total é igual ao último ponto, senão toda visita a
`/conta` encheria a série de pontos repetidos. Cap em 500 pontos, igual
ao `history.py` do app local.
"""
from __future__ import annotations

import time
from pathlib import Path

from skinvault.public_site import user_store

_KIND = "history"
_CAP = 500


def load_history(steamid: str, path: "Path | str | None" = None) -> list[dict]:
    return user_store.load_user_json(steamid, _KIND, [], path=path)


def record_if_changed(steamid: str, total: float,
                      path: "Path | str | None" = None,
                      now: "float | None" = None) -> list[dict]:
    """Grava {ts, total} se `total` mudou desde o último ponto.

    Chamado a cada visita a `/conta` -- sem o dedup, cada refresh da
    página adicionaria um ponto idêntico ao anterior.
    """
    series = load_history(steamid, path=path)
    if series and series[-1].get("total") == float(total):
        return series
    series.append({"ts": now if now is not None else time.time(),
                   "total": float(total)})
    series = series[-_CAP:]
    user_store.save_user_json(steamid, _KIND, series, path=path)
    return series
