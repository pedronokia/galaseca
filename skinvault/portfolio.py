"""Portfolio fee-aware -- a verdade do 'quanto paguei / quanto devo vender'.

O pulo do gato e' a taxa de ~15% do Steam. Voce lista por P, mas recebe ~P/1.15.
Logo, 'vale mais do que paguei' NAO e' lucro -- so' e' lucro DEPOIS da taxa. Este
modulo faz essa conta honesta + o preco de break-even.

Persiste local em data/portfolio.json (sem login, sem nuvem). Custo e' entrada
manual: privado e on-brand. Obs: o 'lucro' aqui e' em saldo Steam (a Wallet nao
saca pra conta) -- a ferramenta e' pra quem opera dentro do Steam.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

_DEFAULT_PATH = DATA_DIR / "portfolio.json"

# ~5% Steam + 10% jogo, cobrados sobre o valor que o VENDEDOR recebe.
STEAM_FEE = 0.15


def net_proceeds(price: float, fee_rate: float = STEAM_FEE) -> float:
    """Quanto VOCE recebe ao vender por `price` (liquido da taxa).
    Steam: buyer_price = seller_amount * (1+fee) => seller = price/(1+fee)."""
    return price / (1.0 + fee_rate)


def break_even_price(cost: float, fee_rate: float = STEAM_FEE) -> float:
    """Preco de LISTAGEM necessario pra receber de volta o que custou."""
    return cost * (1.0 + fee_rate)


def position_pnl(cost: float, current_price: float, quantity: int = 1,
                 fee_rate: float = STEAM_FEE) -> dict:
    """Breakdown honesto de UMA posicao. 'market' e' o bruto (o que aparenta
    valer); 'net_if_sold' e' o que voce realmente recebe; 'pnl' e' a verdade."""
    cost_total = cost * quantity
    market = current_price * quantity
    net = net_proceeds(current_price, fee_rate) * quantity
    pnl = net - cost_total
    if pnl > 0.005:
        status = "profit"
    elif pnl < -0.005:
        status = "loss"
    else:
        status = "even"
    return {
        "cost_total": cost_total,
        "market": market,
        "net_if_sold": net,
        "pnl": pnl,
        "pnl_pct": (pnl / cost_total * 100) if cost_total else 0.0,
        "break_even": break_even_price(cost, fee_rate),
        "status": status,
    }


def has_cost_basis(pos: dict) -> bool:
    """True se a posicao tem custo CONHECIDO.

    O sync grava `cost: 0.0` porque a Steam nao diz quanto voce pagou --
    isso e' "desconhecido", nao "custou zero". Tratar os dois igual faz o
    P&L reportar o inventario inteiro como lucro: foi o que aconteceu na
    tela de conta (R$ 850,42 de "lucro" com R$ 0,00 investido).

    Item de drop realmente custou zero, mas ai' e' entrada manual --
    por isso a distincao olha a origem, nao so' o valor.
    """
    cost = pos.get("cost")
    if cost is None:
        return False
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return False
    if cost > 0:
        return True
    return pos.get("source") != "steam_sync"


def evaluate_portfolio(positions: list[dict], price_fn,
                       fee_rate: float = STEAM_FEE) -> dict:
    """positions: [{name, cost, quantity}]. price_fn(name) -> float | None.
    Retorna {rows, totals}. price_fn None -> linha sem preco (item ilustravel).

    P&L so' agrega posicoes com custo conhecido (ver has_cost_basis). Valor
    de mercado e liquido agregam TUDO -- esses nao dependem de custo.
    `totals.unknown_cost` diz quantas ficaram de fora, pra UI poder avisar
    em vez de exibir lucro inventado.
    """
    rows: list[dict] = []
    t_cost = t_market = t_net = 0.0
    t_net_conhecido = 0.0
    sem_custo = 0
    com_custo = 0
    for pos in positions:
        name = pos["name"]
        conhecido = has_cost_basis(pos)
        cost = float(pos.get("cost") or 0.0)
        qty = int(pos.get("quantity", 1))
        price = price_fn(name)
        if price is None:
            rows.append({"name": name, "cost": cost, "quantity": qty,
                         "price": None, "pnl": None,
                         "has_cost": conhecido})
            continue
        d = position_pnl(cost, price, qty, fee_rate)
        if not conhecido:
            # Sem custo nao ha' lucro nem prejuizo -- ha' valor.
            d["pnl"] = None
            d["pnl_pct"] = None
            d["is_profit"] = False
            d["is_loss"] = False
            sem_custo += 1
        rows.append({"name": name, "cost": cost, "quantity": qty,
                     "price": price, "has_cost": conhecido, **d})
        t_market += d["market"]
        t_net += d["net_if_sold"]
        if conhecido:
            com_custo += 1
            t_cost += d["cost_total"]
            t_net_conhecido += d["net_if_sold"]
    # O gatilho e' EXISTIR posicao com custo conhecido, nao o custo somar
    # mais que zero: drop declarado manualmente custa zero e tem P&L real.
    pnl = (t_net_conhecido - t_cost) if com_custo else None
    totals = {
        "cost": t_cost,
        "market": t_market,
        "net_if_sold": t_net,
        "pnl": pnl,
        "pnl_pct": (pnl / t_cost * 100) if (pnl is not None and t_cost) else None,
        "unknown_cost": sem_custo,
    }
    return {"rows": rows, "totals": totals}


# --- persistencia local -------------------------------------------------------
def load_portfolio(path: Path | str = _DEFAULT_PATH) -> list[dict]:
    data = load_json_record(path, [])
    return data if isinstance(data, list) else []


def save_portfolio(positions: list[dict], path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        atomic_write_text(p, json.dumps(positions, indent=2))
    except OSError as e:
        print(f"WARNING: failed to save portfolio: {e}", file=sys.stderr)


def add_position(name: str, cost: float, quantity: int = 1,
                 path: Path | str = _DEFAULT_PATH,
                 source: str = "manual") -> list[dict]:
    """Adiciona posicao. source distingue entrada manual de sync Steam
    (F10) -- usado pra preservar cost manual em syncs subsequentes."""
    positions = load_portfolio(path)
    positions.append({"name": name, "cost": float(cost),
                      "quantity": int(quantity), "added_ts": time.time(),
                      "source": source})
    save_portfolio(positions, path)
    return positions


def simulate_trade(buy_price: float, sell_price: float, quantity: int = 1,
                   fee_rate: float = STEAM_FEE) -> dict:
    """Simula uma transacao buy->sell e retorna breakdown completo pra UI.

    Diferente de position_pnl, foca em campos legiveis pelo simulador:
    cost_total, gross_sale, steam_fee, net_received, pnl, roi_pct,
    break_even_price (preco minimo de listagem pra empatar).
    """
    cost_total = buy_price * quantity
    gross_sale = sell_price * quantity
    net = net_proceeds(sell_price, fee_rate) * quantity
    fee = gross_sale - net
    pnl = net - cost_total
    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": quantity,
        "cost_total": round(cost_total, 2),
        "gross_sale": round(gross_sale, 2),
        "steam_fee": round(fee, 2),
        "net_received": round(net, 2),
        "pnl": round(pnl, 2),
        "roi_pct": round((pnl / cost_total * 100) if cost_total else 0.0, 2),
        "break_even_price": round(break_even_price(buy_price, fee_rate), 2),
        "is_profit": pnl > 0.005,
        "is_loss": pnl < -0.005,
    }


def _parse_brl(raw: str) -> float:
    """Converte string de custo para float, aceitando formatos BR e US.

    "200"       -> 200.0
    "650.50"    -> 650.5
    "R$ 200"    -> 200.0
    "R$ 1.234,50" -> 1234.5
    "1.234,50"  -> 1234.5
    "1234,50"   -> 1234.5
    """
    s = raw.replace("R$", "").strip()
    if "," in s and "." in s:
        # Formato BR: "1.234,50" -> remove pontos, troca virgula por ponto
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def import_csv(text: str, path: Path | str = _DEFAULT_PATH) -> dict:
    """Importa linhas CSV: nome, custo, qtd (opcional).

    Formatos aceitos:
      AK-47 | Redline (Field-Tested), 200, 1
      AWP | Asiimov (FT), 650.50

    Linhas com # sao ignoradas. Cost pode vir com R$.
    Retorna {imported, skipped, errors}."""
    imported = 0
    skipped = 0
    errors: list[str] = []
    for i, raw in enumerate(text.strip().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            skipped += 1
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            errors.append(f"Linha {i}: formato invalido (precisa de nome, custo) — '{line}'")
            continue
        name = parts[0]
        # Se tem mais de 3 partes, o custo BR tem virgula decimal
        # ex: "AK-47, R$ 1.234,50, 1" -> parts = [AK-47, R$ 1.234, 50, 1]
        if len(parts) > 3:
            cost_raw = ",".join(parts[1:-1])
            qty_raw = parts[-1]
        else:
            cost_raw = parts[1]
            qty_raw = parts[2] if len(parts) >= 3 and parts[2] else ""
        try:
            cost = _parse_brl(cost_raw)
        except ValueError:
            errors.append(f"Linha {i}: custo invalido '{cost_raw}' — '{line}'")
            continue
        try:
            qty = int(qty_raw) if qty_raw else 1
        except ValueError:
            errors.append(f"Linha {i}: quantidade invalida '{qty_raw}' — '{line}'")
            continue
        add_position(name, cost, max(qty, 1), path)
        imported += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}
