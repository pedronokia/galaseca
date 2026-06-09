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

import html as _html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skinvault.steam_session import SteamSession

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


def fetch_inventory_authed(
    session: "SteamSession",
) -> tuple[str, list[dict]]:
    """Versao autenticada de fetch_inventory: usa cookies da sessao,
    permitindo ler inventario privado/amigos do proprio usuario.

    Retorna (status, items) com mesmos codigos de fetch_inventory.
    """
    steam_id = session.steamid
    url = (
        f"https://steamcommunity.com/inventory/{steam_id}/{_APP_CS2}/{_CONTEXT}"
    )
    headers = {"Referer": f"https://steamcommunity.com/profiles/{steam_id}/inventory/"}
    code, body = _http_get_auth(url, session, extra_headers=headers)
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


_WEAR_RE = re.compile(
    r"\s*\((?:Factory New|Minimal Wear|Field-Tested|Well-Worn|Battle-Scarred)\)\s*$",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(
    r"^(?:StatTrak[™®'\s]*|Souvenir\s+|★\s*)+",
    re.IGNORECASE,
)


def _skin_root_name(name: str) -> str:
    """Normaliza o nome para "root" do skin: sem wear, StatTrak, Souvenir,
    ★ (Vanilla knife marker).

    "StatTrak™ AK-47 | Redline (Field-Tested)" -> "ak-47 | redline"
    "Souvenir P250 | Sand Dune"                     -> "p250 | sand dune"
    Util quando a Steam pre-carrega orderbook de um wear so' e queremos
    aproximacao do mesmo skin.
    """
    s = name or ""
    s = _PREFIX_RE.sub("", s)
    s = _WEAR_RE.sub("", s)
    return s.strip().lower()


def _find_query(queries: list, key: str, item_name: str | None = None,
                loose_match: bool = False) -> dict | None:
    """Procura no React Query cache a query com queryKey contendo `key`.

    Se `item_name` for fornecido, tambem confere se o queryKey inclui o
    nome do item (posicao 3, depois de appid).

    `loose_match`: aceita match pelo "skin root" (sem wear/StatTrak/etc).
    Util pra orderbook, que a Steam pre-carrega para apenas um wear do
    skin (ex.: pedi Field-Tested mas SSR so' tem Minimal Wear cached).
    """
    target_root = _skin_root_name(item_name) if (loose_match and item_name) else None
    for q in queries:
        qk = q.get("queryKey", [])
        if not isinstance(qk, list) or key not in qk:
            continue
        if item_name is not None and len(qk) > 3:
            # queryKey = ["market", key, 730, "Item Name"]
            cached_name = str(qk[3])
            if item_name.lower() in cached_name.lower():
                return q.get("state", {}).get("data")
            if target_root and target_root == _skin_root_name(cached_name):
                return q.get("state", {}).get("data")
        else:
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
    # Tenta orderbook exato; se nao houver, aceita orderbook de outro wear
    # do mesmo skin (Steam pre-carrega so' um wear). Sinaliza via flag.
    order_data = _find_query(queries, "orderbook", market_hash_name)
    order_approx = False
    if order_data is None:
        order_data = _find_query(
            queries, "orderbook", market_hash_name, loose_match=True,
        )
        order_approx = order_data is not None

    result: dict = {}
    if price_data:
        prices = price_data.get("prices") if isinstance(price_data, dict) else price_data
        if isinstance(prices, list):
            result["price_history"] = prices

    if order_data and isinstance(order_data, dict):
        result["order_book_approx"] = order_approx
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


# ── Endpoints autenticados (F10) ────────────────────────────────
# Tudo aqui exige uma SteamSession com cookies validos. Funcoes publicas
# acima continuam funcionando sem login.

@dataclass
class MarketEvent:
    """Evento do historico do Steam Market (compra ou venda)."""
    name: str
    side: str                  # 'buy' | 'sell' | 'listed' | 'cancelled'
    price: float | None        # em BRL ja parseado
    date_str: str              # data crua do HTML (ex.: '15 Mar')
    listing_id: str | None     # id da listagem, quando disponivel
    appid: str | None = None   # appid do jogo (730 = CS2), None se nao extraido
    icon_url: str | None = None  # hash do icone Steam CDN, p/ render visual


@dataclass
class TradeEvent:
    """Evento de trade offer aceita (troca entre usuarios)."""
    tradeofferid: str
    partner_steamid: str | None
    date_str: str
    items_given: list[str]
    items_received: list[str]


def _http_get_auth(url: str, session: "SteamSession",
                   timeout: float = 20.0,
                   extra_headers: dict | None = None) -> tuple[int, str | None]:
    """GET com cookies de sessao. Retorna (code, body)."""
    headers = {
        "User-Agent": _UA,
        "Cookie": session.cookie_header(),
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
        "Referer": "https://steamcommunity.com/market/",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def fetch_market_history(session: "SteamSession", start: int = 0,
                         count: int = 100,
                         appid: str | None = "730") -> dict | None:
    """JSON cru de /market/myhistory/render/. Pagina manual via start/count.

    Steam aceita filtro `appid=730` (CS2) na URL; passando None,
    devolve eventos de todos os jogos negociados no Market.
    """
    url = (
        "https://steamcommunity.com/market/myhistory/render/"
        f"?query=&start={start}&count={count}"
    )
    if appid:
        url += f"&appid={appid}"
    code, body = _http_get_auth(url, session)
    if code != 200 or not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def fetch_my_listings(session: "SteamSession", start: int = 0,
                      count: int = 100) -> dict | None:
    """JSON cru de /market/mylistings/render/."""
    url = (
        "https://steamcommunity.com/market/mylistings/render/"
        f"?query=&start={start}&count={count}"
    )
    code, body = _http_get_auth(url, session)
    if code != 200 or not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def fetch_trade_history_html(session: "SteamSession",
                             page: int = 1) -> str | None:
    """HTML cru da pagina /profiles/{id}/tradehistory."""
    if not session.steamid:
        return None
    url = (
        f"https://steamcommunity.com/profiles/{session.steamid}/tradehistory/"
        f"?l=english&p={page}"
    )
    code, body = _http_get_auth(url, session)
    if code != 200 or not body:
        return None
    return body


# ── Parsers ──────────────────────────────────────────────────────
# O Steam devolve results_html com .market_listing_row repetidos.
# Cada row tem o gain/loss indicator, nome, preco e data. Parsers usam
# regex para nao introduzir nova dependencia (bs4).

_ROW_ANCHOR_RE = re.compile(r'<div class="market_listing_row[^>]*>')
_ROW_ID_RE = re.compile(r'id="history_row_(?P<lid>[^"_]+_[^"_]+)_')
_GAINLOSS_RE = re.compile(
    r'market_listing_gainorloss(?![_a-z])[^>]*>\s*(?P<sign>[+\-\s])\s*<',
)
_NAME_RE = re.compile(
    r'market_listing_item_name(?![_a-z])[^>]*>(?P<name>[^<]+)<',
)
_PRICE_RE = re.compile(
    r'market_listing_price(?![_a-z])[^>]*>\s*(?P<price>[^<\n]+?)\s*<',
)
_DATE_RE = re.compile(
    r'market_listing_listed_date(?![_a-z])[^>]*>\s*(?P<date>[^<]+?)\s*<',
)
# Steam usa CDN community.cloudflare.steamstatic.com/economy/image/<hash>/<size>
# O `<hash>` e' base64-url-safe + dois pontos. Aceita qualquer caracter nao
# espaco/aspas. Capturamos so o hash pra montar a URL com tamanho ideal depois.
_ICON_RE = re.compile(
    r'/economy/image/(?P<hash>[^/\s"\']+)/',
)


def parse_market_history_html(results_html: str,
                              default_appid: str | None = None,
                              ) -> list[MarketEvent]:
    """Extrai eventos do results_html devolvido por myhistory/render.

    O HTML nao expoe o appid no `id` do row (so' tem historyid), entao
    `default_appid` permite ao chamador anotar o jogo de origem quando ja'
    filtrou a request (ex.: passou ?appid=730 na URL).

    Best-effort: o HTML do Steam pode mudar; em caso de regex falhar,
    retorna lista vazia (sync entao reporta zero novos).
    """
    if not results_html:
        return []
    anchors = list(_ROW_ANCHOR_RE.finditer(results_html))
    if not anchors:
        return []
    events: list[MarketEvent] = []
    for i, a in enumerate(anchors):
        anchor_text = a.group(0)
        start = a.end()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(results_html)
        body = results_html[start:end]
        name_m = _NAME_RE.search(body)
        if not name_m:
            continue
        sign_m = _GAINLOSS_RE.search(body)
        price_m = _PRICE_RE.search(body)
        date_m = _DATE_RE.search(body)
        id_m = _ROW_ID_RE.search(anchor_text)
        icon_m = _ICON_RE.search(body)
        sign = (sign_m.group("sign") if sign_m else " ").strip()
        if sign == "+":
            side = "buy"
        elif sign == "-":
            side = "sell"
        else:
            side = "listed"
        events.append(MarketEvent(
            name=_html.unescape(name_m.group("name").strip()),
            side=side,
            price=parse_brl(price_m.group("price")) if price_m else None,
            date_str=date_m.group("date").strip() if date_m else "",
            listing_id=id_m.group("lid") if id_m else None,
            appid=default_appid,
            icon_url=icon_m.group("hash") if icon_m else None,
        ))
    return events


def parse_market_history_response(response: dict,
                                  default_appid: str | None = None,
                                  ) -> list[MarketEvent]:
    """Wrapper: extrai results_html do JSON e parseia. `default_appid`
    e' propagado para anotar o jogo de origem (ver `parse_market_history_html`).
    """
    if not isinstance(response, dict):
        return []
    return parse_market_history_html(
        response.get("results_html") or "", default_appid=default_appid,
    )


_TRADE_ANCHOR_RE = re.compile(r'<div class="tradehistoryrow"[^>]*>')
_TRADE_DATE_RE = re.compile(
    r'tradehistory_date[^>]*>\s*(?P<d>[^<]+?)\s*<',
)
_TRADE_TIME_RE = re.compile(
    r'tradehistory_timestamp[^>]*>\s*(?P<t>[^<]+?)\s*<',
)
_TRADE_OFFERID_RE = re.compile(r'tradeofferid[_=]"?(?P<id>\d+)')
_TRADE_PARTNER_RE = re.compile(
    r'steamcommunity\.com/profiles/(?P<sid>\d{16,})/?',
)
_TRADE_ITEM_RE = re.compile(
    r'<span class="history_item_name"[^>]*>(?P<name>[^<]+)</span>',
)


def parse_trade_history_html(html: str) -> list[TradeEvent]:
    """Extrai trade offers aceitas do HTML de /profiles/{id}/tradehistory.

    Best-effort. A pagina divide cada trade em columns "items given"
    vs "items received"; aqui pegamos a lista plana e nao distinguimos
    lado (limitacao consciente; suficiente pra registro/auditoria).
    """
    if not html:
        return []
    anchors = list(_TRADE_ANCHOR_RE.finditer(html))
    if not anchors:
        return []
    events: list[TradeEvent] = []
    for i, a in enumerate(anchors):
        start = a.end()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html)
        body = html[start:end]
        offer_m = _TRADE_OFFERID_RE.search(body)
        partner_m = _TRADE_PARTNER_RE.search(body)
        items = [_html.unescape(im.group("name").strip())
                 for im in _TRADE_ITEM_RE.finditer(body)]
        if not offer_m and not items:
            continue
        date_m = _TRADE_DATE_RE.search(body)
        time_m = _TRADE_TIME_RE.search(body)
        date_str = ""
        if date_m:
            date_str = date_m.group("d")
            if time_m:
                date_str = f"{date_str} {time_m.group('t')}"
        events.append(TradeEvent(
            tradeofferid=offer_m.group("id") if offer_m else "",
            partner_steamid=partner_m.group("sid") if partner_m else None,
            date_str=date_str,
            items_given=items,
            items_received=[],
        ))
    return events
