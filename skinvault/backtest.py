"""Backtest do enhanced_score contra retornos futuros reais.

Usa o price_history (SSR) como verdade de campo: simula scoragem em
pontos no passado e mede o retorno realizado N dias depois.

Limitacao conhecida: order_book (spread, buy_count, sell_count) e
volume 24h "live" nao tem historico no SSR. O backtest cobre os sinais
baseados em preco e em purchases (volume diario do price_history).
Spread e book ficam fora desta versao.

Filosofia: o backtest NAO preve futuro. Ele mede empiricamente se a
heuristica do score correlaciona com retornos passados realizados.
"""
from __future__ import annotations

import statistics
from typing import Sequence

from skinvault import cases, signals


def score_from_history(name: str,
                        price_history: list[dict]) -> int | None:
    """Computa enhanced_score do item usando price_history como prefix 'agora'.

    Reconstroi verdict via _mock_verdict_from_history e roda enhanced_score.
    Sem dados de order book (nao temos historico) — so' sinais de preco +
    multi_trend + rel_ath + caso container + vintage.

    Util para watchlist/portfolio: "qual o score do meu item AGORA?"
    """
    if not price_history or len(price_history) < 5:
        return None
    verdict = _mock_verdict_from_history(price_history)
    if not verdict:
        return None
    mt = signals.multi_trend(price_history)
    vol = _volume_at(price_history, window_days=1)
    is_container = cases.is_container(name)
    cs = cases.case_status(name)
    score, _ = signals.enhanced_score(
        verdict, volume=vol, multi_trend=mt,
        price_history=price_history,
        case_status=cs,
        is_container=is_container,
    )
    return int(score)


def _slice_history(price_history: list[dict], cutoff_ts: float) -> list[dict]:
    """Retorna prefixo do price_history com time <= cutoff_ts."""
    return [p for p in price_history if p["time"] <= cutoff_ts]


def _mock_verdict_from_history(prefix: list[dict]) -> dict:
    """Reconstroi verdict factivel do prefixo (so sinais de preco).

    Usa mediana trailing 30d como referencia e ultimo price_median como
    "lowest". Trend baseado em media 7d vs 30d anteriores.
    Retorna {} se prefixo curto demais.
    """
    if len(prefix) < 5:
        return {}

    prices = [p["price_median"] for p in prefix]
    last = prices[-1]
    ref_window = prices[-30:] if len(prices) >= 30 else prices
    median = statistics.median(ref_window)
    if median == 0:
        return {}

    diff_pct = ((last - median) / median) * 100

    if diff_pct <= -5:
        verdict_lbl = "below_median"
    elif diff_pct <= 5:
        verdict_lbl = "fair"
    elif diff_pct <= 20:
        verdict_lbl = "slightly_above"
    else:
        verdict_lbl = "overpriced"

    result: dict = {
        "diff_pct": round(diff_pct, 2),
        "verdict": verdict_lbl,
    }

    # Tendencia recente: media 7d vs 30d anteriores
    if len(prices) >= 14:
        recent = statistics.mean(prices[-7:])
        older_window = prices[-30:-7] if len(prices) >= 30 else prices[:-7]
        if older_window:
            older = statistics.mean(older_window)
            if older > 0:
                if recent > older * 1.02:
                    result["trend_verdict"] = "rising"
                elif recent < older * 0.98:
                    result["trend_verdict"] = "falling"
                else:
                    result["trend_verdict"] = "stable"

    return result


def _price_at(price_history: list[dict], ts: float) -> float | None:
    """Retorna o price_median mais proximo de ts (em <= 7d) ou None."""
    if not price_history:
        return None
    sorted_hist = sorted(price_history, key=lambda x: x["time"])
    candidate = min(sorted_hist, key=lambda e: abs(e["time"] - ts))
    if abs(candidate["time"] - ts) > 7 * 86400:
        return None
    return candidate["price_median"]


