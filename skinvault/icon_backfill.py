"""Backfill de icon_url em eventos antigos do steam_market_events.json.

Eventos sincronizados antes da Phase B nao tem `icon_url`. Este modulo
busca a pagina publica de listagem (`/market/listings/730/<nome>`) por
nome unico e extrai o icon_url do HTML — uma requisicao por NOME
(nao por evento), com throttle conservador pra nao queimar rate-limit.

Fluxo:
  1. Carrega eventos do JSON
  2. Filtra eventos sem icon_url → coleta nomes unicos
  3. Pra cada nome, GET /market/listings/730/<urlencoded>
  4. Extrai icon_hash via regex (mesmo padrao do parser de history)
  5. Atualiza icon_url no JSON

Idempotente: re-rodar nao causa fetch desnecessario (eventos ja' com
icon_url sao ignorados).
"""
from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Callable

from skinvault import steam_api
from skinvault._paths import DATA_DIR, atomic_write_text

_EVENTS_PATH = DATA_DIR / "steam_market_events.json"
_LISTING_URL_TPL = "https://steamcommunity.com/market/listings/730/{name}"
# Usa o parser compartilhado com os metadados do scan.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_TIMEOUT = 15.0
_THROTTLE_S = 2.0  # conservador


def extract_icon_hash(html: str) -> str | None:
    """Extrai o primeiro icon hash do HTML de uma pagina de listing."""
    return steam_api.extract_market_icon_hash(html)


_RATE_LIMIT_FAMILIA = "market_listings"


def fetch_icon_hash_for_name(name: str,
                              timeout: float = _TIMEOUT) -> str | None:
    """GET /market/listings/730/<name>, extrai icon_hash. None se falhar.

    Mesmo disjuntor de steam_api.em_cooldown() -- achado real de
    2026-10-19, bloqueio que comecou isolado virou de horas porque
    cada tentativa nova (manual, batch de 22 nomes) contava como
    trafego novo pro mesmo endpoint ja' sinalizado. Familia propria
    ("market_listings"), separada de "inventory"/"resolve"/"search":
    medido no mesmo dia que um endpoint libera sem o outro liberar
    junto."""
    if not name:
        return None
    if steam_api.em_cooldown(_RATE_LIMIT_FAMILIA):
        return None
    try:
        import httpx
    except ImportError:
        return None
    url = _LISTING_URL_TPL.format(name=urllib.parse.quote(name))
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": _UA}) as client:
            resp = client.get(url)
            if resp.status_code == 429:
                steam_api._registrar_rate_limit(_RATE_LIMIT_FAMILIA)
                return None
            if resp.status_code != 200 or not resp.text:
                return None
            steam_api._limpar_rate_limit(_RATE_LIMIT_FAMILIA)
            return extract_icon_hash(resp.text)
    except Exception:
        return None


def _load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_events(path: Path, events: list[dict]) -> None:
    atomic_write_text(
        path,
        json.dumps(events, ensure_ascii=False, indent=2),
    )


def names_pending_backfill(events: list[dict]) -> list[str]:
    """Nomes unicos que aparecem em eventos sem icon_url."""
    seen: set[str] = set()
    out: list[str] = []
    for e in events:
        if e.get("icon_url"):
            continue
        name = e.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def backfill_market_events(
    path: Path | str = _EVENTS_PATH,
    throttle_s: float = _THROTTLE_S,
    max_names: int | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
    fetcher: Callable[[str], str | None] | None = None,
    interruption_check: Callable[[], bool] | None = None,
) -> dict:
    """Orquestra backfill. Retorna {names_resolved, events_updated,
    fetched, total_names}.

    `fetcher` permite injecao em testes (default = fetch_icon_hash_for_name).
    `interruption_check` retorna True se a operacao deve abortar (usado
    pelo QThread pra cancelar limpo).
    """
    p = Path(path)
    events = _load_events(p)
    pending = names_pending_backfill(events)
    total = len(pending)
    if max_names is not None:
        pending = pending[:max_names]

    fetch = fetcher or fetch_icon_hash_for_name
    name_to_icon: dict[str, str] = {}
    fetched = 0
    for i, name in enumerate(pending):
        if interruption_check and interruption_check():
            break
        if on_progress is not None:
            on_progress(i + 1, len(pending), name)
        icon = fetch(name)
        fetched += 1
        if icon:
            name_to_icon[name] = icon
        if throttle_s > 0 and i < len(pending) - 1:
            time.sleep(throttle_s)

    # Aplica nos eventos
    n_updated = 0
    for e in events:
        if e.get("icon_url"):
            continue
        h = name_to_icon.get(e.get("name") or "")
        if h:
            e["icon_url"] = h
            n_updated += 1
    if n_updated > 0:
        _save_events(p, events)
    return {
        "total_names": total,
        "fetched": fetched,
        "names_resolved": len(name_to_icon),
        "events_updated": n_updated,
    }
