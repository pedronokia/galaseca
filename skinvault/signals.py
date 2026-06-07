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

    Para cada periodo, busca o entry mais antigo dentro da janela desejada
    (prioriza entries com time <= cutoff). Se nao houver entry antigo o
    suficiente, usa o mais proximo do cutoff. Descartado se o entry mais
    proximo estiver a mais de 20% do periodo alvo.

    age_hours no retorno reflete a idade real do entry usado, que pode
    ser maior ou menor que o rotulo. Ex.: "24h" com age_hours=20 significa
    que a variacao cobre ~20h, nao 24h exatas.

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
        # Entry mais proximo do cutoff, com desempate pro mais antigo
        # (time <= cutoff) quando as distancias sao iguais. Isso
        # garante janela >= periodo rotulado quando possivel.
        candidate = min(sorted_hist, key=lambda e: (abs(e["time"] - cutoff),
                                                      e["time"] > cutoff))
        # Só usa se estiver dentro da janela (tolera 20% além do período)
        if abs(candidate["time"] - cutoff) > period_h * 3600 * 0.2:
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


def price_zscore(price_history: list[dict], window: int = 30) -> dict:
    """Z-score do preco atual vs media e desvio padrao da janela trailing.

    z = (last_price - mean) / std

    z negativo => preco abaixo da media (potencial reversao a media para cima)
    z positivo => preco acima da media (potencial reversao para baixo)

    Sinal factual: descreve o quanto o preco atual se desvia do
    comportamento recente, normalizado pela volatilidade. NAO preve.

    Retorna {z, mean, std, window_used, band, label} ou {} se historico
    curto demais ou std == 0.
    """
    if not price_history or len(price_history) < window:
        return {}
    sorted_hist = sorted(price_history, key=lambda x: x["time"])
    prices = [p["price_median"] for p in sorted_hist[-window:]]
    last = prices[-1]
    mean_p = sum(prices) / len(prices)
    var = sum((p - mean_p) ** 2 for p in prices) / len(prices)
    std = var ** 0.5
    if std == 0 or mean_p == 0:
        return {}
    z = (last - mean_p) / std
    if z <= -2:
        band = "extreme_low"
    elif z <= -1:
        band = "low"
    elif z >= 2:
        band = "extreme_high"
    elif z >= 1:
        band = "high"
    else:
        band = "neutral"
    return {
        "z": round(z, 2),
        "mean": round(mean_p, 2),
        "std": round(std, 2),
        "window_used": len(prices),
        "band": band,
        "label": f"Z={z:.2f} ({band})",
    }


def relative_to_ath(price_history: list[dict]) -> dict:
    """Quao perto o preco atual esta do all-time high historico.

    Retorna {pct_of_ath, distance_pct, ath, current, band, label}.
    band: at_ath (>=0.9), near_ath (>=0.5), midrange (>=0.2),
          deep_below (>=0.05), very_deep (<0.05).

    Util pra detectar squeeze tardio em containers: preco perto do ATH
    historico tem upside limitado vs squeeze inicial (Chroma 2 em
    centavos vs Clutch ja' em dolares). Filosofia honesta: descreve, nao
    preve.
    """
    if not price_history or len(price_history) < 10:
        return {}
    # Robusto a entries sem 'time' (testes legados/fixtures simples):
    # se nao tiver time, assume ordem do input.
    try:
        sorted_h = sorted(price_history, key=lambda x: x["time"])
    except (KeyError, TypeError):
        sorted_h = list(price_history)
    prices = [p["price_median"] for p in sorted_h]
    ath = max(prices)
    if ath <= 0:
        return {}
    current = prices[-1]
    pct = current / ath
    distance_pct = (ath - current) / ath * 100
    if pct >= 0.9:
        band = "at_ath"
    elif pct >= 0.5:
        band = "near_ath"
    elif pct >= 0.2:
        band = "midrange"
    elif pct >= 0.05:
        band = "deep_below"
    else:
        band = "very_deep"
    return {
        "pct_of_ath": round(pct, 3),
        "distance_pct": round(distance_pct, 2),
        "ath": round(ath, 4),
        "current": round(current, 4),
        "band": band,
        "label": f"Preco a {pct:.0%} do ATH (${ath:.2f})",
    }


