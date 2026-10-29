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
