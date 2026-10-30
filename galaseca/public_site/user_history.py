"""Histórico de valor da carteira (site público) -- por usuário.

Cada ponto contém `{ts, total}`.
`record_if_changed` pula pontos quando o total é igual ao último; sem isso,
cada visita a `/conta` encheria a série de repetições. O histórico tem limite
de 500 pontos.
"""
from __future__ import annotations

import time
from pathlib import Path

from galaseca.public_site import user_store

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
