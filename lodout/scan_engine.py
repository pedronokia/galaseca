"""Lógica de coleta e avaliação usada pelo worker do site público."""
from __future__ import annotations

import sys
import time
from typing import Callable

from lodout import cases, discovery, scan_targets, signals, steam_api
from lodout.prices import PriceCache
from lodout import textos


def _overview_da_pagina(page: "dict | None",
                        fator_preco: float) -> "dict | None":
    """{lowest, median, volume} só com a listing page, no formato do
    priceoverview -- pro modo de 1 requisição por item. None quando o
    book é de outro desgaste (aproximado) ou falta dado: aí quem chama
    faz a consulta completa.

    - lowest: menor anúncio do book x `fator_preco` (a razão medida pelo
      modo sombra entre priceoverview e o book; ex. 0.01 se o book vem
      em centavos).
    - median: mediana das vendas das 24 h anteriores ao ponto mais
      recente, ponderada pela quantidade de compras de cada ponto.
    - volume: compras nessas 24 h."""
    if not page or page.get("order_book_approx"):
        return None
    ask = (page.get("order_book") or {}).get("best_ask")
    if not isinstance(ask, (int, float)) or ask <= 0:
        return None
    median, volume = _mediana_volume_24h(page.get("price_history"))
    return {"lowest": round(ask * fator_preco, 2), "median": median,
            "volume": volume or None}


def _mediana_volume_24h(price_history: "list | None") -> "tuple[float | None, int | None]":
    """(mediana ponderada por compras, compras) das 24 h anteriores ao
    ponto mais recente do histórico da listing page."""
    hist = [p for p in price_history or []
            if isinstance(p, dict) and isinstance(p.get("time"), (int, float))
            and isinstance(p.get("price_median"), (int, float))]
    if not hist:
        return None, None
    corte = max(p["time"] for p in hist) - 86400
    janela = [p for p in hist if p["time"] > corte]
    volume = sum(int(p.get("purchases") or 0) for p in janela)
    pesos = sorted((p["price_median"], max(1, int(p.get("purchases") or 0)))
                   for p in janela)
    metade, acum = sum(w for _v, w in pesos) / 2, 0
    for v, w in pesos:
        acum += w
        if acum >= metade:
            return v, volume
    return None, volume


