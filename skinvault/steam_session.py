"""Sessao autenticada Steam -- cookies de steamcommunity.com.

Quebra explicita da filosofia "Zero login" das fases F1-F9: aqui o usuario
opta por logar pra liberar sync de dados privados (historico de market,
listagens ativas, trade offers). Cookies sao guardados em data/steam_session.json.

Aviso ao usuario sempre que essa sessao for usada: cookies sao credenciais,
nao compartilhar o arquivo.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from skinvault._paths import DATA_DIR

logger = logging.getLogger(__name__)

_DEFAULT_PATH = DATA_DIR / "steam_session.json"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"

# Cookies que importam pra Steam autenticada
_AUTH_COOKIES = ("sessionid", "steamLoginSecure", "steamRefresh_steam",
                 "browserid", "steamCountry")


@dataclass
class SteamSession:
    steamid: str
    cookies: dict = field(default_factory=dict)
    captured_at: float = 0.0
    validated_at: float = 0.0

    def cookie_header(self) -> str:
        """Header Cookie pronto pra urllib/httpx."""
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items() if v)

    def is_complete(self) -> bool:
        """Sessao minima viavel: precisa do steamLoginSecure."""
        return bool(self.steamid) and bool(self.cookies.get("steamLoginSecure"))


def extract_steamid_from_cookie(cookies: dict) -> str | None:
    """O cookie steamLoginSecure codifica o SteamID64 no prefixo do valor:
    '76561198XXXXXXXXX%7C%7C<token>' (onde %7C%7C = ||).
    """
    raw = cookies.get("steamLoginSecure") or ""
    if not raw:
        return None
    decoded = urllib.parse.unquote(raw)
    candidate = decoded.split("||", 1)[0]
    candidate = candidate.strip()
    if candidate.isdigit() and len(candidate) >= 16:
        return candidate
    return None


def persist(session: SteamSession, path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_warning": "CONTEM CREDENCIAIS DE SESSAO STEAM. NAO COMPARTILHAR.",
            **asdict(session),
        }
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.exception("Falha ao persistir sessao em %s: %s", p, exc)


def load(path: Path | str = _DEFAULT_PATH) -> SteamSession | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Nenhuma sessao previa para carregar: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    data.pop("_warning", None)
    try:
        return SteamSession(
            steamid=str(data.get("steamid", "")),
            cookies=dict(data.get("cookies", {})),
            captured_at=float(data.get("captured_at", 0.0)),
            validated_at=float(data.get("validated_at", 0.0)),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("Sessao corrompida: %s", exc)
        return None


def clear(path: Path | str = _DEFAULT_PATH) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Falha ao limpar sessao: %s", exc)


def validate(session: SteamSession, timeout: float = 10.0) -> bool:
    """Bate em https://steamcommunity.com/my/ com cookies. Se o redirect final
    leva a /profiles/{id} ou /id/{vanity}, sessao OK. Se cai em /login/, expirou.

    Atualiza session.validated_at em sucesso.
    """
    if not session.is_complete():
        return False
    final_url = _follow_redirect("https://steamcommunity.com/my/",
                                 session.cookie_header(), timeout)
    if not final_url:
        return False
    if "/login" in final_url:
        return False
    if "/profiles/" in final_url or "/id/" in final_url:
        session.validated_at = time.time()
        return True
    return False


def _follow_redirect(url: str, cookie_header: str, timeout: float) -> str | None:
    """GET com cookies, segue redirects, devolve URL final (ou None em erro)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Cookie": cookie_header}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.geturl()
    except urllib.error.HTTPError as exc:
        return getattr(exc, "url", None) or url
    except Exception as exc:
        logger.info("Redirect follow falhou: %s", exc)
        return None


def merge_cookies(existing: dict, new: dict) -> dict:
    """Combina dicts de cookies, mantendo so' os relevantes pra auth."""
    merged = dict(existing)
    for k, v in new.items():
        if k in _AUTH_COOKIES and v:
            merged[k] = v
    return merged


# ── renovacao automatica de sessao (refresh token) ────────────
# O steamLoginSecure (token de acesso web) expira em ~24h. O
# steamRefresh_steam e' um refresh token de longa duracao (~1 ano) que
# permite gerar novos tokens de acesso sem novo login interativo.
#
# Fluxo web (audience web/renew/derive — NAO precisa do audience mobile
# que o IAuthenticationService/GenerateAccessTokenForApp exigiria):
#   1. POST login.steampowered.com/jwt/finalizelogin
#      (nonce=refresh_token, sessionid novo, redir community) -> JSON com
#      transfer_info: [{url, params:{nonce, auth}}, ...]
#   2. POST em cada transfer com {steamID, **params} -> Set-Cookie traz o
#      novo steamLoginSecure pro dominio daquele transfer
# Referencia do fluxo: DoctorMcKay/node-steam-session (getWebCookies).
_FINALIZE_URL = "https://login.steampowered.com/jwt/finalizelogin"
_REDIR = "https://steamcommunity.com/login/home/?goto="
_STEAM_HOSTS = ("steampowered.com", "steamcommunity.com")


def _refresh_token_from_cookies(cookies: dict) -> str | None:
    """Extrai o JWT puro do cookie steamRefresh_steam.

    Formato do cookie: 'steamid||jwt' (pode vir URL-encoded com %7C%7C).
    O finalizelogin espera so' o jwt (sem o prefixo steamid).
    """
    raw = cookies.get("steamRefresh_steam") or ""
    if not raw:
        return None
    decoded = urllib.parse.unquote(raw)
    parts = decoded.split("||", 1)
    token = parts[1] if len(parts) == 2 else decoded
    token = token.strip()
    return token or None