def data_quality(price_history: list[dict],
                  now: float | None = None) -> dict:
    """Estima confianca do sinal baseado em tamanho e recencia.

    confidence ∈ [0, 1]. Combina dois fatores:
      - size: len(history)/200 (saturado em 1.0)
      - recency: 1.0 se ultimo ponto <30d; decai linearmente ate 180d.

    now: timestamp de referencia (default time.time()). Util para
    backtest historico onde queremos calcular confianca em t passado.

    Retorna {confidence, n, age_days, level, label}.
    level: high (>=0.8), medium (>=0.5), low (>=0.2), very_low (<0.2).

    Util para:
      - Filtrar score: ignorar/dampear scores com baixa confianca
      - UI badge: mostrar ao usuario quando confiar no score
    """
    if not price_history:
        return {"confidence": 0.0, "n": 0, "age_days": None,
                "level": "none", "label": "sem dados"}
    n = len(price_history)
    size_factor = min(n / 200.0, 1.0)
    try:
        last_ts = max(p["time"] for p in price_history
                       if isinstance(p, dict) and "time" in p)
    except (TypeError, ValueError):
        return {"confidence": 0.0, "n": n, "age_days": None,
                "level": "none", "label": "dados invalidos"}
    ref_now = now if now is not None else time.time()
    age_days = (ref_now - last_ts) / 86400
    if age_days < 30:
        recency = 1.0
    elif age_days < 180:
        recency = max(0.0, 1.0 - (age_days - 30) / 150.0)
    else:
        recency = 0.0
    confidence = round(size_factor * recency, 2)
    if confidence >= 0.8:
        level = "high"
    elif confidence >= 0.5:
        level = "medium"
    elif confidence >= 0.2:
        level = "low"
    else:
        level = "very_low"
    return {
        "confidence": confidence,
        "n": n,
        "age_days": round(age_days, 1),
        "level": level,
        "label": f"Confianca {level} ({confidence:.2f}) — n={n}, "
                  f"ultimo {age_days:.0f}d atras",
    }


def drawdown(price_history: list[dict], window_days: int = 90) -> dict:
    """Drawdown atual = quanto o preco caiu vs o maximo da janela trailing.

    drawdown_pct: positivo 0..100. 0 = no maximo. 25 = 25% abaixo.
    band: at_high (<5%), mild (5-15%), moderate (15-30%), deep (>=30%).

    Sinal factual: descreve onde o preco esta em relacao ao pico recente,
    nao preve recuperacao.

    Retorna {drawdown_pct, max_price, current_price, days_since_max,
    band, label} ou {} se historico insuficiente.
    """
    if not price_history or len(price_history) < 5:
        return {}
    sorted_hist = sorted(price_history, key=lambda x: x["time"])
    last_ts = sorted_hist[-1]["time"]
    cutoff = last_ts - window_days * 86400
    window = [p for p in sorted_hist if p["time"] >= cutoff]
    if len(window) < 5:
        return {}
    max_entry = max(window, key=lambda x: x["price_median"])
    max_price = max_entry["price_median"]
    current = window[-1]["price_median"]
    if max_price == 0:
        return {}
    dd_pct = ((max_price - current) / max_price) * 100
    days_since_max = (last_ts - max_entry["time"]) / 86400
    if dd_pct < 5:
        band = "at_high"
    elif dd_pct < 15:
        band = "mild"
    elif dd_pct < 30:
        band = "moderate"
    else:
        band = "deep"
    return {
        "drawdown_pct": round(dd_pct, 2),
        "max_price": round(max_price, 2),
        "current_price": round(current, 2),
        "days_since_max": round(days_since_max, 1),
        "band": band,
        "label": f"DD {dd_pct:.1f}% ({band}), max {days_since_max:.0f}d atras",
    }