def _future_return(price_history: list[dict], from_ts: float,
                   horizon_days: int) -> float | None:
    """Retorno realizado entre from_ts e from_ts + horizon. None se sem dado."""
    target_ts = from_ts + horizon_days * 86400
    p_start = _price_at(price_history, from_ts)
    p_end = _price_at(price_history, target_ts)
    if p_start is None or p_end is None or p_start == 0:
        return None
    return (p_end - p_start) / p_start


def _volume_at(prefix: list[dict], window_days: int = 1) -> int | None:
    """Soma de purchases nas ultimas window_days entradas do prefixo."""
    if not prefix:
        return None
    last = prefix[-min(window_days, len(prefix)):]
    total = sum(int(e.get("purchases", 0)) for e in last)
    return total if total > 0 else None


def simulate_item(name: str, price_history: list[dict],
                  horizon_days: int = 90,
                  step_days: int = 14,
                  min_history_days: int = 60,
                  with_factors: bool = False) -> list[dict]:
    """Roda backtest pra um item.

    Para cada ponto t (com step de step_days) no historico:
      1. Toma prefixo ate t
      2. Reconstroi verdict + multi_trend + volume estimado
      3. Calcula enhanced_score
      4. Compara com retorno realizado em t+horizon_days

    Retorna lista de {item, ts, score, return_pct, breakdown_count}.

    `with_factors=True` adiciona `factors`: {nome_do_fator: delta}, que e' o
    que `factor_ic()` consome pra medir cada fator separadamente.
    """
    if not price_history or len(price_history) < 20:
        return []

    sorted_hist = sorted(price_history, key=lambda x: x["time"])
    first_ts = sorted_hist[0]["time"]
    last_ts = sorted_hist[-1]["time"]

    samples: list[dict] = []
    step = step_days * 86400
    horizon = horizon_days * 86400

    t = first_ts + min_history_days * 86400
    while t < last_ts - horizon:
        prefix = _slice_history(sorted_hist, t)
        if len(prefix) < 5:
            t += step
            continue

        verdict = _mock_verdict_from_history(prefix)
        if not verdict:
            t += step
            continue

        mt = signals.multi_trend(prefix)
        vol = _volume_at(prefix, window_days=1)
        is_container = cases.is_container(name)
        # Status NO INSTANTE t: caixa com data de aposentadoria registrada
        # ainda aparece ativa antes dela (sem lookahead -- AGENTS.md 4f).
        cs = cases.case_status(name, as_of=t)
        score, breakdown = signals.enhanced_score(
            verdict, volume=vol, multi_trend=mt, price_history=prefix,
            case_status=cs,
            is_container=is_container,
            # Sem now_ts a idade do container seria "hoje menos lancamento"
            # em TODA amostra -- lookahead puro (ver enhanced_score).
            now_ts=t,
        )
        ret = _future_return(sorted_hist, t, horizon_days)
        if ret is None:
            t += step
            continue

        # Confidence no tempo de simulacao (now=t) — permite ver
        # confianca historica correta no scatter plot.
        dq = signals.data_quality(prefix, now=t)

        amostra = {
            "item": name,
            "ts": t,
            "score": score,
            "return_pct": round(ret * 100, 2),
            "breakdown_count": len(breakdown),
            "confidence": dq.get("confidence", 0.0),
            "level": dq.get("level", "none"),
        }
        if with_factors:
            fatores: dict = {}
            for b in breakdown:
                chave = b.get("factor") or b.get("label") or "?"
                fatores[chave] = fatores.get(chave, 0) + (b.get("delta") or 0)
            amostra["factors"] = fatores
        samples.append(amostra)
        t += step

    return samples


_DEFAULT_BUCKETS: tuple[tuple[int, int], ...] = (
    (0, 30), (30, 50), (50, 70), (70, 85), (85, 101),
)


