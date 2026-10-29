"""Blueprint de trades pessoais -- `/conta/trades`.

Mesmo padrão do portfólio (Fase 2a): a matemática (`trade_stats`,
`build_trade`) continua 100% em `skinvault/trades.py`, sem alteração --
só a mutação (adicionar/remover) é nova, porque as funções do app local
estão presas a um caminho de arquivo (gotcha #17 do AGENTS.md).
"""
from __future__ import annotations

import math

from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
)

from skinvault import trades as trades_mod
from skinvault.localization import localize_name
from skinvault.public_site import fmt, user_trades
from skinvault.public_site.auth import csrf_protect, csrf_token, login_required
from skinvault.public_site.rate_limit import (
    MUTATION_MAX_HITS, MUTATION_WINDOW_S, rate_limited,
)

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
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def adicionar():
    steamid = session["steamid"]
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Informe o nome do item.", "error")
        return redirect(url_for("trades.listar"))

    try:
        buy_cost = float(request.form.get("buy_cost") or "")
        sell_price = float(request.form.get("sell_price") or "")
    except ValueError:
        flash(
            "Confira os valores: compra e venda precisam ser números maiores que zero.",
            "error",
        )
        return redirect(url_for("trades.listar"))

    quantity_raw = (request.form.get("quantity") or "").strip()
    try:
        quantity = int(quantity_raw) if quantity_raw else 1
    except ValueError:
        quantity = 0
    if quantity < 1:
        flash(
            "A quantidade precisa ser um número inteiro maior que zero.",
            "error",
        )
        return redirect(url_for("trades.listar"))

    if (not math.isfinite(buy_cost) or buy_cost <= 0
            or not math.isfinite(sell_price) or sell_price <= 0):
        flash(
            "Confira os valores: compra e venda precisam ser números maiores que zero.",
            "error",
        )
        return redirect(url_for("trades.listar"))

    notes = (request.form.get("notes") or "").strip()
    user_trades.add_trade(
        steamid, name, buy_cost, sell_price, quantity, notes)
    return redirect(url_for("trades.listar"))


@bp.route("/conta/trades/<int:index>/remover", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def remover(index: int):
    steamid = session["steamid"]
    user_trades.remove_trade(steamid, index)
    return redirect(url_for("trades.listar"))
