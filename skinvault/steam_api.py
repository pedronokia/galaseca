"""Acesso a dados PUBLICOS do Steam -- somente leitura, sem login.

Principio de design (o diferencial do produto): este modulo NUNCA recebe
senha, cookie de sessao ou API key privada. Le' so' o que ja' e' publico:

- Inventario publico (CS2 = appid 730, contextid 2):
    https://steamcommunity.com/inventory/{steamid}/730/2?l=english&count=5000
- Preco publico no Market (currency=7 = BRL):
    https://steamcommunity.com/market/priceoverview/?appid=730&currency=7&market_hash_name={name}

Sem login => nao da' pra roubar item, nao da' pra dar ban. Informa, nao age.

Implementado com urllib (stdlib): o "momento magico" roda sem pip install.
"""
from __future__ import annotations

import json
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