def aggregate_by_bucket(
    samples: list[dict],
    buckets: Sequence[tuple[int, int]] = _DEFAULT_BUCKETS,
) -> list[dict]:
    """Agrega samples por bucket de score.

    Cada bucket e' [low, high) -- o ultimo deve cobrir 100 (use high=101).
    Retorna lista de {bucket, n, avg_return_pct, median_return_pct, hit_rate}.
    """
    out: list[dict] = []
    for low, high in buckets:
        in_bucket = [s for s in samples if low <= s["score"] < high]
        label = f"{low}-{min(high - 1, 100)}"
        if not in_bucket:
            out.append({
                "bucket": label,
                "n": 0,
                "avg_return_pct": 0.0,
                "median_return_pct": 0.0,
                "hit_rate": 0.0,
            })
            continue
        returns = [s["return_pct"] for s in in_bucket]
        positive = sum(1 for r in returns if r > 0)
        out.append({
            "bucket": label,
            "n": len(in_bucket),
            "avg_return_pct": round(statistics.mean(returns), 2),
            "median_return_pct": round(statistics.median(returns), 2),
            "hit_rate": round(positive / len(returns) * 100, 1),
        })
    return out


def _pearson_raw(x: list[float], y: list[float]) -> float | None:
    """Pearson bruto entre duas listas. None se < 3 ou variancia zero."""
    if len(x) < 3 or len(y) < 3:
        return None
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den_x = sum((v - mean_x) ** 2 for v in x) ** 0.5
    den_y = sum((v - mean_y) ** 2 for v in y) ** 0.5
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _rank(values: list[float]) -> list[float]:
    """Rank transform com average para ties."""
    indexed = [(v, i) for i, v in enumerate(values)]
    indexed.sort(key=lambda x: x[0])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j < len(indexed) and indexed[j][0] == indexed[i][0]:
            j += 1
        avg_rank = (i + j - 1) / 2.0  # average rank (0-indexed)
        for k in range(i, j):
            ranks[indexed[k][1]] = avg_rank
        i = j
    return ranks


def correlation(samples: list[dict],
                method: str = "spearman") -> float | None:
    """Correlacao entre score e return_pct. None se < 3 samples.

    method='spearman' (default) — rank-based, robusto a relacao S-shaped.
    method='pearson' — linear, sensivel a outliers.
    """
    if len(samples) < 3:
        return None
    scores = [float(s["score"]) for s in samples]
    returns = [s["return_pct"] for s in samples]
    if method == "spearman":
        r = _pearson_raw(_rank(scores), _rank(returns))
    else:
        r = _pearson_raw(scores, returns)
    return round(r, 4) if r is not None else None


# ── Analise CROSS-ITEM ─────────────────────────────────────────────
#
# `correlation()` mistura todas as amostras de todas as datas. Num mercado
# que subiu 12 anos, isso mede principalmente "o mercado subiu", nao "o
# score escolheu melhor". Medido em 2026-07-28 num corpus de 123 series:
# correlacao pooled +0.043 contra baseline de +6.25% em 90d -- o baseline
# explicava quase tudo.
#
# A pergunta que o scanner de fato responde e' transversal: entre os itens
# disponiveis HOJE, quais valem mais? Por isso a correlacao tem que ser
# calculada DENTRO de cada data e so' depois promediada entre datas. Assim
# o movimento de mercado atinge todos os itens da data igualmente e sai da
# conta. Em quant isso se chama information coefficient (IC).


