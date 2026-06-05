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
import time
from pathlib import Path

from skinvault._paths import DATA_DIR

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
        "pnl_pct": (pnl / cost_total) if cost_total else 0.0,
        "break_even": break_even_price(cost, fee_rate),
        "status": status,
    }


def evaluate_portfolio(positions: list[dict], price_fn,
                       fee_rate: float = STEAM_FEE) -> dict:
    """positions: [{name, cost, quantity}]. price_fn(name) -> float | None.
    Retorna {rows, totals}. price_fn None -> linha sem preco (item ilustravel)."""
    rows: list[dict] = []
    t_cost = t_market = t_net = 0.0
    for pos in positions:
        name = pos["name"]
        cost = float(pos["cost"])
        qty = int(pos.get("quantity", 1))
        price = price_fn(name)
        if price is None:
            rows.append({"name": name, "cost": cost, "quantity": qty,
                         "price": None, "pnl": None})
            continue
        d = position_pnl(cost, price, qty, fee_rate)
        rows.append({"name": name, "cost": cost, "quantity": qty, "price": price, **d})
        t_cost += d["cost_total"]
        t_market += d["market"]
        t_net += d["net_if_sold"]
    totals = {
        "cost": t_cost,
        "market": t_market,
        "net_if_sold": t_net,
        "pnl": t_net - t_cost,
        "pnl_pct": ((t_net - t_cost) / t_cost) if t_cost else 0.0,
    }
    return {"rows": rows, "totals": totals}


# --- persistencia local -------------------------------------------------------
def load_portfolio(path: Path | str = _DEFAULT_PATH) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_portfolio(positions: list[dict], path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(positions, indent=2), encoding="utf-8")
    except OSError:
        pass


def add_position(name: str, cost: float, quantity: int = 1,
                 path: Path | str = _DEFAULT_PATH) -> list[dict]:
    positions = load_portfolio(path)
    positions.append({"name": name, "cost": float(cost),
                      "quantity": int(quantity), "added_ts": time.time()})
    save_portfolio(positions, path)
    return positions


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
        try:
            cost = float(parts[1].replace("R$", "").replace(" ", "").replace(",", "."))
        except ValueError:
            errors.append(f"Linha {i}: custo invalido '{parts[1]}' — '{line}'")
            continue
        try:
            qty = int(parts[2]) if len(parts) >= 3 and parts[2] else 1
        except ValueError:
            errors.append(f"Linha {i}: quantidade invalida '{parts[2]}' — '{line}'")
            continue
        add_position(name, cost, max(qty, 1), path)
        imported += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}
