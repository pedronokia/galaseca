"""Acesso a dados PUBLICOS do Steam -- somente leitura, sem login.

Principio de design (o diferencial do produto): este modulo NUNCA recebe
senha, cookie de sessao ou API key privada. Le' so' o que ja' e' publico:

- Inventario publico (CS2 = appid 730, contextid 2):
    https://steamcommunity.com/inventory/{steamid}/730/2?l=english&count=5000
- Preco publico no Market (currency=7 = BRL):
    https://steamcommunity.com/market/priceoverview/?appid=730&currency=7&market_hash_name={name}
- Pagina de listagem do Market (SSR com price history + order book):
    https://steamcommunity.com/market/listings/730/{market_hash_name}

Sem login => nao da' pra roubar item, nao da' pra dar ban. Informa, nao age.

Implementado com urllib (stdlib): o "momento magico" roda sem pip install.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

_APP_CS2 = 730
_CONTEXT = 2
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"

# Status do fetch de inventario -- nascido de um teste real: perfil publico
# NAO garante inventario publico, e o Steam sinaliza cada caso diferente.
INV_OK = "ok"
# 400/403: nao acessivel. ATENCAO: o Steam e' inconsistente aqui -- pode ser
# privado, VAZIO (conta sem skins de CS2), ou ate rate-limit disfarcado. Nao da'
# pra afirmar "privado" so' pelo codigo. (Aprendido num teste real: settings em
# "Publico" e ainda assim 400.)
INV_PRIVATE = "private"
INV_RATE_LIMITED = "rate_limited"  # 429: bater de novo daqui a pouco
INV_EMPTY = "empty"             # 200 porem sem itens marketaveis de CS2
INV_ERROR = "error"             # rede/erro inesperado


def _http_get(url: str, timeout: float = 15.0) -> tuple[int, str | None]:
    """GET cru. Retorna (status_code, body). status 0 = erro de rede.
    Esta e' a unica camada que toca a rede -- e' o ponto de mock nos testes."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _get_json(url: str) -> dict | None:
    code, body = _http_get(url)
    if code != 200 or body is None:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def _parse_items(data: dict) -> list[dict]:
    """Cruza assets x descriptions e agrega por market_hash_name.
    So' itens marketaveis (da' pra avaliar no Market). Logica pura, testavel."""
    desc = {(d["classid"], d["instanceid"]): d for d in data.get("descriptions", [])}
    counts: dict[str, dict] = {}
    for asset in data.get("assets", []):
        d = desc.get((asset["classid"], asset["instanceid"]))
        if not d or not d.get("marketable"):
            continue
        name = d.get("market_hash_name")
        if not name:
            continue
        entry = counts.setdefault(
            name, {"name": name, "quantity": 0, "tradable": bool(d.get("tradable"))}
        )
        entry["quantity"] += int(asset.get("amount", 1))
    return list(counts.values())


def fetch_inventory(steam_id: str) -> tuple[str, list[dict]]:
    """Le o inventario publico e DIZ por que falhou, se falhar.

    Retorna (status, items). status em {ok, private, rate_limited, empty, error}.
    items so' vem preenchido quando status == 'ok'.
    """
    url = (
        f"https://steamcommunity.com/inventory/{steam_id}/{_APP_CS2}/{_CONTEXT}"
        f"?l=english&count=5000"
    )
    code, body = _http_get(url)
    if code in (400, 403):
        return INV_PRIVATE, []
    if code == 429:
        return INV_RATE_LIMITED, []
    if code != 200 or body is None:
        return INV_ERROR, []
    try:
        data = json.loads(body)
    except ValueError:
        return INV_ERROR, []
    if not data or not data.get("assets") or not data.get("descriptions"):
        return INV_EMPTY, []
    items = _parse_items(data)
    return (INV_OK, items) if items else (INV_EMPTY, [])


def fetch_public_inventory(steam_id: str) -> list[dict]:
    """Wrapper simples: so' os itens (lista vazia em qualquer falha)."""
    return fetch_inventory(steam_id)[1]


def get_market_price(market_hash_name: str, currency: int = 7) -> float | None:
    """Preco mais baixo atual no Steam Market, em BRL (currency=7). None se
    indisponivel. O Steam limita ~20 req/min -- producao precisa de cache+backoff."""
    url = (
        "https://steamcommunity.com/market/priceoverview/"
        f"?appid={_APP_CS2}&currency={currency}"
        f"&market_hash_name={urllib.parse.quote(market_hash_name)}"
    )
    data = _get_json(url)
    if not data or not data.get("success"):
        return None
    return parse_brl(data.get("lowest_price") or data.get("median_price"))


