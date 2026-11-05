"""Mede, sem adivinhar, se um fator do score correlaciona com retorno real.

Reconstrói o score que `enhanced_score()` teria dado NUM INSTANTE PASSADO,
usando só o prefixo do histórico disponível até aquele instante (sem
lookahead), e compara com o retorno realmente observado dali pra frente.
É o mesmo método descrito nos comentários de `signals.py`/AGENTS.md (IC/
Spearman por horizonte, ON x OFF) -- só que o script que gerou aqueles
números não sobreviveu neste checkout. Este módulo reconstrói a FERRAMENTA
de medição; não reproduz nenhuma medição específica já feita.

Limite estrutural conhecido: os fatores "spread" (±25) e "book" (±20) de
`enhanced_score()` dependem do livro de ofertas (buy/sell orders) da Steam
AGORA -- a Steam não devolve histórico de livro de ofertas, só de preço
(`price_history`). Um backtest nunca consegue testar esses dois fatores;
só os fatores derivados de `price_history` (mediana, tendência, momentum,
multi-período, drawdown, distância do topo, nível de preço, caixa/
cápsula, risco de pump). Isso bate com os comentários de validação já
existentes em signals.py, que nunca citam spread/book.

Zero dependência nova: Spearman/Pearson implementados em Python puro
(mesmo espírito hand-rolled do resto do projeto -- rate_limit.py, db.py).

Dois limites de interpretação, achados em auditoria da skill
backtesting-frameworks (2026-11-05), que nenhum fix de código resolve
(são sobre como LER o número, não sobre como calculá-lo):

- Viés de seleção da amostra: `scripts/build_score_backtest_dataset.py`
  puxa nomes de `scan_targets.SCAN_BY_CATEGORY` -- uma lista fixa,
  escrita a mão, de itens POPULARES/conhecidos (Redline, Asiimov,
  Howl, karambits...), não uma amostra aleatória ou abrangente do
  mercado. Não é viés de sobrevivência clássico (itens não são
  removidos da lista por terem caído de preço -- a lista é por fama,
  não por desempenho), mas o IC/Spearman medido não necessariamente
  generaliza pra itens obscuros/pouco líquidos fora dela.
- Retorno medido é BRUTO: `forward_return()` não desconta a taxa de
  15% que a Steam cobra na venda (a mesma que `format_exit_context`
  em signals.py já avisa o usuário). Um IC positivo aqui mede
  correlação com movimento de preço, não lucro realizável líquido --
  consistente com o produto nunca prometer retorno (AGENTS.md), mas
  vale lembrar antes de usar o número pra decidir se vale a pena agir.
"""
from __future__ import annotations

import random
import statistics
import time
from typing import Callable

from galaseca import cases, signals, steam_api

_MIN_PONTOS_PARA_SCORE = 10  # mesmo piso que enhanced_score já exige
                              # pros fatores de price_history entrarem.
_JANELA_MEDIANA_DIAS = 30.0  # referência de "preço típico" no replay --
                              # mesmo papel do `median` que get_market_
                              # overview() devolve ao vivo, mas isso não
                              # tem equivalente histórico público: aqui é
                              # a mediana dos pontos dos últimos 30 dias
                              # DENTRO do prefixo (sem olhar o futuro).


def _prefixo_ate(price_history: list[dict], as_of_ts: float) -> list[dict]:
    """Só os pontos com `time <= as_of_ts`, ordenados -- o prefixo que
    teria existido naquele instante. Base de todo o resto deste módulo:
    sem isso, qualquer medição mede conhecimento do futuro."""
    pontos = sorted(
        (p for p in (price_history or [])
         if isinstance(p, dict) and p.get("time") is not None
         and p.get("price_median")),
        key=lambda p: p["time"])
    return [p for p in pontos if p["time"] <= as_of_ts]


def score_at(name: str, price_history: list[dict], as_of_ts: float,
            is_container: bool = False) -> "tuple[int, list[dict]] | None":
    """Score que `enhanced_score()` teria dado em `as_of_ts`, só com o
    prefixo do histórico disponível até lá. None se não há prefixo
    suficiente (mesmo piso de `enhanced_score` pros fatores de preço).

    `name`: usado só pra resolver `cases.case_status(name, as_of=...)` --
    não entra em nenhum cálculo de preço.
    """
    prefixo = _prefixo_ate(price_history, as_of_ts)
    if len(prefixo) < _MIN_PONTOS_PARA_SCORE:
        return None

    lowest = prefixo[-1]["price_median"]
    corte = as_of_ts - _JANELA_MEDIANA_DIAS * 86400
    janela = [p["price_median"] for p in prefixo if p["time"] >= corte]
    if not janela:
        janela = [p["price_median"] for p in prefixo]
    median = statistics.median(janela)

    # Sem order book histórico -- verdict sai sem spread_verdict/
    # book_verdict (ver limite documentado no topo do arquivo).
    verdict = steam_api.fair_value_verdict(lowest, median)
    multi = signals.multi_trend(prefixo)
    cs = cases.case_status(name, as_of=as_of_ts)

    return signals.enhanced_score(
        verdict, volume=None, supply=None, multi_trend=multi,
        price_history=prefixo, case_status=cs, is_container=is_container,
        now_ts=as_of_ts)


