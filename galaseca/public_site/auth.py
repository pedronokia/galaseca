"""Login exigido e proteção CSRF compartilhados pelas rotas pessoais."""
from __future__ import annotations

import secrets
from functools import wraps

from flask import abort, redirect, request, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("steamid"):
            return redirect(url_for("account.login"))
        return view(*args, **kwargs)
    return wrapped


def csrf_token() -> str:
    """Token por sessão pras POST autenticadas -- sem isto, qualquer site
    externo poderia montar um form que muda seus dados só por você estar
    logado (CSRF clássico)."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def csrf_valid(token: "str | None") -> bool:
    """`token` precisa existir: sem isto, uma sessao que NUNCA visitou
    uma pagina com formulario (entao nunca gerou token) e um form
    forjado que tambem omite o campo comparariam None == None e
    passariam -- o cenario exato que o CSRF tenta impedir.

    `secrets.compare_digest` (tempo constante) em vez de `==`/`!=` --
    achado de auditoria, 2026-11-04: comparar o token assim caractere a
    caractere deixa vazar, pelo tempo de resposta, em qual posição a
    tentativa divergiu do valor certo. Risco baixo na prática (ruído de
    rede atrapalha a medição), mas é a defesa padrão recomendada pra
    comparação de segredo, e não muda nenhum comportamento."""
    stored = session.get("csrf_token")
    if not stored or not token:
        return False
    return secrets.compare_digest(token, stored)


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not csrf_valid(request.form.get("csrf_token")):
            abort(403)
        return view(*args, **kwargs)
    return wrapped
