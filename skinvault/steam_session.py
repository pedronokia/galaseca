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
