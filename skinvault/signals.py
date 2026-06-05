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
_VOLUME_PATH = DATA_DIR / "volume_history.json"
_SUPPLY_PATH = DATA_DIR / "supply_history.json"

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


def _record_metric(name: str, value: float, path: Path) -> None:
    """Registra um snapshot de metrica (volume/supply). Cap em 100 entradas."""
    try:
        data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    entry = data.setdefault(name, [])
    entry.append({"ts": time.time(), "value": value})
    if len(entry) > 200:
        entry[:] = entry[-200:]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _load_metric_history(name: str, path: Path) -> list[dict]:
    """Retorna a serie [{ts, value}] de uma metrica."""
    try:
        data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    return data.get(name, [])


def record_item_volume(name: str, volume: int) -> None:
    """Registra snapshot do volume 24h do item."""
    _record_metric(name, float(volume), _VOLUME_PATH)


def load_item_volume(name: str) -> list[dict]:
    """Retorna historico de volume [{ts, value}]."""
    return _load_metric_history(name, _VOLUME_PATH)


def record_item_supply(name: str, supply: int) -> None:
    """Registra snapshot da oferta (cSellOrders) do item."""
    _record_metric(name, float(supply), _SUPPLY_PATH)


def load_item_supply(name: str) -> list[dict]:
    """Retorna historico de oferta [{ts, value}]."""
    return _load_metric_history(name, _SUPPLY_PATH)


def supply_demand_ratio(volume: int | None, supply: int | None) -> dict:
    """Razao oferta/demanda. Quanto maior, mais demanda por anuncio."""
    if volume is None or supply is None or supply == 0:
        return {"ratio": 0, "label": "N/D"}
    ratio = volume / supply
    label = f"{ratio:.2f}" if ratio < 10 else f"{ratio:.1f}"
    return {"ratio": round(ratio, 4), "label": label}


def volume_anomaly(history: list[dict], factor: float = 2.0) -> dict:
    """Detecta se o ultimo volume esta anormal vs a media movel.

    Retorna {is_anomaly, ratio, current, avg, direction, label}.
    """
    if len(history) < 4:
        return {"is_anomaly": False, "ratio": 1.0}
    values = [e["value"] for e in history]
    current = values[-1]
    if len(values) < 3:
        return {"is_anomaly": False, "ratio": 1.0}
    avg = sum(values[:-1]) / (len(values) - 1)
    if avg == 0:
        return {"is_anomaly": False, "ratio": 1.0}
    ratio = current / avg
    is_anom = ratio >= factor or ratio <= (1 / factor)
    direction = "acima" if ratio >= factor else ("abaixo" if ratio <= (1 / factor) else "normal")
    return {
        "is_anomaly": is_anom,
        "ratio": round(ratio, 2),
        "current": int(current),
        "avg": round(avg, 1),
        "direction": direction,
        "label": f"Volume {direction} da media: {ratio:.1f}x" if is_anom else "",
    }


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


def multi_trend(price_history: list[dict], periods: list[int] | None = None) -> dict:
    """Calcula variacao percentual em multiplos periodos a partir do price_history SSR.

    price_history: lista de {time: unix_seconds, price_median: float, purchases: int}
    periods: lista de janelas em horas (ex: [24, 168, 720, 2160, 8760])
    Retorna dict com {period_label: {change_pct, age_hours, direction, first_price, last_price}}

    Exemplo de retorno:
    {"24h": {"change_pct": 1.2, "age_hours": 23, "direction": "subiu", ...},
     "7d":  {"change_pct": -3.5, "age_hours": 160, "direction": "caiu", ...}}
    """
    if periods is None:
        periods = [24, 168, 720, 2160, 8760]  # 24h, 7d, 30d, 90d, 1y
    if not price_history or len(price_history) < 2:
        return {}

    now = time.time()
    sorted_hist = sorted(price_history, key=lambda x: x["time"])
    last_price = sorted_hist[-1]["price_median"]
    last_ts = sorted_hist[-1]["time"]

    result: dict = {}
    labels = {24: "24h", 168: "7d", 720: "30d", 2160: "90d", 8760: "1y"}

    for period_h in periods:
        cutoff = last_ts - period_h * 3600
        # Encontra o entry mais proximo do cutoff
        candidate = None
        for entry in sorted_hist:
            if entry["time"] >= cutoff:
                candidate = entry
                break
        if candidate is None:
            continue

        first_price = candidate["price_median"]
        if first_price == 0:
            continue

        age_h = (now - candidate["time"]) / 3600
        change = ((last_price - first_price) / first_price) * 100
        direction = "subiu" if change > 0.5 else ("caiu" if change < -0.5 else "estavel")
        label = labels.get(period_h, f"{period_h}h")

        result[label] = {
            "change_pct": round(change, 2),
            "age_hours": round(age_h, 1),
            "direction": direction,
            "first_price": first_price,
            "last_price": last_price,
        }

    return result


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


