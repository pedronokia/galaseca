""""No ar desde quando" -- primeira vez que o processo `web` rodou.

Grava uma única vez, na primeira chamada depois de criado o arquivo. Não é
uptime de servidor (reinícios não resetam -- o arquivo sobrevive), é
"desde quando existe essa instalação do site".
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

_DEFAULT_PATH = DATA_DIR / "no_ar_desde.json"


def no_ar_desde(path: "Path | str | None" = None,
               now: float | None = None) -> float:
    """Timestamp da primeira vez que isto foi chamado. Idempotente."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, None)
    if isinstance(data, dict) and data.get("ts"):
        return float(data["ts"])
    ts = time.time() if now is None else now
    try:
        atomic_write_text(p, json.dumps({"ts": ts}))
    except OSError:
        pass
    return ts
