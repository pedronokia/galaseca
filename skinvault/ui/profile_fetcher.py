"""Busca avatar + nome do perfil Steam publico (F11).

Endpoint legado e' estavel: https://steamcommunity.com/profiles/{id}?xml=1
retorna XML do perfil publico (sem login). Avatar fica em data/avatars/.

Cache em data/steam_profiles.json com TTL 24h. Falha silenciosa: caller
recebe None e usa fallback (silhueta generica + steamid como nome).
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time
from pathlib import Path

import httpx

from skinvault._paths import DATA_DIR, atomic_write_text

_PROFILES_PATH = DATA_DIR / "steam_profiles.json"
_AVATARS_DIR = DATA_DIR / "avatars"
_TTL_SECONDS = 24 * 3600
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"

# Protege o ciclo leitura-modificacao-escrita do cache (um JSON so',
# com entrada por steamid). Achado numa cacada dirigida por essa familia
# de bug, 2026-10-27: no site publico, `fetch_public_profile` roda
# dentro de um request do Flask toda vez que alguem loga -- dois
# visitantes DIFERENTES logando perto um do outro podiam fazer o
# segundo sobrescrever o arquivo inteiro com uma copia carregada ANTES
# do primeiro salvar, apagando a entrada do primeiro em silencio
# (self-cura no proximo cache miss, mas e' trabalho jogado fora e um
# `write` perdido de verdade). `atomic_write_text` so' protege contra
# arquivo corrompido por escrita cortada -- nao protege contra dois
# escritores concorrentes com snapshots diferentes do mesmo dict.
_cache_lock = threading.Lock()

# httpx (não urllib) com timeout via thread pool -- mesmo achado de
# `steam_api._http_get` (2026-10-26): urllib.request era especificamente
# sinalizado pela Steam onde httpx passava, e o timeout de socket do
# Python não cobre DNS pendurado. Este módulo roda dentro do request do
# Flask no login público -- um hang aqui travaria o worker do gunicorn
# que atendeu aquele visitante.
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="profile_fetcher_http")


def _http_get(url: str, timeout: float = 10.0) -> bytes | None:
    def _pedido():
        resp = httpx.get(url, headers={"User-Agent": _UA}, timeout=timeout,
                         follow_redirects=True)
        return resp.content if resp.status_code == 200 else None

    futuro = _EXECUTOR.submit(_pedido)
    try:
        return futuro.result(timeout=timeout)
    except Exception:
        return None


def _load_cache() -> dict:
    try:
        return json.loads(_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    try:
        atomic_write_text(_PROFILES_PATH, json.dumps(data, indent=2))
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
    with _cache_lock:
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
    # Re-le sob o lock em vez de reusar o `cache` carregado la' em cima --
    # outro steamid pode ter escrito uma entrada nova enquanto este
    # fazia a chamada de rede (fora do lock, de proposito: nao serializa
    # fetch lento atras de um lock).
    with _cache_lock:
        cache = _load_cache()
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


def apagar_perfil_cache(steamid: str) -> None:
    """Remove o avatar em disco + a entrada do cache desse steamid --
    achado 2026-10-26: `/conta/excluir` apagava o banco (portfólio/
    trades/watchlist) mas não isto, deixando um JPEG órfão e uma linha
    de cache pra trás depois de "excluir todos os meus dados"."""
    if not steamid:
        return
    try:
        cache = _load_cache()
        if steamid in cache:
            del cache[steamid]
            _save_cache(cache)
    except Exception:
        pass
    try:
        (_AVATARS_DIR / f"{steamid}.jpg").unlink(missing_ok=True)
    except OSError:
        pass


def load_avatar_bytes(steamid: str) -> bytes | None:
    """Le avatar em disco se existir."""
    if not steamid:
        return None
    path = _AVATARS_DIR / f"{steamid}.jpg"
    try:
        return path.read_bytes()
    except OSError:
        return None
