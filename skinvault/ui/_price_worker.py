"""Bridge pattern para atualizacao async de precos (F11).

Emite sinais com progresso e resultado em vez de blocagem na UI thread.
Reutilizado por AccountScreen e futuras telas.
"""
from __future__ import annotations

import threading
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from skinvault import portfolio as portfolio_mod
from skinvault import prices as prices_mod
from skinvault.prices import PriceCache


def _safe_emit(sig: pyqtSignal, *args) -> None:
    """Emit com tolerancia a C++ objeto deletado."""
    try:
        sig.emit(*args)
    except (RuntimeError, AttributeError) as e:
        print(f"WARNING: _safe_emit falhou (receptor deletado?): {e}",
              file=__import__('sys').stderr)


class PriceWorker(QObject):
    """Worker async que avalia o portfolio em background thread."""

    eval_done = pyqtSignal(dict)
    progress = pyqtSignal(int, int)  # done, total

    def __init__(self, cache: PriceCache,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = cache

    def start(self) -> None:
        sig_progress = self.progress
        sig_done = self.eval_done

        def worker() -> None:
            try:
                positions = portfolio_mod.load_portfolio()
                total = len(positions)
                done = [0]

                def price_fn(n: str) -> float | None:
                    p = prices_mod.cached_price(n, self._cache)
                    done[0] += 1
                    _safe_emit(sig_progress, done[0], total)
                    return p

                result = portfolio_mod.evaluate_portfolio(
                    positions, price_fn,
                )
                _safe_emit(sig_done, {
                    "positions": positions,
                    "rows": result["rows"],
                    "totals": result["totals"],
                })
            except Exception as exc:
                _safe_emit(sig_done, {
                    "positions": [],
                    "rows": [],
                    "totals": {"market": 0, "net_if_sold": 0, "pnl": 0,
                               "cost": 0},
                    "error": str(exc),
                })

        threading.Thread(target=worker, daemon=True).start()


class BatchPriceWorker(QObject):
    """Worker async que popula o cache de precos para uma lista de itens.

    Emite progress(done, total) durante a execucao e batch_done() ao final.
    Re-fetch ja' eh skip-pado quando o cache tem preco fresco (TTL).
    """

    progress = pyqtSignal(int, int)
    batch_done = pyqtSignal()

    def __init__(self, cache: PriceCache,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._running = False

    def start(self, names: list[str]) -> None:
        if self._running:
            return
        self._running = True
        sig_progress = self.progress
        sig_done = self.batch_done

        def worker() -> None:
            seen: set[str] = set()
            unique = [n for n in names if not (n in seen or seen.add(n))]
            total = len(unique)
            for i, name in enumerate(unique, 1):
                try:
                    prices_mod.cached_price(name, self._cache)
                except Exception:
                    pass
                _safe_emit(sig_progress, i, total)
            self._running = False
            _safe_emit(sig_done)

        threading.Thread(target=worker, daemon=True).start()


class SinglePriceWorker(QObject):
    """Worker para buscar o preco de um unico item."""

    done = pyqtSignal(str, object)  # name, price_or_None

    def __init__(self, cache: PriceCache,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = cache

    def start(self, name: str) -> None:
        sig_done = self.done

        def worker() -> None:
            try:
                price = prices_mod.cached_price(name, self._cache)
                _safe_emit(sig_done, name, price)
            except Exception:
                _safe_emit(sig_done, name, None)

        threading.Thread(target=worker, daemon=True).start()
