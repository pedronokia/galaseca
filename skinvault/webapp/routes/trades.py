"""Rotas da tela de Trades -- Fase 4. CRUD puro, sem rede (trades.py so'
grava em data/trades.json -- P&L ja vem calculado em `build_trade`).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault import trades as trades_mod

bp = Blueprint("trades", __name__)


@bp.route("/trades")
def page():
    return render_template("trades.html", active="trades")


def _payload() -> dict:
    items = trades_mod.load_trades()
    return {
        "trades": [
            {**t, "index": i} for i, t in enumerate(items)
        ],
        "stats": trades_mod.trade_stats(items),
    }


@bp.route("/api/trades")
def list_trades():
    return jsonify(_payload())


def _parse_float(data: dict, key: str) -> "tuple[float | None, str | None]":
    try:
        return float(data[key]), None
    except (KeyError, TypeError, ValueError):
        return None, f"{key} invalido"


@bp.route("/api/trades", methods=["POST"])
def add_trade():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome obrigatorio"}), 400
    buy_cost, err = _parse_float(data, "buy_cost")
    if err:
        return jsonify({"error": err}), 400
    sell_price, err = _parse_float(data, "sell_price")
    if err:
        return jsonify({"error": err}), 400
    if buy_cost < 0 or sell_price < 0:
        return jsonify({"error": "precos nao podem ser negativos"}), 400
    try:
        quantity_raw = data.get("quantity")
        quantity = 1 if quantity_raw in (None, "") else int(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "quantidade invalida"}), 400
    if quantity < 1:
        return jsonify({"error": "quantidade precisa ser pelo menos 1"}), 400
    notes = (data.get("notes") or "").strip()
    trades_mod.record_trade(name, buy_cost, sell_price, quantity, notes=notes)
    return jsonify(_payload())


@bp.route("/api/trades/<int:index>", methods=["PATCH"])
def edit_trade(index: int):
    data = request.get_json(silent=True) or {}
    kwargs = {}
    cost = sell_price = None
    if "buy_cost" in data:
        cost, err = _parse_float(data, "buy_cost")
        if err or cost < 0:
            return jsonify({"error": "buy_cost invalido"}), 400
    if "sell_price" in data:
        sell_price, err = _parse_float(data, "sell_price")
        if err or sell_price < 0:
            return jsonify({"error": "sell_price invalido"}), 400
    if "notes" in data:
        kwargs["notes"] = (data.get("notes") or "").strip()
    result = trades_mod.update_trade(
        index, cost=cost, sell_price=sell_price, **kwargs)
    if result is None:
        return jsonify({"error": "trade nao encontrado"}), 404
    return jsonify(_payload())


@bp.route("/api/trades/<int:index>", methods=["DELETE"])
def delete_trade(index: int):
    items = trades_mod.load_trades()
    if not (0 <= index < len(items)):
        return jsonify({"error": "trade nao encontrado"}), 404
    trades_mod.remove_trade(index)
    return jsonify(_payload())
