"""Catalogo de eventos da Valve que afetam o mercado CS2.

Updates da Valve sao o maior catalyst E maior risco do mercado de skins:
- Out/2025: trade-up de knife/glove -> ~$2B apagados em 48h
- Dez/2025: rare drops removidos -> cases descontinuadas +40-57%
- Mai/2026: Cologne 2026 -> capsulas abolidas, todas legacy viraram supply-fixa

Este modulo cataloga esses eventos pra:
1. Justificar status de items descontinuados em cases.py / _CAPSULES
2. Avisar usuario na UI quando ele olha categoria com regime mudado recente
3. Servir de referencia historica pra interpretar backtests

Atualizacao: adicionar entrada aqui sempre que descobrir update novo (e salvar
memoria correspondente em memory/).
"""
from __future__ import annotations

from datetime import date
from typing import Optional


# Tipos de impacto:
# - 'positive_discontinued': aumenta valor de items descontinuados da categoria
# - 'positive_all_legacy': aumenta valor de todos os items legacy da categoria
# - 'negative_craftable': diminui valor de items que se tornaram craftaveis
# - 'neutral_overhaul': mudou regime sem direcao clara (volatilidade alta)

EVENTS: list[dict] = [
    {
        "id": "trade_up_knife_2025_10",
        "date": date(2025, 10, 23),
        "type": "trade_up_change",
        "categories": ["Facas", "Luvas", "Coverts"],
        "impact": "negative_craftable",
        "magnitude": "catastrophic",
        "title": "Trade-up de knife/glove (5 coverts)",
        "summary": (
            "Valve permitiu craftar facas e luvas a partir de 5 coverts. "
            "~$2B apagados em 48h; facas/luvas -20% a -70%, "
            "coverts subiram 10-20x como combustivel de craft."
        ),
    },
    {
        "id": "rare_drops_removed_2025_12",
        "date": date(2025, 12, 17),
        "type": "drop_pool_change",
        "categories": ["Caixas"],
        "impact": "positive_discontinued",
        "magnitude": "high",
        "title": "Rare case drops removidos do weekly drop",
        "summary": (
            "Valve desativou rare case drops no weekly care package. "
            "Cases descontinuadas subiram 40-57% em dezembro 2025."
        ),
    },
    {
        "id": "capsule_abolition_2026_05",
        "date": date(2026, 5, 22),
        "type": "capsule_abolition",
        "categories": ["Cápsulas"],
        "impact": "positive_all_legacy",
        "magnitude": "high",
        "title": "Cápsulas de Major abolidas (IEM Cologne 2026)",
        "summary": (
            "Valve aboliu o sistema de capsulas com o IEM Cologne 2026. "
            "Stickers de Major agora sao vendidas direto via Major Shop com "
            "tokens. Todas as capsulas legacy (Katowice 2014 -> Budapest 2025) "
            "viraram supply-fixa permanente do dia pra noite."
        ),
    },
]


def events_for_category(
    category: str,
    *,
    since_days: int = 365,
    reference_date: Optional[date] = None,
) -> list[dict]:
    """Eventos da Valve que afetam `category` nos ultimos `since_days`.

    Ordenados do mais recente para o mais antigo. Eventos futuros (data >
    reference_date) sao ignorados.
    """
    ref = reference_date or date.today()
    out: list[dict] = []
    for ev in EVENTS:
        if category not in ev["categories"]:
            continue
        delta = (ref - ev["date"]).days
        if delta < 0:
            continue
        if delta > since_days:
            continue
        out.append(ev)
    return sorted(out, key=lambda e: e["date"], reverse=True)


def latest_regime_change(
    category: str,
    *,
    reference_date: Optional[date] = None,
) -> Optional[dict]:
    """Evento mais recente que afetou `category`, ou None se nao houver."""
    ref = reference_date or date.today()
    eligible = [
        ev for ev in EVENTS
        if category in ev["categories"] and (ref - ev["date"]).days >= 0
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda e: e["date"])
