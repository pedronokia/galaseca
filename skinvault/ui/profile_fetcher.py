"""Busca avatar + nome do perfil Steam publico (F11).

Endpoint legado e' estavel: https://steamcommunity.com/profiles/{id}?xml=1
retorna XML do perfil publico (sem login). Avatar fica em data/avatars/.

Cache em data/steam_profiles.json com TTL 24h. Falha silenciosa: caller
recebe None e usa fallback (silhueta generica + steamid como nome).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from skinvault._paths import DATA_DIR

_PROFILES_PATH = DATA_DIR / "steam_profiles.json"
_AVATARS_DIR = DATA_DIR / "avatars"
_TTL_SECONDS = 24 * 3600
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"


def _http_get(url: str, timeout: float = 10.0) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def _load_cache() -> dict:
    try:
        return json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        _PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PROFILES_PATH.write_text(json.dumps(data, indent=2),
                                  encoding="utf-8")
    except OSError:
        pass


def parse_profile_xml(xml: str) -> dict | None:
    """Extrai {steamid, name, avatar_url} do XML do perfil. Regex pra evitar
    dependencia de XML parser e mantem robusto a CDATA."""
    if not xml or "<profile>" not in xml:
        return None

    def _get(tag: str) -> str | None:
        m = re.search(
            rf"<{tag}>\s*(?:<!\[CDATA\[(.*?)\]\]>|([^<]*))\s*</{tag}>",
            xml, re.DOTALL,
        )
        if not m:
            return None
        return (m.group(1) or m.group(2) or "").strip()

    steamid = _get("steamID64")
    if not steamid:
        return None
    name = _get("steamID") or steamid
    avatar = _get("avatarFull") or _get("avatarMedium") or _get("avatarIcon")
    return {
        "steamid": steamid,
        "name": name,
        "avatar_url": avatar,
    }


def fetch_public_profile(steamid: str,
                         force: bool = False) -> dict | None:
    """Retorna {steamid, name, avatar_url, avatar_path, fetched_at}.

    Usa cache de TTL 24h. force=True ignora cache.
    Retorna None em falha total (rede + sem cache).
    """
    if not steamid:
        return None
    cache = _load_cache()
    entry = cache.get(steamid)
    now = time.time()

    if not force and entry and now - entry.get("fetched_at", 0) < _TTL_SECONDS:
        return entry

    xml_bytes = _http_get(
        f"https://steamcommunity.com/profiles/{steamid}?xml=1"
    )
    if xml_bytes is None:
        return entry  # cache stale > nada
    try:
        xml = xml_bytes.decode("utf-8", "replace")
    except Exception:
        return entry

    parsed = parse_profile_xml(xml)
    if not parsed:
        return entry

    avatar_path = None
    if parsed.get("avatar_url"):
        avatar_path = _download_avatar(steamid, parsed["avatar_url"])

    record = {
        **parsed,
        "avatar_path": avatar_path,
        "fetched_at": now,
    }
    cache[steamid] = record
    _save_cache(cache)
    return record


def _download_avatar(steamid: str, url: str) -> str | None:
    try:
        _AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    data = _http_get(url, timeout=15.0)
    if data is None:
        return None
    path = _AVATARS_DIR / f"{steamid}.jpg"
    try:
        path.write_bytes(data)
        return str(path)
    except OSError:
        return None


def load_cached_profile(steamid: str) -> dict | None:
    """Le do cache sem bater na rede. Util pra UI no startup."""
    if not steamid:
        return None
    return _load_cache().get(steamid)


def load_avatar_bytes(steamid: str) -> bytes | None:
    """Le avatar em disco se existir."""
    if not steamid:
        return None
    path = _AVATARS_DIR / f"{steamid}.jpg"
    try:
        return path.read_bytes()
    except OSError:
        return None
