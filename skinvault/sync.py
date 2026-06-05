"""Orquestrador de sync da conta Steam (F10).

Sincroniza quatro fontes de dados privadas usando SteamSession:
  - Inventario CS2 atual         -> portfolio.json (posicoes novas)
  - Historico do Steam Market    -> steam_market_events.json (eventos crus)
  - Listagens ativas no Market   -> active_listings.json (overwrite)
  - Trade offers aceitas         -> trade_history.json (cumulativo)

Princípios:
  - NUNCA sobrescreve registros marcados como source='manual'.
  - Dedupe via chaves estaveis (listing_id, tradeofferid, ou composite hash).
  - Sync e' idempotente: rodar 2x consecutivo nao infla os arquivos.
"""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Callable

from skinvault import portfolio as portfolio_mod
from skinvault import steam_api
from skinvault._paths import DATA_DIR
from skinvault.steam_session import SteamSession

_EVENTS_PATH = DATA_DIR / "steam_market_events.json"
_LISTINGS_PATH = DATA_DIR / "active_listings.json"
_TRADES_PATH = DATA_DIR / "trade_history.json"

# Pageamento conservador pra nao bater rate limit do Steam.
_HISTORY_PAGE_SIZE = 100
_HISTORY_MAX_PAGES = 20
_HISTORY_THROTTLE_S = 1.5


