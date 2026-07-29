from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record
from skinvault.portfolio import net_proceeds

_DEFAULT_PATH = DATA_DIR / "trades.json"


def load_trades(path: Path | str = _DEFAULT_PATH) -> list[dict]:
    data = load_json_record(path, [])
    return data if isinstance(data, list) else []


def save_trades(trades: list[dict], path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        atomic_write_text(p, json.dumps(trades, indent=2))
    except OSError as e:
        print(f"WARNING: failed to save trades: {e}", file=__import__('sys').stderr)


def build_trade(name: str, buy_cost: float, sell_price: float,
                quantity: int = 1,
                notes: str = "", tags: list[str] | None = None,
                buy_ts: float | None = None,
                source: str = "manual",
                steam_event_id: str | None = None,
                sell_ts: float | None = None) -> dict:
    """Monta o registro de trade sem tocar em disco.

    Existe separado de `record_trade` porque a importacao da Steam grava
    centenas de trades de uma vez: passar por `record_trade` faria um
    load+save do arquivo inteiro por trade.
    """
    cost_total = buy_cost * quantity
    net = net_proceeds(sell_price) * quantity
    pnl = net - cost_total
    now = time.time()
    return {
        "name": name,
        "buy_cost": buy_cost,
        "sell_price": sell_price,
        "quantity": quantity,
        "cost_total": cost_total,
        "net_received": round(net, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round((pnl / cost_total * 100) if cost_total else 0, 2),
        "buy_ts": buy_ts or now,
        "sell_ts": sell_ts or now,
        "notes": notes,
        "tags": tags or [],
        "source": source,
        "steam_event_id": steam_event_id,
    }


def record_trade(name: str, buy_cost: float, sell_price: float,
                 quantity: int = 1,
                 notes: str = "", tags: list[str] | None = None,
                 buy_ts: float | None = None,
                 path: Path | str = _DEFAULT_PATH,
                 source: str = "manual",
                 steam_event_id: str | None = None,
                 sell_ts: float | None = None) -> dict:
    """Registra trade. source distingue entrada manual de sync Steam (F10).
    steam_event_id identifica o evento original na Steam pra dedupe."""
    trade = build_trade(
        name, buy_cost, sell_price, quantity,
        notes=notes, tags=tags, buy_ts=buy_ts,
        source=source, steam_event_id=steam_event_id, sell_ts=sell_ts,
    )
    trades = load_trades(path)
    trades.append(trade)
    save_trades(trades, path)
    return trade


def update_trade(index: int, path: Path | str = _DEFAULT_PATH,
                 cost: float | None = None,
                 sell_price: float | None = None,
                 **kwargs) -> dict | None:
    trades = load_trades(path)
    if not (0 <= index < len(trades)):
        return None
    t = trades[index]
    if cost is not None:
        t["buy_cost"] = cost
        t["cost_total"] = cost * t["quantity"]
    if sell_price is not None:
        t["sell_price"] = sell_price
    if cost is not None or sell_price is not None:
        net = net_proceeds(t["sell_price"]) * t["quantity"]
        t["net_received"] = round(net, 2)
        t["pnl"] = round(net - t["cost_total"], 2)
        t["pnl_pct"] = round((t["pnl"] / t["cost_total"] * 100) if t["cost_total"] else 0, 2)
    for k, v in kwargs.items():
        t[k] = v
    save_trades(trades, path)
    return t


def remove_trade(index: int, path: Path | str = _DEFAULT_PATH) -> list[dict]:
    trades = load_trades(path)
    if 0 <= index < len(trades):
        trades.pop(index)
        save_trades(trades, path)
    return trades


def clear_trades(path: Path | str = _DEFAULT_PATH) -> None:
    save_trades([], path)


def filter_trades(keyword: str | None = None,
                  tags: list[str] | None = None,
                  profit_only: bool | None = None,
                  loss_only: bool | None = None,
                  pnl: str | None = None,
                  path: Path | str = _DEFAULT_PATH) -> list[dict]:
    trades = load_trades(path)
    if keyword:
        kw = keyword.lower()
        trades = [t for t in trades if kw in t["name"].lower()
                  or kw in t.get("notes", "").lower()]
    if tags:
        trades = [t for t in trades
                  if any(tg in t.get("tags", []) for tg in tags)]
    if profit_only:
        trades = [t for t in trades if t["pnl"] > 0]
    if loss_only:
        trades = [t for t in trades if t["pnl"] < 0]
    if pnl == "profit":
        trades = [t for t in trades if t["pnl"] >= 0]
    elif pnl == "loss":
        trades = [t for t in trades if t["pnl"] < 0]
    return trades


def trade_stats(trades: list[dict] | None = None,
                path: Path | str = _DEFAULT_PATH) -> dict:
    if trades is None:
        trades = load_trades(path)
    total = len(trades)
    if not total:
        return {"total": 0, "pnl_total": 0, "pnl_medio": 0,
                "win_count": 0, "loss_count": 0, "win_rate": 0,
                "best": None, "worst": None, "monthly": [],
                "fees_total": 0.0, "avg_days": 0}
    pnl_total = sum(t["pnl"] for t in trades)
    win = sum(1 for t in trades if t["pnl"] > 0.005)
    loss = sum(1 for t in trades if t["pnl"] < -0.005)
    best = max(trades, key=lambda t: t["pnl"])
    worst = min(trades, key=lambda t: t["pnl"])
    fees_total = sum(
        (t["sell_price"] * t["quantity"]) - t["net_received"]
        for t in trades
    )
    days_list = [
        (t["sell_ts"] - t["buy_ts"]) / 86400
        for t in trades if t["sell_ts"] > t["buy_ts"]
    ]
    avg_days = round(sum(days_list) / len(days_list), 1) if days_list else 0
    monthly_stats = monthly_pnl(trades)
    return {
        "total": total,
        "pnl_total": round(pnl_total, 2),
        "pnl_medio": round(pnl_total / total, 2),
        "win_count": win,
        "loss_count": loss,
        "win_rate": round(win / total * 100, 1),
        "best": best,
        "worst": worst,
        "monthly": monthly_stats,
        "fees_total": round(fees_total, 2),
        "avg_days": avg_days,
    }


def monthly_pnl(trades: list[dict]) -> list[dict]:
    """Agrega P&L por mes. Cada item: {month: '%Y-%m', trades: n, pnl: x}.

    So exige sell_ts/buy_ts e pnl — tolera trades legados sem as demais
    chaves (alimenta o MonthBarChart da History)."""
    monthly: dict[str, list] = {}
    for t in trades:
        key = _month_key(t.get("sell_ts", t.get("buy_ts", 0)))
        monthly.setdefault(key, []).append(t)
    return [
        {
            "month": k, "trades": len(v),
            "pnl": round(sum(t.get("pnl", 0) for t in v), 2),
        }
        for k, v in sorted(monthly.items())
    ]


def _month_key(ts: float) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts))
