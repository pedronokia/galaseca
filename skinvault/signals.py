"""Sinais honestos sobre itens -- tendencia factual, liquidez, oferta.

Nada de 'vai valorizar', 'previsao', 'vencedor'. So' dados descritivos
que ajudam a decidir. A decisao e' sempre do usuario.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR

_DEFAULT_PATH = DATA_DIR / "item_history.json"

# Casos/containers notoriamente descontinuados (fonte: csgobackpack, community).
# NUNCA afirme "vai valorizar" por estar aqui.
_DISCONTINUED_NAMES = [
    "CS:GO Weapon Case", "CS:GO Weapon Case 2", "CS:GO Weapon Case 3",
    "Operation Bravo Case", "Operation Phoenix Case", "Operation Breakout Case",
    "Operation Vanguard Case", "Operation Falchion Case", "Operation Shadow Case",
    "Operation Wildfire Case", "Operation Bloodhound Case", "Operation Hydra Case",
    "Operation Shattered Web Case", "Operation Broken Fang Case",
    "Clutch Case", "Fracture Case", "Prisma Case", "Prisma 2 Case",
    "Revolver Case", "Spectrum Case", "Spectrum 2 Case",
    "Winter Offensive Case", "ESL One Cologne 2014", "ESL One Cologne 2015",
    "EMS One 2014",
]

_MIN_VOLUME_LIQUID = 50


def record_item_price(name: str, price: float,
                      path: Path | str = _DEFAULT_PATH) -> None:
    """Registra um snapshot de preco pro item. Cap em 100 entradas."""
    p = Path(path)
    try:
        data = json.loads(p.read_text("utf-8")) if p.exists() else {}
    except Exception:
        data = {}
    entry = data.setdefault(name, [])
    entry.append({"ts": time.time(), "price": price})
    if len(entry) > 100:
        entry[:] = entry[-100:]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def load_item_history(name: str,
                      path: Path | str = _DEFAULT_PATH) -> list[dict]:
    """Retorna a serie [{ts, price}] do item."""
    p = Path(path)
    try:
        data = json.loads(p.read_text("utf-8")) if p.exists() else {}
    except Exception:
        data = {}
    return data.get(name, [])


def trend(history: list[dict]) -> dict | None:
    """Tendencia factual descritiva. Nao preve futuro.

    Retorna {direction, change_pct, days, first_price, last_price, label}
    ou None se historico insuficiente."""
    if len(history) < 2:
        return None
    first = history[0]["price"]
    last = history[-1]["price"]
    if first == 0:
        return None
    days = (history[-1]["ts"] - history[0]["ts"]) / 86400
    change_pct = ((last - first) / first) * 100
    direction = "estavel" if change_pct == 0 else ("subiu" if change_pct > 0 else "caiu")
    if change_pct == 0:
        label = f"Preco estavel em {days:.0f}d" if days >= 1 else "Preco estavel"
    else:
        label = (
            f"{direction} {abs(change_pct):.1f}% em {days:.0f}d"
            if days >= 1 else
            f"{direction} {abs(change_pct):.1f}%"
        )
    return {
        "direction": direction,
        "change_pct": round(change_pct, 2),
        "days": round(days, 1),
        "first_price": first,
        "last_price": last,
        "label": label,
    }


def liquidity_flag(volume: int | None) -> dict:
    """Sinal de liquidez baseado no volume de 24h.

    Retorna {level, flag}. level em {liquid, low, unknown}."""
    if volume is None:
        return {"level": "unknown", "flag": ""}
    if volume >= _MIN_VOLUME_LIQUID:
        return {"level": "liquid", "flag": ""}
    return {
        "level": "low",
        "flag": f"Volume baixo ({volume}/dia) — pode ser dificil revender",
    }


def sma(values: list[float], period: int = 7) -> list[float | None]:
    """Simple Moving Average. Retorna lista do mesmo tamanho com None nos primeiros period-1."""
    if len(values) < period:
        return [None] * len(values)
    result: list[float | None] = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def find_support_resistance(
    price_history: list[dict],
    window: int = 5,
    min_separation_pct: float = 1.0,
) -> dict:
    """Retorna {support, resistance} com niveis de suporte/resistencia do historico.

    Detecta pontos de inflexao local (minimos/maximos) e agrupa niveis proximos.
    window: quantos pontos de cada lado para comparar.
    min_separation_pct: percentual minimo entre niveis agrupados.
    """
    prices = [p["price_median"] for p in price_history]
    if len(prices) < window * 2 + 1:
        return {"support": [], "resistance": []}

    pivots_low: list[float] = []
    pivots_high: list[float] = []
    for i in range(window, len(prices) - window):
        left = prices[i - window:i]
        right = prices[i + 1:i + window + 1]
        if prices[i] < min(left) and prices[i] < min(right):
            pivots_low.append(prices[i])
        if prices[i] > max(left) and prices[i] > max(right):
            pivots_high.append(prices[i])

    def _cluster(levels: list[float]) -> list[float]:
        if not levels:
            return []
        sorted_lv = sorted(levels)
        groups: list[list[float]] = [[sorted_lv[0]]]
        for v in sorted_lv[1:]:
            avg = sum(groups[-1]) / len(groups[-1])
            if abs(v - avg) / max(avg, 1) * 100 < min_separation_pct:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [round(sum(g) / len(g), 2) for g in groups]

    return {
        "support": _cluster(pivots_low),
        "resistance": _cluster(pivots_high),
    }


def scan_score(verdict: dict) -> int:
    """Score de 0-100 para classificacao de oportunidade.
    Quanto maior, melhor oportunidade de compra.
    Pondera: abaixo mediana (+40), spread tight (+25), buyer_dominant (+20), trending up (+15).
    Penaliza: overpriced (-40), seller_dominant (-15), trending down (-10).
    """
    score = 50  # neutro
    v = verdict.get("verdict", "")
    if v == "below_median":
        score += 40
    elif v == "fair":
        score += 20
    elif v == "slightly_above":
        score -= 10
    elif v == "overpriced":
        score -= 40

    sv = verdict.get("spread_verdict", "")
    if sv == "tight":
        score += 25
    elif sv == "wide":
        score -= 15

    bv = verdict.get("book_verdict", "")
    if bv == "buyer_dominant":
        score += 20
    elif bv == "seller_dominant":
        score -= 15

    tv = verdict.get("trend_verdict", "")
    if tv == "rising":
        score += 15
    elif tv == "falling":
        score -= 10

    return max(0, min(100, score))


def discontinued_flag(name: str) -> dict:
    """Sinal de oferta: item pode ser descontinuado (caixa antiga).

    Retorna {is_discontinued, flag}. Apenas informativo."""
    lower = name.lower()
    for known in _DISCONTINUED_NAMES:
        if known.lower() in lower:
            return {
                "is_discontinued": True,
                "flag": "Caixa descontinuada — oferta nao cresce mais",
            }
    return {"is_discontinued": False, "flag": ""}
