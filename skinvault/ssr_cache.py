"""Cache local do price_history SSR (Steam Market).

Reduz chamadas de rede repetidas durante backtest / Validar score.
Default TTL 24h porque price_history e' granularidade diaria -- mais
novo que isso e' redundante.

Armazena em data/ssr_cache.json como mapa nome -> {ts, price_history}.
Cache miss ou expirado retorna None; quem chama decide se busca da rede.

Filosofia: dados publicos da Steam podem ser cacheados a vontade.
Cache invalida-se sozinho via TTL; user pode forcar refresh com clear().
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR

_DEFAULT_PATH = DATA_DIR / "ssr_cache.json"
_TTL_SECONDS = 24 * 60 * 60  # 24h


class PriceHistoryCache:
    """Cache JSON nome -> {ts, price_history}. TTL default 24h."""

    def __init__(self, path: Path | str = _DEFAULT_PATH,
                 ttl: float = _TTL_SECONDS) -> None:
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
        except OSError as e:
            print(f"WARNING: failed to save SSR cache: {e}",
                  file=__import__('sys').stderr)

    def get(self, name: str) -> list[dict] | None:
        """Retorna price_history se cache hit e nao expirado, senao None."""
        entry = self._data.get(name)
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > self.ttl:
            return None
        ph = entry.get("price_history")
        return ph if isinstance(ph, list) else None

    def put(self, name: str, price_history: list[dict]) -> None:
        """Armazena price_history para um item. Persiste em disco."""
        if not isinstance(price_history, list):
            return
        self._data[name] = {
            "ts": time.time(),
            "price_history": price_history,
        }
        self._save()

    def has(self, name: str) -> bool:
        """True se cache hit e nao expirado."""
        return self.get(name) is not None

    def clear(self) -> None:
        """Apaga todo o cache. Util pra forcar refresh."""
        self._data = {}
        self._save()

    def size(self) -> int:
        """Numero de itens cacheados (inclui possivelmente expirados)."""
        return len(self._data)


def cached_price_history(
    name: str,
    cache: PriceHistoryCache | None = None,
) -> list[dict] | None:
    """Pega price_history pelo nome usando cache.

    Se cache miss ou expirado, busca via steam_api.get_market_page_data e
    armazena. Retorna None se Steam tambem nao tiver dados.
    """
    from skinvault import steam_api
    cache = cache or PriceHistoryCache()
    cached = cache.get(name)
    if cached is not None:
        return cached
    page = steam_api.get_market_page_data(name)
    if not page:
        return None
    ph = page.get("price_history")
    if ph:
        cache.put(name, ph)
        return ph
    return None