def _multipart_encode(fields: dict) -> tuple[bytes, str]:
    """Monta corpo multipart/form-data. Retorna (body, content_type).

    O jwt/finalizelogin + os transfers do Steam esperam multipart (mesmo
    encoding que o node-steam-session usa); form-urlencoded nao e' aceito
    de forma confiavel.
    """
    boundary = "----SkinVault" + secrets.token_hex(16)
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{name}"'.encode()
        )
        lines.append(b"")
        lines.append(str(value).encode())
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    return b"\r\n".join(lines), f"multipart/form-data; boundary={boundary}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Nao segue 3xx — deixa a resposta de redirect propagar como HTTPError.

    Critico pro fluxo de transfer: a Steam pode setar o steamLoginSecure
    num 302 e redirecionar. O urlopen padrao seguiria o redirect e os
    headers finais NAO trariam o Set-Cookie do hop intermediario. Com este
    handler o 302 vira HTTPError e lemos o Set-Cookie dele.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_no_redirect_opener = urllib.request.build_opener(_NoRedirect)


def _post_multipart(url: str, fields: dict, timeout: float,
                    extra_headers: dict | None = None,
                    ) -> tuple[int, bytes, list[str]] | None:
    """POST multipart. Retorna (status, body, set_cookie_headers) ou None.

    Usa opener sem-redirect: os transfers da Steam setam o cookie e
    redirecionam (3xx), entao o Set-Cookie e' lido do branch HTTPError.
    """
    body, content_type = _multipart_encode(fields)
    headers = {"User-Agent": _UA, "Content-Type": content_type}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST")
    try:
        with _no_redirect_opener.open(req, timeout=timeout) as resp:
            return (resp.status, resp.read(),
                    resp.headers.get_all("Set-Cookie") or [])
    except urllib.error.HTTPError as exc:
        try:
            return (exc.code, exc.read(),
                    exc.headers.get_all("Set-Cookie") or [])
        except Exception:
            return exc.code, b"", []
    except Exception as exc:
        logger.info("POST multipart falhou (%s): %s", url, exc)
        return None


def _extract_cookie_value(set_cookie_headers: list[str],
                          name: str) -> str | None:
    """Acha o valor de `name` numa lista de headers Set-Cookie."""
    prefix = f"{name}="
    for sc in set_cookie_headers:
        if sc.startswith(prefix):
            return sc[len(prefix):].split(";", 1)[0]
    return None


def refresh(session: SteamSession, timeout: float = 15.0) -> bool:
    """Renova o steamLoginSecure usando o steamRefresh_steam.

    Atualiza session.cookies (steamLoginSecure + sessionid) e captured_at
    em caso de sucesso. Nao faz nada destrutivo em falha (retorna False).
    """
    token = _refresh_token_from_cookies(session.cookies)
    if not token or not session.steamid:
        return False

    session_id = secrets.token_hex(12)
    fin = _post_multipart(
        _FINALIZE_URL,
        {"nonce": token, "sessionid": session_id, "redir": _REDIR},
        timeout,
        extra_headers={
            "Origin": "https://steamcommunity.com",
            "Referer": "https://steamcommunity.com/",
        },
    )
    if not fin:
        return False
    _status, raw, _ = fin
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return False
    transfers = data.get("transfer_info") or []
    if not transfers:
        return False

    tokens: dict[str, str] = {}  # host -> steamLoginSecure emitido
    for tr in transfers:
        url = tr.get("url") or ""
        params = tr.get("params") or {}
        # So' POSTamos em URLs https de dominios Steam (as URLs vem da
        # resposta da Steam, mas validamos por seguranca).
        if not url.startswith("https://"):
            continue
        host = urllib.parse.urlparse(url).hostname or ""
        if not any(host == h or host.endswith("." + h)
                   for h in _STEAM_HOSTS):
            continue
        res = _post_multipart(url, {"steamID": session.steamid, **params},
                              timeout)
        if not res:
            continue
        val = _extract_cookie_value(res[2], "steamLoginSecure")
        if val:
            tokens[host] = val

    # Prefere o token do dominio community — e' o que validate()/sync usam.
    # Os tokens sao audience-scoped: pegar o do store por engano (ex.: o
    # transfer community falhou) faria o validate() seguinte cair em /login.
    new_secure: str | None = None
    for host, val in tokens.items():
        if "steamcommunity.com" in host:
            new_secure = val
            break
    if new_secure is None and tokens:
        new_secure = next(iter(tokens.values()))
    if not new_secure:
        return False

    session.cookies["steamLoginSecure"] = new_secure
    session.cookies["sessionid"] = session_id
    session.captured_at = time.time()
    return True


def ensure_valid(session: SteamSession, timeout: float = 15.0) -> bool:
    """Garante sessao utilizavel: valida e, se expirou, tenta renovar.

    Retorna True se a sessao esta valida ao final (com ou sem refresh).
    Em sucesso de refresh, os cookies da `session` ja' foram atualizados
    in-place — o chamador deve persist() para nao perder a renovacao.
    """
    if validate(session, timeout):
        return True
    if refresh(session, timeout) and validate(session, timeout):
        return True
    return False
