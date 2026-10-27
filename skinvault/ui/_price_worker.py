"""Bridge pattern para atualizacao async de precos (F11).

Emite sinais com progresso e resultado em vez de blocagem na UI thread.
Reutilizado por AccountScreen e futuras telas.
"""
from __future__ import annotations

import threading
import time
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

    def start(self, seq: int | None = None) -> None:
        # `seq` e' opcional (default None): quem chama sem passar nada
        # (toda a suite de testes existente, e qualquer chamador que so'
        # dispara uma avaliacao por vez) continua funcionando identico.
        # Quem chama com `seq` (AccountScreen.refresh) pode disparar esta
        # thread mais de uma vez em sequencia -- navegar pra Conta, editar
        # custo no Inventario, navegar de novo, tudo chama refresh() sem
        # nenhuma guarda. Como o tempo de avaliacao varia MUITO (rate
        # limit por item), a mais ANTIGA pode terminar DEPOIS da mais
        # recente e sobrescrever o resultado fresco com dado velho --
        # mesma familia do bug ja' corrigido em market_screen.py
        # (_search_seq) e inventory.js (stale save). `_on_eval` descarta
        # qualquer resultado cujo `seq` nao seja mais o mais recente.
        sig_progress = self.progress
        sig_done = self.eval_done

        def worker() -> None:
            try:
                from skinvault import steam_api

                positions = portfolio_mod.load_portfolio()
                total = len(positions)
                done = [0]
                limitado = [False]

                def price_fn(n: str) -> float | None:
                    # Uma vez que a Steam devolveu 429, o bloqueio e' do
                    # IP/conta e vale pra todos os itens. Continuar batendo
                    # so' gasta o backoff de cada um -- medido: 24 itens
                    # sem cache viravam minutos de espera. O cache ainda
                    # responde, entao itens ja' conhecidos seguem saindo.
                    if limitado[0]:
                        cache_hit = (self._cache.get(n)
                                     if self._cache.has(n) else None)
                        done[0] += 1
                        _safe_emit(sig_progress, done[0], total)
                        return cache_hit
                    hit = self._cache.has(n)
                    status, p = prices_mod.cached_price_status(n, self._cache)
                    if status == steam_api.PRICE_RATE_LIMITED:
                        limitado[0] = True
                    elif not hit:
                        # So' pausa em MISS de verdade (cache hit nao bateu
                        # rede). Preveni o 429 em vez de so' reagir a ele --
                        # sem isso, um inventario grande sem cache queima o
                        # limite inteiro antes do primeiro item vir limitado.
                        time.sleep(steam_api.RATE_LIMIT_DELAY_S)
                    done[0] += 1
                    _safe_emit(sig_progress, done[0], total)
                    return p

                result = portfolio_mod.evaluate_portfolio(
                    positions, price_fn,
                )
                payload = {
                    "positions": positions,
                    "rows": result["rows"],
                    "totals": result["totals"],
                    "rate_limited": limitado[0],
                }
                if seq is not None:
                    payload["seq"] = seq
                _safe_emit(sig_done, payload)
            except Exception as exc:
                payload = {
                    "positions": [],
                    "rows": [],
                    "totals": {"market": 0, "net_if_sold": 0, "pnl": 0,
                               "cost": 0},
                    "error": str(exc),
                }
                if seq is not None:
                    payload["seq"] = seq
                _safe_emit(sig_done, payload)

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


class IconWorker(QObject):
    """Baixa do CDN da Steam os icones que faltam no cache local.

    A grade de inventario e' network-free de proposito (`icons.local_path`
    so' olha o disco), e nada no app populava esse disco -- `ensure_cached`
    existia sem nenhum chamador. Resultado: 25 das 31 posicoes apareciam
    como "?" numa tela cujo proposito e' reconhecer item pelo icone.

    O CDN de icone e' um host separado do priceoverview: medido em
    2026-07-29, respondia normalmente com os outros endpoints em 429.
    """

    done = pyqtSignal(int)  # quantos icones novos entraram no cache

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    def start(self, icon_hashes: list) -> None:
        if self._running:
            return
        from skinvault import icons

        faltando = []
        vistos = set()
        for h in icon_hashes:
            if not h or h in vistos:
                continue
            vistos.add(h)
            if icons.local_path(h) is None:
                faltando.append(h)
        if not faltando:
            return  # nada a fazer: nao acorda thread nem emite sinal

        self._running = True
        sig_done = self.done

        def worker() -> None:
            try:
                baixados = icons.ensure_cached(faltando)
                n = len(baixados)
            except Exception:
                n = 0  # icone e' cosmetico; falha nunca derruba a tela
            finally:
                self._running = False
            _safe_emit(sig_done, n)

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
