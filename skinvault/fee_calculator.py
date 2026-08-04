"""Calculadora de arbitragem/taxas — líquido por plataforma e preço de listagem.

A taxa é cobrada de jeitos DIFERENTES conforme a plataforma, e misturar os
dois modelos dá conta errada:

  - Steam (≈15%): a taxa incide sobre o que o VENDEDOR recebe. Você lista
    por P e recebe P/(1+taxa) — lista 115, recebe 100. Modelo
    `seller_added`. É a mesma conta de portfolio.net_proceeds (AGENTS.md 4b).

  - Mercados externos (Skinport 12%, CS.MONEY 5%, DMarket ~10%): a taxa é
    percentual do preço de venda. Você lista por P e recebe P*(1-taxa).
    Modelo `percent_off`. É a conta de markets.compare_all.

As taxas são DEFAULTS editáveis: mudam com promoções/parcerias, e a
calculadora é ferramenta de planejamento, não contrato. A diferença
importante é o MODELO — Steam é saldo (não saca), o resto é dinheiro.

Obs.: DMarket não está em markets.MARKET_FEES (decisão de produto de
02/08/2026 mantém o escopo em Steam + Skinport + CSGOTM). A taxa aqui é um
default para o usuário comparar cenários; quem usa o app não passa a listar
lá por causa da calculadora.
"""
from __future__ import annotations

#: {key, label, fee (fração), model, currency}. currency marca que o
#: líquido da Steam é SALDO, não dinheiro — informação que o relatório
#: precisa preservar pra não inventar patrimônio em lugar nenhum.
MARKETPLACES = [
    {"key": "steam",    "label": "Steam Market", "fee": 0.15,
     "model": "seller_added", "currency": "saldo Steam"},
    {"key": "skinport", "label": "Skinport",     "fee": 0.12,
     "model": "percent_off",  "currency": "dinheiro"},
    {"key": "cs.money", "label": "CS.MONEY",     "fee": 0.05,
     "model": "percent_off",  "currency": "dinheiro"},
    {"key": "dmarket",  "label": "DMarket",      "fee": 0.10,
     "model": "percent_off",  "currency": "dinheiro"},
]

MODELS = ("seller_added", "percent_off")


def net_proceeds(price: float, fee: float, model: str) -> float:
    """Quanto o vendedor recebe ao listar por `price`."""
    price = float(price)
    if model == "seller_added":
        return price / (1.0 + float(fee))
    return price * (1.0 - float(fee))


def listing_price(net: float, fee: float, model: str) -> float:
    """Preço de LISTAGEM que entrega `net` líquido ao vendedor."""
    net = float(net)
    if model == "seller_added":
        return net * (1.0 + float(fee))
    return net / (1.0 - float(fee))


def quote(cost: float, margin_pct: float, market: dict,
          quantity: int = 1) -> dict:
    """Preço de listagem e breakdown para um marketplace.

    `cost` é o custo unitário. Quer receber `cost * (1 + margin_pct/100)`
    de líquido por unidade; devolve o preço de listagem que faz isso na
    plataforma + quanto a plataforma leva de taxa.
    """
    cost = float(cost)
    margin = float(margin_pct) / 100.0
    qty = int(quantity) if quantity and quantity > 0 else 1
    net = cost * (1.0 + margin)
    price = listing_price(net, float(market.get("fee", 0.0)),
                          market.get("model", "percent_off"))
    return {
        "key": market.get("key", "?"),
        "label": market.get("label", market.get("key", "?")),
        "fee": float(market.get("fee", 0.0)),
        "model": market.get("model", "percent_off"),
        "currency": market.get("currency", "dinheiro"),
        "cost": round(cost, 2),
        "quantity": qty,
        "net_target": round(net, 2),
        "list_price": round(price, 2),
        "fee_abs": round(price - net, 2),
        "profit": round(net - cost, 2),
        "margin_pct": round(margin_pct, 2),
        "list_total": round(price * qty, 2),
        "net_total": round(net * qty, 2),
        "profit_total": round((net - cost) * qty, 2),
    }


def quote_all(cost: float, margin_pct: float, quantity: int = 1) -> list[dict]:
    """O mesmo custo em todas as plataformas, ordenado pelo preço de listagem.

    Menor preço de listagem = menos capital preso pra conseguir o mesmo
    líquido. Inclui a Steam (saldo) junto dos externos (dinheiro) — a UI
    separa visualmente pelo campo `currency`.
    """
    quotes = [
        quote(cost, margin_pct, m, quantity) for m in MARKETPLACES
    ]
    quotes.sort(key=lambda q: q["list_price"])
    return quotes


def marketplace(key: str) -> dict:
    """Registry lookup — devolve um clone pra UI editar a taxa sem mutar a base."""
    for m in MARKETPLACES:
        if m["key"] == key:
            return dict(m)
    return {"key": key, "label": key, "fee": 0.0,
            "model": "percent_off", "currency": "dinheiro"}
