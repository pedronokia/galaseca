"""Rotas gerais: casco da pagina, ping, eventos (SSE) e debug de notificacao.

A rota de debug existe so' na Fase 0/1 da migracao -- prova o pipeline
bandeja+toast+SSE antes do Watchlist (produtor real de alertas) existir
na UI web. Remover quando `alerts_scheduler.py` entrar.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, render_template

from skinvault.webapp import events

bp = Blueprint("misc", __name__)


@bp.route("/")
def index():
    return render_template("account.html", active="account")


@bp.route("/api/ping")
def ping():
    return jsonify({"ok": True})


@bp.route("/api/events")
def sse_events():
    q = events.subscribe()
    return Response(events.stream(q), mimetype="text/event-stream")


@bp.route("/api/debug/notify", methods=["POST"])
def debug_notify():
    from skinvault.webapp import tray

    title = "SkinVault"
    body = "Notificacao de teste (bandeja + pagina)."
    tray.notify(title, body, "info")
    events.publish("notification",
                    {"title": title, "body": body, "severity": "info"})
    return jsonify({"sent": True})
