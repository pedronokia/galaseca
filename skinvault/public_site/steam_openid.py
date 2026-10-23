"""Login "Entrar com Steam" -- Steam OpenID 2.0, NÃO a sessão revertida.

O F10 (revertido em 2026-08-07, ver AGENTS.md) automatizava uma sessão
LOGADA com cookies pra ler dado privado -- é isso que o Steam Subscriber
Agreement proíbe de forma ampla. Este módulo é outra coisa: o fluxo
público que qualquer site usa pra "Entrar com Steam" -- o navegador do
visitante é redirecionado pro domínio da própria Steam, ele loga LÁ (nunca
digita senha aqui), e a Steam devolve só um SteamID64 verificado. Sem
cookie, sem senha, sem automação de conta.
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

import httpx

STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"

_CLAIMED_ID_RE = re.compile(
    r"^https://steamcommunity\.com/openid/id/(\d+)$")


def login_redirect_url(return_to: str, realm: str) -> str:
    """URL pra onde redirecionar o navegador do visitante.

    `return_to`/`realm` vêm de `request.url_root` em tempo de requisição
    (ver account.py) -- funciona local e depois de hospedado, sem
    configurar domínio agora.
    """
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": return_to,
        "openid.realm": realm,
        "openid.identity":
            "http://specs.openid.net/auth/2.0/identifier_select",
        "openid.claimed_id":
            "http://specs.openid.net/auth/2.0/identifier_select",
    }
    return f"{STEAM_OPENID_URL}?{urlencode(params)}"


def verify_callback(args: "dict[str, str]") -> "str | None":
    """Verifica a volta da Steam. Devolve o SteamID64 ou None se inválida.

    `args`: query string da callback (ex.: `request.args` como dict).
    Reenvia os MESMOS parâmetros à Steam com `openid.mode=
    check_authentication` -- é assim que o OpenID 2.0 confirma que a
    assinatura é legítima e ninguém forjou a volta (visitante malicioso
    batendo direto na rota de callback com um claimed_id de outra
    pessoa).
    """
    claimed_id = args.get("openid.claimed_id", "")
    m = _CLAIMED_ID_RE.match(claimed_id)
    if not m:
        return None

    verify_params = dict(args)
    verify_params["openid.mode"] = "check_authentication"
    try:
        resp = httpx.post(STEAM_OPENID_URL, data=verify_params, timeout=10)
    except httpx.HTTPError:
        return None

    if "is_valid:true" not in resp.text:
        return None
    return m.group(1)
