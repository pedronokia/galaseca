"""Rotas gerais: casco da pagina, ping, eventos (SSE) e debug de notificacao.

A rota de debug existe so' na Fase 0/1 da migracao -- prova o pipeline
bandeja+toast+SSE antes do Watchlist (produtor real de alertas) existir
na UI web. Remover quando `alerts_scheduler.py` entrar.
"""
from __future__ import annotations

from flask import Blueprint, Response, jsonify, render_template, send_file

from skinvault.webapp import events

bp = Blueprint("misc", __name__)


@bp.route("/")
def index():
    return render_template("account.html", active="account")


@bp.route("/api/icon/<path:icon_hash>")
def icon(icon_hash):
    """Serve o icone do item (cache local em data/icons/, baixa do CDN
    de imagem da Steam se faltar -- icons.py). CDN de imagem e' dominio
    separado do steamcommunity.com que o resto do app as vezes esbarra
    em rate limit: servir isto nao disputa a mesma cota.

    <path:...> porque o hash pode ter '/' (icons.py ja' trata isso pra
    nome de arquivo local, mas a rota precisa aceitar na URL tambem).
    Sem cache -> 404: a tela mostra um marcador generico em vez de
    imagem quebrada.
    """
    from skinvault import icons as icons_mod

    path = icons_mod.fetch(icon_hash)
    if not path:
        return "", 404
    return send_file(path, mimetype="image/png", max_age=86400 * 7)


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
