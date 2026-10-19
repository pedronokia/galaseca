"""Rotas da tela de Inventario -- Fase 3 (segunda tela real).

MVP: tabela com filtro, custo editavel e "+ Adicionar item". Sem grade de
icones, comparacao com mercados externos, liquidez sob demanda, nota/topo
nem import/export de CSV -- isso reusa a logica em ui/inventory_screen.py
(cases.py/markets.py/signals.py) e fica pra uma fase seguinte.

Editar custo NAO dispara avaliacao com rede: o preco nao mudou, so' o
P&L. `account_data.summary_payload()` (cache-only) ja' reflete o novo
custo na hora.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault import portfolio as portfolio_mod
from skinvault.settings import load_settings
from skinvault.webapp import account_data, events, inventory_data

bp = Blueprint("inventory", __name__)


@bp.route("/inventario")
def page():
    return render_template("inventory.html", active="inventory")


@bp.route("/api/inventory")
def list_items():
    return jsonify(account_data.summary_payload())


@bp.route("/api/inventory/import", methods=["POST"])
def import_steam():
    data = request.get_json(silent=True) or {}
    profile = (data.get("profile") or "").strip()
    remove_missing = bool(data.get("remove_missing"))
    if not profile:
        return jsonify({"error": "cole o link do seu perfil"}), 400

    def on_done(result: dict) -> None:
        if "error" not in result:
            result = dict(result, **account_data.summary_payload())
        events.publish("inventory_import_done", result)

    if not inventory_data.start_import(profile, remove_missing, on_done):
        return jsonify({"error": "já há uma importação em andamento"}), 409
    return jsonify({"started": True})


@bp.route("/api/inventory/import/status")
def import_status():
    return jsonify({
        "importing": inventory_data.is_importing(),
        "steam_profile": load_settings().get("steam_profile", ""),
    })


def _publish_and_return():
    payload = account_data.summary_payload()
    events.publish("account_eval", payload)
    return jsonify(payload)


@bp.route("/api/inventory/cost", methods=["POST"])
def set_cost():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    cost = data.get("cost")
    if not name:
        return jsonify({"error": "nome obrigatorio"}), 400
    try:
        cost = round(float(cost), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "custo invalido"}), 400
    if cost < 0:
        return jsonify({"error": "custo nao pode ser negativo"}), 400
    if portfolio_mod.update_position_cost(name, cost) is None:
        portfolio_mod.add_position(name, cost, 1)
    return _publish_and_return()


@bp.route("/api/inventory/add", methods=["POST"])
def add_item():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome obrigatorio"}), 400
    cost_raw = data.get("cost")
    cost = None
    if cost_raw not in (None, ""):
        try:
            cost = round(float(cost_raw), 2)
        except (TypeError, ValueError):
            return jsonify({"error": "custo invalido"}), 400
        if cost < 0:
            return jsonify({"error": "custo nao pode ser negativo"}), 400
    try:
        # NAO usar `data.get("quantity") or 1`: quantity=0 e' falsy em
        # Python e o `or` o trocaria por 1 em vez de cair na checagem
        # de "< 1" abaixo. `quantity ausente` e' o unico caso que deve
        # virar o default.
        quantity_raw = data.get("quantity")
        quantity = 1 if quantity_raw is None else int(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "quantidade invalida"}), 400
    if quantity < 1:
        return jsonify({"error": "quantidade precisa ser pelo menos 1"}), 400
    portfolio_mod.add_position(name, cost, quantity)
    return _publish_and_return()
