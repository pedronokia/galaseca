"""Ultimo scan do Scanner, persistido.

Sem isso a tela abria vazia a cada execucao, e o unico jeito de rever o
resultado era escanear de novo -- dezenas de chamadas num endpoint que a
Steam bloqueia por dezenas de minutos. O resultado volta marcado com a
hora: a tela diz "ultimo scan ha' X", nunca finge que o dado e' de agora.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text

_DEFAULT_PATH = DATA_DIR / "scanner_last.json"


def save_last_scan(category: str, results: list,
                   path: Path | str = _DEFAULT_PATH,
                   now: float | None = None) -> None:
    """Grava o scan concluido. Falha de disco nao derruba o scan."""
    data = {"ts": time.time() if now is None else now,
            "category": category or "", "results": list(results or [])}
    try:
        atomic_write_text(path, json.dumps(data, ensure_ascii=False,
                                           default=str))
    except OSError:
        pass


def load_last_scan(path: Path | str = _DEFAULT_PATH) -> "dict | None":
    """{ts, category, results} ou None (ausente, ilegivel ou vazio).

    E' cache: arquivo ruim vira None em silencio, sem quarentena.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    if not all(isinstance(r, dict) and "name" in r and "score" in r
               for r in results):
        return None
    return {"ts": float(data.get("ts") or 0),
            "category": str(data.get("category") or ""),
            "results": results}


def idade_txt(ts: float, now: float | None = None) -> str:
    """"agora há pouco", "há 5 min", "há 2 h", "há 3 dias"."""
    seg = max(0.0, (time.time() if now is None else now) - (ts or 0))
    if seg < 60:
        return "agora há pouco"
    if seg < 3600:
        return f"há {int(seg // 60)} min"
    if seg < 86400:
        return f"há {int(seg // 3600)} h"
    dias = int(seg // 86400)
    return f"há {dias} dia{'s' if dias != 1 else ''}"
