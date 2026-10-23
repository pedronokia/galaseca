"""Blueprint de trades pessoais -- `/conta/trades`.

Mesmo padrão do portfólio (Fase 2a): a matemática (`trade_stats`,
`build_trade`) continua 100% em `skinvault/trades.py`, sem alteração --
só a mutação (adicionar/remover) é nova, porque as funções do app local
estão presas a um caminho de arquivo (gotcha #17 do AGENTS.md).
"""
from __future__ import annotations

from flask import (
    Blueprint, redirect, render_template, request, session, url_for,
)

from skinvault import trades as trades_mod
from skinvault.localization import localize_name
from skinvault.public_site import fmt, user_trades
from skinvault.public_site.auth import csrf_protect, csrf_token, login_required

bp = Blueprint("trades", __name__)


def _formatar(registros: list[dict]) -> list[dict]:
    """Acrescenta `index` (posição original, pra remover certo) e
    campos *_fmt -- mesmo padrão de `account.py:_formatar_linhas`."""
    out = []
    for i, t in enumerate(registros):
        out.append({
            **t,
            "index": i,
            "name_fmt": localize_name(t["name"]),
            "buy_cost_fmt": fmt.brl(t.get("buy_cost")),
            "sell_price_fmt": fmt.brl(t.get("sell_price")),
            "pnl_fmt": fmt.brl(t.get("pnl")),
        })
    return out


@bp.route("/conta/trades")
@login_required
def listar():
    steamid = session["steamid"]
    registros = user_trades.load_trades(steamid)
    stats = trades_mod.trade_stats(trades=registros)
    stats["pnl_total_fmt"] = fmt.brl(stats.get("pnl_total"))
    stats["pnl_medio_fmt"] = fmt.brl(stats.get("pnl_medio"))
    linhas = _formatar(registros)
    linhas.reverse()  # mais recente primeiro; `index` já é o original
    return render_template(
        "conta_trades.html", trades=linhas, stats=stats,
        csrf_token=csrf_token(),
    )


@bp.route("/conta/trades", methods=["POST"])
@login_required
@csrf_protect
def adicionar():
    steamid = session["steamid"]
    name = (request.form.get("name") or "").strip()
    try:
        buy_cost = float(request.form.get("buy_cost") or 0)
        sell_price = float(request.form.get("sell_price") or 0)
        quantity = max(1, int(request.form.get("quantity") or 1))
    except ValueError:
        return redirect(url_for("trades.listar"))
    notes = (request.form.get("notes") or "").strip()
    if name and buy_cost > 0 and sell_price > 0:
        user_trades.add_trade(
            steamid, name, buy_cost, sell_price, quantity, notes)
    return redirect(url_for("trades.listar"))


@bp.route("/conta/trades/<int:index>/remover", methods=["POST"])
@login_required
@csrf_protect
def remover(index: int):
    steamid = session["steamid"]
    user_trades.remove_trade(steamid, index)
    return redirect(url_for("trades.listar"))
