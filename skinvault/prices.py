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
from skinvault._paths import DATA_DIR

_TTL_SECONDS = 6 * 3600
_NEG_TTL_SECONDS = 60 * 60  # 1h pra entries "sem preco" (None cacheado)
_DEFAULT_PATH = DATA_DIR / "prices.json"


class PriceCache:
    """Cache simples nome -> {price, ts}, persistido em JSON.

    Cacheia tambem entries `None` (itens que o Steam nao tem preco)
    com TTL mais curto, evitando re-fetch repetido a cada startup.
    """

    def __init__(self, path: Path | str = _DEFAULT_PATH, ttl: float = _TTL_SECONDS,
                 neg_ttl: float = _NEG_TTL_SECONDS):
        self.path = Path(path)
        self.ttl = ttl
        self.neg_ttl = neg_ttl
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

    def _entry_valid(self, entry: dict, now: float) -> bool:
        price = entry.get("price")
        ttl = self.ttl if price is not None else self.neg_ttl
        return (now - entry.get("ts", 0)) < ttl

    def has(self, name: str, now: float | None = None) -> bool:
        """Diz se o cache tem entry valida para `name` (inclusive None)."""
        now = time.time() if now is None else now
        entry = self._data.get(name)
        return entry is not None and self._entry_valid(entry, now)

    def get(self, name: str, now: float | None = None) -> float | None:
        now = time.time() if now is None else now
        entry = self._data.get(name)
        if entry and self._entry_valid(entry, now):
            return entry.get("price")
        return None

    def put(self, name: str, price: float | None,
            now: float | None = None) -> None:
        """Cacheia preco. price=None registra "sem preco" (TTL curto)."""
        now = time.time() if now is None else now
        self._data[name] = {"price": price, "ts": now}
        self._save()

    def age(self, name: str, now: float | None = None) -> float | None:
        """Idade da entry em segundos, ou None se nao houver entry.

        Inclui entries expiradas e entries negativas (sem preco). Util
        para UI exibir "cache de Xmin atras" sem invadir self._data.
        """
        entry = self._data.get(name)
        if entry is None:
            return None
        now = time.time() if now is None else now
        return now - entry.get("ts", now)


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


def cached_price(name: str, cache: "PriceCache | None" = None) -> float | None:
    """Preco de UM item usando cache (so' bate na rede em miss). Reuso pro
    portfolio, que tem poucos itens. Itens sem preco no Steam tambem sao
    cacheados (TTL curto) para evitar re-fetch a cada startup."""
    cache = cache or PriceCache()
    if cache.has(name):
        return cache.get(name)
    price = _fetch_with_backoff(name)
    cache.put(name, price)
    return price


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
