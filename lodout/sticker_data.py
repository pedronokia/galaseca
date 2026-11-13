# Auto-generated from ByMykel/CSGO-API
# Source: https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/stickers.json
# Lazy-loaded from stickers.json to avoid ~10k lines at import time.

from __future__ import annotations

import json
import os
import threading

_cache: dict[str, dict] | None = None
_cache_lock = threading.Lock()
_DATA_PATH = os.path.join(os.path.dirname(__file__), "stickers.json")


def get_all() -> dict[str, dict]:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    _cache = json.load(f)
    return _cache
