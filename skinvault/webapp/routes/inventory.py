"""Rotas da tela de Inventario -- Fase 3 (segunda tela real).

So' Steam: importar, editar custo e remover (2026-10-20, a pedido do
usuario -- entrada manual/CSV saiu da tela, dado publico da Steam e'
o unico jeito de entrar com item). `portfolio.add_position` continua
usado internamente por `set_cost` (celula de custo cria a posicao se o
nome ainda nao existir) e pela sincronizacao real.

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
    from skinvault import steam_api

    cooldown_s = max(steam_api.cooldown_restante_s("inventory"),
                      steam_api.cooldown_restante_s("resolve"))
    return jsonify({
        "importing": inventory_data.is_importing(),
        "steam_profile": load_settings().get("steam_profile", ""),
        "cooldown_s": cooldown_s,
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


@bp.route("/api/inventory/remove", methods=["POST"])
def remove_item():
    # POST com nome no corpo, igual /cost -- nao DELETE/<name> na URL: nome
    # de skin tem "|", "(", ")", espacos e as vezes ate' "/" (Holo-Foil
    # trocado por barra na busca), frageis demais pra ir no path.
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome obrigatorio"}), 400
    if not portfolio_mod.remove_position(name):
        return jsonify({"error": "item nao encontrado"}), 404
    return _publish_and_return()

