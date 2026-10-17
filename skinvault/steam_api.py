"""Acesso a dados PUBLICOS do Steam -- somente leitura, sem login.

Principio de design (o diferencial do produto): este modulo NUNCA recebe
senha, cookie de sessao ou API key privada. Le' so' o que ja' e' publico:

- Inventario publico (CS2 = appid 730, contextid 2):
    https://steamcommunity.com/inventory/{steamid}/730/2?l=english&count=75
    (paginado via start_assetid -- ver _collect_inventory)
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
import time
import urllib.error
import urllib.parse
import urllib.request

_APP_CS2 = 730
_CONTEXT = 2
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"

# Espaco minimo entre chamadas ao Market (priceoverview/listagem/inventario).
# 2026-08-07: pesquisado apos um scan de "Todas as categorias" estourar 429.
# Fontes (comunidade Steam + ArchiSteamFarm, ver memoria do projeto):
# limite citado de ~20 req/min no endpoint de inventario/mercado, e o
# ArchiSteamFarm recomenda ~1 req/4s como margem segura. Os throttles
# espalhados pelo projeto usavam 1.0-2.0s (30-60 req/min) -- ACIMA do
# limite. 429 e' bloqueio temporario (ate' ~6h em casos relatados), NUNCA
# ban de conta -- a Valve nao usa ban por IP, so' por conta, e reservado
# pra fraude/trapaca, nao trafego de leitura publica.
RATE_LIMIT_DELAY_S = 4.0

# Itens por pagina do endpoint /inventory/ (o Steam recusa valores maiores).
_INV_PAGE = 75
# Trava do loop de paginacao: 75 * 40 = 3000 itens. Evita loop infinito se o
# Steam (ou um mock) devolver more_items=true pra sempre.
_INV_MAX_PAGES = 40

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
            name, {"name": name, "quantity": 0,
                   "tradable": bool(d.get("tradable")),
                   # icon_url e' o hash do CDN; icons.py resolve pro arquivo
                   # local. Sem ele a grade do inventario fica sem imagem e
                   # deixa de parecer com a Steam.
                   "icon": d.get("icon_url") or None,
                   "type": d.get("type") or None}
        )
        entry["quantity"] += int(asset.get("amount", 1))
        if not entry.get("icon") and d.get("icon_url"):
            entry["icon"] = d["icon_url"]
    return list(counts.values())


def _inventory_url(steam_id: str, start_assetid: str | None = None) -> str:
    """URL de uma pagina do inventario, com cache-buster obrigatorio.

    O endpoint /inventory/ e' servido por CDN e devolve snapshot ANTIGO sem
    sinalizar nada -- inclusive com total_inventory_count desatualizado junto,
    o que faz o dado velho parecer coerente. Medido num caso real: 27 itens
    retornados pra um inventario de 66. O `_` unico por chamada e' o que forca
    o edge a buscar na origem; header no-cache sozinho nao resolve.
    """
    params = {
        "l": "english",
        "count": str(_INV_PAGE),
        "_": str(int(time.time() * 1000)),
    }
    if start_assetid:
        params["start_assetid"] = str(start_assetid)
    return (
        f"https://steamcommunity.com/inventory/{steam_id}/{_APP_CS2}/{_CONTEXT}"
        f"?{urllib.parse.urlencode(params)}"
    )


def _collect_inventory(get_page) -> tuple[str, list[dict]]:
    """Pagina o inventario ate o fim e agrega. `get_page(start)` -> (code, body).

    Sem paginacao o Steam devolve so' a primeira pagina (75 itens) e nao avisa:
    inventario grande vinha truncado em silencio. A parada e' `more_items`.

    Retorna (status, items) com os mesmos codigos de fetch_inventory.
    """
    assets: list[dict] = []
    descriptions: list[dict] = []
    start: str | None = None
    for _ in range(_INV_MAX_PAGES):
        code, body = get_page(start)
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
        if not data:
            return INV_EMPTY, []
        assets.extend(data.get("assets") or [])
        descriptions.extend(data.get("descriptions") or [])
        if not data.get("more_items"):
            break
        start = data.get("last_assetid")
        if not start:
            break  # more_items sem cursor: nao da' pra avancar, para aqui
    if not assets or not descriptions:
        return INV_EMPTY, []
    items = _parse_items({"assets": assets, "descriptions": descriptions})
    return (INV_OK, items) if items else (INV_EMPTY, [])


def fetch_inventory(steam_id: str) -> tuple[str, list[dict]]:
    """Le o inventario publico e DIZ por que falhou, se falhar.

    Retorna (status, items). status em {ok, private, rate_limited, empty, error}.
    items so' vem preenchido quando status == 'ok'.
    """
    return _collect_inventory(
        lambda start: _http_get(_inventory_url(steam_id, start))
    )


def fetch_public_inventory(steam_id: str) -> list[dict]:
    """Wrapper simples: so' os itens (lista vazia em qualquer falha)."""
    return fetch_inventory(steam_id)[1]