def scan_item(name: str, category: str | None = None,
             price_cache: "PriceCache | None" = None,
             fonte: str = "ambas",
             fator_preco: "float | None" = None) -> dict | None:
    """Avalia um item: preço, veredito, score + breakdown, riscos.

    `category` alimenta a exclusão de `pump_risk` por evento da Valve
    (ver `signals.pump_risk`). `price_cache`, se passado, recebe o preço
    mais recente (mesmo papel do `self._cache.put(...)` do Scanner).

    Retorna None se a Steam não devolveu preço nenhum     (falha de rede, item sem listagem, ou rate limit. Várias páginas sem
    `price_history` em sequência são suspeita de bloqueio, não prova de
    que os itens não têm histórico).

    `fonte="pagina"` (com `fator_preco`): 1 requisição por item -- tudo
    sai da listing page (`_overview_da_pagina`); só item com book
    aproximado ou sem dado faz o priceoverview também. Padrão "ambas":
    as 2 requisições de sempre.
    """
    try:
        if fonte == "pagina" and fator_preco:
            page = steam_api.get_market_page_data(name)
            overview = _overview_da_pagina(page, fator_preco)
            if overview is None:
                time.sleep(steam_api.RATE_LIMIT_DELAY_S)
                overview = steam_api.get_market_overview(name)
        else:
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
    sombra = _fonte_pagina(page, ob, ob_approx)
    approx_suffix = " ~" if ob_approx else ""

    return {
        "name": name,
        # Momento da coleta deste item -- o worker usa pra manter o dado
        # do ciclo anterior (marcado) quando o item falha no ciclo atual.
        "coletado_em": time.time(),
        "price": lowest,
        "median": median,
        "score": score,
        "breakdown": breakdown,
        "data_quality": dq,
        "is_container": is_cont,
        # Codigo interno traduzido na hora (textos.py) -- quem exibe nao
        # precisa saber "tight"/"buyer_dominant"/"rising".
        "verdict": verdict.get("label", "—"),
        # `.get("diff_pct", 0)` sozinho não bastava: o default só vale
        # para chave ausente, não quando ela existe mas é None.
        "verdict_ok": (verdict.get("diff_pct")
                       if verdict.get("diff_pct") is not None else 0) <= 0,
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
        "case_retired_at": cs.get("retired_at"),
        "case": cs.get("case"),
        "icon": meta.get("icon_url"),
        # Raridade da skin -- name_color (hex da Steam) e rarity_id (enum
        # estável) alimentam a cor de raridade do item na tabela. Vêm de
        # graça na mesma listing page, sem requisição extra.
        "rarity_id": meta.get("rarity_id"),
        "name_color": meta.get("name_color"),
        # quality_id (achado 2026-11-07, request real numa Karambit e
        # numas Sport Gloves): faca/luva tem name_color/rarity_id IGUAIS
        # aos de uma skin Covert comum -- só quality_id="unusual" (o
        # prefixo ★) distingue. Ver _raridade_suffix em server.py.
        "quality_id": meta.get("quality_id"),
        "category": category,
        "pump_risk": pr,
        "order_book_approx": ob_approx,
        "derived_price": derived_price,
        "variantes": _resumo_variantes(name, page),
        # Modo sombra (2026-11-13): o que a listing page sozinha diria de
        # menor preço e volume 24h, ao lado do priceoverview. Só medido --
        # `run_full_scan` tira isto do resultado (não vai pro scan_store
        # nem pra API) e resume em `comparar_fontes`.
        # Página veio sem histórico -- pode ser throttle silencioso da
        # Steam (AGENTS.md). `run_full_scan` decide e tira do resultado.
        "_sem_historico": not (page and page.get("price_history")),
        "_sombra": {
            **(sombra or {}),
            "lowest_overview": (overview or {}).get("lowest"),
            "volume_overview": volume,
            "median_overview": (overview or {}).get("median"),
        },
    }


def _fonte_pagina(page: "dict | None", ob: "dict | None",
                  ob_approx: bool) -> "dict | None":
    """Menor preço (book de venda) e compras das últimas 24h segundo a
    listing page -- só quando o book é do próprio item (não aproximado
    de outro wear). Valores crus, na unidade que a Steam mandou."""
    if not page or not ob or ob_approx:
        return None
    ask = ob.get("best_ask")
    hist = page.get("price_history") or []
    tempos = [p.get("time") for p in hist
              if isinstance(p.get("time"), (int, float))]
    compras = None
    if tempos:
        corte = max(tempos) - 86400
        compras = sum(int(p.get("purchases") or 0) for p in hist
                      if isinstance(p.get("time"), (int, float))
                      and p["time"] > corte)
    if not isinstance(ask, (int, float)) and compras is None:
        return None
    mediana, _vol = _mediana_volume_24h(hist)
    return {"best_ask": ask if isinstance(ask, (int, float)) else None,
            "compras_24h": compras,
            "mediana_24h": mediana}


# Ordem de exibição das variantes: desgaste (melhor -> pior) e, dentro
# dele, normal antes de StatTrak/Souvenir.
_ORDEM_DESGASTE = ("(Factory New)", "(Minimal Wear)", "(Field-Tested)",
                   "(Well-Worn)", "(Battle-Scarred)")
_VARIANTES_MAX = 12


def _resumo_variantes(nome: str, page: "dict | None") -> "list[dict]":
    """Outras versões da mesma skin (desgaste, StatTrak, Souvenir) que a
    listing page JÁ trouxe -- zero requisição extra. Pra cada uma: o
    preço mediano do ponto mais recente do histórico e as compras nas 24h
    anteriores a ele. É mediana de venda, não menor anúncio."""
    variantes = (page or {}).get("variants") or {}
    out = []
    for outro, hist in variantes.items():
        if outro == nome or not isinstance(hist, list):
            continue
        pontos = [p for p in hist if isinstance(p, dict)
                  and isinstance(p.get("time"), (int, float))
                  and isinstance(p.get("price_median"), (int, float))]
        if not pontos:
            continue
        ultimo = max(pontos, key=lambda p: p["time"])
        corte = ultimo["time"] - 86400
        out.append({
            "name": outro,
            "mediana": ultimo["price_median"],
            "ts": ultimo["time"],
            "compras_24h": sum(int(p.get("purchases") or 0) for p in pontos
                               if p["time"] > corte),
        })

    def _ordem(v: dict) -> tuple:
        n = v["name"]
        desgaste = next((i for i, w in enumerate(_ORDEM_DESGASTE) if w in n),
                        len(_ORDEM_DESGASTE))
        tipo = 1 if "StatTrak" in n else (2 if "Souvenir" in n else 0)
        return (desgaste, tipo, n)

    out.sort(key=_ordem)
    return out[:_VARIANTES_MAX]


