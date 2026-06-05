"""Pareamento BUY <-> SELL de eventos do Steam Market.

Sintetiza trades fechados a partir dos eventos brutos sincronizados
(`data/steam_market_events.json`): agrupa por nome do item, ordena por
data e casa FIFO (compra mais antiga com venda mais antiga). Calcula
P&L liquido descontando a taxa Steam de 15%.

Modulo puro: parsing + matching, sem IO direto (apenas o helper
`load_closed_trades` carrega via `sync`). Testavel sem rede.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from skinvault import portfolio, sync


_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def parse_steam_date(date_str: str, now: float | None = None) -> float | None:
    """Converte string do Steam ("15 Mar", "15 Mar, 2024", "15 Mar 18:30")
    em timestamp Unix. Ano implicito assume ano corrente; se a data cair
    no futuro (>1 dia), recua 1 ano (Steam omite ano para o ano atual).
    Devolve None quando nao consegue parsear.
    """
    if not date_str:
        return None
    now_ts = now if now is not None else time.time()
    cur_year = time.localtime(now_ts).tm_year

    parts = date_str.replace(",", " ").split()
    if len(parts) < 2:
        return None
    try:
        day = int(parts[0])
    except ValueError:
        return None
    month = _MONTHS.get(parts[1][:3].capitalize())
    if month is None:
        return None

    year = cur_year
    explicit_year = False
    hh = 0
    mm = 0
    for p in parts[2:]:
        if p.isdigit() and len(p) == 4:
            year = int(p)
            explicit_year = True
        elif ":" in p:
            try:
                h, m = p.split(":")
                hh, mm = int(h), int(m)
            except ValueError:
                pass

    try:
        ts = time.mktime((year, month, day, hh, mm, 0, 0, 0, -1))
    except (ValueError, OverflowError):
        return None

    if not explicit_year and ts > now_ts + 86400:
        try:
            ts = time.mktime((year - 1, month, day, hh, mm, 0, 0, 0, -1))
        except (ValueError, OverflowError):
            return None
    return ts


@dataclass
class ClosedTrade:
    name: str
    buy_date: str
    buy_price: float
    sell_date: str
    sell_price: float
    sell_ts: float
    pnl: float
    pnl_pct: float


@dataclass
class OpenBuy:
    """Compra registrada no Steam Market que ainda nao foi pareada
    com uma venda subsequente."""
    name: str
    buy_date: str
    buy_price: float
    buy_ts: float


def _group_by_name(events: list[dict],
                   now: float | None = None) -> dict[str, dict[str, list]]:
    by_name: dict[str, dict[str, list]] = {}
    for ev in events:
        name = ev.get("name")
        side = (ev.get("side") or "").lower()
        price = ev.get("price")
        if not name or price is None or side not in ("buy", "sell"):
            continue
        bucket = by_name.setdefault(name, {"buy": [], "sell": []})
        ts = parse_steam_date(ev.get("date_str", ""), now=now) or 0.0
        bucket[side].append({
            "price": float(price),
            "ts": ts,
            "date_str": ev.get("date_str", ""),
        })
    return by_name


def _pair_and_split(events: list[dict], now: float | None = None,
                    ) -> tuple[list[ClosedTrade], list[OpenBuy]]:
    """Roda o pareamento FIFO e devolve trades fechados + buys abertos."""
    by_name = _group_by_name(events, now=now)
    closed: list[ClosedTrade] = []
    opens: list[OpenBuy] = []
    for name, sides in by_name.items():
        buys = sorted(sides["buy"], key=lambda e: e["ts"])
        sells = sorted(sides["sell"], key=lambda e: e["ts"])
        bi = si = 0
        while bi < len(buys) and si < len(sells):
            b, s = buys[bi], sells[si]
            if b["ts"] and s["ts"] and s["ts"] < b["ts"]:
                si += 1
                continue
            d = portfolio.position_pnl(b["price"], s["price"], 1)
            closed.append(ClosedTrade(
                name=name,
                buy_date=b["date_str"],
                buy_price=b["price"],
                sell_date=s["date_str"],
                sell_price=s["price"],
                sell_ts=s["ts"],
                pnl=d["pnl"],
                pnl_pct=d["pnl_pct"],
            ))
            bi += 1
            si += 1
        for b in buys[bi:]:
            opens.append(OpenBuy(
                name=name,
                buy_date=b["date_str"],
                buy_price=b["price"],
                buy_ts=b["ts"],
            ))
    return closed, opens


def match_events(events: list[dict],
                 now: float | None = None) -> list[ClosedTrade]:
    """Casa BUY com SELL FIFO por nome. Cada par usa 1 unidade.

    Regras:
      - eventos sem nome, sem preco ou com side != buy/sell sao ignorados;
      - sells que ocorrem ANTES do buy correspondente (ts conhecidos) sao
        puladas (pareamento nao faz sentido);
      - buys ou sells sem contraparte ficam pendentes (nao geram trade).
    """
    closed = _pair_and_split(events, now=now)[0]
    closed.sort(key=lambda c: c.sell_ts, reverse=True)
    return closed


def find_open_buys(events: list[dict],
                   now: float | None = None) -> list[OpenBuy]:
    """Devolve as compras que nao foram casadas com nenhuma venda
    subsequente (posicoes "abertas" no Steam Market)."""
    opens = _pair_and_split(events, now=now)[1]
    opens.sort(key=lambda o: o.buy_ts, reverse=True)
    return opens


def load_closed_trades() -> list[ClosedTrade]:
    """Carrega eventos sincronizados e devolve trades pareados."""
    return match_events(sync.load_market_events())


def load_open_buys() -> list[OpenBuy]:
    """Carrega eventos sincronizados e devolve buys ainda nao vendidos."""
    return find_open_buys(sync.load_market_events())


def summarize(closed: list[ClosedTrade]) -> dict:
    """Estatisticas agregadas de uma lista de trades fechados."""
    if not closed:
        return {"count": 0, "total_pnl": 0.0, "winners": 0, "losers": 0,
                "win_rate": 0.0}
    winners = sum(1 for c in closed if c.pnl > 0)
    losers = sum(1 for c in closed if c.pnl < 0)
    return {
        "count": len(closed),
        "total_pnl": sum(c.pnl for c in closed),
        "winners": winners,
        "losers": losers,
        "win_rate": winners / len(closed) if closed else 0.0,
    }
