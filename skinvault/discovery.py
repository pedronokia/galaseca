"""Descoberta de itens pra escanear, via busca por faceta no Market.

O scanner nasceu com lista fixa (`_SCAN_BY_CATEGORY`): ~85 nomes escritos a
mao, com o wear colado no nome. Isso o torna incapaz de achar item que
ninguem digitou antes -- so' de Rifle Field-Tested o Market tem 611.

Aqui a categoria vira consulta por faceta e devolve nomes reais do Market.

DESENHO: e' ADITIVO. Toda falha -- rate limit, rede, categoria sem faceta
mapeada, filtro sem resultado -- cai na lista fixa que o chamador passa.
O scanner nunca fica pior do que era; no maximo fica igual.

O cache nao e' otimizacao, e' requisito: o endpoint de busca e'
agressivamente rate-limited (medido em 2026-07-28: dezenas de minutos de
bloqueio depois de poucas dezenas de chamadas). Descoberta e' varredura
periodica alimentando cache, nao botao que o usuario aperta.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR

_DEFAULT_PATH = DATA_DIR / "discovery_cache.json"
_TTL_SECONDS = 24 * 60 * 60

# Piso de preco. Sem ele a busca por liquidez devolve a cauda de R$ 0,03
# (SG 553 Safari Print e afins, 100k+ anuncios) -- liquido e inutil pra
# analise de investimento.
_MIN_PRICE = 1.0

# Categoria do scanner -> facetas do Market. Só as que tem equivalente
# limpo; o resto cai no fallback de proposito, em vez de inventar mapeamento.
CATEGORY_FACETS: dict = {
    "Rifles": {"type": "CSGO_Type_Rifle"},
    "Pistolas": {"type": "CSGO_Type_Pistol"},
    "Facas": {"type": "CSGO_Type_Knife"},
    "Luvas": {"type": "Type_Hands"},
    "SMGs": {"type": "CSGO_Type_SMG"},
    "Caixas": {"type": "CSGO_Type_WeaponCase"},
}

SOURCE_DISCOVERY = "discovery"
SOURCE_CACHE = "cache"
SOURCE_FALLBACK = "fallback"


class DiscoveryCache:
    """Cache JSON chave -> {ts, items}. TTL default 24h."""

    def __init__(self, path: "Path | str" = _DEFAULT_PATH,
                 ttl: float = _TTL_SECONDS) -> None:
        self.path = Path(path)
        self.ttl = ttl
        self._data: dict = {}
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
            pass  # cache e' conveniencia; falha de disco nao derruba scan

    def get(self, key: str) -> "list | None":
        entry = self._data.get(key)
        if not entry:
            return None
        if time.time() - entry.get("ts", 0) > self.ttl:
            return None
        items = entry.get("items")
        return items if isinstance(items, list) and items else None

    def put(self, key: str, items: list) -> None:
        if not isinstance(items, list) or not items:
            return
        self._data[key] = {"ts": time.time(), "items": list(items)}
        self._save()

    def clear(self) -> None:
        self._data = {}
        self._save()

    def size(self) -> int:
        return len(self._data)


def cache_key(category: str, max_items: int, min_price: float) -> str:
    """Chave estavel do cache -- muda quando o filtro muda."""
    return f"{category}|{max_items}|{min_price}"


def discover_category(category: str, max_items: int = 60,
                      min_price: float = _MIN_PRICE,
                      cache: "DiscoveryCache | None" = None,
                      use_cache: bool = True) -> "tuple[list, str] | tuple[None, str]":
    """Nomes de itens da categoria pelo Market. (items, origem) ou (None, ...).

    Ordena por liquidez (quantidade de anuncios) e corta abaixo de
    `min_price`. Devolve None quando nao ha' faceta mapeada ou a busca
    falha -- cabe ao chamador usar a lista fixa.
    """
    facets = CATEGORY_FACETS.get(category)
    if not facets:
        return None, SOURCE_FALLBACK

    cache = cache or DiscoveryCache()
    key = cache_key(category, max_items, min_price)
    if use_cache:
        hit = cache.get(key)
        if hit:
            return hit, SOURCE_CACHE

    from skinvault import steam_api
    status, results, _total = steam_api.search_market_all(
        facets=facets, sort="quantity", descending=True,
        max_items=max_items * 3,  # folga: o piso de preco corta parte
    )
    if status != steam_api.SEARCH_OK or not results:
        return None, SOURCE_FALLBACK

    nomes = [
        r["hash_name"] for r in results
        if r.get("hash_name")
        and (r.get("price") is None or r["price"] >= min_price)
    ][:max_items]
    if not nomes:
        return None, SOURCE_FALLBACK

    cache.put(key, nomes)
    return nomes, SOURCE_DISCOVERY


def resolve_scan_items(category: str, fallback: list,
                       max_items: int = 60,
                       min_price: float = _MIN_PRICE,
                       cache: "DiscoveryCache | None" = None,
                       enabled: bool = True) -> "tuple[list, str]":
    """Itens a escanear na categoria. Sempre devolve algo utilizavel.

    Com `enabled=False`, ou em qualquer falha da descoberta, devolve
    `fallback` -- o comportamento historico do scanner.
    """
    if not enabled:
        return list(fallback), SOURCE_FALLBACK
    try:
        nomes, origem = discover_category(
            category, max_items=max_items, min_price=min_price, cache=cache)
    except Exception:
        # Descoberta e' melhoria opcional: nunca pode derrubar o scan.
        return list(fallback), SOURCE_FALLBACK
    if nomes:
        return nomes, origem
    return list(fallback), SOURCE_FALLBACK
