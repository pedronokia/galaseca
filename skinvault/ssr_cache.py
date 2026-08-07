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

from skinvault._paths import (
    DATA_DIR, atomic_write_text, load_json_record,
)

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
        # Cache, mas o unico que vale preservar: sao ~265 series de historico
        # acumuladas contra um endpoint agressivamente rate-limited. Refazer
        # custa dias, entao um arquivo ilegivel vai pra quarentena em vez de
        # ser apagado pelo proximo save.
        data = load_json_record(self.path, {})
        self._data = data if isinstance(data, dict) else {}

    def _save(self) -> None:
        try:
            atomic_write_text(self.path, json.dumps(self._data))
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

    def put_many(self, mapping: dict) -> int:
        """Armazena varios itens com UM save. Retorna quantos gravou.

        Existe porque uma listing page devolve ate ~10 series de uma vez:
        chamar put() em laco faria 10 escritas em disco pra um unico fetch.
        Entradas vazias ou de tipo errado sao ignoradas.
        """
        if not isinstance(mapping, dict):
            return 0
        now = time.time()
        gravados = 0
        for name, ph in mapping.items():
            if not isinstance(ph, list) or not ph:
                continue
            self._data[str(name)] = {"ts": now, "price_history": ph}
            gravados += 1
        if gravados:
            self._save()
        return gravados

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

    Wrapper fino de `cached_price_history_and_book` pra quem so' quer o
    historico (a maioria dos chamadores) sem mudar o contrato existente.
    """
    ph, _ob = cached_price_history_and_book(name, cache=cache)
    return ph


def cached_price_history_and_book(
    name: str,
    cache: PriceHistoryCache | None = None,
) -> "tuple[list[dict] | None, dict | None]":
    """Como `cached_price_history`, mas tambem devolve o order_book.

    O order_book NUNCA e' persistido no cache (so' price_history) -- por
    isso so' vem preenchido numa busca FRESCA (cache miss). Em cache hit
    volta None: sem fetch novo nesse ciclo, nao ha' book atual pra mostrar.

    Existe pra quem quer aproveitar o order_book que a MESMA resposta ja'
    trouxe de graca (ex.: Watchlist, que so' buscava price_history e
    descartava o resto) sem gerar uma segunda requisicao.

    A pagina buscada traz as variantes irmas do skin (cada wear x
    Normal/StatTrak/Souvenir) na MESMA resposta. Todas sao gravadas no
    cache, nao so' a pedida: sem isso, escanear os 6 wears de um skin
    custaria 6 requisicoes quando uma ja' respondeu por todas -- e o
    endpoint e' agressivamente rate-limited.
    """
    from skinvault import steam_api
    cache = cache or PriceHistoryCache()
    cached = cache.get(name)
    if cached is not None:
        return cached, None
    page = steam_api.get_market_page_data(name)
    if not page:
        return None, None

    variants = page.get("variants")
    semeados = cache.put_many(variants) if isinstance(variants, dict) else 0
    order_book = page.get("order_book")

    ph = page.get("price_history")
    if ph:
        # put_many ja' gravou o item pedido quando ele veio no lote; repetir
        # so' geraria outra escrita em disco.
        if not (semeados and isinstance(variants, dict) and name in variants):
            cache.put(name, ph)
        return ph, order_book
    return None, order_book
