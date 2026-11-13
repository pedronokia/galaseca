"""Textos de exibição para códigos internos -- linguagem de usuário comum.

Os modulos de analise (steam_api, signals) trabalham com codigos curtos em
ingles ("tight", "buyer_dominant", "rising"): o score, o backtest e os
testes dependem deles. Só a exibição traduz, e sempre por aqui, para manter os termos consistentes.

Os códigos continuam em inglês nas interfaces internas; os rótulos
apresentados aos visitantes ficam em português.
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