# ── utilitarios JSON ──────────────────────────────────────────
def _load_json_list(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_json_list(path: Path, data: list[dict]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    except OSError:
        pass


# ── chaves de dedupe ──────────────────────────────────────────
def market_event_key(event: dict) -> str:
    """ID estavel pra evento do market. Usa listing_id quando disponivel,
    senao composite hash (name|side|date|price)."""
    lid = event.get("listing_id")
    if lid:
        return f"L:{lid}"
    return "|".join([
        event.get("name") or "",
        event.get("side") or "",
        event.get("date_str") or "",
        str(event.get("price") or ""),
    ])


# ── sync individual ───────────────────────────────────────────
def sync_inventory(session: SteamSession,
                   path: Path | str = portfolio_mod._DEFAULT_PATH) -> dict:
    """Adiciona ao portfolio itens do inventario Steam que ainda nao
    estao registrados (por nome). Posicoes manuais sao preservadas.

    Retorna {status, added, skipped}.
    """
    status, items = steam_api.fetch_inventory_authed(session)
    if status != steam_api.INV_OK:
        return {"status": status, "added": 0, "skipped": 0}

    positions = portfolio_mod.load_portfolio(path)
    existing_names = {p.get("name") for p in positions}
    added = 0
    for it in items:
        name = it.get("name")
        if not name or name in existing_names:
            continue
        qty = int(it.get("quantity", 1))
        positions.append({
            "name": name,
            "cost": 0.0,
            "quantity": qty,
            "added_ts": time.time(),
            "source": "steam_sync",
        })
        existing_names.add(name)
        added += 1
    portfolio_mod.save_portfolio(positions, path)
    return {"status": status, "added": added,
            "skipped": len(items) - added}


def sync_market_history(session: SteamSession,
                        path: Path | str = _EVENTS_PATH,
                        max_pages: int = _HISTORY_MAX_PAGES) -> dict:
    """Pagina /market/myhistory/render/ e armazena eventos crus.
    Dedupe via market_event_key.

    Retorna {fetched, new, total}.
    """
    p = Path(path)
    stored = _load_json_list(p)
    known_keys = {market_event_key(e) for e in stored}

    new_events: list[dict] = []
    fetched = 0
    for page in range(max_pages):
        resp = steam_api.fetch_market_history(
            session, start=page * _HISTORY_PAGE_SIZE,
            count=_HISTORY_PAGE_SIZE,
        )
        if not resp:
            break
        parsed = steam_api.parse_market_history_response(resp)
        fetched += len(parsed)
        if not parsed:
            break
        added_this_page = 0
        for ev in parsed:
            d = dataclasses.asdict(ev)
            d["synced_at"] = time.time()
            key = market_event_key(d)
            if key in known_keys:
                continue
            known_keys.add(key)
            new_events.append(d)
            added_this_page += 1
        total_count = int(resp.get("total_count", 0))
        if (page + 1) * _HISTORY_PAGE_SIZE >= total_count:
            break
        # Throttle conservador
        time.sleep(_HISTORY_THROTTLE_S)

    if new_events:
        # Eventos mais novos primeiro
        stored = new_events + stored
        _save_json_list(p, stored)
    return {"fetched": fetched, "new": len(new_events),
            "total": len(stored)}


def sync_listings(session: SteamSession,
                  path: Path | str = _LISTINGS_PATH) -> dict:
    """Snapshot atual das listagens ativas. Overwrite (estado momentaneo)."""
    resp = steam_api.fetch_my_listings(session)
    if not resp:
        return {"count": 0, "status": "error"}
    listings = _extract_listings_from_response(resp)
    _save_json_list(Path(path), listings)
    return {"count": len(listings), "status": "ok"}


def _extract_listings_from_response(resp: dict) -> list[dict]:
    """Extrai listings do payload de mylistings/render.

    O Steam devolve `assets` indexado, mas o numero ativo aparece em
    `num_active_listings`. Aqui retornamos uma forma simplificada:
    [{name, asset_id, list_price (centavos), list_ts}], extraida do
    `results_html` quando presente. Fallback minimo se HTML ausente.
    """
    html = resp.get("results_html") or ""
    items: list[dict] = []
    if html:
        events = steam_api.parse_market_history_html(html)
        for e in events:
            if e.side not in ("listed", "buy", "sell"):
                continue
            items.append({
                "name": e.name,
                "price": e.price,
                "listing_id": e.listing_id,
                "snapshot_ts": time.time(),
            })
    return items


def sync_trade_offers(session: SteamSession,
                      path: Path | str = _TRADES_PATH,
                      max_pages: int = 10) -> dict:
    """Pagina /profiles/{id}/tradehistory e adiciona trades novos.
    Dedupe via tradeofferid."""
    p = Path(path)
    stored = _load_json_list(p)
    known = {t.get("tradeofferid") for t in stored if t.get("tradeofferid")}

    new_trades: list[dict] = []
    fetched = 0
    for page in range(1, max_pages + 1):
        html = steam_api.fetch_trade_history_html(session, page=page)
        if not html:
            break
        parsed = steam_api.parse_trade_history_html(html)
        fetched += len(parsed)
        if not parsed:
            break
        added_this_page = 0
        for ev in parsed:
            if not ev.tradeofferid or ev.tradeofferid in known:
                continue
            known.add(ev.tradeofferid)
            d = dataclasses.asdict(ev)
            d["synced_at"] = time.time()
            new_trades.append(d)
            added_this_page += 1
        if added_this_page == 0:
            break
        time.sleep(_HISTORY_THROTTLE_S)

    if new_trades:
        stored = new_trades + stored
        _save_json_list(p, stored)
    return {"fetched": fetched, "new": len(new_trades),
            "total": len(stored)}


# ── orquestrador ──────────────────────────────────────────────
ProgressCb = Callable[[str, dict], None]


def sync_all(session: SteamSession,
             progress_cb: ProgressCb | None = None) -> dict:
    """Roda os 4 syncs em sequencia. progress_cb(step, result) e' chamado
    apos cada um. Retorna {inventory, market, listings, trades}.
    """
    def _step(name: str, fn: Callable[[], dict]) -> dict:
        try:
            result = fn()
        except Exception as exc:
            result = {"error": str(exc)}
        if progress_cb is not None:
            try:
                progress_cb(name, result)
            except Exception:
                pass
        return result

    return {
        "inventory": _step("inventory", lambda: sync_inventory(session)),
        "market": _step("market", lambda: sync_market_history(session)),
        "listings": _step("listings", lambda: sync_listings(session)),
        "trades": _step("trades", lambda: sync_trade_offers(session)),
    }


# ── leitores publicos pros consumidores da UI ─────────────────
def load_market_events(path: Path | str = _EVENTS_PATH) -> list[dict]:
    return _load_json_list(Path(path))


def load_active_listings(path: Path | str = _LISTINGS_PATH) -> list[dict]:
    return _load_json_list(Path(path))


def load_trade_offers(path: Path | str = _TRADES_PATH) -> list[dict]:
    return _load_json_list(Path(path))
