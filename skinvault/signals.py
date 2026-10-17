"""Sinais honestos sobre itens -- tendencia factual, liquidez, oferta.

Nada de 'vai valorizar', 'previsao', 'vencedor'. So' dados descritivos
que ajudam a decidir. A decisao e' sempre do usuario.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

from skinvault._paths import (
    DATA_DIR, atomic_write_text, load_json_record,
)

# EXPERIMENT 2026-06-08: vintage bonus — V4 APROVADO (Spearman criterion).
# Trajetoria:
# - V1 (+3 universal): reprovado — piorou skins (-0.0033 Pe), inflou b85+.
# - V2 (+3 containers-only): reprovado — Pe +0.0016 capsulas (falha);
#   bucket 85+ avg cai -4pp caixas, -2pp capsulas.
# - V3 aditivo (+1 containers-only): reprovado — Pe +0.0006 capsulas.
# - V3 multiplicativo (×1.05 containers-only): reprovado — Pe capsulas +0.0014.
# - V5 (+3 cont, age>=8, score>=60): inferior a V4 — Sp CAPSULAS +0.0010.
# - V6 (×1.03 mult, age>=10): borderline, pior que V4.
# V4 (+2 aditivo, containers-only, age >= 8): APROVADO por criterio Spearman
# (metrica default desde 2026-06-08, S-shaped em capsulas).
#   CAIXAS Sp +0.0057 / Pe +0.0046 — b85+ 200->233, avg +1.8pp, hit +2.7pp
#   CAPSULAS Sp +0.0031 / Pe +0.0011 — b85+ estavel (avg -0.6pp tolerado)
#   AUTOGRAPHS: sem efeito (todos pos-2021, age < 8)
#   SKINS: sem efeito (containers-only filter)
# 2/2 universos containers passam Sp >= 0.002. Bucket 85+ avg dentro
# tolerancia (cai < 2pp em qualquer universo).
# Detalhes: memory/vintage-v4-aprovado.md
#
# 2026-07-29: V4 DESLIGADO. A aprovacao acima media lookahead.
# `enhanced_score` calculava a idade como `date.today().year - year`, sem
# olhar o instante simulado -- entao TODA amostra de uma caixa de 2013
# recebia o bonus, inclusive as de 2013, quando ela tinha 0 anos. O fator
# virava uma constante por item, e o IC dele media "caixas lancadas ha'
# muito tempo se sairam bem", sabendo de antemao quais eram.
# Com `now_ts` passado pelo backtest (idade real no momento da amostra),
# medido em 41 caixas com serie diaria completa:
#   90d  -> Spearman -0.0002, Pearson -0.0031
#   365d -> Spearman -0.0080, Pearson -0.0067
# Nenhum passa o criterio de Sp >= +0.002; em 365d atrapalha claramente.
# Bate com o estudo de coortes do mesmo dia (AGENTS.md 4c): dentro das
# aposentadas, Spearman(idade, retorno) = -0.762. Premiar idade e' premiar
# a ponta que DECAI -- o ganho esta' na aposentadoria recente, nao na
# antiguidade.
# RESSALVA: reavaliado so' em CAIXAS. A aprovacao do v4 exigia 2/2
# universos (caixas + capsulas) e nao ha' serie de capsula em cache pra
# refazer o teste. Como o vies era estrutural e atingia todo universo
# igualmente, o +0.0031 das capsulas tambem esta' sob suspeita.
_VINTAGE_BONUS_ENABLED = False
_VINTAGE_AGE_YEARS = 8
_VINTAGE_BONUS = 2

# EXPERIMENT 2026-06-08: pump_risk penalty — V3 APROVADO.
# V1 (rally +30%/14d, penalty -10): reprovado — CAPSULAS -0.0044, Clutch
#   nao pego (criterio estrito demais).
# V2 (rally +20%/30d, peso 2 at_ath, exclusao valve_events, -10):
#   CAIXAS -0.0037 Sp (regressao), CAPSULAS +0.0037, SKINS +0.0081.
#   2/3 mas CAIXAS regrediu, Clutch ainda 27/206 no 85+ — zero melhora UX.
# V3B (-10 high + -3 medium): pior em CAIXAS (Sp -0.0051), b85+ avg cai.
# V3 (-5 high only) APROVADO:
#   CAIXAS Sp -0.0012 (negligivel), Pe +0.0018
#   CAPSULAS Sp +0.0039 / Pe +0.0020
#   AUTOGRAPHS Sp +0.0109 / Pe +0.0087
#   SKINS Sp +0.0033 / Pe +0.0022
# 3/4 universos melhoram em Sp E Pe. Bucket 85+ intacto (dN=0 em todos —
# items at_ath estao em buckets baixos, nao 85+). Mantém Clutch UX-limitada
# mas melhora correlacao consistente.
# Funcao pump_risk() ja era publica para coluna Risco no Scanner.
# Detalhes: memory/pump-risk-v3-aprovado.md
_PUMP_PENALTY_ENABLED = True
_PUMP_HIGH_PENALTY = -5

_DEFAULT_PATH = DATA_DIR / "item_history.json"
_VOLUME_PATH = DATA_DIR / "volume_history.json"
_SUPPLY_PATH = DATA_DIR / "supply_history.json"

# _DISCONTINUED_NAMES removida em 2026-07-29. Era uma lista escrita a mao,
# paralela ao catalogo de cases.py, e estava majoritariamente errada:
# 11 das 25 entradas nao casavam com caixa nenhuma ("Operation Phoenix
# Case" em vez de "...Weapon Case", "Operation Falchion Case" em vez de
# "Falchion Case", etc.), e 22 das 36 caixas descontinuadas reais passavam
# despercebidas -- 61% de falha, em silencio.
# A fonte da verdade agora e' cases.case_status(), cujos nomes foram
# verificados um a um contra a listing page da Steam.

# EXPERIMENT 2026-07-30: nivel de preco absoluto.
# Medido em 84 itens / 7541 amostras / 365d, cross-sectional por data
# (AGENTS.md 4d): IC do preco absoluto = -0.2635 no geral, -0.3036 em
# caixas, -0.0415 em skins. Negativo em 80% das janelas de 90d.
# Mediana do retorno 365d por faixa: R$0-1 +73.0%, R$1-5 +41.1%,
# R$5-20 +44.0%, R$20-100 +27.4%, R$100-500 +18.7%, R$500+ +8.7%.
# O score nunca viu preco absoluto -- foi o que produziu o anti-padrao do
# Clutch Case (memory/clutch-case-falling-knife).
# Faixas em escala log, que e' onde o efeito e' ~linear.
# APROVADO em 2026-07-30, CONTAINERS-ONLY. Medido ON x OFF, 153 itens:
#   CAIXAS  90d  Sp +0.0052 / Pe +0.0087   passa
#   CAIXAS 365d  Sp +0.0222 / Pe +0.0160   passa (o maior delta ja' medido)
#   SKINS   90d  Sp -0.0130               REPROVA
#   SKINS  365d  Sp +0.0007               abaixo do criterio
# 2/2 nos universos de container, igual ao criterio do vintage v4. Em
# skins o fator ATRAPALHA, o que bate com o IC (-0.30 caixas x -0.04
# skins) -- dai' o filtro `is_container`, mesmo padrao do vintage.
_PRICE_LEVEL_ENABLED = True

# 2026-10-17: momentum e multi_period com o SINAL DE REVERSAO A MEDIA.
# O backtest de 2026-07-28 (AGENTS.md 4b) mediu IC negativo nos dois em
# TODOS os horizontes de 7d a 365d (momentum -0.327 em 7d, -0.190 em 90d),
# estavel nas duas metades cronologicas -- e invertendo-os o IC do score
# ia de +0.051 a +0.207. A mudanca ficou registrada e nunca foi aplicada:
# o score seguia premiando "acima da media" e "todos os periodos subindo",
# exatamente o que o dado diz que reverte. +1 = pro-tendencia (antigo),
# -1 = reversao. Medicao ON x OFF: ver AGENTS.md 4e.
#
# SKINS-ONLY. Re-medido em 2026-10-17 (373 series, ~50-58 mil amostras por
# horizonte, IC transversal):
#   SKINS   7d IC 0.055 -> 0.301 | 90d 0.035 -> 0.160 | 365d 0.001 -> 0.052
#   CAIXAS  7d IC 0.036 -> 0.150 | 90d 0.024 -> 0.070 | 365d 0.065 -> 0.064
# Em caixas a 365d o Spearman cai 0.068 e a mediana do quintil superior vai
# de +66.8% a +59.9% -- e 365d em caixa e' justamente a tese de
# aposentadoria (4c), a unica que vence a taxa. Mesmo padrao das "duas
# familias" do 4b: reversao no curto, estrutural no longo em container.
_MOMENTUM_SIGN = -1
_MULTI_PERIOD_SIGN = -1
_REVERSAL_IN_CONTAINERS = False
# Bonus de drawdown "no topo + subindo" (+5). Contradiz a distancia do topo
# medida em 4d (IC -0.20), mas desligar NAO passou no criterio (2026-10-17):
# dSp +0.007 / +0.0002 / -0.003 em 7d/90d/365d. Negative finding: fica.
_DRAWDOWN_AT_HIGH_ENABLED = True
_PRICE_LEVEL_BANDS = (
    (5.0, 4, "abaixo de R$ 5"),
    (50.0, 2, "entre R$ 5 e 50"),
    (200.0, 0, "entre R$ 50 e 200"),
    (float("inf"), -4, "acima de R$ 200"),
)


def price_level_band(price: "float | None") -> "tuple[int, str] | None":
    """(delta, rotulo) da faixa de preco. None se nao ha' preco.

    Publica pra a UI poder mostrar a faixa mesmo com o fator desligado --
    mesmo padrao do `pump_risk`, que virou coluna antes de virar score.
    """
    if price is None or price <= 0:
        return None
    for teto, delta, rotulo in _PRICE_LEVEL_BANDS:
        if price < teto:
            return delta, rotulo
    return None


def price_band_labels() -> list[str]:
    """Rotulos das faixas de preco absoluto, em ordem crescente.

    Publica pra a UI montar um filtro por faixa usando as MESMAS bandas
    que ja' entram no score (price_level_band), em vez de inventar cortes
    novos e desalinhados do que o score considera.
    """
    return [rotulo for _, _, rotulo in _PRICE_LEVEL_BANDS]


_MIN_VOLUME_LIQUID = 50


def record_item_price(name: str, price: float,
                      path: Path | str = _DEFAULT_PATH) -> None:
    """Registra um snapshot de preco pro item. Cap em 100 entradas."""
    p = Path(path)
    data = load_json_record(p, {})
    if not isinstance(data, dict):
        data = {}
    entry = data.setdefault(name, [])
    entry.append({"ts": time.time(), "price": price})
    if len(entry) > 100:
        entry[:] = entry[-100:]
    try:
        atomic_write_text(p, json.dumps(data))
    except OSError as e:
        print(f"WARNING: failed to save item history: {e}", file=sys.stderr)


def load_item_history(name: str,
                      path: Path | str = _DEFAULT_PATH) -> list[dict]:
    """Retorna a serie [{ts, price}] do item."""
    p = Path(path)
    data = load_json_record(p, {})
    if not isinstance(data, dict):
        data = {}
    return data.get(name, [])


def _record_metric(name: str, value: float, path: Path) -> None:
    """Registra um snapshot de metrica (volume/supply). Cap em 100 entradas."""
    data = load_json_record(path, {})
    if not isinstance(data, dict):
        data = {}
    entry = data.setdefault(name, [])
    entry.append({"ts": time.time(), "value": value})
    if len(entry) > 200:
        entry[:] = entry[-200:]
    try:
        atomic_write_text(path, json.dumps(data))
    except OSError as e:
        print(f"WARNING: failed to save metric: {e}", file=sys.stderr)


def _load_metric_history(name: str, path: Path) -> list[dict]:
    """Retorna a serie [{ts, value}] de uma metrica."""
    data = load_json_record(path, {})
    if not isinstance(data, dict):
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


def approx_liquidity_from_ssr(price_history: list[dict] | None,
                              order_book: dict | None) -> dict:
    """Oferta/demanda aproximada a partir de UMA resposta SSR.

    Existe pra telas que so' tem price_history + order_book (a pagina de
    listagem) e nao querem pagar uma segunda chamada ao priceoverview so'
    pra ter o volume 24h real. Usa as `purchases` do ULTIMO DIA do
    price_history (via daily_series) como proxy de volume.

    Quem chama NUNCA deve gravar esse valor com record_item_volume: e'
    uma unidade diferente do volume 24h real que Scanner/Market gravam,
    e misturar as duas no mesmo volume_history.json contaminaria a
    deteccao de anomalia deles. `supply` (sell_count do order_book) e' a
    MESMA unidade em toda parte -- esse sim e' seguro compartilhar.

    Retorna {sd_label, supply} ou {} se faltar order_book ou dado
    suficiente pra montar a razao.
    """
    if not order_book:
        return {}
    supply = order_book.get("sell_count")
    diario = daily_series(price_history) if price_history else []
    approx_vol = diario[-1]["purchases"] if diario else None
    sd = supply_demand_ratio(approx_vol, supply)
    if not sd.get("ratio"):
        return {}
    return {"sd_label": sd["label"], "supply": supply}


def market_breadth(trends: list[str]) -> dict:
    """Retrato agregado de quantos itens escaneados sobem/caem/estao estaveis.

    trends: lista de trend_verdict por item ('rising'/'falling'/'stable';
    entradas vazias ou desconhecidas sao ignoradas).

    Sinal factual sobre o LOTE escaneado, nao sobre o mercado todo -- so'
    descreve a composicao do que ja' foi olhado, sem prever direcao futura.

    Retorna {total, up, down, flat, pct_up, pct_down, pct_flat, tone,
    label} ou {} se nao houver trend valido.
    tone: 'up' se pct_up supera pct_down por >=10pp, 'down' no inverso,
    'mixed' senao.
    """
    valid = [t for t in trends if t in ("rising", "falling", "stable")]
    if not valid:
        return {}
    total = len(valid)
    up = valid.count("rising")
    down = valid.count("falling")
    flat = total - up - down
    pct_up = up / total * 100
    pct_down = down / total * 100
    pct_flat = flat / total * 100
    if pct_up - pct_down >= 10:
        tone = "up"
        tone_label = "mercado em alta"
    elif pct_down - pct_up >= 10:
        tone = "down"
        tone_label = "mercado em queda"
    else:
        tone = "mixed"
        tone_label = "mercado misto"
    return {
        "total": total,
        "up": up,
        "down": down,
        "flat": flat,
        "pct_up": round(pct_up, 1),
        "pct_down": round(pct_down, 1),
        "pct_flat": round(pct_flat, 1),
        "tone": tone,
        "label": f"{tone_label} — {pct_up:.0f}% subindo, {pct_down:.0f}%"
                 f" caindo, {pct_flat:.0f}% estável (n={total})",
    }


def liquidity_depth(supply: int | None, volume_history: list[dict],
                    window: int = 7) -> dict:
    """Profundidade de liquidez: dias de listagens pela frente no ritmo atual.

    depth_days = supply / media do volume 24h nos ultimos `window` snapshots.
    Cada snapshot de volume_history JA e' um volume 24h da Steam (nao um
    incremento por poll), entao a media aproxima o volume diario mesmo com
    scans irregulares.

    Sinal factual -- descreve quanto tempo o estoque atual levaria pra
    esvaziar no ritmo de negociacao recente, nao preve quando isso vai
    acontecer.

    Retorna {days, avg_volume, supply, band, label} ou {} se supply ou
    historico de volume insuficientes.
    band: muito_liquido (<1d), liquido (<7d), moderado (<30d), fino (<90d),
    iliquido (>=90d).
    """
    if supply is None or supply <= 0 or not volume_history:
        return {}
    values = [e["value"] for e in volume_history[-window:]
              if isinstance(e, dict) and e.get("value")]
    if not values:
        return {}
    avg_volume = sum(values) / len(values)
    if avg_volume <= 0:
        return {}
    days = supply / avg_volume
    if days < 1:
        band = "muito_liquido"
    elif days < 7:
        band = "liquido"
    elif days < 30:
        band = "moderado"
    elif days < 90:
        band = "fino"
    else:
        band = "iliquido"
    days_str = f"{days:.1f}" if days < 10 else f"{days:.0f}"
    return {
        "days": round(days, 1),
        "avg_volume": round(avg_volume, 1),
        "supply": supply,
        "band": band,
        "label": f"~{days_str}d de listagens no ritmo atual "
                 f"({avg_volume:.0f}/dia)",
    }


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
        "label": f"Volume {direction} da média: {ratio:.1f}x" if is_anom else "",
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
    direction = "estável" if change_pct == 0 else ("subiu" if change_pct > 0 else "caiu")
    if change_pct == 0:
        label = f"Preço estável em {days:.0f}d" if days >= 1 else "Preço estável"
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
        "flag": f"Volume baixo ({volume}/dia) — pode ser difícil revender",
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
        direction = "subiu" if change > 0.5 else ("caiu" if change < -0.5 else "estável")
        label = labels.get(period_h, f"{period_h}h")

        result[label] = {
            "change_pct": round(change, 2),
            "age_hours": round(age_h, 1),
            "direction": direction,
            "first_price": first_price,
            "last_price": last_price,
        }

    return result


def daily_series(price_history: list[dict], days: int | None = None,
                 now: float | None = None) -> list[dict]:
    """Agrega o price_history em UM ponto por dia (UTC).

    Existe porque a Steam serve granularidade MISTA: diaria no historico
    antigo e HORARIA nos ultimos ~28 dias. Medido em 2026-07-28 na serie da
    AK-47 Redline FT: 4510 intervalos de 86400s contra 641 de 3600s, em
    5188 pontos. A transicao comecou em 28/06/2026.

    O efeito e' que fatia por contagem mente: `[-15:]` cobre 15 dias na
    regiao antiga e 15 HORAS na recente. E somar volume direto compara
    hora com dia (mediana de `purchases`: 605 nos pontos diarios, 3 nos
    horarios).

    Cada dia vira {time, price_median, purchases}, com preco ponderado por
    volume quando ha' `purchases` -- que e' o preco medio real das
    transacoes do dia -- e media simples quando nao ha'.

    Entries sem `time` sao ignorados; use `recent_prices()` quando o
    historico puder vir sem timestamp.
    """
    if not price_history:
        return []
    baldes: dict = {}
    for e in price_history:
        t = e.get("time")
        preco = e.get("price_median")
        if t is None or preco is None:
            continue
        try:
            dia = int(float(t) // 86400)
        except (TypeError, ValueError):
            continue
        try:
            vol = int(e.get("purchases") or 0)
        except (TypeError, ValueError):
            vol = 0
        b = baldes.setdefault(dia, {"soma_pv": 0.0, "vol": 0,
                                    "soma_p": 0.0, "n": 0})
        b["soma_pv"] += float(preco) * vol
        b["vol"] += vol
        b["soma_p"] += float(preco)
        b["n"] += 1

    out = []
    for dia in sorted(baldes):
        b = baldes[dia]
        preco = (b["soma_pv"] / b["vol"]) if b["vol"] else (b["soma_p"] / b["n"])
        out.append({"time": dia * 86400,
                    "price_median": preco,
                    "purchases": b["vol"]})
    if days is not None and days > 0:
        ref = now if now is not None else (out[-1]["time"] if out else 0)
        corte = ref - days * 86400
        out = [d for d in out if d["time"] > corte]
    return out


def recent_prices(price_history: list[dict], days: int = 15,
                  now: float | None = None) -> list[float]:
    """Precos recentes respeitando TEMPO, com fallback por contagem.

    Com `time` nos entries, agrega por dia e devolve os ultimos `days`.
    Sem `time` (historico sintetico ou legado), cai pro comportamento
    historico -- ultimos `days` pontos -- pra nao quebrar quem passa serie
    crua sem timestamp.
    """
    diario = daily_series(price_history, days=days, now=now)
    if diario:
        return [d["price_median"] for d in diario]
    return [e["price_median"] for e in price_history[-days:]
            if e.get("price_median") is not None]


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
        "label": f"Preço a {pct:.0%} do ATH (${ath:.2f})",
    }


def pump_risk(price_history: list[dict] | None = None,
              volume_history: list[dict] | None = None,
              category: str | None = None) -> dict:
    """Detecta combinacao de red flags de pump-and-dump / falling knife.

    Combina 3 sinais factuais (v2, 2026-06-08):
       1. Near/at ATH (rel_ath band) — at_ath conta como 2 flags
       2. Rally recente >= +20% em 30d — mais flexivel que v1 (+30%/14d)
       3. Volume sustentado 7d >= 2x media 30d — atividade anormal

    Se category e' fornecida e valve_events.latest_regime_change(category)
    retornar um evento < 30d atras, as flags ATH e rally sao suspensas
    (movimento tem catalyst legitimo conhecido). Apenas volume anomaly
    ainda conta.

    Output:
      {level: 'low'|'medium'|'high', flags: int, reasons: list[str]}

    level = 'low' se 0 flags, 'medium' se 1, 'high' se 2+.
    """
    reasons: list[str] = []
    flags = 0

    # Valve events exclusion: se categoria tem regime change recente,
    # suspende flags ATH e rally (movimento e' catalyst legitimo)
    from skinvault.valve_events import latest_regime_change
    regime_change = (latest_regime_change(category)
                     if category else None)
    regime_recent = (regime_change
                     and (date.today() - regime_change["date"]).days < 30)

    # Flag 1: near/at ATH (at_ath peso 2)
    if price_history and len(price_history) >= 10:
        rta = relative_to_ath(price_history)
        band = rta.get("band") if rta else None
        if band in ("near_ath", "at_ath") and not regime_recent:
            peso = 2 if band == "at_ath" else 1
            flags += peso
            pct = rta.get("pct_of_ath", 0) * 100
            reasons.append(f"{pct:.0f}% do ATH ({band}, peso {peso})")

    # Flag 2: rally recente >= +20% em 30d (v1 era +30%/14d)
    if price_history and len(price_history) >= 30 and not regime_recent:
        try:
            sorted_h = sorted(price_history, key=lambda x: x["time"])
        except (KeyError, TypeError):
            sorted_h = list(price_history)
        prices = [p["price_median"] for p in sorted_h]
        if len(prices) >= 30:
            recent = prices[-1]
            earlier = prices[-30]
            if earlier > 0:
                pct_change = (recent - earlier) / earlier
                if pct_change >= 0.20:
                    flags += 1
                    reasons.append(f"Rally +{pct_change*100:.0f}% em 30d")

    # Flag 3: volume sustentado 7d vs 30d
    if volume_history and len(volume_history) >= 30:
        recent_7 = volume_history[-7:]
        baseline_window = volume_history[-30:-7]
        if recent_7 and baseline_window:
            avg_7 = sum(e.get("value", 0) for e in recent_7) / len(recent_7)
            avg_baseline = (sum(e.get("value", 0) for e in baseline_window)
                            / len(baseline_window))
            if avg_baseline > 0 and avg_7 / avg_baseline >= 2.0:
                flags += 1
                reasons.append(
                    f"Volume 7d {avg_7 / avg_baseline:.1f}x acima média 30d"
                )

    if flags >= 2:
        level = "high"
    elif flags == 1:
        level = "medium"
    else:
        level = "low"

    return {"level": level, "flags": flags, "reasons": reasons}


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
        "label": f"Confiança {level} ({confidence:.2f}) — n={n}, "
                  f"último {age_days:.0f}d atrás",
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
        "label": f"DD {dd_pct:.1f}% ({band}), max {days_since_max:.0f}d atrás",
    }


def enhanced_score(verdict: dict, volume: int | None = None,
                   supply: int | None = None,
                   multi_trend: dict | None = None,
                   price_history: list[dict] | None = None,
                   case_status: dict | None = None,
                   is_container: bool = False,
                   volume_history: list[dict] | None = None,
                   now_ts: float | None = None,
                   ) -> tuple[int, list[dict]]:
    """Score 0-100 + breakdown com contribuicao de cada fator.

    Retorna (score_final, breakdown) onde breakdown e lista de
    {factor, delta, label} ordenada por |delta| decrescente.
    Base = 50, clipado em [0, 100].

    is_container: usado pelo vintage bonus (V4, aprovado em 2026-06-08)
    quando a caixa eh descontinuada ha >= 8 anos. rel_ath aplica
    universal desde 2026-06-07, entao nao depende mais de is_container.

    now_ts: instante de referencia pra IDADE do container. Default None =
    agora, que e' o certo ao vivo. O backtest precisa passar o timestamp da
    amostra: sem isso a idade era sempre "hoje menos o ano de lancamento",
    entao uma amostra de 2013 numa caixa de 2013 recebia o bonus de
    vintage como se ela ja' tivesse 13 anos (medido em 2026-07-29). O
    fator virava uma constante por item, e o IC dele media conhecimento do
    futuro.
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
        _add("trend", 15, "Tendência: subindo (+15)")
    elif tv == "falling":
        # EXPERIMENT 2026-06-07: fair_penalty_halving — REVERTIDO
        # Hipótese: trend falling quando preco esta "fair" (±5%) e' ruido.
        # Resultado: +0.0016 agg corr (56 itens, n=22014), abaixo do criterio
        # de +0.002. Keep: 85-100 intacto, 112 falsos negativos removidos.
        # Negative finding: efeito real mas marginal; nao justifica mudanca.
        _add("trend", -10, "Tendência: caindo (-10)")

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
            if (_DRAWDOWN_AT_HIGH_ENABLED and band == "at_high"
                    and trend_dir in ("rising", "stable")):
                _add("drawdown", 5,
                     f"No topo (DD {dd_pct:.0f}%) + trend up (+5)")
            elif band == "deep" and trend_dir == "falling":
                _add("drawdown", -5,
                     f"DD profundo {dd_pct:.0f}% + trend down (-5)")
            elif band == "deep" and trend_dir == "rising":
                _add("drawdown", 5,
                     f"DD profundo {dd_pct:.0f}% + recuperacao (+5)")

    # Momentum: preco atual vs media dos ultimos 15 DIAS.
    # Era `price_history[-15:]` -- 15 pontos. Funcionava enquanto a Steam
    # servia so' dado diario; com pontos horarios nos ultimos ~28 dias
    # virou "media das ultimas 15 horas" em silencio. recent_prices()
    # agrega por dia quando ha' timestamp e mantem o corte por contagem
    # quando nao ha'.
    # Reversao a media so' fora de container (ver _REVERSAL_IN_CONTAINERS).
    reverte = (not is_container) or _REVERSAL_IN_CONTAINERS
    sinal_mom = _MOMENTUM_SIGN if reverte else 1
    sinal_mp = _MULTI_PERIOD_SIGN if reverte else 1

    if price_history and len(price_history) >= 10:
        prices_m = recent_prices(price_history, days=15)
        if not prices_m:
            prices_m = [e["price_median"] for e in price_history[-15:]]
        mean_recent = sum(prices_m) / len(prices_m)
        last_p = prices_m[-1]
        # Com sinal -1, acima da media PERDE ponto (tende a reverter) e
        # abaixo GANHA.
        if last_p > mean_recent * 1.02:
            d = 5 * sinal_mom
            _add("momentum", d, f"Acima da média recente ({d:+d})")
        elif last_p < mean_recent * 0.98:
            d = -5 * sinal_mom
            _add("momentum", d, f"Abaixo da média recente ({d:+d})")

    # Concordancia multi-periodo
    if multi_trend and len(multi_trend) >= 3:
        dirs = []
        for lbl in ("24h", "7d", "30d", "90d"):
            if lbl in multi_trend:
                cp = multi_trend[lbl]["change_pct"]
                dirs.append(cp > 0)
        if len(dirs) >= 3:
            if all(dirs):
                d = 10 * sinal_mp
                _add("multi_period", d,
                     f"{len(dirs)} periodos subindo ({d:+d})")
            elif not any(dirs):
                d = -10 * sinal_mp
                _add("multi_period", d,
                     f"{len(dirs)} periodos caindo ({d:+d})")

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

    # Nivel de preco absoluto (2026-07-30). O preco vem do ULTIMO ponto do
    # prefixo, entao no backtest e' o preco no instante simulado -- sem
    # lookahead, ao contrario do que acontecia com a idade do vintage.
    if _PRICE_LEVEL_ENABLED and is_container and price_history:
        try:
            preco_atual = sorted(
                price_history, key=lambda e: e["time"])[-1]["price_median"]
        except (KeyError, IndexError, TypeError):
            preco_atual = None
        faixa = price_level_band(preco_atual)
        if faixa and faixa[0]:
            delta, rotulo = faixa
            _add("price_level", delta,
                 f"Preço {rotulo} ({delta:+d})")

    # Caixa descontinuada / rara (F7)
    #
    # NAO IMPLEMENTADO (2026-08-08): fator de "recencia de aposentadoria"
    # informado por caixa-aposentadoria-salto-e-decai (idade desde
    # aposentar, nao desde lancamento, tem Sp(idade,retorno)=-0.762 dentro
    # das aposentadas). cases.py so' guarda ano de LANCAMENTO -- a data de
    # aposentadoria (a variavel que importa) nao e' recuperavel hoje:
    # items_game.txt nao cobre a era pre-2016 e nao tem drop pool na era
    # CS:GO (negative-finding-data-aposentadoria), e nao ha' fonte publica
    # unica e confiavel pras 36 caixas discontinued (achado novo, mesma
    # investigacao, ver negative-finding-retirement-recency-2026-08).
    # Retomar so' quando gamedata.py acumular eventos reais de retirada
    # com retorno 365d ja observado.
    if case_status:
        if case_status.get("is_discontinued"):
            _add("case", 5, "Caixa descontinuada (+5)")
        elif case_status.get("is_rare"):
            _add("case", 3, "Caixa rara (+3)")

        # V4: vintage +2 aditivo, CONTAINERS-only, age >= 8 anos.
        # +2 em vez de +3 (v2) evita inflar borderlines no bucket 85+;
        # aditivo em vez de ×1.05 (v3 mult) e mais previsivel.
        # Validado em 2026-06-08: CAIXAS Sp +0.0057, CAPSULAS Sp +0.0031.
        if (_VINTAGE_BONUS_ENABLED
                and is_container
                and case_status.get("is_discontinued")):
            year = case_status.get("year")
            if year:
                ano_ref = (date.today().year if now_ts is None
                           else time.localtime(now_ts).tm_year)
                age = ano_ref - year
                if age >= _VINTAGE_AGE_YEARS:
                    score += _VINTAGE_BONUS
                    breakdown.append({
                        "factor": "vintage",
                        "delta": _VINTAGE_BONUS,
                        "label": f"Vintage ({age} anos descontinuado) (+{_VINTAGE_BONUS})",
                    })

    # V3/V4: pump_risk penalty -5 em 'high' (2+ flags combinadas).
    # Combina near_ath + rally 30d + volume sustentado. So' high para nao
    # double-count com rel_ath sozinho. -5 (em vez de v1/v2 -10) calibrado
    # via backtest 2026-06-08: 3/4 universos melhoram Sp+Pe, bucket 85+ intacto.
    # V4 (2026-06-09): regime change window 180d -> 30d, para suspender flags
    # apenas em catalisadores muito recentes. Efeito apenas live (backtest
    # nao passa category para pump_risk).
    if _PUMP_PENALTY_ENABLED and price_history:
        pr = pump_risk(price_history, volume_history)
        if pr["level"] == "high":
            reason_short = ", ".join(pr["reasons"][:2]) or "multiplas flags"
            _add("pump_risk", _PUMP_HIGH_PENALTY,
                 f"Risco alto: {reason_short} ({_PUMP_HIGH_PENALTY})")

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
        return f"{int(age_s / 60)}min atrás"
    if age_s < 86400:
        return f"{int(age_s / 3600)}h atrás"
    days = age_s / 86400
    if days < 30:
        return f"{int(days)}d atrás"
    return f"{int(days)}d atrás (desatualizado)"