def forward_return(price_history: list[dict], as_of_ts: float,
                   horizon_days: float,
                   tolerancia_dias: float = 5.0) -> "float | None":
    """Retorno % realizado de `as_of_ts` até `as_of_ts + horizon_days`.

    None se não há ponto em `as_of_ts` (ou antes, mais próximo) ou se não
    há ponto dentro de `tolerancia_dias` do alvo futuro -- não inventa
    retorno de onde não há dado."""
    prefixo = _prefixo_ate(price_history, as_of_ts)
    if not prefixo:
        return None
    preco_base = prefixo[-1]["price_median"]
    if not preco_base:
        return None

    alvo_ts = as_of_ts + horizon_days * 86400
    candidatos = [
        p for p in (price_history or [])
        if isinstance(p, dict) and p.get("time") is not None
        and p.get("price_median")
        and abs(p["time"] - alvo_ts) <= tolerancia_dias * 86400
    ]
    if not candidatos:
        return None
    mais_proximo = min(candidatos, key=lambda p: abs(p["time"] - alvo_ts))
    return (mais_proximo["price_median"] - preco_base) / preco_base * 100


def _rank(valores: list[float]) -> list[float]:
    """Rank médio (lida com empates) -- base do Spearman."""
    ordenados = sorted(range(len(valores)), key=lambda i: valores[i])
    ranks = [0.0] * len(valores)
    i = 0
    while i < len(ordenados):
        j = i
        while j + 1 < len(ordenados) and valores[ordenados[j + 1]] == valores[ordenados[i]]:
            j += 1
        rank_medio = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[ordenados[k]] = rank_medio
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> "float | None":
    """Correlação de Pearson, Python puro. None se n < 2 ou variância 0."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def spearman(xs: list[float], ys: list[float]) -> "float | None":
    """Correlação de Spearman (Pearson sobre os ranks). None se n < 2."""
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    return pearson(_rank(xs), _rank(ys))


def bootstrap_ci(xs: list[float], ys: list[float], metodo: Callable = spearman,
                 n_resamples: int = 1000, confianca: float = 0.95,
                 seed: "int | None" = None) -> "dict | None":
    """Intervalo de confiança por bootstrap (resample pareado com
    reposição) -- mesma técnica de Monte Carlo sugerida por
    backtesting-frameworks (skill instalada em 2026-11-04) pra responder
    "essa correlação é real ou cabe dentro do ruído da amostra?", algo
    que os relatórios ON/OFF desta sessão não tinham: só o ponto
    estimado, sem faixa de incerteza.

    None se `xs`/`ys` tiverem menos de 2 pontos. Pode devolver um
    intervalo largo com poucas dezenas de pontos -- isso é o esperado,
    não um bug: bootstrap não inventa confiança que a amostra não tem.
    """
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    rng = random.Random(seed)
    valores = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        r = metodo([xs[i] for i in idx], [ys[i] for i in idx])
        if r is not None:
            valores.append(r)
    if not valores:
        return None
    valores.sort()
    cauda = (1 - confianca) / 2
    lo = valores[max(0, round(cauda * (len(valores) - 1)))]
    hi = valores[min(len(valores) - 1, round((1 - cauda) * (len(valores) - 1)))]
    return {"lower": lo, "upper": hi, "n_resamples": len(valores)}


def amostras(name: str, price_history: list[dict], is_container: bool,
            horizon_days: float, intervalo_dias: float = 30.0,
            agora: "float | None" = None) -> list[dict]:
    """Varre o histórico de UM item em pontos espaçados de `intervalo_dias`,
    calculando (score, raw_score, retorno) em cada um -- lookahead-safe.

    Pula pontos perto demais do fim da série (sem como medir o retorno
    futuro pedido) e os primeiros `_MIN_PONTOS_PARA_SCORE` pontos (sem
    como calcular o score). Retorna uma linha por amostra válida:
    {name, as_of_ts, score, raw_score, retorno_pct}.
    """
    prefixo_completo = _prefixo_ate(price_history, agora or time.time())
    if len(prefixo_completo) < _MIN_PONTOS_PARA_SCORE + 1:
        return []
    inicio = prefixo_completo[_MIN_PONTOS_PARA_SCORE]["time"]
    fim = prefixo_completo[-1]["time"] - horizon_days * 86400
    if fim <= inicio:
        return []

    out = []
    ts = inicio
    while ts <= fim:
        resultado = score_at(name, price_history, ts, is_container=is_container)
        if resultado is not None:
            score, breakdown = resultado
            ret = forward_return(price_history, ts, horizon_days)
            if ret is not None:
                out.append({
                    "name": name,
                    "as_of_ts": ts,
                    "score": score,
                    "raw_score": signals.raw_score(breakdown),
                    "retorno_pct": ret,
                })
        ts += intervalo_dias * 86400
    return out


def avaliar(itens: "list[dict]", horizon_days: float,
           intervalo_dias: float = 30.0,
           usar_raw_score: bool = True,
           agora: "float | None" = None,
           bootstrap: int = 0,
           seed: "int | None" = None) -> dict:
    """Roda `amostras()` em vários itens e agrega num relatório Sp/Pe.

    `itens`: [{"name", "price_history", "is_container"}, ...] -- formato
    de `scripts/build_score_backtest_dataset.py` (ver lá pra como gerar isso a
    partir da Steam).

    `usar_raw_score=True` usa a nota SEM o corte em [0,100] (mesmo motivo
    de `signals.raw_score`: dois itens cortados em 100 têm mérito
    diferente, e isso distorceria a correlação pra pior -- achado
    2026-11-04). `False` usa a nota exibida de verdade, pra quem quiser
    medir o efeito do próprio corte.

    `bootstrap`: se > 0, roda `bootstrap_ci()` sobre os pares (score,
    retorno) com esse número de resamples e inclui `spearman_ci`/
    `pearson_ci` no retorno. Default 0 (desligado) porque é caro -- cada
    resample recalcula a correlação do zero, e n aqui costuma ser
    grande (ver ressalva abaixo). CAVEAT: os pares NÃO são independentes
    -- várias linhas vêm da mesma série (amostrada a cada `intervalo_
    dias`) e de variantes-irmãs que se movem juntas no mercado, então
    esse bootstrap pareado tende a SUBESTIMAR a incerteza real (menos
    graus de liberdade do que `n` sugere). Útil pra comparar duas
    rodadas entre si; não é um p-valor rigoroso.

    Retorna {n, spearman, pearson, horizon_days} (+ spearman_ci/
    pearson_ci se `bootstrap>0`). n pequeno (poucas dezenas) não é
    amostra suficiente pra decisão nenhuma -- é só o que a ferramenta
    mede, a leitura é de quem chama.
    """
    linhas = []
    for item in itens:
        linhas.extend(amostras(
            item["name"], item.get("price_history") or [],
            bool(item.get("is_container")), horizon_days,
            intervalo_dias=intervalo_dias, agora=agora))

    chave = "raw_score" if usar_raw_score else "score"
    scores = [r[chave] for r in linhas]
    retornos = [r["retorno_pct"] for r in linhas]
    resultado = {
        "n": len(linhas),
        "spearman": spearman(scores, retornos),
        "pearson": pearson(scores, retornos),
        "horizon_days": horizon_days,
    }
    if bootstrap > 0:
        resultado["spearman_ci"] = bootstrap_ci(
            scores, retornos, metodo=spearman, n_resamples=bootstrap, seed=seed)
        resultado["pearson_ci"] = bootstrap_ci(
            scores, retornos, metodo=pearson, n_resamples=bootstrap, seed=seed)
    return resultado


def comparar_on_off(itens: "list[dict]", horizon_days: float,
                    ligar: Callable[[], None],
                    desligar: Callable[[], None],
                    **kwargs) -> dict:
    """Roda `avaliar()` duas vezes, ligando/desligando um fator entre as
    rodadas -- mesmo método ON x OFF dos comentários de signals.py.

    `ligar`/`desligar`: funções que mudam uma constante de módulo (ex.
    `lambda: setattr(signals, "_PRICE_LEVEL_ENABLED", True)`) e a
    restauram depois. Quem chama é responsável por deixar o estado como
    encontrou, mesmo em caso de erro -- este helper não faz isso sozinho
    de propósito: side effect em constante de módulo é coisa séria
    demais pra esconder atrás de um context manager implícito."""
    desligar()
    off = avaliar(itens, horizon_days, **kwargs)
    ligar()
    on = avaliar(itens, horizon_days, **kwargs)
    desligar()
    return {"on": on, "off": off}