def enhanced_score(verdict: dict, volume: int | None = None,
                   supply: int | None = None,
                   multi_trend: dict | None = None,
                   price_history: list[dict] | None = None,
                   case_status: dict | None = None) -> tuple[int, list[dict]]:
    """Score 0-100 + breakdown com contribuicao de cada fator.

    Retorna (score_final, breakdown) onde breakdown e lista de
    {factor, delta, label} ordenada por |delta| decrescente.
    Base = 50, clipado em [0, 100].
    """
    score = 50.0
    breakdown: list[dict] = []

    def _add(factor: str, delta: float, label: str) -> None:
        nonlocal score
        if delta == 0:
            return
        score += delta
        breakdown.append({
            "factor": factor,
            "delta": round(delta, 1),
            "label": label,
        })

    # Diferenca da mediana
    diff = verdict.get("diff_pct") or 0
    if diff < 0:
        bonus = min(abs(diff) * 1.2, 35)
        _add("mediana", bonus, f"Mediana: {diff:.1f}% (+{bonus:.0f})")
    elif diff > 0:
        penalty = min(diff * 0.8, 35)
        _add("mediana", -penalty, f"Mediana: +{diff:.1f}% (-{penalty:.0f})")

    v = verdict.get("verdict", "")
    if v == "below_median":
        _add("verdict", 5, "Abaixo da mediana (+5)")
    elif v == "overpriced":
        _add("verdict", -5, "Sobrepreco (-5)")

    sv = verdict.get("spread_verdict", "")
    if sv == "tight":
        _add("spread", 25, "Spread apertado (+25)")
    elif sv == "wide":
        _add("spread", -15, "Spread largo (-15)")

    bv = verdict.get("book_verdict", "")
    if bv == "buyer_dominant":
        _add("book", 20, "Book: compradores dominam (+20)")
    elif bv == "seller_dominant":
        _add("book", -15, "Book: vendedores dominam (-15)")

    tv = verdict.get("trend_verdict", "")
    if tv == "rising":
        _add("trend", 15, "Tendencia: subindo (+15)")
    elif tv == "falling":
        _add("trend", -10, "Tendencia: caindo (-10)")

    # Oferta / Demanda
    if volume is not None and supply is not None and supply > 0:
        sd = volume / supply
        if sd >= 5:
            _add("supply_demand", 15, f"S/D forte ({sd:.1f}) (+15)")
        elif sd >= 3:
            _add("supply_demand", 10, f"S/D bom ({sd:.1f}) (+10)")
        elif sd < 0.5:
            _add("supply_demand", -10, f"S/D fraco ({sd:.2f}) (-10)")

    # Momentum: preco vs SMA curta
    if price_history and len(price_history) >= 10:
        prices_m = [e["price_median"] for e in price_history[-15:]]
        sma10 = sum(prices_m) / len(prices_m)
        last_p = prices_m[-1]
        if last_p > sma10 * 1.02:
            _add("momentum", 5, "Acima da SMA curta (+5)")
        elif last_p < sma10 * 0.98:
            _add("momentum", -5, "Abaixo da SMA curta (-5)")

    # Concordancia multi-periodo
    if multi_trend and len(multi_trend) >= 3:
        dirs = []
        for lbl in ("24h", "7d", "30d", "90d"):
            if lbl in multi_trend:
                cp = multi_trend[lbl]["change_pct"]
                dirs.append(cp > 0)
        if len(dirs) >= 3:
            if all(dirs):
                _add("multi_period", 10, f"{len(dirs)} periodos subindo (+10)")
            elif not any(dirs):
                _add("multi_period", -10, f"{len(dirs)} periodos caindo (-10)")

    # Bonus de volume
    if volume is not None and volume > 2000:
        _add("liquidity", 5, f"Volume alto ({int(volume)}) (+5)")

    # Caixa descontinuada / rara (F7)
    if case_status:
        if case_status.get("is_discontinued"):
            _add("case", 5, "Caixa descontinuada (+5)")
        elif case_status.get("is_rare"):
            _add("case", 3, "Caixa rara (+3)")

    final = max(0, min(100, int(round(score))))
    breakdown.sort(key=lambda b: abs(b["delta"]), reverse=True)
    return final, breakdown


def scan_score(verdict: dict, volume: int | None = None,
               supply: int | None = None,
               multi_trend: dict | None = None,
               price_history: list[dict] | None = None,
               case_status: dict | None = None) -> int:
    """Wrapper retornando apenas o score. Ver enhanced_score para breakdown."""
    score, _ = enhanced_score(verdict, volume, supply, multi_trend,
                              price_history, case_status)
    return score


def format_breakdown(breakdown: list[dict]) -> str:
    """Formata breakdown como texto multi-linha para tooltip."""
    if not breakdown:
        return "Sem fatores relevantes (base 50)"
    lines = []
    pos = [b for b in breakdown if b["delta"] > 0]
    neg = [b for b in breakdown if b["delta"] < 0]
    if pos:
        lines.append("Positivos:")
        for b in pos:
            lines.append(f"  + {b['label']}")
    if neg:
        if pos:
            lines.append("")
        lines.append("Negativos:")
        for b in neg:
            lines.append(f"  - {b['label']}")
    return "\n".join(lines)


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
