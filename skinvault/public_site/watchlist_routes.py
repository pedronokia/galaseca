"""Blueprint da watchlist pessoal -- `/conta/watchlist`.

Avalia as regras com `alerts.evaluate_item` (sem alteração), usando só
dado já compartilhado -- preço (`PriceCache`), volume/oferta
(`signals.load_item_volume`/`load_item_supply`) e nota (último scan
público). Zero chamada nova à Steam por visita à página -- mesmo
princípio da Fase 1.
"""
from __future__ import annotations

import math

from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
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
            valor = float(bruto)
        except ValueError:
            raise ValueError(campo)
        if not math.isfinite(valor) or valor <= 0:
            raise ValueError(campo)
        if campo in ("price_drop_pct", "score_above") and valor > 100:
            raise ValueError(campo)
        if campo == "score_above" and not valor.is_integer():
            raise ValueError(campo)
        rules[campo] = valor
    return rules


def _notificar_discord(steamid: str, items_avaliados: list[dict],
                       url: str) -> None:
    """Manda os alertas disparados AGORA pro Discord do próprio usuário,
    um item de cada vez, respeitando o dedup de 1h (user_webhook). Falha
    de rede/URL ausente nunca derruba a página -- `discord_notify.enviar`
    já devolve False em qualquer erro, sem levantar.

    `url` vem de fora (não busca sozinho) -- `listar()` já precisa do
    mesmo valor pro template, e cada `get_webhook_url` é uma conexão
    SQLite nova (`user_store.load_user_json` via `db.connect`); buscar
    duas vezes na mesma requisição dobrava a leitura à toa."""
    if not url:
        return
    for it in items_avaliados:
        if not it["disparado"]:
            continue
        if not user_webhook.deve_notificar(steamid, it["name"]):
            continue
        texto = (f"AlertaSkins: {it['name_fmt']} disparou um alerta -- "
                f"{'; '.join(a['label'] for a in it['alertas'])}")
        if discord_notify.enviar(url, texto):
            user_webhook.marcar_notificado(steamid, it["name"])


@bp.route("/conta/watchlist")
@login_required
def listar():
    steamid = session["steamid"]
    items = user_watchlist.load_items(steamid)
    avaliados = _avaliar(items)
    webhook_url = user_webhook.get_webhook_url(steamid)
    _notificar_discord(steamid, avaliados, webhook_url)
    return render_template(
        "conta_watchlist.html", items=avaliados,
        csrf_token=csrf_token(),
        webhook_url=webhook_url,
        erro_webhook=bool(request.args.get("erro_webhook")),
    )


@bp.route("/conta/watchlist/webhook", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def salvar_webhook():
    steamid = session["steamid"]
    url = (request.form.get("webhook_url") or "").strip()
    # URL vazia limpa o webhook (válido); URL não-vazia precisa bater
    # com o formato oficial da Discord -- ver discord_notify.url_valida.
    if url and not discord_notify.url_valida(url):
        return redirect(url_for("watchlist.listar", erro_webhook="1"))
    user_webhook.set_webhook_url(steamid, url)
    return redirect(url_for("watchlist.listar"))


@bp.route("/conta/watchlist", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def adicionar():
    steamid = session["steamid"]
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Informe o nome do item.", "error")
        return redirect(url_for("watchlist.listar"))

    target_raw = (request.form.get("target") or "").strip()
    try:
        target = float(target_raw) if target_raw else 0.0
    except ValueError:
        flash(
            "O preço-alvo precisa ser um número válido e igual ou maior que zero.",
            "error",
        )
        return redirect(url_for("watchlist.listar"))
    if not math.isfinite(target) or target < 0:
        flash(
            "O preço-alvo precisa ser um número válido e igual ou maior que zero.",
            "error",
        )
        return redirect(url_for("watchlist.listar"))

    user_watchlist.add_item(steamid, name, target)
    return redirect(url_for("watchlist.listar"))


@bp.route("/conta/watchlist/<name>/regras", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def editar_regras(name: str):
    steamid = session["steamid"]
    try:
        rules = _rules_do_form()
    except ValueError:
        flash(
            "As regras não foram salvas. Use números maiores que zero; "
            "percentuais e nota devem ficar entre 0 e 100, e a nota deve "
            "ser inteira.",
            "error",
        )
        return redirect(url_for("watchlist.listar"))

    baseline_raw = (request.form.get("baseline_price") or "").strip()
    baseline = None
    if baseline_raw:
        try:
            baseline = float(baseline_raw)
        except ValueError:
            flash(
                "O preço-base precisa ser um número válido maior que zero.",
                "error",
            )
            return redirect(url_for("watchlist.listar"))
        if not math.isfinite(baseline) or baseline <= 0:
            flash(
                "O preço-base precisa ser um número válido maior que zero.",
                "error",
            )
            return redirect(url_for("watchlist.listar"))

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