def discontinued_flag(name: str) -> dict:
    """Sinal de oferta: o item E' um container descontinuado.

    Retorna {is_discontinued, flag}. Apenas informativo.

    Dispara so' quando o proprio item e' o container. `case_status` tambem
    resolve SKIN -> caixa de origem, e usar isso aqui marcaria toda skin de
    caixa antiga como "descontinuada" -- outra afirmacao, que mudaria o
    significado do sinal.
    """
    alvo = (name or "").strip().lower()
    if not alvo:
        return {"is_discontinued": False, "flag": ""}
    from skinvault import cases
    # `case_status` casa por nome exato; canonicaliza antes pra "clutch case"
    # continuar valendo, como valia com o match case-insensitive antigo.
    canonico = name
    for catalogo in (cases._CASES, cases._CAPSULES,
                     cases._AUTOGRAPH_CAPSULES):
        achado = next((k for k in catalogo if k.lower() == alvo), None)
        if achado:
            canonico = achado
            break
    st = cases.case_status(canonico)
    container = (st.get("case") or "").strip().lower()
    if st.get("is_discontinued") and container == canonico.strip().lower():
        return {
            "is_discontinued": True,
            "flag": "Caixa descontinuada — oferta não cresce mais",
        }
    return {"is_discontinued": False, "flag": ""}
