"""Blueprint de conta: "Entrar com Steam" + portfólio pessoal.

O dashboard público (`server.py`/`index.html`) continua anônimo e sem
conta, como na Fase 1 -- isto aqui é opcional, só pra quem quiser
acompanhar a própria carteira.
"""
from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from skinvault import portfolio
from skinvault.localization import localize_name
from skinvault.prices import PriceCache
from skinvault.public_site import (
    fmt, steam_openid, user_history, user_portfolio, user_store,
)
from skinvault.public_site.auth import csrf_protect, csrf_token, login_required
from skinvault.public_site.rate_limit import (
    LOGIN_MAX_HITS, LOGIN_WINDOW_S, MUTATION_MAX_HITS, MUTATION_WINDOW_S,
    rate_limited,
)
from skinvault.ui.profile_fetcher import fetch_public_profile

bp = Blueprint("account", __name__)


def _formatar_linhas(avaliacao: dict) -> dict:
    """Acrescenta campos *_fmt pro template -- mesmo padrão de
    `server.py:_candidatos` (formata em Python, template fica simples)."""
    for row in avaliacao["rows"]:
        row["name_fmt"] = localize_name(row["name"])
        row["price_fmt"] = fmt.brl(row.get("price"))
        row["cost_fmt"] = fmt.brl(row.get("cost"))
        row["pnl_fmt"] = fmt.brl(row.get("pnl"))
    t = avaliacao["totals"]
    t["cost_fmt"] = fmt.brl(t.get("cost"))
    t["cost_known_fmt"] = fmt.brl(t.get("cost_known"))
    t["market_fmt"] = fmt.brl(t.get("market"))
    t["net_if_sold_fmt"] = fmt.brl(t.get("net_if_sold"))
    t["pnl_fmt"] = fmt.brl(t.get("pnl"))
    return avaliacao


@bp.route("/login")
@rate_limited(LOGIN_MAX_HITS, LOGIN_WINDOW_S)
def login():
    return_to = request.url_root.rstrip("/") + url_for("account.login_callback")
    realm = request.url_root
    return redirect(steam_openid.login_redirect_url(return_to, realm))


@bp.route("/login/callback")
@rate_limited(LOGIN_MAX_HITS, LOGIN_WINDOW_S)
def login_callback():
    steamid = steam_openid.verify_callback(request.args.to_dict())
    if not steamid:
        return redirect(url_for("index"))
    perfil = fetch_public_profile(steamid) or {}
    user_store.upsert_user(
        steamid,
        persona_name=perfil.get("name"),
        avatar_url=perfil.get("avatar_url"),
    )
    session["steamid"] = steamid
    return redirect(url_for("account.conta"))


@bp.route("/logout")
def logout():
    session.pop("steamid", None)
    return redirect(url_for("index"))


@bp.route("/conta")
@login_required
def conta():
    steamid = session["steamid"]
    usuario = user_store.get_user(steamid)
    positions = user_portfolio.load_positions(steamid)
    # Preço vem do mesmo cache compartilhado da Fase 1 -- leitura pura,
    # sem rede. Se o item nunca foi escaneado, a linha some sem preço
    # (igual ao app local quando a Steam não respondeu).
    avaliacao_bruta = portfolio.evaluate_portfolio(positions, PriceCache().get)
    # Grava o ponto de histórico ANTES de formatar -- precisa do valor
    # numérico (totals.market), não do "_fmt" em string. Dedup embutido:
    # visitar /conta duas vezes seguidas sem nada mudar não dobra a série.
    user_history.record_if_changed(steamid, avaliacao_bruta["totals"]["market"])
    avaliacao = _formatar_linhas(avaliacao_bruta)
    return render_template(
        "conta.html", usuario=usuario, avaliacao=avaliacao,
        csrf_token=csrf_token(),
    )


@bp.route("/conta/posicoes", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def adicionar_posicao():
    steamid = session["steamid"]
    name = (request.form.get("name") or "").strip()
    if name:
        cost_raw = (request.form.get("cost") or "").strip()
        cost = float(cost_raw) if cost_raw else None
        try:
            quantity = max(1, int(request.form.get("quantity") or 1))
        except ValueError:
            quantity = 1
        user_portfolio.add_position(steamid, name, cost, quantity)
    return redirect(url_for("account.conta"))


@bp.route("/conta/posicoes/<name>/custo", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def editar_custo(name: str):
    steamid = session["steamid"]
    cost_raw = (request.form.get("cost") or "").strip()
    if cost_raw:
        try:
            user_portfolio.update_position_cost(steamid, name, float(cost_raw))
        except ValueError:
            pass
    return redirect(url_for("account.conta"))


@bp.route("/conta/posicoes/<name>/remover", methods=["POST"])
@rate_limited(MUTATION_MAX_HITS, MUTATION_WINDOW_S)
@login_required
@csrf_protect
def remover_posicao(name: str):
    steamid = session["steamid"]
    user_portfolio.remove_position(steamid, name)
    return redirect(url_for("account.conta"))
