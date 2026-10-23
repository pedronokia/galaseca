"""Blueprint de conta: "Entrar com Steam" + portfólio pessoal.

O dashboard público (`server.py`/`index.html`) continua anônimo e sem
conta, como na Fase 1 -- isto aqui é opcional, só pra quem quiser
acompanhar a própria carteira.
"""
from __future__ import annotations

import secrets
from functools import wraps

from flask import (
    Blueprint, abort, redirect, render_template, request, session, url_for,
)

from skinvault import portfolio
from skinvault.localization import localize_name
from skinvault.prices import PriceCache
from skinvault.public_site import steam_openid, user_portfolio, user_store
from skinvault.ui.profile_fetcher import fetch_public_profile

bp = Blueprint("account", __name__)


def _brl(v: "float | None") -> str:
    """Cópia mínima de `ui/theme.py:brl` -- este pacote não importa
    PyQt6 de propósito (ver AGENTS.md/plano da Fase 1)."""
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _formatar_linhas(avaliacao: dict) -> dict:
    """Acrescenta campos *_fmt pro template -- mesmo padrão de
    `server.py:_candidatos` (formata em Python, template fica simples)."""
    for row in avaliacao["rows"]:
        row["name_fmt"] = localize_name(row["name"])
        row["price_fmt"] = _brl(row.get("price"))
        row["cost_fmt"] = _brl(row.get("cost"))
        row["pnl_fmt"] = _brl(row.get("pnl"))
    t = avaliacao["totals"]
    t["cost_fmt"] = _brl(t.get("cost"))
    t["cost_known_fmt"] = _brl(t.get("cost_known"))
    t["market_fmt"] = _brl(t.get("market"))
    t["net_if_sold_fmt"] = _brl(t.get("net_if_sold"))
    t["pnl_fmt"] = _brl(t.get("pnl"))
    return avaliacao


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("steamid"):
            return redirect(url_for("account.login"))
        return view(*args, **kwargs)
    return wrapped


def _csrf_token() -> str:
    """Token por sessão pras POST de /conta -- sem isto, qualquer site
    externo poderia montar um form que adiciona/remove posição no seu
    nome só por você estar logado (CSRF clássico)."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        token = session.get("csrf_token")
        # `token` precisa existir: sem isto, uma sessao que NUNCA visitou
        # uma pagina com formulario (entao nunca gerou token) e um form
        # forjado que tambem omite o campo comparariam None == None e
        # passariam -- o cenario exato que o CSRF tenta impedir.
        if not token or request.form.get("csrf_token") != token:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/login")
def login():
    return_to = request.url_root.rstrip("/") + url_for("account.login_callback")
    realm = request.url_root
    return redirect(steam_openid.login_redirect_url(return_to, realm))


@bp.route("/login/callback")
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
    avaliacao = _formatar_linhas(
        portfolio.evaluate_portfolio(positions, PriceCache().get))
    return render_template(
        "conta.html", usuario=usuario, avaliacao=avaliacao,
        csrf_token=_csrf_token(),
    )


@bp.route("/conta/posicoes", methods=["POST"])
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
@login_required
@csrf_protect
def remover_posicao(name: str):
    steamid = session["steamid"]
    user_portfolio.remove_position(steamid, name)
    return redirect(url_for("account.conta"))
