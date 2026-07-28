"""Login na Steam por QR (device auth) -- sem navegador, sem senha.

POR QUE ISTO SUBSTITUI O steam_login_dialog
-------------------------------------------
O fluxo antigo abre um Chrome com --remote-debugging-port, espera o
usuario logar na pagina da Steam e extrai os cookies por CDP sobre
WebSocket. Isso arrasta uma dependencia dura de navegador Chromium
instalado -- login simplesmente morria em maquina sem ele.

Aqui o proprio app gera o QR, o usuario escaneia com o Steam Mobile e
confirma no celular. Nenhuma janela externa, nenhuma senha passando pelo
app, nenhum navegador.

O FLUXO (verificado em 2026-07-28, responde JSON puro, sem protobuf)
--------------------------------------------------------------------
1. BeginAuthSessionViaQR  -> client_id, request_id, challenge_url, interval
2. desenha challenge_url como QR e espera
3. PollAuthSessionStatus  -> enquanto pendente: had_remote_interaction
                          -> apos confirmar: refresh_token + access_token
4. finalizelogin          -> troca o refresh_token pelos cookies web
                             (steamLoginSecure), que e' o que o resto do
                             app consome

Logica pura separada da rede: `_http_post` e' o unico ponto que toca a
rede e o unico ponto de mock nos testes, igual ao steam_api.py.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

_AUTH = "https://api.steampowered.com/IAuthenticationService"
_FINALIZE = "https://login.steampowered.com/jwt/finalizelogin"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# platform_type=2 (SteamClient). Com 0/WebBrowser a Steam recusa o QR.
_PLATFORM_STEAM_CLIENT = "2"

OK = "ok"
PENDING = "pending"
EXPIRED = "expired"
ERROR = "error"

# A sessao QR morre sozinha; nao adianta pollar pra sempre.
_MAX_WAIT_S = 180.0


def _http_post(url: str, campos: dict,
               timeout: float = 30.0) -> "tuple[int, str | None]":
    """POST form-encoded. (status, body). status 0 = erro de rede.

    Unico ponto que toca a rede -- e' onde os testes mockam.
    """
    dados = urllib.parse.urlencode(campos).encode()
    req = urllib.request.Request(url, data=dados, headers={
        "User-Agent": _UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "Origin": "https://steamcommunity.com",
        "Referer": "https://steamcommunity.com/",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _json_ou_none(body: "str | None") -> "dict | None":
    if not body:
        return None
    try:
        d = json.loads(body)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def begin_session(device_name: str = "SkinVault") -> "tuple[str, dict]":
    """Abre a sessao QR. (status, {client_id, request_id, challenge_url,
    interval}).

    `challenge_url` e' o texto que vai dentro do QR.
    """
    code, body = _http_post(f"{_AUTH}/BeginAuthSessionViaQR/v1/", {
        "device_friendly_name": device_name,
        "platform_type": _PLATFORM_STEAM_CLIENT,
    })
    if code != 200:
        return ERROR, {}
    d = _json_ou_none(body)
    resp = (d or {}).get("response") or {}
    if not resp.get("client_id") or not resp.get("challenge_url"):
        return ERROR, {}
    try:
        intervalo = float(resp.get("interval") or 5)
    except (TypeError, ValueError):
        intervalo = 5.0
    return OK, {
        "client_id": str(resp["client_id"]),
        "request_id": str(resp.get("request_id") or ""),
        "challenge_url": str(resp["challenge_url"]),
        "interval": max(1.0, intervalo),
    }


def poll_once(client_id: str, request_id: str) -> "tuple[str, dict]":
    """Uma checagem. (status, dados).

    status:
      pending -- ninguem confirmou ainda
      ok      -- veio refresh_token
      expired -- a Steam invalidou a sessao (QR vencido)
      error   -- rede ou resposta ilegivel
    """
    code, body = _http_post(f"{_AUTH}/PollAuthSessionStatus/v1/", {
        "client_id": client_id,
        "request_id": request_id,
    })
    if code != 200:
        # A Steam devolve 400 quando o client_id ja' nao vale mais.
        return (EXPIRED if code == 400 else ERROR), {}
    d = _json_ou_none(body)
    if d is None:
        return ERROR, {}
    resp = d.get("response") or {}
    if resp.get("refresh_token"):
        return OK, {
            "refresh_token": resp["refresh_token"],
            "access_token": resp.get("access_token") or "",
            "account_name": resp.get("account_name") or "",
        }
    # `new_challenge_url` significa QR rotacionado: a UI precisa redesenhar.
    if resp.get("new_challenge_url"):
        return PENDING, {"challenge_url": str(resp["new_challenge_url"]),
                         "client_id": str(resp.get("new_client_id")
                                          or client_id)}
    return PENDING, {"had_remote_interaction":
                     bool(resp.get("had_remote_interaction"))}


def finalize(refresh_token: str,
             session_id: str = "") -> "tuple[str, dict]":
    """Troca o refresh_token pelos cookies web. (status, {dominio: cookie}).

    E' este passo que produz o steamLoginSecure -- o mesmo cookie que o
    fluxo antigo arrancava do Chrome via CDP.
    """
    if not refresh_token:
        return ERROR, {}
    code, body = _http_post(_FINALIZE, {
        "nonce": refresh_token,
        "sessionid": session_id or "skinvault",
        "redir": "https://steamcommunity.com/login/home/?goto=",
    })
    if code != 200:
        return ERROR, {}
    d = _json_ou_none(body)
    if not d:
        return ERROR, {}
    transferencias = d.get("transfer_info") or []
    if not transferencias:
        return ERROR, {}
    return OK, {"transfer_info": transferencias,
                "steamID": str(d.get("steamID") or "")}


def wait_for_confirmation(sessao: dict, poll=poll_once,
                          sleep=time.sleep,
                          now=time.monotonic,
                          max_wait: float = _MAX_WAIT_S,
                          on_new_qr=None) -> "tuple[str, dict]":
    """Espera o usuario confirmar no celular. (status, dados).

    `on_new_qr(url)` e' chamado quando a Steam rotaciona o codigo -- a UI
    precisa redesenhar, senao o usuario escaneia um QR morto.

    Os parametros poll/sleep/now sao injetaveis pra o teste nao dormir de
    verdade nem depender de rede.
    """
    client_id = sessao.get("client_id") or ""
    request_id = sessao.get("request_id") or ""
    intervalo = float(sessao.get("interval") or 5)
    limite = now() + max_wait
    while now() < limite:
        status, dados = poll(client_id, request_id)
        if status == OK:
            return OK, dados
        if status in (EXPIRED, ERROR):
            return status, dados
        if dados.get("challenge_url"):
            client_id = dados.get("client_id") or client_id
            if on_new_qr:
                on_new_qr(dados["challenge_url"])
        sleep(intervalo)
    return EXPIRED, {}


def qr_matrix(challenge_url: str) -> "list[list[bool]]":
    """Matriz booleana do QR. Separada do desenho pra poder testar.

    Usa segno (Python puro). Escrever encoder proprio seria reinventar
    algo resolvido, num caminho critico onde erro silencioso vira "o
    login nao funciona e ninguem sabe por que".
    """
    import segno
    q = segno.make(challenge_url, error="l")
    return [list(linha) for linha in q.matrix]
