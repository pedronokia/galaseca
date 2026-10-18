"""Rotas da tela de Conta -- primeira tela real da migracao (Fase 2).

GET /api/account/summary volta na hora (so' cache, sem rede) pra tela
nunca esperar o rate limit pra pintar algo. POST /api/account/refresh
dispara a avaliacao completa em background e publica o progresso e o
resultado via SSE (/api/events) -- o mesmo pipeline que o botao de
notificacao de teste (misc.py) ja provou na Fase 0/1.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from skinvault.webapp import account_data, events

bp = Blueprint("account", __name__)


@bp.route("/api/account/summary")
def summary():
    return jsonify(account_data.summary_payload())


@bp.route("/api/account/refresh", methods=["POST"])
def refresh():
    def on_progress(done: int, total: int) -> None:
        events.publish("account_progress", {"done": done, "total": total})

    def on_done(payload: dict) -> None:
        events.publish("account_eval", payload)

    started = account_data.start_refresh(on_progress, on_done)
    if not started:
        return jsonify({"started": False,
                         "reason": "ja ha uma atualizacao em andamento"}), 409
    return jsonify({"started": True})
