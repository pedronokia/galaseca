"""Feed de atividade recente — agrega trades, alertas e snapshots de ranking.

Estilo "Recent Activity" do Faceit: lista vertical, mais novo primeiro,
formato unificado pra a UI consumir sem se preocupar com as fontes.
"""
from __future__ import annotations

import time
from pathlib import Path

from skinvault import alerts, ranking, trades

# Tipos de evento normalizados
TYPE_TRADE = "trade"
TYPE_ALERT = "alert"
TYPE_RANKING = "ranking"

# Cores semanticas (mapeiam para theme.ACCENT/DANGER/STEAM_BLUE/TEXT_MUTED na UI)
COLOR_GREEN = "green"
COLOR_RED = "red"
COLOR_ACCENT = "accent"
COLOR_MUTED = "muted"


def _trade_event(t: dict) -> dict | None:
    ts = t.get("sell_ts") or t.get("buy_ts")
    if ts is None:
        return None
    pnl = t.get("pnl", 0) or 0
    pnl_pct = t.get("pnl_pct", 0) or 0
    return {
        "type": TYPE_TRADE,
        "ts": float(ts),
        "title": t.get("name") or "Trade",
        "subtitle": f"P&L R$ {pnl:+.2f} ({pnl_pct:+.1f}%)",
        "color": COLOR_GREEN if pnl >= 0 else COLOR_RED,
        "icon": "↑" if pnl >= 0 else "↓",
    }


def _alert_event(a: dict) -> dict | None:
    ts = a.get("ts")
    if ts is None:
        return None
    return {
        "type": TYPE_ALERT,
        "ts": float(ts),
        "title": a.get("name") or "Alerta",
        "subtitle": a.get("label") or a.get("rule") or "",
        "color": COLOR_ACCENT,
        "icon": "★",
    }


def _ranking_event(s: dict) -> dict | None:
    ts = s.get("ts")
    if ts is None:
        return None
    items = s.get("items") or []
    top = items[0] if items else None
    if top:
        subtitle = f"Lider: {top.get('name', '?')}"
    else:
        subtitle = "Snapshot vazio"
    return {
        "type": TYPE_RANKING,
        "ts": float(ts),
        "title": "Ranking Top 20",
        "subtitle": subtitle,
        "color": COLOR_MUTED,
        "icon": "·",
    }


def load_recent_activity(limit: int = 10) -> list[dict]:
    """Agrega trades + alertas + snapshots em uma lista unica ordenada
    por timestamp desc. Retorna no maximo `limit` eventos.

    Cada evento e {type, ts, title, subtitle, color, icon}.
    """
    events: list[dict] = []
    for t in trades.load_trades():
        ev = _trade_event(t)
        if ev:
            events.append(ev)
    for a in alerts.load_alerts_log():
        ev = _alert_event(a)
        if ev:
            events.append(ev)
    for s in ranking.load_snapshots():
        ev = _ranking_event(s)
        if ev:
            events.append(ev)
    events.sort(key=lambda e: -e["ts"])
    return events[:max(limit, 0)]


def format_relative_ts(ts: float, now: float | None = None) -> str:
    """Formato curto estilo Faceit: 'agora', '5m', '2h', '3d', '5 mai'."""
    n = now if now is not None else time.time()
    delta = n - ts
    if delta < 60:
        return "agora"
    if delta < 3600:
        return f"{int(delta // 60)}m"
    if delta < 86400:
        return f"{int(delta // 3600)}h"
    if delta < 86400 * 7:
        return f"{int(delta // 86400)}d"
    import datetime as _dt
    dt = _dt.datetime.fromtimestamp(ts)
    months = ["jan", "fev", "mar", "abr", "mai", "jun",
              "jul", "ago", "set", "out", "nov", "dez"]
    return f"{dt.day} {months[dt.month - 1]}"
