"""Blueprint da watchlist pessoal -- `/conta/watchlist`.

Avalia as regras com `alerts.evaluate_item` (sem alteração), usando só
dado já compartilhado -- preço (`PriceCache`), volume/oferta
(`signals.load_item_volume`/`load_item_supply`) e nota (último scan
público). Zero chamada nova à Steam por visita à página -- mesmo
princípio da Fase 1.
"""
from __future__ import annotations

from flask import (
    Blueprint, redirect, render_template, request, session, url_for,
)

from skinvault import alerts, scan_store, signals
from skinvault.localization import localize_name
from skinvault.prices import PriceCache
from skinvault.public_site import discord_notify, fmt, user_watchlist, user_webhook
from skinvault.public_site.auth import csrf_protect, csrf_token, login_required
from skinvault.public_site.rate_limit import (
    MUTATION_MAX_HITS, MUTATION_WINDOW_S, rate_limited,
)

bp = Blueprint("watchlist", __name__)

_RULE_FIELDS = (
    "price_below", "price_drop_pct", "volume_spike", "supply_drop",
    "score_above",
)


def _score_lookup() -> dict:
    """{name: score} do último scan público -- leitura, sem rede."""
    scan = scan_store.load_last_scan()
    if not scan:
        return {}
    return {r["name"]: r.get("score") for r in scan["results"]}


def _avaliar(items: list[dict]) -> list[dict]:
    cache = PriceCache()
    scores = _score_lookup()
    out = []
    for it in items:
        name = it["name"]
        price = cache.get(name)
        alertas = alerts.evaluate_item(
            it, price,
            volume_history=signals.load_item_volume(name),
            supply_history=signals.load_item_supply(name),
            current_score=scores.get(name),
        )
        out.append({
            **it,
            "name_fmt": localize_name(name),
            "price_fmt": fmt.brl(price),
            "rules_resumo": alerts.format_rules_summary(it.get("rules"))
                            or "Sem regra configurada",
            "alertas": alertas,
            "disparado": bool(alertas),
        })
    return out


def _rules_do_form() -> dict:
    rules = {}
    for campo in _RULE_FIELDS:
        bruto = (request.form.get(campo) or "").strip()
        if not bruto:
            continue
        try:
            rules[campo] = float(bruto)
        except ValueError:
            continue
    return rules


def _notificar_discord(steamid: str, items_avaliados: list[dict]) -> None:
    """Manda os alertas disparados AGORA pro Discord do próprio usuário,
    um item de cada vez, respeitando o dedup de 1h (user_webhook). Falha
    de rede/URL ausente nunca derruba a página -- `discord_notify.enviar`
    já devolve False em qualquer erro, sem levantar."""
    url = user_webhook.get_webhook_url(steamid)
    if not url:
        return
    for it in items_avaliados:
        if not it["disparado"]:
            continue
        if not user_webhook.deve_notificar(steamid, it["name"]):
            continue
        texto = (f"SkinVault: {it['name_fmt']} disparou um alerta -- "
                f"{'; '.join(a['label'] for a in it['alertas'])}")
        if discord_notify.enviar(url, texto):
            user_webhook.marcar_notificado(steamid, it["name"])


@bp.route("/conta/watchlist")
@login_required
def listar():
    steamid = session["steamid"]
    items = user_watchlist.load_items(steamid)
    avaliados = _avaliar(items)
    _notificar_discord(steamid, avaliados)
    return render_template(
        "conta_watchlist.html", items=avaliados,
        csrf_token=csrf_token(),
        webhook_url=user_webhook.get_webhook_url(steamid),
    )


@bp.route("/conta/watchlist/webhook", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def salvar_webhook():
    steamid = session["steamid"]
    url = (request.form.get("webhook_url") or "").strip()
    user_webhook.set_webhook_url(steamid, url)
    return redirect(url_for("watchlist.listar"))


@bp.route("/conta/watchlist", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def adicionar():
    steamid = session["steamid"]
    name = (request.form.get("name") or "").strip()
    if name:
        target_raw = (request.form.get("target") or "").strip()
        try:
            target = float(target_raw) if target_raw else 0.0
        except ValueError:
            target = 0.0
        user_watchlist.add_item(steamid, name, target)
    return redirect(url_for("watchlist.listar"))


@bp.route("/conta/watchlist/<name>/regras", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def editar_regras(name: str):
    steamid = session["steamid"]
    rules = _rules_do_form()
    baseline_raw = (request.form.get("baseline_price") or "").strip()
    try:
        baseline = float(baseline_raw) if baseline_raw else None
    except ValueError:
        baseline = None
    # Sem baseline informado mas com price_drop_pct: comeca a contar a
    # queda a partir do preco guardado agora.
    if rules.get("price_drop_pct") and baseline is None:
        baseline = PriceCache().get(name)
    user_watchlist.update_rules(steamid, name, rules, baseline_price=baseline)
    return redirect(url_for("watchlist.listar"))


@bp.route("/conta/watchlist/<name>/remover", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def remover(name: str):
    steamid = session["steamid"]
    user_watchlist.remove_item(steamid, name)
    return redirect(url_for("watchlist.listar"))