# ── Link do perfil -> SteamID64 (publico, sem login nem chave de API) ──
RESOLVE_OK = "ok"
RESOLVE_INVALID = "invalid"        # o texto nao parece perfil nenhum
RESOLVE_NOT_FOUND = "not_found"    # apelido nao existe
RESOLVE_RATE_LIMITED = "rate_limited"
RESOLVE_ERROR = "error"

_STEAMID64_RE = re.compile(r"^7656119\d{10}$")
_PERFIL_ID64_RE = re.compile(r"steamcommunity\.com/profiles/(7656119\d{10})")
_PERFIL_APELIDO_RE = re.compile(r"steamcommunity\.com/id/([A-Za-z0-9_-]{2,32})")
_APELIDO_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


def parse_profile_input(texto: str | None) -> tuple[str, str]:
    """O que o usuario colou -> ("id64", id) | ("vanity", apelido) |
    ("invalid", ""). Logica pura.

    Aceita: SteamID64, link /profiles/<id>, link /id/<apelido> e o
    apelido sozinho (o que aparece no fim do link personalizado).
    """
    s = (texto or "").strip()
    if not s:
        return "invalid", ""
    if _STEAMID64_RE.match(s):
        return "id64", s
    m = _PERFIL_ID64_RE.search(s)
    if m:
        return "id64", m.group(1)
    m = _PERFIL_APELIDO_RE.search(s)
    if m:
        return "vanity", m.group(1)
    if "/" not in s and _APELIDO_RE.match(s):
        return "vanity", s
    return "invalid", ""


def resolve_steam_id(texto: str | None) -> tuple[str, str | None]:
    """Link/apelido/ID -> (status, steamid64).

    Apelido (link personalizado, /id/<apelido>) e' resolvido pela pagina
    XML publica do perfil (?xml=1) -- a mesma que o profile_fetcher usa pra
    avatar. Nao precisa de login nem de chave da Web API.
    """
    tipo, valor = parse_profile_input(texto)
    if tipo == "id64":
        return RESOLVE_OK, valor
    if tipo != "vanity":
        return RESOLVE_INVALID, None
    url = ("https://steamcommunity.com/id/"
           f"{urllib.parse.quote(valor)}/?xml=1")
    code, body = _http_get(url)
    if code == 429:
        return RESOLVE_RATE_LIMITED, None
    if code != 200 or body is None:
        return RESOLVE_ERROR, None
    m = re.search(r"<steamID64>\s*(7656119\d{10})\s*</steamID64>", body)
    if m:
        return RESOLVE_OK, m.group(1)
    return RESOLVE_NOT_FOUND, None


PRICE_OK = "ok"                     # a Steam respondeu com preco
PRICE_NO_PRICE = "no_price"         # a Steam respondeu: este item nao tem preco
PRICE_RATE_LIMITED = "rate_limited"  # 429 -- nao diz nada sobre o item
PRICE_ERROR = "error"               # rede/HTTP/parse -- tambem nao diz nada

# Só estes dois são fato sobre o item; os outros dois são estado da rede.
PRICE_CACHEABLE = (PRICE_OK, PRICE_NO_PRICE)


