"""Historico de valor do inventario -- alimenta o grafico 'valor no tempo'.

Cada avaliacao grava um ponto {ts, total} em data/history.json. O grafico le'
a serie. Primeira rodada = 1 ponto (sem linha ainda), igual ao sparkline do Future.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

_DEFAULT_PATH = DATA_DIR / "history.json"


def record_snapshot(total: float, path: Path | str = _DEFAULT_PATH,
                    now: float | None = None) -> None:
    now = time.time() if now is None else now
    series = load_history(path)
    series.append({"ts": now, "total": float(total)})
    series = series[-500:]  # nao deixa crescer infinito
    p = Path(path)
    try:
        atomic_write_text(p, json.dumps(series))
    except OSError as e:
        print(f"WARNING: failed to save history: {e}",
              file=__import__('sys').stderr)


def load_history(path: Path | str = _DEFAULT_PATH) -> list[dict]:
    data = load_json_record(path, [])
    return data if isinstance(data, list) else []
