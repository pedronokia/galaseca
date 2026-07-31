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


# ── ter custo nao depende de ter cotacao ───────────────────────────
#
# Bug visto em 30/07/2026 com a Steam em 429: `price_fn` devolvia None pra
# tudo, o laco saltava a contagem, e a tela de conta exibia "Total investido
# R$ 0,00" pra quem tinha R$ 850,00 declarados -- alem de "0 sem custo" com
# 29 posicoes sem custo.


def test_unknown_cost_conta_mesmo_sem_preco():
    tot = portfolio.evaluate_portfolio([SYNC, COMPRADO], lambda n: None)["totals"]
    assert tot["unknown_cost"] == 1, "posicao sem preco sumiu da contagem"
    assert tot["known_cost"] == 1
    assert tot["positions"] == 2


def test_cost_known_soma_sem_preco():
    """O que o dono pagou nao muda porque a Steam nao respondeu."""
    tot = portfolio.evaluate_portfolio([SYNC, COMPRADO], lambda n: None)["totals"]
    assert tot["cost_known"] == 60.0
    # ...e continua o mesmo quando o preco volta.
    tot2 = portfolio.evaluate_portfolio([SYNC, COMPRADO], _preco)["totals"]
    assert tot2["cost_known"] == 60.0


def test_cost_do_pnl_fica_separado_de_cost_known():
    """`cost` acompanha o P&L; `cost_known` acompanha o desembolso."""
    tot = portfolio.evaluate_portfolio([COMPRADO], lambda n: None)["totals"]
    assert tot["cost_known"] == 60.0
    # Nada entrou no P&L, entao o custo que o lastreia e' zero -- e o
    # pnl_pct nao pode nascer dessa divisao.
    assert tot["cost"] == 0.0
    assert tot["pnl"] is None and tot["pnl_pct"] is None
    # Com preco, os dois convergem.
    tot2 = portfolio.evaluate_portfolio([COMPRADO], _preco)["totals"]
    assert tot2["cost"] == tot2["cost_known"] == 60.0


def test_linha_sem_preco_carrega_cost_total():
    linha = portfolio.evaluate_portfolio(
        [dict(COMPRADO, quantity=3)], lambda n: None)["rows"][0]
    assert linha["cost_total"] == 180.0
    assert linha["price"] is None and linha["pnl"] is None


def test_quantidade_entra_no_cost_known():
    tot = portfolio.evaluate_portfolio(
        [dict(COMPRADO, quantity=2)], lambda n: None)["totals"]
    assert tot["cost_known"] == 120.0


# ── composicao da carteira ─────────────────────────────────────────


def test_classifica_pelas_regras_conhecidas():
    assert portfolio.classify_item("Kilowatt Case") == "Caixas e cápsulas"
    assert portfolio.classify_item("Sticker | rallen | Paris 2023") == "Adesivos"
    assert portfolio.classify_item(
        "Sealed Graffiti | Bling (War Pig Pink)") == "Grafites"
    assert portfolio.classify_item("AK-47 | Redline (Field-Tested)") == "Skins"


def test_faca_nao_cai_em_skins():
    """Faca tambem tem '|' no nome -- a regra do estrela vem antes."""
    assert portfolio.classify_item(
        "★ Falchion Knife | Autotronic (Field-Tested)") == "Facas e luvas"


def test_item_desconhecido_vira_outros():
    """Chutar a categoria seria afirmar o que nao se sabe."""
    assert portfolio.classify_item("Sealed Genesis Terminal") == "Outros"
    assert portfolio.classify_item("") == "Outros"


def test_composicao_conta_mesmo_sem_preco():
    """Com a Steam racionada a contagem e' tudo o que sobra -- e vale."""
    rows = [{"name": "Kilowatt Case", "quantity": 3, "market": None},
            {"name": "AK-47 | Redline (Field-Tested)", "quantity": 1,
             "market": None}]
    grupos = {g["label"]: g for g in portfolio.composition(rows)}
    assert grupos["Caixas e cápsulas"]["count"] == 3
    assert grupos["Caixas e cápsulas"]["value"] == 0.0
    assert grupos["Skins"]["count"] == 1


def test_composicao_soma_valor_quando_ha():
    rows = [{"name": "Kilowatt Case", "quantity": 2, "market": 10.0},
            {"name": "Revolution Case", "quantity": 1, "market": 5.0}]
    grupos = portfolio.composition(rows)
    assert len(grupos) == 1
    assert grupos[0]["value"] == 15.0
    assert grupos[0]["count"] == 3
    assert grupos[0]["priced"] == 2


def test_composicao_ordena_pelo_maior():
    rows = [{"name": "AK-47 | Redline (Field-Tested)", "quantity": 1,
             "market": 1.0},
            {"name": "Kilowatt Case", "quantity": 1, "market": 90.0}]
    assert portfolio.composition(rows)[0]["label"] == "Caixas e cápsulas"


def test_composicao_vazia_e_segura():
    assert portfolio.composition([]) == []
    assert portfolio.composition(None) == []
    assert portfolio.composition(["lixo", None]) == []
