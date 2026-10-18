"""Logica de dados do Scanner -- sem Flask, testavel isolado.

Equivalente web de `ui/scanner_screen.py` (`_scan_item`/`_on_scan`),
reduzido ao nucleo: escolher uma categoria da lista fixa
(`scan_targets.py`), escanear e ver a tabela ordenada por nota.
Descoberta por faceta (settings.scanner_discovery), Ranking Top 20 e
o dialog de validacao historica ficam de fora deste MVP -- a lista
fixa e' o default do proprio app (descoberta nasce desligada).
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Callable, Optional

from skinvault import cases, signals, steam_api
from skinvault.prices import PriceCache
from skinvault.scan_targets import SCAN_BY_CATEGORY

ProgressCb = Callable[[int, int, str], None]
ItemCb = Callable[[dict], None]
DoneCb = Callable[[dict], None]

# Mesmas 3 traducoes de ui/textos.py, duplicadas de proposito: o webapp
# nao importa nada de skinvault.ui (pacote Qt) para nao criar um
# acoplamento que nao existe hoje -- sao 3 dicts pequenos, o custo de
# duplicar e' bem menor que o de uma dependencia cruzada.
_SPREAD_TXT = {"tight": "Pequena", "normal": "Normal", "wide": "Grande"}
_BOOK_TXT = {"buyer_dominant": "Mais compradores",
             "seller_dominant": "Mais vendedores",
             "balanced": "Equilibrada"}
_TREND_TXT = {"rising": "Subindo", "falling": "Caindo", "stable": "Estável"}

_scan_lock = threading.Lock()
_scanning = False
_cancel_requested = False


def categories() -> list[str]:
    return list(SCAN_BY_CATEGORY.keys())


def _scan_item(name: str, cache: PriceCache) -> Optional[dict]:
    """Avalia UM item: preco + veredito + nota. Mesma logica de
    `ScannerScreen._scan_item`, sem os campos so' de apresentacao Qt
    (cor do tema -- a UI web usa classe CSS pelo `verdict` cru)."""
    try:
        overview = steam_api.get_market_overview(name)
        time.sleep(steam_api.RATE_LIMIT_DELAY_S)
        page = steam_api.get_market_page_data(name)
    except Exception as e:
        print(f"WARNING: _scan_item({name}) failed: {e}", file=sys.stderr)
        return None

    lowest = overview.get("lowest") if overview else None
    median = overview.get("median") if overview else None
    volume = overview.get("volume") if overview else None
    derived_price = False

    if lowest is None and page and page.get("price_history"):
        last = page["price_history"][-1]
        price_val = last.get("price_median")
        if price_val and price_val > 0:
            lowest = price_val
            derived_price = True

    if lowest is None:
        return None

    cache.put(name, lowest)

    ob = page.get("order_book") if page else None
    meta = (page.get("meta") or {}) if page else {}
    verdict = steam_api.fair_value_verdict(
        lowest, median,
        spread=ob.get("spread") if ob else None,
        buy_count=ob.get("buy_count") if ob else None,
        sell_count=ob.get("sell_count") if ob else None,
        price_history=page.get("price_history") if page else None,
        tradable_restriction=meta.get("tradable_restriction"),
    ) if page else steam_api.fair_value_verdict(lowest, median)

    signals.record_item_price(name, lowest)
    if volume:
        signals.record_item_volume(name, volume)
    supply = ob.get("sell_count") if ob else None
    if supply is not None:
        signals.record_item_supply(name, supply)

    multi = (signals.multi_trend(page.get("price_history", []))
             if page and page.get("price_history") else None)
    cs = cases.case_status(name, collection=meta.get("collection"))
    is_cont = cases.is_container(name)

    score, breakdown = signals.enhanced_score(
        verdict, volume, supply,
        multi_trend=multi,
        price_history=page.get("price_history") if page else None,
        case_status=cs,
        is_container=is_cont,
    )

    ob_approx = bool(page.get("order_book_approx")) if page else False
    return {
        "name": name,
        "price": lowest,
        "derived_price": derived_price,
        "median": median,
        "score": score,
        "score_tooltip": signals.format_breakdown(breakdown),
        "is_container": is_cont,
        "verdict": verdict.get("verdict", "unknown"),
        "verdict_label": verdict.get("label", "—"),
        "spread": _SPREAD_TXT.get(verdict.get("spread_verdict", ""), ""),
        "book": _BOOK_TXT.get(verdict.get("book_verdict", ""), ""),
        "trend": _TREND_TXT.get(verdict.get("trend_verdict", ""), ""),
        "volume": volume,
        "supply": supply,
        "sd_label": signals.supply_demand_ratio(volume, supply).get("label", ""),
        "case_label": cs.get("label", ""),
        "order_book_approx": ob_approx,
    }


def is_scanning() -> bool:
    return _scanning


def cancel_scan() -> None:
    global _cancel_requested
    _cancel_requested = True


def start_scan(category: str, on_progress: ProgressCb, on_item: ItemCb,
                on_done: DoneCb, cache: Optional[PriceCache] = None) -> bool:
    """Escaneia uma categoria (ou todas) em background. Entre itens
    dorme `steam_api.RATE_LIMIT_DELAY_S`, igual o worker do Qt."""
    global _scanning, _cancel_requested
    with _scan_lock:
        if _scanning:
            return False
        _scanning = True
        _cancel_requested = False

    cache = cache or PriceCache()
    if category == "Todas as categorias":
        items: list[str] = []
        seen: set = set()
        for names in SCAN_BY_CATEGORY.values():
            for n in names:
                if n not in seen:
                    seen.add(n)
                    items.append(n)
    else:
        items = list(SCAN_BY_CATEGORY.get(category, []))

    def _worker() -> None:
        global _scanning
        cancelled = False
        try:
            total = len(items)
            for i, name in enumerate(items, start=1):
                if _cancel_requested:
                    cancelled = True
                    break
                on_progress(i, total, name)
                result = _scan_item(name, cache)
                if result:
                    on_item(result)
                time.sleep(steam_api.RATE_LIMIT_DELAY_S)
        except Exception as exc:
            print(f"WARNING: scan worker falhou: {exc}", file=sys.stderr)
        finally:
            with _scan_lock:
                _scanning = False
            on_done({"cancelled": cancelled})

    threading.Thread(target=_worker, daemon=True,
                      name="skinvault-web-scanner").start()
    return True