def comparar_fontes(sombras: "list[dict]") -> "dict | None":
    """Quanto a listing page concorda com o priceoverview neste ciclo.

    `razao_preco` = mediana de lowest_overview / best_ask (1.0 = mesma
    unidade; 0.01 = book em centavos). `preco_concorda_pct` = % dos itens
    cujo preço convertido pela razão mediana fica a até 2% do overview.
    Mesma ideia pro volume (tolerância 25%) e pra mediana de 24 h
    (`razao_mediana`, tolerância 5%; a página já em reais, então a razão
    esperada é 1). Serve pra decidir, com dado de produção, se
    dá pra dispensar o priceoverview (metade das requisições por item)."""
    pares_p, pares_v, pares_m = [], [], []
    for f in sombras:
        lo, ask = f.get("lowest_overview"), f.get("best_ask")
        if isinstance(lo, (int, float)) and isinstance(ask, (int, float)) \
                and lo > 0 and ask > 0:
            pares_p.append(lo / ask)
        vo, vc = f.get("volume_overview"), f.get("compras_24h")
        if isinstance(vo, (int, float)) and isinstance(vc, (int, float)) \
                and vo > 0 and vc > 0:
            pares_v.append(vc / vo)
        mo, mp = f.get("median_overview"), f.get("mediana_24h")
        if isinstance(mo, (int, float)) and isinstance(mp, (int, float)) \
                and mo > 0 and mp > 0:
            pares_m.append(mp / mo)

    def _resumo(razoes: "list[float]", tol: float) -> "tuple[float | None, float | None]":
        if not razoes:
            return None, None
        ordenadas = sorted(razoes)
        med = ordenadas[len(ordenadas) // 2]
        ok = sum(1 for x in razoes if abs(x / med - 1) <= tol)
        return round(med, 6), round(100 * ok / len(razoes), 1)

    if not pares_p and not pares_v and not pares_m:
        return None
    rp, cp = _resumo(pares_p, 0.02)
    rv, cv = _resumo(pares_v, 0.25)
    rm, cm = _resumo(pares_m, 0.05)
    return {"itens_preco": len(pares_p), "razao_preco": rp,
            "preco_concorda_pct": cp, "itens_volume": len(pares_v),
            "razao_volume": rv, "volume_concorda_pct": cv,
            "itens_mediana": len(pares_m), "razao_mediana": rm,
            "mediana_concorda_pct": cm}


# Itens SEGUIDOS cuja página veio sem histórico, sendo que no ciclo
# anterior tinham, pra tratar como throttle silencioso da Steam.
_SEM_HIST_SEGUIDOS = 3

# Primeiros itens do ciclo sem NENHUM resultado (e sem 429) pra concluir
# que a Steam (ou a rede) está fora e encerrar o ciclo.
_ABORTA_SEM_NADA = 10


# Famílias do disjuntor de `steam_api` que `scan_item` usa.
_FAMILIAS_SCAN = ("priceoverview", "market_listings")
# Teto de espera pelo disjuntor num ciclo. Passou disso, a Steam está
# bloqueando de verdade: o ciclo para e o worker mantém o dado anterior
# dos itens que faltaram, em vez de seguir batendo.
_ESPERA_DISJUNTOR_MAX_S = 45 * 60


def _cooldown_scan_s() -> float:
    return max(steam_api.cooldown_restante_s(f) for f in _FAMILIAS_SCAN)


def _algum_cooldown() -> bool:
    return any(steam_api.em_cooldown(f) for f in _FAMILIAS_SCAN)


def run_full_scan(categories: "dict[str, list[str]] | None" = None,
                  on_progress: "Callable[[str], None] | None" = None,
                  discovery_enabled: bool = False,
                  cancelled: "Callable[[], bool] | None" = None,
                  falhas: "list[str] | None" = None,
                  ritmo: float = 1.0,
                  relatorio: "dict | None" = None,
                  tinham_historico: "set[str] | None" = None,
                  pular: "set[str] | None" = None,
                  on_resultado: "Callable[[dict], None] | None" = None,
                  prioridade: "dict[str, float] | None" = None,
                  fonte: str = "ambas",
                  fator_preco: "float | None" = None,
                  ) -> list[dict]:
    """Escaneia as categorias (default: todas de `scan_targets`), sem Qt.

    Pensado pro worker do site público: roda num processo próprio, sem
    threading/sinais, respeitando o mesmo `RATE_LIMIT_DELAY_S` de sempre.
    `on_progress`/`cancelled` são ganchos opcionais pra quem chama logar
    ou pedir parada graciosa entre itens. `falhas`, se passada, recebe o
    nome de cada item que terminou o ciclo sem resultado.

    Disjuntor (2026-11-13): com uma família em cooldown depois de um 429,
    `steam_api` recusa a chamada sem requisição -- o laço antigo seguia
    pela lista e perdia ~8 itens por 429 (o ciclo voltava com 177-181 de
    185). Agora o laço ESPERA o cooldown acabar antes do próximo item
    (mesmo total de requisições, nenhum item pulado) e o item que levou
    o 429 é repetido UMA vez no fim do ciclo, bem depois do bloqueio --
    nunca em seguida (ver AGENTS.md). Esperas somadas acima de
    `_ESPERA_DISJUNTOR_MAX_S` encerram o ciclo.

    `ritmo` (>= 1) multiplica a pausa ENTRE itens -- o worker sobe quando
    o ciclo anterior levou 429 (lido de `steam_api.RATE_LIMIT_DELAY_S` na
    hora, nunca copiado). `relatorio`, se passado, recebe `pausas_429`
    (quantas vezes o laço esperou o disjuntor) e `sem_preco` (itens que
    falharam sem bloqueio nenhum -- candidatos a "sem anúncio") e
    `throttle_silencioso` (quantas vezes a regra abaixo disparou).

    Throttle silencioso (AGENTS.md): a Steam às vezes responde 200 com a
    página sem histórico. Um item assim entrava com nota calculada sem
    histórico -- nota errada, não item faltando. Com `tinham_historico`
    (itens que tinham histórico no ciclo anterior), `_SEM_HIST_SEGUIDOS`
    itens seguidos nessa situação abrem o disjuntor de listing page (a
    mesma pausa escalonada de um 429) e voltam pro fim do ciclo. Se um
    item normal aparece antes disso, os anteriores eram genuínos e
    entram como vieram.

    Retomada (2026-11-13): `pular` são nomes já coletados neste ciclo
    antes de um reinício (checkpoint do worker) -- não são buscados de
    novo. `on_resultado` é chamado com cada resultado aceito, na hora,
    pra quem chama gravar o checkpoint.

    `prioridade` (nome -> chave, menor primeiro) ordena a lista INTEIRA,
    não categoria por categoria: se o ciclo for cortado, quem fica sem
    preço é o menos relevante, não sempre a última categoria. Nome sem
    chave vale 0.

    Steam fora do ar (2026-11-13): se os `_ABORTA_SEM_NADA` primeiros
    itens falham sem nenhum resultado e sem 429 (manutenção, rede da VM
    caída), o ciclo encerra ali -- antes ele seguia a lista inteira com
    2 requisições por item, todas perdidas. `relatorio["abortado"]`.
    """
    ritmo = max(1.0, float(ritmo or 1.0))
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

    def _avisa(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    esperado = 0.0
    pausas = 0

    def _espera_disjuntor() -> bool:
        """Dorme até o disjuntor fechar. False = estourou o teto do ciclo."""
        nonlocal esperado, pausas
        espera = _cooldown_scan_s()
        if espera <= 0:
            return True
        pausas += 1
        if esperado + espera > _ESPERA_DISJUNTOR_MAX_S:
            _avisa("Steam segue bloqueando; ciclo encerrado antes do fim")
            return False
        _avisa(f"Steam pediu pausa (429): esperando {espera / 60:.1f} min")
        time.sleep(espera)
        esperado += espera
        return True

    if pular:
        items = [(n, c) for n, c in items if n not in pular]
    if prioridade:
        # sort é estável: empate mantém a ordem das categorias.
        items.sort(key=lambda it: prioridade.get(it[0], 0.0))

    # Só repassa a fonte quando não é a padrão (os fakes de teste de
    # scan_item não conhecem os parâmetros novos).
    extra_item = ({"fonte": fonte, "fator_preco": fator_preco}
                  if fonte != "ambas" else {})

    results: list[dict] = []
    sem_resultado: list[str] = []
    sem_preco: list[str] = []
    sombras: list[dict] = []

    suspeitos: list[tuple[str, str, dict]] = []
    throttle = 0

    def _libera_suspeitos() -> None:
        for _n, _c, r in suspeitos:
            _guarda(r)
        suspeitos.clear()

    def _avalia(name: str, cat: str, result: dict) -> None:
        nonlocal throttle
        if (tinham_historico is not None and result.get("_sem_historico")
                and name in tinham_historico):
            suspeitos.append((name, cat, result))
            if len(suspeitos) >= _SEM_HIST_SEGUIDOS:
                throttle += 1
                _avisa(f"{len(suspeitos)} páginas seguidas sem histórico: "
                       "tratando como bloqueio silencioso")
                steam_api._registrar_rate_limit("market_listings")
                adiados.extend((n, c) for n, c, _r in suspeitos)
                suspeitos.clear()
            return
        _libera_suspeitos()
        _guarda(result)

    def _guarda(result: dict) -> None:
        result.pop("_sem_historico", None)
        sombra = result.pop("_sombra", None)
        if sombra:
            sombras.append(sombra)
        results.append(result)
        if on_resultado:
            on_resultado(result)
    adiados: list[tuple[str, str]] = []
    interrompido = False
    abortado = False
    for i, (name, cat) in enumerate(items):
        if cancelled and cancelled():
            interrompido = True
            break
        if not _espera_disjuntor():
            interrompido = True
            sem_resultado.extend(n for n, _c in items[i:])
            break
        _avisa(f"[{i + 1}/{len(items)}] {name}")
        result = scan_item(name, category=cat, **extra_item)
        if result:
            _avalia(name, cat, result)
        elif _algum_cooldown():
            # Este item levou o 429: tenta de novo só no fim do ciclo.
            adiados.append((name, cat))
        else:
            sem_resultado.append(name)
            sem_preco.append(name)
            if (len(sem_preco) >= _ABORTA_SEM_NADA and not results
                    and not suspeitos and not adiados):
                _avisa(f"{len(sem_preco)} primeiros itens sem nenhuma "
                       "resposta: Steam fora do ar? Ciclo encerrado")
                interrompido = abortado = True
                sem_resultado.extend(n for n, _c in items[i + 1:])
                break
        time.sleep(steam_api.RATE_LIMIT_DELAY_S * ritmo)

    _libera_suspeitos()
    for name, cat in adiados:
        if interrompido or (cancelled and cancelled()) or not _espera_disjuntor():
            interrompido = True
            sem_resultado.append(name)
            continue
        _avisa(f"Repetindo depois da pausa: {name}")
        result = scan_item(name, category=cat, **extra_item)
        if result:
            _guarda(result)
        else:
            sem_resultado.append(name)
            if not _algum_cooldown():
                sem_preco.append(name)
        time.sleep(steam_api.RATE_LIMIT_DELAY_S * ritmo)

    if falhas is not None:
        falhas.extend(sem_resultado)
    if relatorio is not None:
        relatorio["pausas_429"] = pausas
        relatorio["sem_preco"] = sem_preco
        relatorio["comparacao_fontes"] = comparar_fontes(sombras)
        relatorio["throttle_silencioso"] = throttle
        relatorio["abortado"] = abortado
    return results
