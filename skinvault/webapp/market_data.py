"""Logica de dados da Consulta de Mercado -- sem Flask, testavel isolado.

Equivalente web de `market_screen.py`: UMA consulta ao vivo por busca
(get_market_overview + get_market_page_data), nao um lote -- bem mais
barato em rate limit que Conta/Scanner, que avaliam dezenas de itens.
Por isso e' sincrono (sem SSE): a tela trava por 1-3s no pior caso, que
e' exatamente o que o botao "Consultar item" do Qt tambem faz.
"""
from __future__ import annotations

import json
from typing import Optional

from skinvault import cases, signals, steam_api
from skinvault._paths import DATA_DIR, atomic_write_text
from skinvault.prices import PriceCache

_RECENT_PATH = DATA_DIR / "market_recent.json"
_RECENT_CAP = 8


def load_recent() -> list[str]:
    try:
        data = json.loads(_RECENT_PATH.read_text("utf-8"))
        return data[:_RECENT_CAP] if isinstance(data, list) else []
    except Exception:
        return []


def _save_recent(items: list[str]) -> None:
    try:
        atomic_write_text(_RECENT_PATH, json.dumps(items[:_RECENT_CAP]))
    except OSError:
        pass


def _record_recent(name: str) -> list[str]:
    items = [n for n in load_recent() if n != name]
    items.insert(0, name)
    items = items[:_RECENT_CAP]
    _save_recent(items)
    return items


def search(name: str, cache: Optional[PriceCache] = None) -> dict:
    """Busca AO VIVO (2 chamadas: priceoverview + listing page). Grava no
    cache de preco, no historico de volume e nos recentes -- mesmos
    efeitos colaterais do `_on_search`/`_on_data` do Qt."""
    cache = cache or PriceCache()
    data: dict = {"name": name}
    try:
        overview = steam_api.get_market_overview(name)
        if overview:
            data["overview"] = overview
        page = steam_api.get_market_page_data(name)
        if page:
            data["page"] = page
    except Exception as exc:  # pragma: no cover - defensivo, igual o Qt
        data["error"] = str(exc)

    overview = data.get("overview")
    page = data.get("page")
    if not overview and not page:
        data["found"] = False
        return data

    data["found"] = True
    data["recent"] = _record_recent(name)
    data["case_status"] = cases.case_status(name)

    verdict: dict = {}
    if overview:
        lowest = overview.get("lowest")
        median = overview.get("median")
        volume = overview.get("volume")
        ob = page.get("order_book") if page else None
        verdict = steam_api.fair_value_verdict(
            lowest, median,
            spread=ob.get("spread") if ob else None,
            buy_count=ob.get("buy_count") if ob else None,
            sell_count=ob.get("sell_count") if ob else None,
            price_history=page.get("price_history") if page else None,
        )
        if lowest is not None:
            cache.put(name, lowest)
        if volume:
            signals.record_item_volume(name, volume)
            hist = signals.load_item_volume(name)
            data["volume_anomaly"] = signals.volume_anomaly(hist)
    data["verdict"] = verdict
    data["throttled"] = bool(page) and not overview

    if page:
        # price_history/order_book podem ser grandes; a tela so' precisa
        # dos ultimos pontos pro sparkline, nao da serie inteira (~5000).
        ph = page.get("price_history") or []
        data["price_history_tail"] = ph[-90:]
        data["order_book"] = page.get("order_book")
        data["order_book_approx"] = bool(page.get("order_book_approx"))
    return data