def enhanced_score(verdict: dict, volume: int | None = None,
                   supply: int | None = None,
                   multi_trend: dict | None = None,
                   price_history: list[dict] | None = None,
                   case_status: dict | None = None,
                   is_container: bool = False) -> tuple[int, list[dict]]:
    """Score 0-100 + breakdown com contribuicao de cada fator.

    Retorna (score_final, breakdown) onde breakdown e lista de
    {factor, delta, label} ordenada por |delta| decrescente.
    Base = 50, clipado em [0, 100].

    is_container: parametro mantido por compatibilidade; nao e' mais
    usado internamente (rel_ath agora aplica universal — backtest
    2026-06-07 validou ganho para skins tambem).
    """
    score = 50.0
    breakdown: list[dict] = []

    def _add(factor: str, delta: float, label: str) -> None:
        nonlocal score
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
        # EXPERIMENT 2026-06-07: fair_penalty_halving — REVERTIDO
        # Hipótese: trend falling quando preco esta "fair" (±5%) e' ruido.
        # Resultado: +0.0016 agg corr (56 itens, n=22014), abaixo do criterio
        # de +0.002. Keep: 85-100 intacto, 112 falsos negativos removidos.
        # Negative finding: efeito real mas marginal; nao justifica mudanca.
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

    # NOTAS DE EXPERIMENTOS (manter como guia):
    # - Z-score como reversao a media (universal): regrediu 7/9 itens.
    # - Z-score gated por trend (universal): regrediu agregado +0.041 -> +0.036.
    # - Z-score so' para containers: SEM ganho sobre drawdown sozinho
    #   (Clutch 0.0162->0.0171, Prisma 0.0534->0.0494, agg 0.0313->0.0304).
    #   Drawdown ja' captura o sinal que z-score tentava.
    # A funcao price_zscore() e is_container() seguem disponiveis como
    # sinais standalone para UI/alertas futuros, mas nao entram no score.

    # Drawdown como modificador de momentum (NAO reversao a media).
    # Hipotese: em mercado de skins, "at highs + trend up" confirma
    # momentum; "deep + falling" confirma distress continuo.
    if price_history and len(price_history) >= 30:
        dd = drawdown(price_history)
        if dd:
            band = dd["band"]
            dd_pct = dd["drawdown_pct"]
            trend_dir = verdict.get("trend_verdict", "")
            if band == "at_high" and trend_dir in ("rising", "stable"):
                _add("drawdown", 5,
                     f"No topo (DD {dd_pct:.0f}%) + trend up (+5)")
            elif band == "deep" and trend_dir == "falling":
                _add("drawdown", -5,
                     f"DD profundo {dd_pct:.0f}% + trend down (-5)")
            elif band == "deep" and trend_dir == "rising":
                _add("drawdown", 5,
                     f"DD profundo {dd_pct:.0f}% + recuperacao (+5)")

    # Momentum: preco atual vs media dos ultimos 15 pontos
    if price_history and len(price_history) >= 10:
        prices_m = [e["price_median"] for e in price_history[-15:]]
        mean_recent = sum(prices_m) / len(prices_m)
        last_p = prices_m[-1]
        if last_p > mean_recent * 1.02:
            _add("momentum", 5, "Acima da media recente (+5)")
        elif last_p < mean_recent * 0.98:
            _add("momentum", -5, "Abaixo da media recente (-5)")

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

    # Distancia ao ATH historico — UNIVERSAL (skins + containers).
    # Inicialmente testado so' para containers apos investigacao do Clutch Case.
    # Validado universal em 2026-06-07: agg corr +0.0985 -> +0.1173 (+19% rel).
    # Skins ganham sinal de mean reversion (corr +0.0239); containers mantem.
    # Bonifica squeeze inicial, penaliza squeeze tardio.
    if price_history and len(price_history) >= 10:
        rta = relative_to_ath(price_history)
        if rta:
            band = rta["band"]
            pct = rta["pct_of_ath"]
            if band == "very_deep":
                _add("rel_ath", 5,
                     f"{pct:.0%} do ATH (squeeze inicial) (+5)")
            elif band == "deep_below":
                _add("rel_ath", 2,
                     f"{pct:.0%} do ATH (squeeze ainda jovem) (+2)")
            elif band == "near_ath":
                _add("rel_ath", -8,
                     f"{pct:.0%} do ATH (squeeze tardio) (-8)")
            elif band == "at_ath":
                _add("rel_ath", -10,
                     f"{pct:.0%} do ATH (topo histórico) (-10)")

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
               case_status: dict | None = None,
               is_container: bool = False) -> int:
    """Wrapper retornando apenas o score. Ver enhanced_score para breakdown."""
    score, _ = enhanced_score(verdict, volume, supply, multi_trend,
                              price_history, case_status, is_container)
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


def is_score_stale(score_ts: float | None,
                   max_age_days: int = 7) -> bool:
    """True se score_ts e' None ou mais velho que max_age_days."""
    if score_ts is None:
        return True
    age_days = (time.time() - score_ts) / 86400
    return age_days > max_age_days


def score_age_text(score_ts: float | None) -> str:
    """Texto legivel da idade do score para tooltip."""
    if score_ts is None:
        return "nunca calculado"
    age_s = time.time() - score_ts
    if age_s < 60:
        return "agora"
    if age_s < 3600:
        return f"{int(age_s / 60)}min atras"
    if age_s < 86400:
        return f"{int(age_s / 3600)}h atras"
    days = age_s / 86400
    if days < 30:
        return f"{int(days)}d atras"
    return f"{int(days)}d atras (desatualizado)"


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
