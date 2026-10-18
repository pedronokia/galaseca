"""Rotas da tela de Historico -- Fase 7.

MVP: dois segmentos (evolucao do valor da carteira + trades, lendo o
mesmo /api/trades da Fase 4) e o simulador de trade. Os segmentos
Market/Offers/Watchlist do Qt dependem do sync.py (dado legado da F10,
revertida) e da Watchlist (ainda nao portada -- Fase 8); ficam de fora
deste MVP.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault import history as history_mod
from skinvault import portfolio as portfolio_mod

bp = Blueprint("history", __name__)


@bp.route("/historico")
def page():
    return render_template("history.html", active="history")


@bp.route("/api/history/value")
def value_series():
    series = history_mod.load_history()
    return jsonify({"series": list(reversed(series))})


def _parse_float(data: dict, key: str) -> "tuple[float | None, str | None]":
    try:
        return float(data[key]), None
    except (KeyError, TypeError, ValueError):
        return None, f"{key} inválido"


@bp.route("/api/history/simulate", methods=["POST"])
def simulate():
    data = request.get_json(silent=True) or {}
    buy, err = _parse_float(data, "buy_price")
    if err or buy < 0:
        return jsonify({"error": "preço de compra inválido"}), 400
    sell, err = _parse_float(data, "sell_price")
    if err or sell < 0:
        return jsonify({"error": "preço de venda inválido"}), 400
    try:
        quantity_raw = data.get("quantity")
        quantity = 1 if quantity_raw in (None, "") else int(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "quantidade inválida"}), 400
    if quantity < 1:
        return jsonify({"error": "quantidade precisa ser pelo menos 1"}), 400
    return jsonify(portfolio_mod.simulate_trade(buy, sell, quantity))