def get_market_price_status(market_hash_name: str,
                            currency: int = 7) -> "tuple[str, float | None]":
    """(status, preco) do priceoverview.

    Existe porque `get_market_price` devolve None em quatro situacoes bem
    diferentes, e todas pediam tratamento distinto:

    - `ok` / `no_price`: a Steam respondeu. É fato sobre o item, pode ir
      pro cache.
    - `rate_limited`: 429. Não diz nada sobre o item -- cachear isso como
      "sem preço" envenena o cache por 1h (o TTL negativo) e o item some da
      tela mesmo depois de a Steam liberar.
    - `error`: rede, HTTP ou JSON quebrado. Mesma coisa.
    """
    url = (
        "https://steamcommunity.com/market/priceoverview/"
        f"?appid={_APP_CS2}&currency={currency}"
        f"&market_hash_name={urllib.parse.quote(market_hash_name)}"
    )
    code, body = _http_get(url)
    if code == 429:
        return PRICE_RATE_LIMITED, None
    if code != 200 or body is None:
        return PRICE_ERROR, None
    try:
        data = json.loads(body)
    except ValueError:
        return PRICE_ERROR, None
    if not data or not data.get("success"):
        # Resposta valida dizendo que nao ha' item/preco: fato sobre o item.
        return PRICE_NO_PRICE, None
    preco = parse_brl(data.get("lowest_price") or data.get("median_price"))
    return (PRICE_OK, preco) if preco is not None else (PRICE_NO_PRICE, None)


def get_market_price(market_hash_name: str, currency: int = 7) -> float | None:
    """Preco mais baixo atual no Steam Market, em BRL (currency=7). None se
    indisponivel. O Steam limita ~20 req/min -- producao precisa de cache+backoff.

    Wrapper retrocompatível de `get_market_price_status`."""
    return get_market_price_status(market_hash_name, currency)[1]


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


# ── Busca no Market: camada de DESCOBERTA ──────────────────────────
#
# priceoverview responde "quanto vale ESTE item" -- exige saber o nome antes.
# A busca responde "quais itens existem com estas caracteristicas", que e' o
# que permite achar candidato novo em vez de reescanear lista fixa.
#
# Ela NAO substitui priceoverview nem o parse SSR: devolve preco mais baixo e
# numero de anuncios (oferta), mas nao devolve volume de 24h nem mediana.
# O uso certo e' em dois estagios -- busca afunila, scanner aprofunda.

SEARCH_OK = "ok"
SEARCH_RATE_LIMITED = "rate_limited"
SEARCH_ERROR = "error"

# Nome legivel -> chave de URL da faceta (confirmado em /market/appfilters/730).
#
# CUIDADO com o par invertido: a faceta que a Steam ROTULA "Category"
# (Normal/StatTrak/Souvenir) vai em category_730_Quality, e a rotulada
# "Quality" (raridade: Consumer/Mil-Spec/Covert) vai em category_730_Rarity.
# Trocar as duas nao gera erro -- devolve resultado errado em silencio.
MARKET_FACETS = {
    "type": "Type",                        # Rifle, Knife, Container, Charm...
    "exterior": "Exterior",                # WearCategory0..4, NA
    "category": "Quality",                 # normal, strange (ST), tournament
    "rarity": "Rarity",                    # Rarity_Common_Weapon, ...
    "collection": "ItemSet",
    "weapon": "Weapon",                    # weapon_ak47, weapon_mp9...
    "tournament": "Tournament",
    "team": "TournamentTeam",
    "pro_player": "ProPlayer",
    "sticker_collection": "StickerCapsule",
    "sticker_type": "StickerCategory",
    "patch_collection": "PatchCapsule",
    "patch_type": "PatchCategory",
    "charm_collection": "KeychainCapsule",
    "graffiti_collection": "SprayCapsule",
    "graffiti_type": "SprayCategory",
    "graffiti_color": "SprayColorCategory",
}

_SORT_COLUMNS = ("quantity", "price", "name", "default")
# A Steam ignora count menor que o dela e devolve o proprio tamanho de pagina;
# por isso a paginacao avanca por len(resultados), nunca pelo count pedido.
_SEARCH_MAX_PAGES = 40


def _search_url(query: str, facets: dict | None, sort: str, descending: bool,
                start: int, count: int, currency: int) -> str:
    """Monta a URL de /market/search/render/ com as facetas pedidas.

    `facets` usa as chaves legiveis de MARKET_FACETS; o valor pode ser uma tag
    ou uma lista de tags. O prefixo `tag_` e' adicionado quando faltar -- o
    appfilters devolve as tags sem ele, mas a URL exige.
    """
    params: list[tuple[str, str]] = [
        ("appid", str(_APP_CS2)),
        ("norender", "1"),
        ("currency", str(currency)),
        ("start", str(max(0, int(start)))),
        ("count", str(max(1, int(count)))),
        ("sort_column", sort if sort in _SORT_COLUMNS else "quantity"),
        ("sort_dir", "desc" if descending else "asc"),
    ]
    if query:
        params.append(("query", query))
    for key, value in (facets or {}).items():
        facet = MARKET_FACETS.get(key)
        if not facet:
            continue
        tags = value if isinstance(value, (list, tuple, set)) else [value]
        for tag in tags:
            if not tag:
                continue
            tag = str(tag)
            if not tag.startswith("tag_"):
                tag = "tag_" + tag
            params.append((f"category_730_{facet}[]", tag))
    return (
        "https://steamcommunity.com/market/search/render/?"
        + urllib.parse.urlencode(params)
    )


