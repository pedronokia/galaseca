"""Calculadora de arbitragem/taxas — lógica pura (fee_calculator.py)."""
from __future__ import annotations

import pytest

from skinvault import fee_calculator as calc


# ── modelos de taxa ───────────────────────────────────────────


def test_steam_seller_added_recebe_pela_regra_do_vendedor():
    # lista 115 -> recebe 100 (AGENTS.md 4b: a taxa incide sobre o valor
    # do vendedor, não é % do preço).
    assert calc.net_proceeds(115.0, 0.15, "seller_added") == pytest.approx(100.0)


def test_percent_off_recebe_bruto_menos_taxa():
    assert calc.net_proceeds(100.0, 0.12, "percent_off") == pytest.approx(88.0)


def test_listing_price_steam():
    assert calc.listing_price(100.0, 0.15, "seller_added") == pytest.approx(115.0)


def test_listing_price_percent_off():
    assert calc.listing_price(88.0, 0.12, "percent_off") == pytest.approx(100.0)


def test_round_trip_net_listing():
    for modelo, taxa in (("seller_added", 0.15), ("percent_off", 0.12)):
        net = 250.0
        preco = calc.listing_price(net, taxa, modelo)
        assert calc.net_proceeds(preco, taxa, modelo) == pytest.approx(net)


# ── quote ─────────────────────────────────────────────────────


def test_quote_steam_com_margem():
    steam = calc.marketplace("steam")
    q = calc.quote(200.0, 10.0, steam)
    assert q["net_target"] == pytest.approx(220.0)
    assert q["list_price"] == pytest.approx(253.0)  # 220 * 1.15
    assert q["fee_abs"] == pytest.approx(33.0)
    assert q["profit"] == pytest.approx(20.0)
    assert q["currency"] == "saldo Steam"


def test_quote_externo_com_margem():
    skinport = calc.marketplace("skinport")
    q = calc.quote(200.0, 10.0, skinport)
    assert q["net_target"] == pytest.approx(220.0)
    assert q["list_price"] == pytest.approx(250.0)  # 220 / 0.88
    assert q["fee_abs"] == pytest.approx(30.0)


def test_quote_quantidade_totaliza():
    steam = calc.marketplace("steam")
    q = calc.quote(100.0, 0.0, steam, quantity=3)
    assert q["list_total"] == pytest.approx(345.0)
    assert q["net_total"] == pytest.approx(300.0)
    assert q["profit_total"] == pytest.approx(0.0)


def test_quote_custo_zero_nao_quebra():
    q = calc.quote(0.0, 10.0, calc.marketplace("steam"))
    assert q["list_price"] == 0.0
    assert q["net_target"] == 0.0


# ── quote_all ────────────────────────────────────────────────


def test_quote_all_cobre_os_mercados():
    quotes = calc.quote_all(200.0, 10.0)
    chaves = [q["key"] for q in quotes]
    assert set(chaves) == {"steam", "skinport", "cs.money", "dmarket"}


def test_quote_all_ordenado_por_preco_listagem():
    quotes = calc.quote_all(200.0, 10.0)
    precos = [q["list_price"] for q in quotes]
    assert precos == sorted(precos)


def test_quote_all_mais_barato_de_listar_e_cs_money():
    quotes = calc.quote_all(200.0, 10.0)
    assert quotes[0]["key"] == "cs.money"


# ── registry ─────────────────────────────────────────────────


def test_marketplace_devolve_clone():
    m = calc.marketplace("steam")
    m["fee"] = 0.5
    assert calc.marketplace("steam")["fee"] == 0.15


def test_marketplace_desconhecido_default():
    m = calc.marketplace("nao-existe")
    assert m["fee"] == 0.0
    assert m["label"] == "nao-existe"
