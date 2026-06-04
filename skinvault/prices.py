"""Cache de precos + backoff -- pra avaliar o inventario INTEIRO sem morrer no
rate-limit do Steam (~20 req/min).

Ideia central: preco de portfolio nao precisa ser real-time. Um TTL de 6h corta
drasticamente as chamadas, e o cache **persiste entre execucoes** -- entao a 2a
rodada e' quase instantanea e o inventario inteiro vai sendo preenchido. So'
dormimos (throttle) em cache MISS; hit e' de graca.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault import steam_api

_TTL_SECONDS = 6 * 3600
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_PATH = _DATA_DIR / "prices.json"


class PriceCache:
    """Cache simples nome -> {price, ts}, persistido em JSON."""

    def __init__(self, path: Path | str = _DEFAULT_PATH, ttl: float = _TTL_SECONDS):
        self.path = Path(path)
        self.ttl = ttl
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data), encoding="utf-8")
        except OSError:
            pass

    def get(self, name: str, now: float | None = None) -> float | None:
        now = time.time() if now is None else now
        entry = self._data.get(name)
        if entry and (now - entry.get("ts", 0)) < self.ttl:
            return entry.get("price")
        return None

    def put(self, name: str, price: float, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._data[name] = {"price": price, "ts": now}
        self._save()


def _fetch_with_backoff(name: str, retries: int = 3) -> float | None:
    """Tenta o preco com recuo exponencial -- cobre o 429 (rate-limit).
    Limitacao conhecida (v1): nao distingue 429 de 'item sem preco', entao
    item sem mercado consome as tentativas. Bom o bastante por enquanto."""
    delay = 2.0
    for _ in range(retries):
        price = steam_api.get_market_price(name)
        if price is not None:
            return price
        time.sleep(delay)
        delay *= 2
    return None


def value_inventory(
    steam_id: str,
    cache: PriceCache | None = None,
    throttle: float = 1.5,
    progress=None,
) -> tuple[str, list[dict], float]:
    """Avalia o inventario INTEIRO usando cache. Retorna (status, rows, total).

    rows: [{name, qty, price, total}] ordenado por total desc.
    progress(i, n, name): callback opcional de progresso.
    """
    cache = cache or PriceCache()
    status, items = steam_api.fetch_inventory(steam_id)
    if status != steam_api.INV_OK:
        return status, [], 0.0

    rows: list[dict] = []
    total = 0.0
    n = len(items)
    for i, it in enumerate(items, start=1):
        name = it["name"]
        price = cache.get(name)
        if price is None:                       # MISS -> rede + throttle
            price = _fetch_with_backoff(name)
            if price is not None:
                cache.put(name, price)
            time.sleep(throttle)
        if progress:
            progress(i, n, name)
        if price is not None:
            line = price * it["quantity"]
            total += line
            rows.append({"name": name, "qty": it["quantity"],
                         "price": price, "total": line})

    rows.sort(key=lambda r: -r["total"])
    return status, rows, total
