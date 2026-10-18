"""Rotas do Scanner -- Fase 11 (a mais pesada: escaneia dezenas de
itens, cada um com rede). Roda em background com progresso/resultado
item-a-item via SSE, mesmo padrao de account_data.start_refresh.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault.webapp import events, scanner_data

bp = Blueprint("scanner", __name__)


@bp.route("/scanner")
def page():
    return render_template("scanner.html", active="scanner")


@bp.route("/api/scanner/categories")
def categories():
    return jsonify({"categories": ["Todas as categorias"] + scanner_data.categories()})


@bp.route("/api/scanner/scan", methods=["POST"])
def scan():
    data = request.get_json(silent=True) or {}
    category = (data.get("category") or "").strip()
    valid = {"Todas as categorias", *scanner_data.categories()}
    if category not in valid:
        return jsonify({"error": "categoria inválida"}), 400

    def on_progress(done: int, total: int, name: str) -> None:
        events.publish("scanner_progress",
                        {"done": done, "total": total, "name": name})

    def on_item(item: dict) -> None:
        events.publish("scanner_item", item)

    def on_done(result: dict) -> None:
        events.publish("scanner_done", result)

    if not scanner_data.start_scan(category, on_progress, on_item, on_done):
        return jsonify({"error": "já há um scan em andamento"}), 409
    return jsonify({"started": True})


@bp.route("/api/scanner/cancel", methods=["POST"])
def cancel():
    scanner_data.cancel_scan()
    return jsonify({"ok": True})


@bp.route("/api/scanner/status")
def status():
    return jsonify({"scanning": scanner_data.is_scanning()})
