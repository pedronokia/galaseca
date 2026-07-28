"""P&L nao pode inventar lucro em item sem custo registrado.

Bug real visto na tela de conta em 28/07/2026: "P&L total R$ 850,42" com
"Total investido R$ 0,00". O sync grava cost=0.0 porque a Steam nao diz
quanto voce pagou -- isso e' desconhecido, nao zero.
"""
from __future__ import annotations

from skinvault import portfolio


def _preco(_nome):
    return 100.0


# A taxa da Steam incide sobre a VENDA: quem lista por 100 recebe 100/1.15,
# nao 100*0.85. O projeto ja' modela assim -- estes numeros seguem dai'.
NET = round(100.0 / 1.15, 2)      # 86.96


SYNC = {"name": "Kilowatt Case", "cost": 0.0, "quantity": 1,
        "source": "steam_sync"}
DROP = {"name": "Drop", "cost": 0.0, "quantity": 1, "source": "manual"}
COMPRADO = {"name": "Comprado", "cost": 60.0, "quantity": 1,
            "source": "manual"}


# ── has_cost_basis ─────────────────────────────────────────────────


def test_sync_com_zero_e_desconhecido():
    assert portfolio.has_cost_basis(SYNC) is False


def test_manual_com_zero_e_custo_real():
    """Drop realmente custou zero -- mas foi o usuario que afirmou isso."""
    assert portfolio.has_cost_basis(DROP) is True


def test_custo_positivo_sempre_vale():
    assert portfolio.has_cost_basis(COMPRADO) is True
    assert portfolio.has_cost_basis(
        {"name": "X", "cost": 5.0, "source": "steam_sync"}) is True


def test_custo_ausente_ou_invalido():
    assert portfolio.has_cost_basis({"name": "X"}) is False
    assert portfolio.has_cost_basis({"name": "X", "cost": None}) is False
    assert portfolio.has_cost_basis({"name": "X", "cost": "abc"}) is False


# ── o bug em si ────────────────────────────────────────────────────


def test_so_itens_de_sync_nao_geram_lucro():
    r = portfolio.evaluate_portfolio([SYNC, dict(SYNC, name="Outro")], _preco)
    tot = r["totals"]
    assert tot["pnl"] is None, "inventario sem custo virou lucro de novo"
    assert tot["pnl_pct"] is None
    assert tot["unknown_cost"] == 2
    # Valor de mercado NAO depende de custo e continua valendo.
    assert tot["market"] == 200.0
    assert round(tot["net_if_sold"], 2) == round(100.0 / 1.15 * 2, 2)


def test_linha_de_sync_nao_tem_pnl():
    r = portfolio.evaluate_portfolio([SYNC], _preco)
    linha = r["rows"][0]
    assert linha["pnl"] is None
    assert linha["has_cost"] is False
    assert linha["is_profit"] is False and linha["is_loss"] is False
    assert linha["market"] == 100.0


def test_pnl_agrega_so_o_que_tem_custo():
    """Misto: o item de sync nao pode inflar o lucro do item comprado."""
    r = portfolio.evaluate_portfolio([SYNC, COMPRADO], _preco)
    tot = r["totals"]
    # comprado: net 86.96 - custo 60. O de sync fica fora do P&L.
    assert round(tot["pnl"], 2) == round(NET - 60.0, 2)
    assert tot["cost"] == 60.0
    assert tot["unknown_cost"] == 1
    # Mas o valor total considera os dois.
    assert tot["market"] == 200.0


def test_drop_manual_entra_no_pnl():
    """Custo zero DECLARADO e' P&L real -- nao pode virar None."""
    tot = portfolio.evaluate_portfolio([DROP], _preco)["totals"]
    assert round(tot["pnl"], 2) == NET
    assert tot["unknown_cost"] == 0
    # Sem custo pra dividir, a porcentagem nao existe.
    assert tot["pnl_pct"] is None


def test_prejuizo_continua_aparecendo():
    caro = {"name": "Caro", "cost": 200.0, "quantity": 1, "source": "manual"}
    tot = portfolio.evaluate_portfolio([caro], _preco)["totals"]
    assert round(tot["pnl"], 2) == round(NET - 200.0, 2)
    assert tot["pnl_pct"] < 0


def test_sem_preco_marca_has_cost():
    r = portfolio.evaluate_portfolio([COMPRADO], lambda n: None)
    assert r["rows"][0]["has_cost"] is True
    assert r["rows"][0]["pnl"] is None


def test_portfolio_vazio():
    tot = portfolio.evaluate_portfolio([], _preco)["totals"]
    assert tot["pnl"] is None
    assert tot["market"] == 0.0
    assert tot["unknown_cost"] == 0