def _bin_por_data(samples: list[dict], bin_days: int) -> dict:
    """Agrupa amostras em janelas de `bin_days`, chaveadas pelo indice."""
    largura = max(1, int(bin_days)) * 86400
    bins: dict = {}
    for s in samples:
        ts = s.get("ts")
        if ts is None:
            continue
        bins.setdefault(int(ts // largura), []).append(s)
    return bins


def cross_sectional_ic(samples: list[dict], bin_days: int = 14,
                       min_items: int = 6,
                       key: str = "score") -> dict:
    """IC do sinal: correlacao dentro de cada data, promediada.

    `key` escolhe o campo ranqueado (default "score").

    Retorna {ic_mean, ic_std, pct_positive, n_dates, ir}. `ir` e'
    ic_mean/ic_std -- consistencia do sinal, nao so' magnitude.

    ATENCAO ao interpretar n_dates: com horizonte de 90d e passo de 14d,
    datas vizinhas compartilham o mesmo retorno futuro. O numero efetivo de
    observacoes independentes e' ~n_dates * step/horizon, bem menor.
    """
    ics: list[float] = []
    for grupo in _bin_por_data(samples, bin_days).values():
        if len(grupo) < min_items:
            continue
        pares = [{"score": s.get(key, 0), "return_pct": s["return_pct"]}
                 for s in grupo]
        if len({p["score"] for p in pares}) < 2:
            continue  # sinal constante na data: nao ranqueia nada
        c = correlation(pares, method="spearman")
        if c is not None:
            ics.append(c)
    if not ics:
        return {"ic_mean": None, "ic_std": None, "pct_positive": None,
                "n_dates": 0, "ir": None}
    media = statistics.mean(ics)
    dp = statistics.pstdev(ics) if len(ics) > 1 else 0.0
    return {
        "ic_mean": round(media, 4),
        "ic_std": round(dp, 4),
        "pct_positive": round(
            sum(1 for c in ics if c > 0) / len(ics) * 100, 1),
        "n_dates": len(ics),
        "ir": round(media / dp, 3) if dp else None,
    }


def factor_ic(samples: list[dict], bin_days: int = 14,
              min_items: int = 6) -> list[dict]:
    """IC de CADA fator do breakdown, ordenado por |IC|.

    Exige amostras de simulate_item(with_factors=True).

    Serve pra achar fator com sinal INVERTIDO: um fator com IC negativo
    consistente nao e' ruido, e' sinal apontado pro lado errado, e ele
    cancela os fatores certos. Medido em 2026-07-28: `momentum` (-0.19) e
    `multi_period` (-0.14) anulavam `mediana` (+0.20) e `verdict` (+0.17),
    derrubando o IC do score inteiro pra +0.05.
    """
    nomes = sorted({k for s in samples for k in (s.get("factors") or {})})
    out: list[dict] = []
    for nome in nomes:
        marcados = [
            {**s, "_f": (s.get("factors") or {}).get(nome, 0)}
            for s in samples
        ]
        r = cross_sectional_ic(marcados, bin_days=bin_days,
                               min_items=min_items, key="_f")
        if r["ic_mean"] is None:
            continue
        r["factor"] = nome
        out.append(r)
    out.sort(key=lambda r: abs(r["ic_mean"]), reverse=True)
    return out


def quintile_spread(samples: list[dict], bin_days: int = 14,
                    min_items: int = 6, parts: int = 5,
                    key: str = "score") -> dict:
    """Retorno do topo vs base do ranking, comparados DENTRO da data.

    Retorna {top_pct, bottom_pct, spread_pp, top_median, bottom_median,
    spread_median_pp, n_top, n_bottom}. E' a leitura economica do IC:
    spread proximo de zero significa que o sinal nao separa, por melhor que
    a correlacao pareca.

    PREFIRA A MEDIANA. Retorno de skin tem cauda gorda: um item que saiu de
    R$ 0,03 pra R$ 5,00 e' +16.000% e sozinho destroi a media. Medido em
    2026-07-28 num corpus de 782 series: media do quintil superior deu 437%
    contra mediana de poucos por cento. A media so' e' util pra detectar
    justamente essa assimetria.
    """
    altos: list[float] = []
    baixos: list[float] = []
    for grupo in _bin_por_data(samples, bin_days).values():
        if len(grupo) < min_items:
            continue
        ordenado = sorted(grupo, key=lambda s: s.get(key, 0))
        k = max(1, len(ordenado) // max(2, parts))
        baixos.extend(s["return_pct"] for s in ordenado[:k])
        altos.extend(s["return_pct"] for s in ordenado[-k:])
    if not altos or not baixos:
        return {"top_pct": None, "bottom_pct": None, "spread_pp": None,
                "top_median": None, "bottom_median": None,
                "spread_median_pp": None, "n_top": 0, "n_bottom": 0}
    ma, mb = statistics.mean(altos), statistics.mean(baixos)
    da, db = statistics.median(altos), statistics.median(baixos)
    return {
        "top_pct": round(ma, 2),
        "bottom_pct": round(mb, 2),
        "spread_pp": round(ma - mb, 2),
        "top_median": round(da, 2),
        "bottom_median": round(db, 2),
        "spread_median_pp": round(da - db, 2),
        "n_top": len(altos),
        "n_bottom": len(baixos),
    }


def net_after_fee(gross_pct: float, fee_rate: float = 0.15) -> float:
    """Retorno liquido depois da taxa de venda, em %.

    CORRIGIDO em 2026-07-30. A versao anterior usava `preco * (1 - taxa)`,
    tratando a taxa como percentual do preco de COMPRA, e devolvia um
    break-even de 17,65%. Nao e' o que a Steam faz: a taxa incide sobre o
    valor do VENDEDOR. Voce lista a R$ 115, o comprador paga 115, voce
    recebe 115/1,15 = 100 -- entao o break-even e' exatamente a taxa, 15%.

    O modelo certo ja' estava em `portfolio.net_proceeds` desde sempre; os
    dois modulos discordavam. O numero do 4b muda junto: o quintil
    superior (+13,64% brutos) da' -1,18% liquidos, nao -3,41%.
    """
    return round(((1 + gross_pct / 100.0) / (1 + fee_rate) - 1) * 100, 2)


def breakeven_gross(fee_rate: float = 0.15) -> float:
    """Retorno bruto minimo pra empatar com a taxa, em %.

    Igual a' propria taxa: listar a custo*(1+taxa) devolve o custo.
    """
    return round(fee_rate * 100, 2)


def pearson_correlation(samples: list[dict]) -> float | None:
    """Correlacao de Pearson (linear) entre score e return_pct.
    Mantida como atalho para comparacoes; prefira correlation() default."""
    return correlation(samples, method="pearson")


def spearman_correlation(samples: list[dict]) -> float | None:
    """Correlacao de Spearman (rank-based) entre score e return_pct.
    Atalho para correlation(method='spearman')."""
    return correlation(samples, method="spearman")


def correlation_by_bucket(samples: list[dict],
                           bucket_lo: int = 70,
                           bucket_hi: int = 101) -> dict:
    """Pearson + Spearman limitado a amostras com score em [lo, hi).

    Retorna {'pearson': float|None, 'spearman': float|None, 'n': int}.
    Util para medir se a correlacao e' mais forte nos buckets altos
    (onde o score supostamente tem mais poder preditivo).
    """
    filtered = [s for s in samples
                if bucket_lo <= s["score"] < bucket_hi]
    if len(filtered) < 3:
        return {"pearson": None, "spearman": None, "n": len(filtered)}
    p = pearson_correlation(filtered)
    s = spearman_correlation(filtered)
    return {"pearson": p, "spearman": s, "n": len(filtered)}


def format_report(buckets: list[dict], spearman_value: float | None = None,
                  horizon_days: int = 30, total_samples: int = 0,
                  pearson_value: float | None = None) -> str:
    """Formata relatorio textual do backtest pra terminal.

    spearman_value e' a metrica principal (default).
    pearson_value e' exibido se fornecido para comparacao.
    """
    lines = [
        f"Backtest enhanced_score (horizonte: {horizon_days}d, "
        f"n={total_samples})",
        "",
        f"{'Bucket':<10} {'N':>6} {'Avg Ret':>10} {'Median':>10} {'Hit Rate':>10}",
        "-" * 50,
    ]
    for b in buckets:
        avg = f"{b['avg_return_pct']:+.2f}%"
        med = f"{b['median_return_pct']:+.2f}%"
        hit = f"{b['hit_rate']:.1f}%"
        lines.append(
            f"{b['bucket']:<10} {b['n']:>6} {avg:>10} {med:>10} {hit:>10}"
        )
    if spearman_value is not None:
        lines.append("")
        lines.append(f"Spearman(score, return): {spearman_value:+.4f} (default)")
    if pearson_value is not None:
        lines.append(f"Pearson(score, return):  {pearson_value:+.4f}")
    if spearman_value is not None or pearson_value is not None:
        lines.append(
            "  > 0 => score maior se associa a retorno maior (sinal valido)"
        )
    return "\n".join(lines)
