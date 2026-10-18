"""Rotas da tela de Watchlist -- Fase 8.

MVP cache-only: "Verificar agora" so' confere `price_below` e
`price_drop_pct` (a cotacao vem do mesmo `prices.PriceCache` da Conta,
nunca bate na rede). `volume_spike`/`supply_drop`/`score_above` ficam
configuraveis desde ja -- o schema e' o mesmo de `alerts.evaluate_item`
-- mas so' disparam quando volume_history.json/supply_history.json/
score tiverem dado de verdade, o que exige o Scanner (Fase 11, ainda
nao portado). Alerta disparado usa o MESMO pipeline de notificacao que
a Fase 0/1 provou (tray.notify + SSE "notification").
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault import alerts as alerts_mod
from skinvault import watchlist as watchlist_mod
from skinvault.prices import PriceCache
from skinvault.webapp import events, tray

bp = Blueprint("watchlist", __name__)

_RULE_KEYS = ("price_below", "price_drop_pct", "volume_spike",
              "supply_drop", "score_above")


@bp.route("/watchlist")
def page():
    return render_template("watchlist.html", active="watchlist")


def _item_view(item: dict, cache: PriceCache, index: int) -> dict:
    price = cache.get(item["name"])
    return {
        "index": index,
        "name": item["name"],
        "target": item.get("target"),
        "rules": item.get("rules") or {},
        "rules_summary": alerts_mod.format_rules_summary(item.get("rules")),
        "baseline_price": item.get("baseline_price"),
        "triggered": bool(item.get("triggered")),
        "muted": watchlist_mod.is_muted(item),
        "price": price,
    }


def _payload() -> dict:
    cache = PriceCache()
    items = watchlist_mod.load_watchlist()
    return {"items": [_item_view(it, cache, i) for i, it in enumerate(items)]}


@bp.route("/api/watchlist")
def list_watchlist():
    return jsonify(_payload())


@bp.route("/api/watchlist", methods=["POST"])
def add_item():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome obrigatório"}), 400
    try:
        target = float(data.get("target") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "preço alvo inválido"}), 400
    if target < 0:
        return jsonify({"error": "preço alvo não pode ser negativo"}), 400
    try:
        watchlist_mod.add_watch(name, target)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_payload())


@bp.route("/api/watchlist/<int:index>", methods=["DELETE"])
def remove_item(index: int):
    items = watchlist_mod.load_watchlist()
    if not (0 <= index < len(items)):
        return jsonify({"error": "item não encontrado"}), 404
    watchlist_mod.remove_watch(index)
    return jsonify(_payload())


@bp.route("/api/watchlist/<int:index>/rules", methods=["PATCH"])
def update_rules(index: int):
    items = watchlist_mod.load_watchlist()
    if not (0 <= index < len(items)):
        return jsonify({"error": "item não encontrado"}), 404
    data = request.get_json(silent=True) or {}
    rules = {}
    for key in _RULE_KEYS:
        if key not in data or data[key] in (None, ""):
            continue
        try:
            rules[key] = float(data[key])
        except (TypeError, ValueError):
            return jsonify({"error": f"{key} inválido"}), 400
        if rules[key] < 0:
            return jsonify({"error": f"{key} não pode ser negativo"}), 400
    items[index]["rules"] = rules
    if "baseline_price" in data:
        try:
            items[index]["baseline_price"] = (
                float(data["baseline_price"])
                if data["baseline_price"] not in (None, "") else None)
        except (TypeError, ValueError):
            return jsonify({"error": "baseline_price inválido"}), 400
    # Regra mudou: o conjunto de triggers antigo nao vale mais, senao a
    # regra nova nunca dispara na primeira checagem (ja' "disparada").
    items[index]["triggered_rules"] = []
    items[index]["triggered"] = False
    watchlist_mod.save_watchlist(items)
    return jsonify(_payload())


@bp.route("/api/watchlist/<int:index>/mute", methods=["POST"])
def mute_item(index: int):
    items = watchlist_mod.load_watchlist()
    if not (0 <= index < len(items)):
        return jsonify({"error": "item não encontrado"}), 404
    data = request.get_json(silent=True) or {}
    hours = data.get("hours", watchlist_mod.MUTE_HORAS)
    watchlist_mod.set_muted(items[index]["name"], hours)
    return jsonify(_payload())


@bp.route("/api/watchlist/check", methods=["POST"])
def check_now():
    cache = PriceCache()
    items = watchlist_mod.load_watchlist()
    fired: list[dict] = []
    for item in items:
        if watchlist_mod.is_muted(item):
            continue
        name = item["name"]
        price = cache.get(name)
        fresh = alerts_mod.evaluate_item(item, current_price=price)
        new = alerts_mod.diff_new_alerts(item, fresh)
        for a in new:
            alerts_mod.record_alert(name, a)
            fired.append({"name": name, **a})
        item["triggered"] = bool(item.get("triggered_rules"))
    watchlist_mod.save_watchlist(items)

    for a in fired:
        title = "SkinVault"
        body = f"{a['name']}: {a['label']}"
        tray.notify(title, body, a.get("severity", "info"))
        events.publish("notification",
                        {"title": title, "body": body,
                         "severity": a.get("severity", "info")})

    payload = _payload()
    payload["fired"] = fired
    return jsonify(payload)


@bp.route("/api/watchlist/log")
def log():
    entries = alerts_mod.load_alerts_log()
    return jsonify({"entries": list(reversed(entries))[:100]})