def _parse_search_results(data: dict) -> list[dict]:
    """results[] -> [{name, hash_name, price, listings}]. Logica pura."""
    out: list[dict] = []
    for r in data.get("results") or []:
        hash_name = r.get("hash_name") or r.get("name")
        if not hash_name:
            continue
        price = None
        raw = r.get("sell_price")
        if isinstance(raw, (int, float)) and raw > 0:
            price = float(raw) / 100.0  # vem em centavos da moeda pedida
        if price is None:
            price = parse_brl(r.get("sell_price_text"))
        try:
            listings = int(r.get("sell_listings") or 0)
        except (TypeError, ValueError):
            listings = 0
        out.append({
            "name": r.get("name") or hash_name,
            "hash_name": hash_name,
            "price": price,
            "listings": listings,
        })
    return out


def search_market(query: str = "", facets: dict | None = None,
                  sort: str = "quantity", descending: bool = True,
                  start: int = 0, count: int = 100,
                  currency: int = 7) -> tuple[str, list[dict], int]:
    """Busca itens no Market por faceta. Retorna (status, items, total).

    status em {ok, rate_limited, error}. `total` e' quantos itens existem no
    filtro inteiro, nao quantos vieram -- serve pra dimensionar a paginacao.

    Ex.: todos os rifles Field-Tested, do mais liquido pro menos:
        search_market(facets={"type": "CSGO_Type_Rifle",
                              "exterior": "WearCategory2"})
    """
    url = _search_url(query, facets, sort, descending, start, count, currency)
    code, body = _http_get(url)
    if code == 429:
        return SEARCH_RATE_LIMITED, [], 0
    if code != 200 or body is None:
        return SEARCH_ERROR, [], 0
    try:
        data = json.loads(body)
    except ValueError:
        return SEARCH_ERROR, [], 0
    if not data or not data.get("success"):
        return SEARCH_ERROR, [], 0
    try:
        total = int(data.get("total_count") or 0)
    except (TypeError, ValueError):
        total = 0
    return SEARCH_OK, _parse_search_results(data), total


def search_market_all(query: str = "", facets: dict | None = None,
                      sort: str = "quantity", descending: bool = True,
                      max_items: int = 500,
                      currency: int = 7) -> tuple[str, list[dict], int]:
    """Pagina search_market ate max_items. Retorna (status, items, total).

    Para em: pagina vazia, max_items atingido, total alcancado ou teto de
    paginas. Rate limit no meio devolve o que ja' juntou com status
    rate_limited -- resultado parcial e' util, silencio nao e'.
    """
    items: list[dict] = []
    total = 0
    start = 0
    for _ in range(_SEARCH_MAX_PAGES):
        status, page, page_total = search_market(
            query=query, facets=facets, sort=sort, descending=descending,
            start=start, count=100, currency=currency,
        )
        if status != SEARCH_OK:
            return (status, items, total) if items else (status, [], 0)
        total = page_total or total
        if not page:
            break
        items.extend(page)
        start += len(page)  # nunca `count`: a Steam clampa o tamanho da pagina
        if len(items) >= max_items or start >= total:
            break
    return SEARCH_OK, items[:max_items], total


