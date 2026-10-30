"""Traduções dos códigos internos exibidos pelo site."""
from __future__ import annotations

from galaseca import textos


def test_codigos_do_veredito_viram_portugues():
    assert textos.traduz(textos.SPREAD, "tight") == "Pequena"
    assert textos.traduz(textos.BOOK, "buyer_dominant") == "Mais compradores"
    assert textos.traduz(textos.BOOK, "seller_dominant") == "Mais vendedores"
    assert textos.traduz(textos.TREND, "rising") == "Subindo"
    assert textos.traduz(textos.TREND, "falling") == "Caindo"


def test_codigo_desconhecido_ou_vazio():
    assert textos.traduz(textos.TREND, "novo_codigo") == "novo_codigo"
    assert textos.traduz(textos.TREND, "") == ""
    assert textos.traduz(textos.TREND, None) == ""
