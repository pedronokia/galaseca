"""Logica de dados da Calculadora de Trade-up -- sem Flask, testavel isolado.

Equivalente web de `tradeup_screen.py` (CatalogWorker + EvalWorker). A
entrada e' uma lista de linhas "nome;float;custo" (float/custo
opcionais) em vez de uma grade de formulario -- bem mais simples de
implementar em HTML puro e cobre o mesmo caso de uso (ver AGENTS.md:
`tradeup.py` ja' e' logica pura, so' falta o encaixe web).
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from skinvault import tradeup as tradeup_mod

ProgressCb = Callable[[int, int, int], None]
DoneCb = Callable[[dict], None]

_eval_lock = threading.Lock()
_evaluating = False
_catalog_lock = threading.Lock()
_refreshing_catalog = False


def parse_lines(raw: str) -> list[dict]:
    """"nome;float;custo" por linha -> [{name, float?, cost?}]."""
    out: list[dict] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        name = parts[0]
        if not name:
            continue
        item: dict = {"name": name}
        if len(parts) > 1 and parts[1]:
            try:
                item["float"] = float(parts[1].replace(",", "."))
            except ValueError:
                pass
        if len(parts) > 2 and parts[2]:
            try:
                item["cost"] = float(parts[2].replace(",", "."))
            except ValueError:
                pass
        out.append(item)
    return out


def _cache_only_price_fn() -> Callable[[str], Optional[float]]:
    """Mesma fonte de preco do SsrPricer, so' que nunca bate na rede --
    resultado instantaneo pra pre-visualizacao."""
    from skinvault.ssr_cache import PriceHistoryCache
    cache = PriceHistoryCache()

    def fn(name: str) -> Optional[float]:
        ph = cache.get(name)
        return tradeup_mod.reference_price(ph) if ph else None

    return fn


def catalog_status() -> dict:
    cat = tradeup_mod.load_catalog()
    if cat is None:
        return {"status": "missing", "updated_at": None,
                "skins": 0, "collections": 0}
    return {"status": "cached", "updated_at": cat.get("ts"),
            "skins": len(cat.get("skins") or {}),
            "collections": len(cat.get("collections") or {})}


def is_refreshing_catalog() -> bool:
    return _refreshing_catalog


def start_catalog_refresh(on_done: Callable[[str], None]) -> bool:
    """Baixa o dataset (GitHub, nao Steam) e regrava o catalogo local."""
    global _refreshing_catalog
    with _catalog_lock:
        if _refreshing_catalog:
            return False
        _refreshing_catalog = True

    def _worker() -> None:
        global _refreshing_catalog
        try:
            status, _cat = tradeup_mod.refresh_catalog(force=True)
            on_done(status)
        except Exception:
            on_done(tradeup_mod.CATALOG_UNAVAILABLE)
        finally:
            with _catalog_lock:
                _refreshing_catalog = False

    threading.Thread(target=_worker, daemon=True,
                      name="skinvault-web-tradeup-catalog").start()
    return True


def quick_plan(raw_lines: str) -> dict:
    """Plano + precificacao SO' com o que ja esta em cache -- instantaneo,
    nunca bate na rede. Cobertura pode vir baixa/zero na primeira vez."""
    catalog = tradeup_mod.load_catalog()
    if catalog is None:
        return {"errors": ["Catálogo ainda não foi baixado — clique em "
                            "'Atualizar catálogo'."],
                "warnings": [], "outcomes": [], "inputs": []}
    inputs = parse_lines(raw_lines)
    plan = tradeup_mod.plan_contract(inputs, catalog)
    if plan.get("errors"):
        return {"errors": plan["errors"], "warnings": plan.get("warnings", []),
                "outcomes": [], "inputs": []}
    return tradeup_mod.evaluate(plan, _cache_only_price_fn())


def is_evaluating() -> bool:
    return _evaluating


def start_evaluate(raw_lines: str, on_progress: ProgressCb,
                    on_done: DoneCb) -> bool:
    """Mesmo plano de `quick_plan`, mas busca preco que falta na Steam
    (SsrPricer) -- pode levar minutos num contrato de faca/luva."""
    global _evaluating
    with _eval_lock:
        if _evaluating:
            return False
        _evaluating = True

    def _worker() -> None:
        global _evaluating
        try:
            catalog = tradeup_mod.load_catalog()
            if catalog is None:
                on_done({"errors": ["Catálogo ainda não foi baixado."],
                         "warnings": [], "outcomes": [], "inputs": []})
                return
            inputs = parse_lines(raw_lines)
            plan = tradeup_mod.plan_contract(inputs, catalog)
            if plan.get("errors"):
                on_done({"errors": plan["errors"],
                         "warnings": plan.get("warnings", []),
                         "outcomes": [], "inputs": []})
                return
            pricer = tradeup_mod.SsrPricer()
            nomes = tradeup_mod.price_names(plan)
            total = len(nomes)
            on_progress(0, total, pricer.pending(nomes))
            for i, nome in enumerate(nomes, 1):
                pricer(nome)
                on_progress(i, total, pricer.fetches)
            res = tradeup_mod.evaluate(plan, pricer)
            if pricer.blocked:
                res["warnings"].append(
                    "A Steam parou de responder (excesso de consultas): "
                    "parte dos preços ficou de fora. Tente de novo mais "
                    "tarde — o que já veio fica guardado.")
            on_done(res)
        except Exception as exc:
            on_done({"errors": [f"Falha ao precificar: {exc}"]})
        finally:
            with _eval_lock:
                _evaluating = False

    threading.Thread(target=_worker, daemon=True,
                      name="skinvault-web-tradeup-eval").start()
    return True