def _js_unescape(s: str) -> str:
    # fmt: off
    """Unescape uma JavaScript string literal (entre as aspas externas).

    Trata escapes conhecidos do SSR do Steam: backslash, aspas, n, r, t,
    uXXXX (unicode), xNN (hex), 0 (null).
    Se encontrar backslash seguido de algo nao reconhecido, preserva literalmente.
    """
    # fmt: on
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
            elif nxt == "u" and i + 5 < len(s):
                try:
                    result.append(chr(int(s[i + 2 : i + 6], 16)))
                except ValueError:
                    result.append(s[i : i + 6])
                i += 5
            elif nxt == "x" and i + 3 < len(s):
                try:
                    result.append(chr(int(s[i + 2 : i + 4], 16)))
                except ValueError:
                    result.append(s[i : i + 4])
                i += 3
            elif nxt == "0":
                result.append("\0")
                i += 1
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

    Com `item_name`, confere o nome na posicao 3 do queryKey. A ordem de
    preferencia e' explicita e NAO e' a ordem de iteracao do SSR:

      1. igualdade exata do nome
      2. substring (compatibilidade: aceita nome parcial do chamador)
      3. skin root, apenas com loose_match=True
      4. queryKey sem slot de nome

    O exato tem que vir primeiro porque "Souvenir X" e "StatTrak(TM) X"
    CONTEM "X". Uma pagina de listagem traz ate 10 variantes do mesmo skin,
    e pegar a primeira que casasse por substring devolvia a serie da
    variante errada em silencio -- medido em 2026-07-28: pedindo
    "AK-47 | Redline (Field-Tested)" vinha a Souvenir com 1 ponto de
    historico, enquanto a correta estava na mesma resposta com 5188.

    `loose_match`: aceita match pelo "skin root" (sem wear/StatTrak/etc).
    Util pra orderbook, que a Steam pre-carrega para apenas um wear do
    skin (ex.: pedi Field-Tested mas SSR so' tem Minimal Wear cached).
    """
    if item_name is None:
        for q in queries:
            qk = q.get("queryKey", [])
            if isinstance(qk, list) and key in qk:
                return q.get("state", {}).get("data")
        return None

    target = item_name.lower()
    target_root = _skin_root_name(item_name) if loose_match else None
    # Candidatos por tier -- a escolha NAO pode depender da ordem do SSR.
    exato = subst = raiz = sem_nome = None

    for q in queries:
        qk = q.get("queryKey", [])
        if not isinstance(qk, list) or key not in qk:
            continue
        if len(qk) <= 3:
            # queryKey sem slot de nome: so' serve se nada melhor aparecer.
            if sem_nome is None:
                sem_nome = q
            continue
        # queryKey = ["market", key, 730, "Item Name"]
        cached_name = str(qk[3])
        low = cached_name.lower()
        if low == target:
            exato = q
            break  # nao existe match melhor que o exato
        if subst is None and target in low:
            subst = q
        if (raiz is None and target_root
                and target_root == _skin_root_name(cached_name)):
            raiz = q

    for candidato in (exato, subst, raiz, sem_nome):
        if candidato is not None:
            return candidato.get("state", {}).get("data")
    return None


def _normalize_facets(raw: dict) -> dict:
    """{key: {label, tags: {tag: label}}} a partir do payload cru da Steam.

    Aceita tanto o formato do SSR (`app_facets`) quanto o de
    /market/appfilters/730 -- sao a mesma estrutura:
      {"Rarity": {"appid":730, "name":"Rarity",
                  "localized_name":"Quality", "tags": {...}}}

    `name` e' a chave que vai na URL (category_730_<name>[]); guardamos ela
    como chave do dict porque e' o que importa pra montar filtro. O
    localized_name e' so' rotulo de UI -- e nao bate com a chave: a faceta
    de chave "Rarity" se chama "Quality" na tela, e vice-versa.
    """
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        key = entry.get("name")
        if not key:
            continue
        tags_raw = entry.get("tags")
        tags: dict = {}
        if isinstance(tags_raw, dict):
            for tag, meta in tags_raw.items():
                if isinstance(meta, dict):
                    tags[str(tag)] = meta.get("localized_name") or str(tag)
                else:
                    tags[str(tag)] = str(tag)
        out[str(key)] = {
            "label": entry.get("localized_name") or str(key),
            "tags": tags,
        }
    return out


def _collect_facets(queries: list) -> dict:
    """Catalogo de facetas que ja' vem embutido na listing page.

    As 17 facetas (Type, Rarity, ItemSet, ProPlayer...) chegam de gracas em
    qualquer pagina de listagem. Os valores mudam sozinhos quando a Valve
    lanca colecao ou torneio novo -- ler daqui evita lista hardcoded que
    envelhece em silencio.
    """
    for q in queries:
        qk = q.get("queryKey")
        if isinstance(qk, list) and "app_facets" in qk:
            return _normalize_facets((q.get("state") or {}).get("data"))
    return {}


def fetch_market_facets(appid: int = _APP_CS2) -> dict:
    """Catalogo de facetas pelo endpoint dedicado. {} em qualquer falha.

    Alternativa a _collect_facets pra quando nao se quer baixar uma listing
    page inteira (4-5 MB) so' pra atualizar o catalogo.
    """
    data = _get_json(
        f"https://steamcommunity.com/market/appfilters/{appid}")
    if not data or not data.get("success"):
        return {}
    return _normalize_facets(data.get("facets"))


# Categoria da tag (minuscula) -> (campo_label, campo_id) no meta do item.
# "Type" vira item_type pra nao colidir com o campo `type` da description,
# que e' outra coisa ("Classified Rifle" vs "Rifle").
_TAG_FIELDS = {
    "itemset": ("collection", "collection_id"),
    "rarity": ("rarity", "rarity_id"),
    "exterior": ("exterior", "exterior_id"),
    "weapon": ("weapon", "weapon_id"),
    "quality": ("quality", "quality_id"),
    "type": ("item_type", "item_type_id"),
}


def _parse_item_meta(desc: dict) -> dict:
    """Metadados oficiais de um item a partir do payload `description`.

    As tags sao a classificacao da PROPRIA Steam -- colecao, raridade,
    exterior, arma. Nada disso precisa de requisicao extra: ja' vem em
    qualquer listing page, uma description por variante.

    Campos que importam alem das tags:
      commodity -- item fungivel (caixa: unidades identicas, order book de
        verdade) vs unico (skin com float/pattern, cada anuncio e' um item).
        Verificado em 2026-07-28: Kilowatt Case=True, AK Redline FT=False.
      market_tradable_restriction -- dias de bloqueio apos a compra (7 no
        CS2). Qualquer "flip" carrega essa exposicao obrigatoria.
    """
    if not isinstance(desc, dict):
        return {}
    meta: dict = {
        "type_label": desc.get("type"),
        "commodity": bool(desc.get("commodity")),
        "name_color": desc.get("name_color"),
    }
    for origem, destino in (
        ("market_tradable_restriction", "tradable_restriction"),
        ("market_marketable_restriction", "marketable_restriction"),
    ):
        try:
            valor = desc.get(origem)
            meta[destino] = int(valor) if valor is not None else None
        except (TypeError, ValueError):
            meta[destino] = None
    for tag in desc.get("tags") or []:
        if not isinstance(tag, dict):
            continue
        campos = _TAG_FIELDS.get(str(tag.get("category", "")).lower())
        if not campos:
            continue
        label, ident = campos
        meta[label] = tag.get("localized_tag_name")
        meta[ident] = tag.get("internal_name")
    return meta


def _collect_item_meta(queries: list) -> dict:
    """{market_hash_name: meta} pra todas as descriptions da pagina."""
    out: dict = {}
    for q in queries:
        qk = q.get("queryKey", [])
        if (not isinstance(qk, list) or "description" not in qk
                or len(qk) <= 3):
            continue
        meta = _parse_item_meta((q.get("state") or {}).get("data"))
        if meta:
            out[str(qk[3])] = meta
    return out


def _collect_variants(queries: list) -> dict:
    """price_history de TODAS as variantes presentes na pagina. Logica pura.

    Uma listing page traz o SSR de ate ~10 itens irmaos do mesmo skin: cada
    wear x Normal/StatTrak/Souvenir. Medido em 2026-07-28 na pagina da
    AK-47 | Redline: 10 series, ~36.500 pontos, numa unica requisicao.

    Pegar uma e descartar nove multiplica por 10 o custo de rede -- e a
    Steam limita agressivamente esses endpoints. Quem chama pode semear o
    cache com o lote inteiro e transformar os 9 proximos scans em cache hit.

    Series vazias sao omitidas: nao adicionam informacao e, cacheadas,
    esconderiam dado real que aparecesse depois.
    """
    out: dict = {}
    for q in queries:
        qk = q.get("queryKey", [])
        if (not isinstance(qk, list) or "pricehistory" not in qk
                or len(qk) <= 3):
            continue
        data = (q.get("state") or {}).get("data")
        prices = data.get("prices") if isinstance(data, dict) else data
        if isinstance(prices, list) and prices:
            out[str(qk[3])] = prices
    return out


def get_market_page_data(
    market_hash_name: str,
) -> dict | None:
    """Busca dados SSR da pagina de listagem do Steam Market.

    Retorna um dict com:
      - price_history: list[dict] -- {time, price_median, purchases}
      - variants: dict -- {market_hash_name: price_history} de TODAS as
        variantes que vieram na mesma pagina (ate ~10 irmas do skin).
        Serve pra semear cache e evitar 1 requisicao por wear.
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
    variants = _collect_variants(queries)
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

    if variants:
        result["variants"] = variants

    facets = _collect_facets(queries)
    if facets:
        result["facets"] = facets

    items_meta = _collect_item_meta(queries)
    if items_meta:
        result["items_meta"] = items_meta
        meta = items_meta.get(market_hash_name)
        if meta:
            result["meta"] = meta

    if order_data and isinstance(order_data, dict):
        result["order_book_approx"] = order_approx
        # `commodity` NAO e' sinonimo de order_book_approx e nao deve
        # sobrescreve-lo. approx = o book veio de outro wear. commodity =
        # o lado da VENDA e' heterogeneo (cada anuncio tem float/pattern
        # proprio), enquanto o lado da COMPRA continua sendo book real.
        # Conflatar os dois perderia informacao; sao eixos diferentes.
        result["order_book_commodity"] = bool(
            (result.get("meta") or {}).get("commodity"))
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
    tradable_restriction: int | None = None,
) -> dict:
    """Compara lowest vs mediana e da' o veredito honesto.

    Parametros opcionais (do order book + price history):
      spread: best_ask - best_bid (em centavos)
      buy_count: numero de ordens de compra
      sell_count: numero de ordens de venda
      price_history: lista de {time, price_median, purchases}
      tradable_restriction: dias de bloqueio apos a compra (7 no CS2)

    Sobre o bloqueio: comprar e revender NAO e' operacao instantanea. O
    item fica travado por `tradable_restriction` dias, entao todo "flip"
    carrega exposicao obrigatoria a preco nesse periodo. Isso e' reportado
    como fato (`hold_days` + linha na mensagem) e NAO altera o score --
    quanto isso pesa depende da volatilidade do item e de quem le'.

    Retorna {diff_pct, verdict, label, message} + quando dados extras:
      {spread_pct, spread_verdict, book_ratio, book_verdict,
       trend_pct, trend_verdict, details, hold_days}
    """
    if lowest is None or median is None or median == 0:
        return {"diff_pct": None, "verdict": "unknown",
                "label": "sem dados",
                "message": "Dados insuficientes para comparar."}

    diff_pct = ((lowest - median) / median) * 100
    if diff_pct <= -5:
        verdict = "below_median"
        label = "abaixo do típico"
        msg = (f"Anúncio mais barato {abs(diff_pct):.0f}% abaixo do preço "
               "típico. Bom negócio.")
    elif diff_pct <= 5:
        verdict = "fair"
        label = "no preço típico"
        msg = "Preço a até 5% do preço típico. Justo."
    elif diff_pct <= 20:
        verdict = "slightly_above"
        label = "levemente acima"
        msg = f"Anúncio {diff_pct:.0f}% acima do preço típico. Um pouco caro."
    else:
        verdict = "overpriced"
        label = "muito acima"
        msg = f"Anúncio {diff_pct:.0f}% acima do preço típico. Caro demais."

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
            msg_parts.append("Muita gente querendo comprar.")
        if extra.get("trend_verdict") == "falling":
            msg_parts.append("Preço caindo nos últimos dias.")
        elif extra.get("trend_verdict") == "rising":
            msg_parts.append("Preço subindo nos últimos dias.")
        result["message"] = " ".join(msg_parts)

    # Bloqueio pos-compra: fato, nao ajuste de score.
    try:
        dias = int(tradable_restriction) if tradable_restriction else 0
    except (TypeError, ValueError):
        dias = 0
    if dias > 0:
        result["hold_days"] = dias
        result["message"] = (
            f"{result['message']} Só dá para revender depois de {dias} "
            "dias de bloqueio."
        ).strip()

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
            details["spread"] = ("Diferença compra/venda pequena — fácil "
                                "de vender.")
        elif spread_pct <= 10:
            extra["spread_verdict"] = "normal"
        else:
            extra["spread_verdict"] = "wide"
            details["spread"] = (f"Diferença compra/venda grande "
                                f"({spread_pct:.0f}%) — difícil vender "
                                "sem perder.")

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

