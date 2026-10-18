"""Rotas da Calculadora de Trade-up -- Fase 5.

GET /api/tradeup/catalog e POST /api/tradeup/plan sao instantaneos
(local/cache-only). POST /api/tradeup/catalog/refresh baixa o dataset
publico do GitHub (nao e' Steam, sem rate limit por conta). POST
/api/tradeup/evaluate e' quem pode bater no Steam Market -- roda em
background e publica progresso/resultado via SSE, mesmo padrao de
account_data.start_refresh.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault.webapp import events, tradeup_data

bp = Blueprint("tradeup", __name__)


@bp.route("/trade-up")
def page():
    return render_template("tradeup.html", active="tradeup")


@bp.route("/api/tradeup/catalog")
def catalog():
    return jsonify(tradeup_data.catalog_status())


@bp.route("/api/tradeup/catalog/refresh", methods=["POST"])
def refresh_catalog():
    def on_done(status: str) -> None:
        payload = tradeup_data.catalog_status()
        payload["refresh_status"] = status
        events.publish("tradeup_catalog", payload)

    if not tradeup_data.start_catalog_refresh(on_done):
        return jsonify({"started": False}), 409
    return jsonify({"started": True})


@bp.route("/api/tradeup/plan", methods=["POST"])
def plan():
    data = request.get_json(silent=True) or {}
    return jsonify(tradeup_data.quick_plan(data.get("lines") or ""))


@bp.route("/api/tradeup/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json(silent=True) or {}
    raw = data.get("lines") or ""

    def on_progress(done: int, total: int, fetches: int) -> None:
        events.publish("tradeup_progress",
                        {"done": done, "total": total, "fetches": fetches})

    def on_done(result: dict) -> None:
        events.publish("tradeup_result", result)

    if not tradeup_data.start_evaluate(raw, on_progress, on_done):
        return jsonify({"started": False}), 409
    return jsonify({"started": True})
