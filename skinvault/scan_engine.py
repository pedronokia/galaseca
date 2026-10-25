"""Motor de scan sem Qt -- usado pelo Scanner (UI) e pelo worker do site
público (`skinvault/public_site/worker.py`).

`scan_item` é o núcleo que antes vivia dentro de
`ui/scanner_screen.py::_scan_item`, extraído pra cá pra não duplicar a
lógica em dois lugares (mesma lição do AGENTS.md #5/#12 -- duplicar quebra
em silêncio quando um lado muda e o outro não). `scanner_screen.py` agora
chama esta função; os campos puramente visuais (cor/formatação Qt) ficam
por conta de quem chama, porque este módulo não importa PyQt6 de propósito
-- o worker do site público roda num processo que não precisa dele.

`run_full_scan` é o laço de "todas as categorias" sem threading/sinais Qt,
pro worker rodar sozinho.
"""
from __future__ import annotations

import sys
import time
from typing import Callable

from skinvault import cases, discovery, scan_targets, signals, steam_api
from skinvault.prices import PriceCache
from skinvault.ui import textos


def scan_item(name: str, category: str | None = None,
             price_cache: "PriceCache | None" = None) -> dict | None:
    """Avalia um item: preço, veredito, score + breakdown, riscos.

    `category` alimenta a exclusão de `pump_risk` por evento da Valve
    (ver `signals.pump_risk`). `price_cache`, se passado, recebe o preço
    mais recente (mesmo papel do `self._cache.put(...)` do Scanner).

    Retorna None se a Steam não devolveu preço nenhum (falha de rede,
    item sem listagem, ou rate limit -- ver AGENTS.md #12: várias
    chamadas sem `price_history` em sequência é suspeita de bloqueio, não
    prova de item sem histórico).
    """
    try:
        overview = steam_api.get_market_overview(name)
        time.sleep(steam_api.RATE_LIMIT_DELAY_S)
        page = steam_api.get_market_page_data(name)
    except Exception as e:
        print(f"WARNING: scan_item({name}) failed: {e}", file=sys.stderr)
        return None

    lowest = overview.get("lowest") if overview else None
    median = overview.get("median") if overview else None
    volume = overview.get("volume") if overview else None
    derived_price = False

    if lowest is None and page and page.get("price_history"):
        ph = page["price_history"]
        last = ph[-1]
        price_val = last.get("price_median")
        if price_val and price_val > 0:
            lowest = price_val
            derived_price = True

    if lowest is None:
        return None

    if price_cache is not None:
        price_cache.put(name, lowest)

    ob = page.get("order_book") if page else None
    # Metadados oficiais da Steam (tags da description) -- vem na mesma
    # pagina, sem requisicao extra.
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

    multi = signals.multi_trend(
        page.get("price_history", [])
    ) if page and page.get("price_history") else None
    # A colecao vem da tag ItemSet da Steam: resolve item que o mapa
    # manual _SKIN_TO_CASE nao cobre, sem sobrescrever o que ja' cobre.
    cs = cases.case_status(name, collection=meta.get("collection"))
    is_cont = cases.is_container(name)

    score, breakdown = signals.enhanced_score(
        verdict, volume, supply,
        multi_trend=multi,
        price_history=page.get("price_history") if page else None,
        case_status=cs,
        is_container=is_cont,
    )

    dq = signals.data_quality(
        page.get("price_history") if page else []
    )

    pr = signals.pump_risk(
        price_history=page.get("price_history") if page else None,
        volume_history=signals.load_item_volume(name),
        category=category,
    )

    ob_approx = bool(page.get("order_book_approx")) if page else False
    approx_suffix = " ~" if ob_approx else ""

    return {
        "name": name,
        "price": lowest,
        "median": median,
        "score": score,
        "breakdown": breakdown,
        "data_quality": dq,
        "is_container": is_cont,
        # Codigo interno traduzido na hora (textos.py) -- quem exibe nao
        # precisa saber "tight"/"buyer_dominant"/"rising".
        "verdict": verdict.get("label", "—"),
        "verdict_ok": verdict.get("diff_pct", 0) <= 0,
        "spread": (textos.traduz(textos.SPREAD, verdict.get("spread_verdict"))
                   + (approx_suffix if verdict.get("spread_verdict") else "")),
        "book": (textos.traduz(textos.BOOK, verdict.get("book_verdict"))
                 + (approx_suffix if verdict.get("book_verdict") else "")),
        "trend": textos.traduz(textos.TREND, verdict.get("trend_verdict")),
        "trend_code": verdict.get("trend_verdict", ""),
        "volume": volume,
        "supply": supply,
        "sd_label": signals.supply_demand_ratio(volume, supply).get("label", ""),
        "liquidity_depth": signals.liquidity_depth(
            supply, signals.load_item_volume(name)),
        "zscore": signals.price_zscore(
            page.get("price_history")) if page else {},
        "score_tooltip": signals.format_breakdown(breakdown),
        "case_label": cs.get("label", ""),
        "icon": meta.get("icon_url"),
        "category": category,
        "pump_risk": pr,
        "order_book_approx": ob_approx,
        "derived_price": derived_price,
    }


def run_full_scan(categories: "dict[str, list[str]] | None" = None,
                  on_progress: "Callable[[str], None] | None" = None,
                  discovery_enabled: bool = False,
                  cancelled: "Callable[[], bool] | None" = None,
                  ) -> list[dict]:
    """Escaneia as categorias (default: todas de `scan_targets`), sem Qt.

    Pensado pro worker do site público: roda num processo próprio, sem
    threading/sinais, respeitando o mesmo `RATE_LIMIT_DELAY_S` de sempre.
    `on_progress`/`cancelled` são ganchos opcionais pra quem chama logar
    ou pedir parada graciosa entre itens.
    """
    if categories is None:
        categories = scan_targets.SCAN_BY_CATEGORY

    items: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for nome_cat, fallback in categories.items():
        if cancelled and cancelled():
            break
        achados, origem = discovery.resolve_scan_items(
            nome_cat, fallback, enabled=discovery_enabled,
        )
        for nome in achados:
            if nome not in vistos:
                vistos.add(nome)
                items.append((nome, nome_cat))
        if origem == discovery.SOURCE_DISCOVERY:
            time.sleep(steam_api.RATE_LIMIT_DELAY_S)

    results: list[dict] = []
    for i, (name, cat) in enumerate(items):
        if cancelled and cancelled():
            break
        if on_progress:
            on_progress(f"[{i + 1}/{len(items)}] {name}")
        result = scan_item(name, category=cat)
        if result:
            results.append(result)
        time.sleep(steam_api.RATE_LIMIT_DELAY_S)
    return results
