"""Busca avatar e nome de um perfil público da Steam.

Endpoint legado e' estavel: https://steamcommunity.com/profiles/{id}?xml=1
retorna XML do perfil publico (sem login). Avatar fica em data/avatars/.

Cache em data/steam_profiles.json com TTL 24h. Falha silenciosa: caller
recebe None e usa fallback (silhueta generica + steamid como nome).
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import json
import re
import threading
import time
from pathlib import Path

import httpx

from galaseca._paths import DATA_DIR, atomic_write_bytes, atomic_write_text

try:
    import fcntl
except ImportError:  # Windows não oferece fcntl; o lock local ainda protege threads.
    fcntl = None

_PROFILES_PATH = DATA_DIR / "steam_profiles.json"
_LOCK_PATH = DATA_DIR / "steam_profiles.json.lock"
_AVATARS_DIR = DATA_DIR / "avatars"
_TTL_SECONDS = 24 * 3600
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkinVault/0.0.1"

# Protege o ciclo leitura-modificacao-escrita do cache (um JSON so',
# com entrada por steamid) contra DOIS niveis de concorrencia:
#
# - threading.Lock: threads do MESMO processo.
# - fcntl.flock num arquivo de lock DEDICADO (nao o JSON em si -- um
#   flock no proprio arquivo do cache entraria em conflito com o padrao
#   replace-via-temp-file do atomic_write_text, descrito em
#   AGENTS.md): processos DIFERENTES. O site publico roda com
#   `gunicorn --workers 2` (confirmado em Dockerfile.public-site),
#   processos separados que NAO compartilham threading.Lock nenhum.
#
# Achado numa cacada dirigida por essa familia de bug, 2026-10-27: dois
# visitantes logando perto um do outro podiam fazer o mais lento
# sobrescrever o cache inteiro com uma copia carregada ANTES do mais
# rapido salvar, apagando a entrada dele em silencio (self-cura no
# proximo cache miss, mas e' um write perdido de verdade). Uma primeira
# correcao só com threading.Lock fechou o caso intra-processo mas
# deixava aberto o caso entre os 2 workers do gunicorn -- fechado agora
# com o flock.
_cache_lock = threading.Lock()


@contextlib.contextmanager
def _ciclo_protegido(path: Path | None = None):
    """Serializa um ciclo leitura-modificacao-escrita do cache de
    perfis. Ver comentario de `_cache_lock` acima pros dois niveis de
    concorrencia cobertos. Sem `fcntl` (Windows), vale so' o
    threading.Lock -- mesmo nivel de protecao que o modulo tinha antes
    desta correcao, nao uma regressao.

    `path` e' parametro so' pra teste apontar pra um arquivo isolado em
    `tmp_path` -- chamador real nunca passa, usa sempre `_LOCK_PATH`.
    Default `None` (resolvido pro `_LOCK_PATH` atual dentro da função,
    não `= _LOCK_PATH` na assinatura) permite substituir o caminho em
    testes após a importação do módulo."""
    if path is None:
        path = _LOCK_PATH
    with _cache_lock:
        if fcntl is None:
            yield
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

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
    with _ciclo_protegido():
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
    with _ciclo_protegido():
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
        atomic_write_bytes(path, data)
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
    de cache pra trás depois de "excluir todos os meus dados".

    Protegido pelo mesmo `_ciclo_protegido()` do fetch (2026-10-27) --
    sem isto, exclusão de conta corria sem lock nenhum contra um login
    de OUTRO usuário salvando no mesmo cache ao mesmo tempo."""
    if not steamid:
        return
    try:
        with _ciclo_protegido():
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
