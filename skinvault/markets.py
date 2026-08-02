"""Precos de mercados fora da Steam, pra comparar com o preco Steam.

POR QUE ISTO EXISTE
-------------------
Medido em 2026-07-28 sobre 732 itens: o preco da Steam e' **36% maior** que
o de mercado com dinheiro real (mediana; 94% dos itens). Isso nao e'
ineficiencia -- e' o mercado precificando que saldo Steam NAO vira dinheiro.

Consequencias, medidas nos mesmos dados:
  - comprar fora com dinheiro real e vender na Steam: +15.3% de poder de
    compra na Steam (positivo em 84% dos itens)
  - comprar na Steam e vender fora pra sacar: -35.2%

Um app Steam-only nao enxerga nada disso, e e' a informacao mais valiosa
do mercado pra quem revende.

FONTE
-----
prices.csgotrader.app publica snapshots diarios por mercado, sem chave.
Precos vem em USD -- por isso `usd_brl()`.

Sem login, sem chave, sem cookie: mantem o principio do steam_api.py.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"
_BASE = "https://prices.csgotrader.app/latest/{source}.json"

# Mercados suportados e a taxa de VENDA de cada um (fracao).
# A da Steam esta' aqui so' pra comparacao; quem cobra la' e' o proprio
# steam_api/portfolio.
# Buff163 saiu em 02/08/2026: nunca respondeu (fetch_market sempre
# ERROR, 0 itens) e a decisao de produto fechou o escopo em Steam +
# CSGOTM/Skinport -- sem novo mercado externo daqui pra frente.
MARKET_FEES = {
    "skinport": 0.12,
    "csgotm": 0.05,
}

_CACHE_PATH = DATA_DIR / "market_prices.json"
_FX_PATH = DATA_DIR / "fx_rate.json"
_TTL = 12 * 60 * 60          # snapshot da fonte e' diario; 12h basta
_FX_TTL = 24 * 60 * 60

OK = "ok"
ERROR = "error"

_FX_FALLBACK = 5.11          # USD/BRL medido em 2026-07-28


def _http_get(url: str, timeout: float = 60.0) -> "tuple[int, str | None]":
    """GET cru com gzip. (status, body). status 0 = erro de rede.

    Unica camada que toca a rede -- e' o ponto de mock nos testes.
    """
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = (resp.headers.get("Content-Encoding") or "").lower()
            if "gzip" in enc:
                raw = gzip.decompress(raw)
            elif "deflate" in enc:
                raw = zlib.decompress(raw)
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _parse_prices(payload: dict) -> dict:
    """{nome: preco_usd} a partir do payload da fonte. Logica pura.

    O formato varia por mercado: alguns trazem {"starting_at": x}, outros
    {"price": x} ou um numero direto. Aceita os tres.
    """
    out: dict = {}
    if not isinstance(payload, dict):
        return out
    for nome, val in payload.items():
        preco = None
        if isinstance(val, dict):
            for campo in ("starting_at", "price", "lowest_price",
                          "suggested_price"):
                v = val.get(campo)
                if isinstance(v, (int, float)) and v > 0:
                    preco = float(v)
                    break
        elif isinstance(val, (int, float)):
            preco = float(val)
        if preco and preco > 0:
            out[str(nome)] = preco
    return out


def fetch_market(source: str = "skinport") -> "tuple[str, dict]":
    """Baixa o snapshot de um mercado. (status, {nome: preco_usd})."""
    code, body = _http_get(_BASE.format(source=source))
    if code != 200 or not body:
        return ERROR, {}
    try:
        data = json.loads(body)
    except ValueError:
        return ERROR, {}
    precos = _parse_prices(data)
    return (OK, precos) if precos else (ERROR, {})


def usd_brl(path: "Path | str | None" = None,
            now: "float | None" = None) -> float:
    """USD/BRL com cache de 24h. Cai no ultimo valor conhecido se falhar.

    O cambio importa: derivar a razao dos proprios precos seria circular --
    e' justamente a diferenca entre mercados que se quer medir.
    """
    p = Path(path) if path else _FX_PATH
    agora = now if now is not None else time.time()
    try:
        cache = json.loads(p.read_text(encoding="utf-8"))
        if agora - float(cache.get("ts", 0)) < _FX_TTL:
            taxa = float(cache.get("rate", 0))
            if taxa > 0:
                return taxa
    except Exception:
        cache = {}
    code, body = _http_get("https://api.frankfurter.app/latest?from=USD&to=BRL",
                           timeout=20)
    taxa = None
    if code == 200 and body:
        try:
            taxa = float(json.loads(body)["rates"]["BRL"])
        except (ValueError, KeyError, TypeError):
            taxa = None
    if not taxa or taxa <= 0:
        try:
            taxa = float(cache.get("rate") or 0) or _FX_FALLBACK
        except (TypeError, ValueError):
            taxa = _FX_FALLBACK
        return taxa
    try:
        atomic_write_text(p, json.dumps({"ts": agora, "rate": taxa}))
    except OSError:
        pass
    return taxa


class MarketPriceCache:
    """Cache JSON {source: {ts, prices}}. TTL 12h."""

    def __init__(self, path: "Path | str" = _CACHE_PATH,
                 ttl: float = _TTL) -> None:
        self.path = Path(path)
        self.ttl = ttl
        self._data: dict = {}
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            atomic_write_text(self.path, json.dumps(self._data))
        except OSError:
            pass  # cache e' conveniencia; disco cheio nao derruba a tela

    def get(self, source: str, now: "float | None" = None) -> "dict | None":
        e = self._data.get(source)
        if not e:
            return None
        agora = now if now is not None else time.time()
        if agora - float(e.get("ts", 0)) > self.ttl:
            return None
        p = e.get("prices")
        return p if isinstance(p, dict) and p else None

    def put(self, source: str, prices: dict,
            now: "float | None" = None) -> None:
        if not isinstance(prices, dict) or not prices:
            return
        self._data[source] = {
            "ts": now if now is not None else time.time(),
            "prices": prices,
        }
        self._save()

    def clear(self) -> None:
        self._data = {}
        self._save()


def cached_market(source: str = "skinport",
                  cache: "MarketPriceCache | None" = None) -> dict:
    """{nome: preco_usd} do mercado, via cache. {} se falhar."""
    cache = cache or MarketPriceCache()
    hit = cache.get(source)
    if hit is not None:
        return hit
    status, precos = fetch_market(source)
    if status != OK:
        return {}
    cache.put(source, precos)
    return precos


def compare_all(name: str, steam_brl: "float | None" = None,
                sources: "list[str] | None" = None,
                fx: "float | None" = None) -> list:
    """O mesmo item em TODAS as plataformas, ordenado pelo liquido.

    Cada entrada: {source, gross_brl, net_brl, fee, premium_pct}. Fonte sem
    cotacao pro item fica de fora -- a lista diz onde da' pra vender, nao
    onde nao da'.

    O liquido e' o que importa: a taxa varia MUITO entre plataformas (5%
    na CSGOTM contra 12% no Skinport), entao o maior preco bruto nem
    sempre e' o melhor negocio.
    """
    fx = usd_brl() if fx is None else fx
    if fx <= 0:
        return []
    out = []
    for fonte in (sources or list(MARKET_FEES)):
        precos = cached_market(fonte)
        usd = precos.get(name)
        if not usd or usd <= 0:
            continue
        taxa = MARKET_FEES.get(fonte, 0.12)
        bruto = usd * fx
        liquido = bruto * (1 - taxa)
        item = {
            "source": fonte,
            "gross_brl": round(bruto, 2),
            "net_brl": round(liquido, 2),
            "fee": taxa,
            "premium_pct": None,
        }
        if steam_brl and steam_brl > 0:
            item["premium_pct"] = round((steam_brl / bruto - 1) * 100, 1)
        out.append(item)
    out.sort(key=lambda x: -x["net_brl"])
    return out


def best_market(name: str, steam_brl: "float | None" = None,
                sources: "list[str] | None" = None,
                fx: "float | None" = None) -> "dict | None":
    """A plataforma que paga mais LIQUIDO por este item. None se nenhuma."""
    todas = compare_all(name, steam_brl, sources, fx)
    return todas[0] if todas else None


def compare(steam_brl: "float | None", market_usd: "float | None",
            fx: float, source: str = "skinport",
            steam_fee: float = 0.15) -> dict:
    """Compara o mesmo item nos dois lados. Tudo em BRL.

    Retorna:
      steam_net    -- saldo Steam recebido vendendo la'
      market_net   -- dinheiro REAL recebido vendendo fora
      premium_pct  -- quanto a Steam pede a mais (o tal dos 36%)
      to_wallet_pct-- ganho de poder de compra comprando fora e vendendo
                      na Steam
      to_cash_pct  -- resultado comprando na Steam e vendendo fora

    steam_net e market_net NAO sao comparaveis como se fossem a mesma
    coisa: um e' saldo travado, o outro e' dinheiro. Quem exibe tem que
    deixar isso claro.
    """
    out = {"steam_net": None, "market_net": None, "premium_pct": None,
           "to_wallet_pct": None, "to_cash_pct": None, "source": source}

    # Os dois lados sao INDEPENDENTES. Ate' 2026-07-30 a funcao desistia
    # inteira quando faltava o preco da Steam, e com isso escondia a
    # cotacao do mercado externo -- que ja' estava em cache e nao depende
    # da Steam pra nada. Com o priceoverview em 429, o inventario mostrava
    # "sem cotacao" em 30 itens que TINHAM cotacao.
    tem_steam = bool(steam_brl) and steam_brl > 0
    tem_mercado = bool(market_usd) and market_usd > 0 and fx > 0

    if tem_steam:
        out["steam_net"] = round(steam_brl * (1 - steam_fee), 2)

    fee = MARKET_FEES.get(source, 0.12)
    if tem_mercado:
        mercado_brl = market_usd * fx
        out["market_net"] = round(mercado_brl * (1 - fee), 2)

    # So' as metricas COMPARATIVAS precisam dos dois lados.
    if tem_steam and tem_mercado:
        out["premium_pct"] = round((steam_brl / mercado_brl - 1) * 100, 1)
        out["to_wallet_pct"] = round(
            (steam_brl * (1 - steam_fee) / mercado_brl - 1) * 100, 1)
        out["to_cash_pct"] = round(
            (mercado_brl * (1 - fee) / steam_brl - 1) * 100, 1)
    return out