def get_market_overview(market_hash_name: str, currency: int = 7) -> dict | None:
    """Retorna {lowest, median, volume} do Steam Market, ou None.
    
    Tudo publico -- same endpoint as get_market_price, mas parseia os 3 campos.
    Usado pelo fair-value (Tarefa 2)."""
    url = (
        "https://steamcommunity.com/market/priceoverview/"
        f"?appid={_APP_CS2}&currency={currency}"
        f"&market_hash_name={urllib.parse.quote(market_hash_name)}"
    )
    data = _get_json(url)
    if not data or not data.get("success"):
        return None
    return {
        "lowest": parse_brl(data.get("lowest_price")),
        "median": parse_brl(data.get("median_price")),
        "volume": _parse_volume(data.get("volume")),
    }


def _parse_volume(text: str | None) -> int | None:
    if not text:
        return None
    s = str(text).strip().replace(",", "")
    try:
        return int(s)
    except ValueError:
        return None


def _js_unescape(s: str) -> str:
    """Unescape uma JavaScript string literal (entre as aspas externas)."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt == '"':
                result.append('"')
            elif nxt == "\\":
                result.append("\\")
            elif nxt == "n":
                result.append("\n")
            elif nxt == "r":
                result.append("\r")
            elif nxt == "t":
                result.append("\t")
            elif nxt == "/":
                result.append("/")
            elif nxt == "u":
                result.append(chr(int(s[i + 2 : i + 6], 16)))
                i += 5
            else:
                result.append(nxt)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return "".join(result)


_MARKET_LISTING_URL = (
    "https://steamcommunity.com/market/listings/{appid}/{name}"
)


def _extract_render_context(html: str) -> dict | None:
    """Extrai o objeto `renderContext` do HTML da pagina de listagem.

    O dado esta' embutido em:
      window.SSR.renderContext = JSON.parse("...");
    """
    m = re.search(
        r'window\.SSR\.renderContext\s*=\s*JSON\.parse\("(.*?)"\)',
        html, re.DOTALL,
    )
    if not m:
        return None
    raw = m.group(1)
    try:
        return json.loads(_js_unescape(raw))
    except (ValueError, TypeError):
        return None


def _find_query(queries: list, key: str, item_name: str | None = None) -> dict | None:
    """Procura no React Query cache a query com queryKey contendo `key`.

    Se `item_name` for fornecido, tambem confere se o queryKey inclui o
    nome do item (posicao 3, depois de appid).
    """
    for q in queries:
        qk = q.get("queryKey", [])
        if not isinstance(qk, list) or key not in qk:
            continue
        if item_name is not None and len(qk) > 3:
            # queryKey = ["market", key, 730, "Item Name"]
            cached_name = str(qk[3])
            if item_name.lower() not in cached_name.lower():
                continue
        return q.get("state", {}).get("data")
    return None


def get_market_page_data(
    market_hash_name: str,
) -> dict | None:
    """Busca dados SSR da pagina de listagem do Steam Market.

    Retorna um dict com:
      - price_history: list[dict] -- {time, price_median, purchases}
      - order_book: dict -- {amtMaxBuyOrder, amtMinSellOrder, eCurrency,
        cBuyOrders, cSellOrders, rgCompactBuyOrders, rgCompactSellOrders}
      - metadata: dict -- {name, exterior, rarity, ...} (quando disponivel)

    Retorna None se a pagina nao carregar ou o parse falhar.
    """
    url = _MARKET_LISTING_URL.format(
        appid=_APP_CS2,
        name=urllib.parse.quote(market_hash_name, safe=""),
    )
    code, body = _http_get(url)
    if code != 200 or body is None:
        return None

    rc = _extract_render_context(body)
    if not rc:
        return None

    qd_raw = rc.get("queryData")
    if not isinstance(qd_raw, str):
        return None

    try:
        qd = json.loads(qd_raw)
    except (ValueError, TypeError):
        return None

    queries = qd.get("queries", [])
    if not queries:
        return None

    # Price history
    price_data = _find_query(queries, "pricehistory", market_hash_name)
    order_data = _find_query(queries, "orderbook", market_hash_name)

    result: dict = {}
    if price_data:
        prices = price_data.get("prices") if isinstance(price_data, dict) else price_data
        if isinstance(prices, list):
            result["price_history"] = prices

    if order_data and isinstance(order_data, dict):
        result["order_book"] = {
            "best_bid": order_data.get("amtMaxBuyOrder"),
            "best_ask": order_data.get("amtMinSellOrder"),
            "buy_count": order_data.get("cBuyOrders"),
            "sell_count": order_data.get("cSellOrders"),
            "buy_orders": order_data.get("rgCompactBuyOrders"),
            "sell_orders": order_data.get("rgCompactSellOrders"),
            "spread": (
                (order_data.get("amtMinSellOrder", 0) - order_data.get("amtMaxBuyOrder", 0))
                if order_data.get("amtMinSellOrder") and order_data.get("amtMaxBuyOrder")
                else None
            ),
        }

    return result if result else None


def fair_value_verdict(
    lowest: float | None,
    median: float | None,
    spread: int | None = None,
    buy_count: int | None = None,
    sell_count: int | None = None,
    price_history: list | None = None,
) -> dict:
    """Compara lowest vs mediana e da' o veredito honesto.

    Parametros opcionais (do order book + price history):
      spread: best_ask - best_bid (em centavos)
      buy_count: numero de ordens de compra
      sell_count: numero de ordens de venda
      price_history: lista de {time, price_median, purchases}

    Retorna {diff_pct, verdict, label, message} + quando dados extras:
      {spread_pct, spread_verdict, book_ratio, book_verdict,
       trend_pct, trend_verdict, details}
    """
    if lowest is None or median is None or median == 0:
        return {"diff_pct": None, "verdict": "unknown",
                "label": "sem dados",
                "message": "Dados insuficientes para comparar."}

    diff_pct = ((lowest - median) / median) * 100
    if diff_pct <= -5:
        verdict = "below_median"
        label = "abaixo da mediana"
        msg = f"Menor listagem {abs(diff_pct):.0f}% abaixo da mediana. Bom negocio."
    elif diff_pct <= 5:
        verdict = "fair"
        label = "preco justo"
        msg = "Preco dentro de 5% da mediana. Justo."
    elif diff_pct <= 20:
        verdict = "slightly_above"
        label = "levemente acima"
        msg = f"Listagem {diff_pct:.0f}% acima da mediana. Levemente caro."
    else:
        verdict = "overpriced"
        label = "muito acima"
        msg = f"Listagem {diff_pct:.0f}% acima da mediana. Caro demais."

    result: dict = {
        "diff_pct": diff_pct,
        "verdict": verdict,
        "label": label,
        "message": msg,
    }

    extra = _extra_verdict(spread, buy_count, sell_count, price_history, lowest)
    if extra:
        result.update(extra)
        msg_parts = [result["message"]]
        if extra.get("spread_verdict") == "wide":
            msg_parts.append(extra["details"].get("spread", ""))
        if extra.get("book_verdict") == "seller_dominant":
            msg_parts.append("Muitos vendedores.")
        elif extra.get("book_verdict") == "buyer_dominant":
            msg_parts.append("Demanda aquecida.")
        if extra.get("trend_verdict") == "falling":
            msg_parts.append("Preco caindo nos ultimos dias.")
        elif extra.get("trend_verdict") == "rising":
            msg_parts.append("Preco subindo nos ultimos dias.")
        result["message"] = " ".join(msg_parts)

    return result


def _extra_verdict(
    spread: int | None,
    buy_count: int | None,
    sell_count: int | None,
    price_history: list | None,
    lowest: float | None = None,
) -> dict | None:
    """Analisa order book + price history e retorna indicadores extras."""
    extra: dict = {}
    details: dict = {}

    if spread is not None and spread > 0 and lowest and lowest > 0:
        spread_pct = spread / (spread + lowest * 100) * 100
        extra["spread_pct"] = round(spread_pct, 2)
        if spread_pct <= 2:
            extra["spread_verdict"] = "tight"
            details["spread"] = "Spread apertado — mercado liquido."
        elif spread_pct <= 10:
            extra["spread_verdict"] = "normal"
        else:
            extra["spread_verdict"] = "wide"
            details["spread"] = f"Spread amplo ({spread_pct:.0f}%) — pouca liquidez."

    if buy_count is not None and sell_count is not None and sell_count > 0:
        ratio = round(buy_count / sell_count, 1)
        extra["book_ratio"] = ratio
        if ratio >= 5:
            extra["book_verdict"] = "buyer_dominant"
        elif ratio <= 0.2:
            extra["book_verdict"] = "seller_dominant"
        else:
            extra["book_verdict"] = "balanced"

    if price_history and len(price_history) >= 7:
        recent = price_history[-7:]
        first = recent[0].get("price_median", 0)
        last = recent[-1].get("price_median", 0)
        if first and last:
            trend_pct = ((last - first) / first) * 100
            extra["trend_pct"] = round(trend_pct, 2)
            extra["trend_verdict"] = (
                "rising" if trend_pct > 3 else
                "falling" if trend_pct < -3 else
                "stable"
            )

    if extra:
        extra["details"] = details
        return extra
    return None


def parse_brl(text: str | None) -> float | None:
    """'R$ 1.234,56' -> 1234.56. Mesma logica do parser do Future."""
    if not text:
        return None
    s = str(text).replace("R$", "").replace("\xa0", " ").strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
