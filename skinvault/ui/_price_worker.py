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


class PriceWorker(QObject):
    """Worker async que avalia o portfolio em background thread."""

    eval_done = pyqtSignal(dict)

    def __init__(self, cache: PriceCache,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = cache

    def start(self) -> None:
        def worker() -> None:
            try:
                positions = portfolio_mod.load_portfolio()
                result = portfolio_mod.evaluate_portfolio(
                    positions,
                    lambda n: prices_mod.cached_price(n, self._cache),
                )
                self.eval_done.emit({
                    "positions": positions,
                    "rows": result["rows"],
                    "totals": result["totals"],
                })
            except Exception as exc:
                self.eval_done.emit({
                    "positions": [],
                    "rows": [],
                    "totals": {"market": 0, "net_if_sold": 0, "pnl": 0,
                               "cost": 0},
                    "error": str(exc),
                })

        threading.Thread(target=worker, daemon=True).start()


class SinglePriceWorker(QObject):
    """Worker para buscar o preco de um unico item."""

    done = pyqtSignal(str, object)  # name, price_or_None

    def __init__(self, cache: PriceCache,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache = cache

    def start(self, name: str) -> None:
        def worker() -> None:
            try:
                price = prices_mod.cached_price(name, self._cache)
                self.done.emit(name, price)
            except Exception:
                self.done.emit(name, None)

        threading.Thread(target=worker, daemon=True).start()
