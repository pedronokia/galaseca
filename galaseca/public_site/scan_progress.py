"""Progresso do ciclo de scan em andamento do worker.

Pedido depois do achado de 2026-10-25: a única forma de ver em que item
o scan estava era `docker logs` do worker. Sobrescrito várias vezes por
ciclo (um item a cada ~4s) -- é status efêmero, não registro: arquivo
ilegível ou ausente vira None em silêncio (mesmo espírito de
`scan_store.load_last_scan`), sem quarentena.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from galaseca._paths import DATA_DIR, atomic_write_text

_DEFAULT_PATH = DATA_DIR / "scan_progress.json"


def registrar(indice: int, total: int, nome_item: str,
              path: "Path | str | None" = None,
              now: "float | None" = None) -> None:
    """Grava o item atual do ciclo. Falha de disco não derruba o scan."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = {
        "indice": indice, "total": total, "item": nome_item,
        "ts": time.time() if now is None else now,
    }
    try:
        atomic_write_text(p, json.dumps(data, ensure_ascii=False))
    except OSError:
        pass


def carregar(path: "Path | str | None" = None) -> "dict | None":
    """{indice, total, item, ts} ou None (ausente/ilegível)."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    try:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "indice" not in data:
        return None
    return data
