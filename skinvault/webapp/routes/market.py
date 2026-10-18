"""Rotas da Consulta de Mercado -- Fase 10.

Unica tela que bate na Steam SINCRONAMENTE dentro do request: uma
busca sao so' 2 chamadas (priceoverview + listing page), nao um lote
-- o mesmo custo que o botao "Consultar item" do Qt sempre teve.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault.webapp import market_data

bp = Blueprint("market", __name__)


@bp.route("/mercado")
def page():
    return render_template("market.html", active="market")


@bp.route("/api/market/recent")
def recent():
    return jsonify({"recent": market_data.load_recent()})


@bp.route("/api/market/search", methods=["POST"])
def search():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome obrigatório"}), 400
    return jsonify(market_data.search(name))
