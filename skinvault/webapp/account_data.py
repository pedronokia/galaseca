"""Logica de dados da tela de Conta -- sem Flask, pra testar isolado.

Equivalente web de `AccountScreen` + `PriceWorker` (ui/account_screen.py,
ui/_price_worker.py), reduzido ao que a Fase 2 precisa: os 4 stat cards e
a lista de posicoes. Graficos/metas/backtest ficam pra fases seguintes.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from skinvault import portfolio as portfolio_mod
from skinvault import prices as prices_mod
from skinvault import steam_api
from skinvault.localization import localize_name
from skinvault.prices import PriceCache

ProgressCb = Callable[[int, int], None]
DoneCb = Callable[[dict], None]

_refresh_lock = threading.Lock()
_refreshing = False


def _row_view(row: dict) -> dict:
    """Projeta uma row de `evaluate_portfolio` pro JSON da tela."""
    return {
        "name": row.get("name", ""),
        "display_name": localize_name(row.get("name", "")),
        "quantity": row.get("quantity", 1),
        "price": row.get("price"),
        "pnl": row.get("pnl"),
        "has_cost": bool(row.get("has_cost")),
    }


def _payload(rows: list[dict], totals: dict,
             rate_limited: bool = False) -> dict:
    rows_sorted = sorted(
        rows, key=lambda r: (r.get("price") or 0) * r.get("quantity", 1),
        reverse=True,
    )
    return {
        "rows": [_row_view(r) for r in rows_sorted],
        "totals": totals,
        "rate_limited": rate_limited,
        "updated_at": time.time(),
    }


def summary_payload(cache: Optional[PriceCache] = None) -> dict:
    """Avaliacao INSTANTANEA, so' com o que ja' esta' em cache -- nunca bate
    na rede. Pra primeira pintura da tela sem esperar o rate limit."""
    cache = cache or PriceCache()
    positions = portfolio_mod.load_portfolio()
    result = portfolio_mod.evaluate_portfolio(positions, cache.get)
    return _payload(result["rows"], result["totals"])


def is_refreshing() -> bool:
    return _refreshing


def start_refresh(on_progress: ProgressCb, on_done: DoneCb,
                   cache: Optional[PriceCache] = None) -> bool:
    """Dispara a avaliacao completa (com rede) numa thread daemon.

    Mesma estrategia do `PriceWorker` do app Qt: para de bater na rede
    assim que vir um 429 (o bloqueio e' do IP/conta, nao do item), mas
    continua servindo o que ja' esta' em cache. Devolve False sem fazer
    nada se ja' houver uma rodada em andamento.
    """
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return False
        _refreshing = True

    cache = cache or PriceCache()

    def _worker() -> None:
        global _refreshing
        try:
            positions = portfolio_mod.load_portfolio()
            total = len(positions)
            done = [0]
            limitado = [False]

            def price_fn(name: str) -> float | None:
                if limitado[0]:
                    hit = cache.get(name) if cache.has(name) else None
                    done[0] += 1
                    on_progress(done[0], total)
                    return hit
                teve_cache = cache.has(name)
                status, price = prices_mod.cached_price_status(name, cache)
                if status == steam_api.PRICE_RATE_LIMITED:
                    limitado[0] = True
                elif not teve_cache:
                    time.sleep(steam_api.RATE_LIMIT_DELAY_S)
                done[0] += 1
                on_progress(done[0], total)
                return price

            result = portfolio_mod.evaluate_portfolio(positions, price_fn)
            on_done(_payload(result["rows"], result["totals"], limitado[0]))
        except Exception as exc:  # pragma: no cover - defensivo, igual PriceWorker
            on_done({"rows": [], "totals": {}, "error": str(exc)})
        finally:
            with _refresh_lock:
                _refreshing = False

    threading.Thread(target=_worker, daemon=True,
                      name="skinvault-web-account-refresh").start()
    return True
