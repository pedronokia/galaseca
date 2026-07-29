"""Pareamento BUY <-> SELL de eventos do Steam Market.

Sintetiza trades fechados a partir dos eventos brutos sincronizados
(`data/steam_market_events.json`): agrupa por nome do item, ordena por
data e casa FIFO (compra mais antiga com venda mais antiga). Calcula
P&L liquido descontando a taxa Steam de 15%.

Parsing e matching sao puros. O IO fica confinado nos helpers do fim do
modulo: `load_closed_trades`/`load_open_buys` leem via `sync`, e
`import_closed_trades` grava em trades.json. Nada aqui usa rede -- a
sincronizacao com a Steam ja' aconteceu antes, em `sync.py`.
"""
from __future__ import annotations

import datetime as _dt
import html as _html
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

    # datetime valida dia/mes; time.mktime e permissivo (vira 31 Apr em
    # 1 Mai silenciosamente). Queremos None pra dia invalido.
    try:
        ts = _dt.datetime(year, month, day, hh, mm).timestamp()
    except (ValueError, OverflowError):
        return None

    if not explicit_year and ts > now_ts + 86400:
        try:
            ts = _dt.datetime(year - 1, month, day, hh, mm).timestamp()
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
    # No fim e com default pra nao quebrar construcao posicional existente.
    buy_ts: float = 0.0


@dataclass
class OpenBuy:
    """Compra registrada no Steam Market que ainda nao foi pareada
    com uma venda subsequente."""
    name: str
    buy_date: str
    buy_price: float
    buy_ts: float


CS2_APPID = "730"


def _group_by_name(events: list[dict],
                   now: float | None = None,
                   appid: str | None = CS2_APPID,
                   ) -> dict[str, dict[str, list]]:
    by_name: dict[str, dict[str, list]] = {}
    for ev in events:
        name = ev.get("name")
        side = (ev.get("side") or "").lower()
        price = ev.get("price")
        ev_appid = ev.get("appid")
        if not name or price is None or side not in ("buy", "sell"):
            continue
        if appid is not None and ev_appid is not None and ev_appid != appid:
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
                    appid: str | None = CS2_APPID,
                    ) -> tuple[list[ClosedTrade], list[OpenBuy]]:
    """Roda o pareamento FIFO e devolve trades fechados + buys abertos."""
    by_name = _group_by_name(events, now=now, appid=appid)
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
                buy_ts=b["ts"],
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
                 now: float | None = None,
                 appid: str | None = CS2_APPID) -> list[ClosedTrade]:
    """Casa BUY com SELL FIFO por nome. Cada par usa 1 unidade.

    Regras:
      - eventos sem nome, sem preco ou com side != buy/sell sao ignorados;
      - eventos cujo appid esta setado e difere do `appid` argumento sao
        filtrados; passe appid=None para incluir todos os jogos;
      - sells que ocorrem ANTES do buy correspondente (ts conhecidos) sao
        puladas (pareamento nao faz sentido);
      - buys ou sells sem contraparte ficam pendentes (nao geram trade).
    """
    closed = _pair_and_split(events, now=now, appid=appid)[0]
    closed.sort(key=lambda c: c.sell_ts, reverse=True)
    return closed


def find_open_buys(events: list[dict],
                   now: float | None = None,
                   appid: str | None = CS2_APPID) -> list[OpenBuy]:
    """Devolve as compras que nao foram casadas com nenhuma venda
    subsequente (posicoes "abertas" no Steam Market)."""
    opens = _pair_and_split(events, now=now, appid=appid)[1]
    opens.sort(key=lambda o: o.buy_ts, reverse=True)
    return opens


def load_closed_trades() -> list[ClosedTrade]:
    """Carrega eventos sincronizados e devolve trades pareados."""
    return match_events(sync.load_market_events())


def load_open_buys() -> list[OpenBuy]:
    """Carrega eventos sincronizados e devolve buys ainda nao vendidos."""
    return find_open_buys(sync.load_market_events())


def _date_key(date_str: str, ts: float) -> str:
    """Componente de data das chaves de dedupe, em ISO.

    O Steam omite o ano quando a data e' do ano corrente (AGENTS.md #4), entao
    a string crua muda sozinha na virada de ano e o mesmo trade seria
    importado duas vezes. Mesma normalizacao de `sync.market_event_key`.
    """
    if ts:
        return time.strftime("%Y-%m-%d", time.localtime(ts))
    return date_str or ""


def closed_trade_key(trade: ClosedTrade) -> str:
    """ID estavel de um trade fechado, usado como `steam_event_id`.

    Nao inclui P&L: ele e' derivado dos precos e mudaria a chave se a taxa
    Steam fosse reconfigurada, reimportando tudo.
    """
    return "|".join([
        _html.unescape(trade.name or ""),
        _date_key(trade.buy_date, trade.buy_ts),
        "{:.2f}".format(trade.buy_price),
        _date_key(trade.sell_date, trade.sell_ts),
        "{:.2f}".format(trade.sell_price),
    ])


def assign_keys(closed: list[ClosedTrade]) -> list[tuple[str, ClosedTrade]]:
    """Casa cada trade com sua chave, desempatando repeticoes.

    Comprar e vender 3 unidades do mesmo item, no mesmo dia, pelo mesmo
    preco gera 3 trades com chave identica -- e sem desempate so' um seria
    importado. O sufixo e' estavel porque o pareamento FIFO e' deterministico:
    a mesma lista de eventos sempre produz a mesma ordem.
    """
    seen: dict[str, int] = {}
    out = []
    for tr in closed:
        base = closed_trade_key(tr)
        n = seen.get(base, 0) + 1
        seen[base] = n
        out.append((base if n == 1 else "{}#{}".format(base, n), tr))
    return out


def import_closed_trades(closed: list[ClosedTrade] | None = None,
                         path=None) -> dict:
    """Grava em trades.json os trades pareados do historico do Steam Market.

    Idempotente: cada trade carrega seu `steam_event_id` e reimportar pula o
    que ja' esta la'. Registros manuais nunca sao tocados nem considerados
    duplicata -- se o usuario registrou o mesmo trade na mao, a nota dele
    tem valor e apagar seria perda de dado. O custo e' uma linha repetida,
    que ele pode remover.

    Devolve {"imported", "skipped", "total"}.
    """
    from skinvault import trades as trades_mod

    if closed is None:
        closed = load_closed_trades()
    path = path if path is not None else trades_mod._DEFAULT_PATH

    existing = trades_mod.load_trades(path)
    known = {
        tr.get("steam_event_id") for tr in existing
        if tr.get("steam_event_id")
    }

    novos = []
    for key, tr in assign_keys(closed):
        if key in known:
            continue
        known.add(key)
        novos.append(trades_mod.build_trade(
            tr.name, tr.buy_price, tr.sell_price, quantity=1,
            buy_ts=tr.buy_ts or None, sell_ts=tr.sell_ts or None,
            source="steam_sync", steam_event_id=key,
        ))

    if novos:
        trades_mod.save_trades(existing + novos, path)
    return {
        "imported": len(novos),
        "skipped": len(closed) - len(novos),
        "total": len(closed),
    }


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
        "win_rate": winners / len(closed) * 100 if closed else 0.0,
    }
