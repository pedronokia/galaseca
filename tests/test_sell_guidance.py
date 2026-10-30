"""Preco-alvo de venda e preco maximo de compra.

O modelo de taxa aqui e' o do `portfolio`, que e' o correto pra Steam: a
taxa incide sobre o valor do VENDEDOR, nao sobre o preco de compra. Voce
lista a R$ 115, o comprador paga 115, voce recebe 100. Logo o break-even
e' +15%, e nao os +17,65% que o `backtest.breakeven_gross` devolve (esse
usa preco*(1-taxa), que e' outro modelo).
"""
from __future__ import annotations

import pytest

from galaseca import portfolio


# ── o modelo de taxa ───────────────────────────────────────────────

def test_listar_a_115_devolve_100():
    assert portfolio.net_proceeds(115.0) == pytest.approx(100.0)


def test_break_even_e_15_por_cento():
    assert portfolio.break_even_price(100.0) == pytest.approx(115.0)


# ── sell_guidance ──────────────────────────────────────────────────

def test_alvo_e_o_liquido():
    g = portfolio.sell_guidance(current_price=230.0, cost=100.0)
    assert g["target_list"] == 230.0
    assert g["net_at_target"] == pytest.approx(200.0, abs=0.01)
    assert g["profit_at_target"] == pytest.approx(100.0, abs=0.01)
    assert g["clears"] is True


def test_alvo_abaixo_do_custo_nao_cobre():
    """Compra a 100, mercado a 110: parece lucro, mas o liquido e' 95,65."""
    g = portfolio.sell_guidance(current_price=110.0, cost=100.0)
    assert g["net_at_target"] == pytest.approx(95.65, abs=0.01)
    assert g["profit_at_target"] < 0
    assert g["clears"] is False


def test_gap_diz_quanto_falta_subir():
    g = portfolio.sell_guidance(current_price=100.0, cost=100.0)
    assert g["break_even_list"] == pytest.approx(115.0)
    assert g["gap_pct"] == pytest.approx(15.0, abs=0.1)


def test_no_break_even_exato_o_gap_e_zero():
    g = portfolio.sell_guidance(current_price=115.0, cost=100.0)
    assert g["gap_pct"] == pytest.approx(0.0, abs=0.1)
    assert g["clears"] is True


def test_sem_custo_ainda_diz_quanto_entra_no_bolso():
    """Posicao vinda do sync nao tem custo -- lucro e' desconhecido, mas o
    liquido da venda nao."""
    g = portfolio.sell_guidance(current_price=230.0, cost=None)
    assert g["net_at_target"] == pytest.approx(200.0, abs=0.01)
    assert g["profit_at_target"] is None
    assert g["clears"] is None
    assert g["break_even_list"] is None


def test_custo_zero_e_tratado_como_desconhecido():
    """cost=0 e' o que o sync grava pra 'nao sei', nao 'foi de graca'."""
    g = portfolio.sell_guidance(current_price=230.0, cost=0.0)
    assert g["break_even_list"] is None
    assert g["profit_at_target"] is None


def test_venda_rapida_cobre_a_menor_listagem():
    g = portfolio.sell_guidance(current_price=230.0, cost=100.0, lowest=220.0)
    assert g["fast_list"] == 219.99
    assert g["net_at_fast"] == pytest.approx(219.99 / 1.15, abs=0.01)
    assert g["net_at_fast"] < g["net_at_target"]


def test_venda_rapida_nao_vira_preco_negativo():
    g = portfolio.sell_guidance(current_price=1.0, cost=None, lowest=0.01)
    assert g["fast_list"] >= 0.01


def test_sem_preco_nao_inventa_alvo():
    g = portfolio.sell_guidance(current_price=None, cost=100.0)
    assert g["target_list"] is None
    assert g["net_at_target"] is None
    # o piso ainda e' conhecido: depende so' do custo
    assert g["break_even_list"] == pytest.approx(115.0)


def test_tudo_ausente_nao_explode():
    g = portfolio.sell_guidance(current_price=None, cost=None)
    assert all(v is None for v in g.values())


# ── max_buy_price ──────────────────────────────────────────────────

def test_maximo_de_compra_sem_margem_e_o_ponto_de_indiferenca():
    """Vendendo a 115 voce recebe 100; pagar mais que 100 da' prejuizo."""
    assert portfolio.max_buy_price(115.0) == pytest.approx(100.0, abs=0.01)


def test_maximo_de_compra_com_margem():
    """Pra sobrar 20% vendendo a 115, o teto de compra cai."""
    teto = portfolio.max_buy_price(115.0, margin_pct=20.0)
    assert teto == pytest.approx(100.0 / 1.2, abs=0.01)
    # e a conta fecha: comprando no teto, o lucro e' os 20%
    lucro = portfolio.net_proceeds(115.0) - teto
    assert lucro / teto * 100 == pytest.approx(20.0, abs=0.1)


def test_maximo_de_compra_cresce_com_o_preco_de_venda():
    assert portfolio.max_buy_price(200.0) > portfolio.max_buy_price(100.0)
