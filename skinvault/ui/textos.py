"""Textos da tela para codigos internos -- linguagem de usuario comum.

Os modulos de analise (steam_api, signals) trabalham com codigos curtos em
ingles ("tight", "buyer_dominant", "rising"): o score, o backtest e os
testes dependem deles. So' a EXIBICAO traduz, e sempre por aqui, pra que
Scanner e Market digam a mesma coisa do mesmo jeito.

Ate' 2026-10-17 esses codigos apareciam crus nas celulas do Scanner e nos
detalhes do Market.
"""
from __future__ import annotations

SPREAD = {"tight": "Pequena", "normal": "Normal", "wide": "Grande"}
BOOK = {"buyer_dominant": "Mais compradores",
        "seller_dominant": "Mais vendedores",
        "balanced": "Equilibrada"}
TREND = {"rising": "Subindo", "falling": "Caindo", "stable": "Estável"}


def traduz(mapa: dict, codigo) -> str:
    """Texto da tela pro codigo; codigo desconhecido passa como veio."""
    if not codigo:
        return ""
    return mapa.get(codigo, str(codigo))
