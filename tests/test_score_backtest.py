"""Testes de galaseca/backtest.py -- a ferramenta de medição em si, não
nenhuma conclusão sobre o modelo. Series sintéticas, sem rede."""
from __future__ import annotations

import time

import pytest

from galaseca import score_backtest as backtest

_DIA = 86400.0


def _serie_diaria(n_dias: int, preco_em: "callable", inicio: float = 0.0):
    """Uma série de n_dias pontos diários, preço = preco_em(indice_do_dia)."""
    return [{"time": inicio + i * _DIA, "price_median": preco_em(i)}
            for i in range(n_dias)]


# ── _prefixo_ate / score_at: sem lookahead ──────────────────────

def test_score_at_none_com_historico_curto():
    serie = _serie_diaria(5, lambda i: 100.0)
    assert backtest.score_at("Item X", serie, serie[-1]["time"]) is None


def test_score_at_ignora_pontos_depois_do_corte():
    """O mesmo prefixo até `as_of_ts` tem que dar o MESMO score, não
    importa o que exista depois dele na série -- essa é a garantia
    central do módulo inteiro."""
    serie = _serie_diaria(40, lambda i: 100.0 - i)  # caindo, linear
    corte = serie[29]["time"]
    resultado_sem_futuro = backtest.score_at(
        "AK-47 | Redline (Field-Tested)", serie[:30], corte)

    serie_com_futuro_diferente = serie[:30] + _serie_diaria(
        20, lambda i: 9999.0, inicio=serie[30]["time"])
    resultado_com_futuro = backtest.score_at(
        "AK-47 | Redline (Field-Tested)", serie_com_futuro_diferente, corte)

    assert resultado_sem_futuro is not None
    assert resultado_sem_futuro == resultado_com_futuro


def test_score_at_devolve_score_e_breakdown_validos():
    serie = _serie_diaria(60, lambda i: 100.0 - i * 0.5)  # caindo suave
    resultado = backtest.score_at(
        "AK-47 | Redline (Field-Tested)", serie, serie[-1]["time"])
    assert resultado is not None
    score, breakdown = resultado
    assert 0 <= score <= 100
    assert isinstance(breakdown, list)


# ── forward_return ───────────────────────────────────────────────

def test_forward_return_calcula_retorno_correto():
    serie = _serie_diaria(120, lambda i: 100.0)
    # duplica o preço exatamente 90 dias depois do ponto de partida
    serie[90]["price_median"] = 200.0
    ret = backtest.forward_return(serie, serie[0]["time"], horizon_days=90)
    assert ret == pytest.approx(100.0)


def test_forward_return_none_sem_ponto_no_horizonte():
    serie = _serie_diaria(10, lambda i: 100.0)  # só 10 dias de dado
    assert backtest.forward_return(serie, serie[0]["time"], horizon_days=365) is None


def test_forward_return_none_sem_prefixo():
    serie = _serie_diaria(10, lambda i: 100.0, inicio=1000 * _DIA)
    assert backtest.forward_return(serie, 0.0, horizon_days=10) is None


def test_forward_return_aceita_ponto_proximo_dentro_da_tolerancia():
    # Só dois pontos: base (dia 0) e um único ponto futuro no dia 91 --
    # sem ambiguidade de qual é "o mais próximo" do alvo (dia 90).
    serie = [
        {"time": 0.0, "price_median": 100.0},
        {"time": 91 * _DIA, "price_median": 150.0},
    ]
    ret = backtest.forward_return(serie, 0.0, horizon_days=90,
                                  tolerancia_dias=5)
    assert ret == pytest.approx(50.0)


# ── pearson / spearman ───────────────────────────────────────────

def test_pearson_correlacao_perfeita_positiva():
    assert backtest.pearson([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == pytest.approx(1.0)


def test_pearson_correlacao_perfeita_negativa():
    assert backtest.pearson([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)


def test_pearson_none_amostra_pequena_ou_sem_variancia():
    assert backtest.pearson([1], [1]) is None
    assert backtest.pearson([5, 5, 5], [1, 2, 3]) is None


def test_spearman_imune_a_outlier_que_pearson_nao_e():
    """Um outlier extremo não deveria quebrar o rank -- Spearman
    continua perfeito, Pearson degrada."""
    xs = [1, 2, 3, 4, 5]
    ys = [10, 20, 30, 40, 1000]  # ordem crescente, mas não linear
    assert backtest.spearman(xs, ys) == pytest.approx(1.0)
    assert backtest.pearson(xs, ys) < 0.9


def test_spearman_lida_com_empates():
    xs = [1, 1, 2, 3]
    ys = [1, 1, 2, 3]
    assert backtest.spearman(xs, ys) == pytest.approx(1.0)


# ── amostras / avaliar: integração fim-a-fim sintética ───────────

def test_avaliar_detecta_correlacao_sintetica_conhecida():
    """Série fabricada onde 'mais barato que a própria mediana recente'
    SEMPRE precede uma volta ao normal (retorno positivo) -- o fator
    'mediana' domina o score aqui (sem spread/book/caixa), então a
    correlação tem que sair claramente positiva. Não testa se o MODELO
    é bom; testa se avaliar() mede o que deveria medir."""
    preco_base = 100.0

    def preco_em(i):
        # oscila: barato nos dias pares (85), caro nos ímpares (115),
        # mas sempre volta pra 100 um dia depois -- "comprar no dip"
        # sempre compensa aqui, de propósito.
        fase = i % 20
        if fase == 10:
            return preco_base * 0.7  # bem abaixo
        return preco_base

    serie = _serie_diaria(300, preco_em)
    itens = [{"name": "AK-47 | Redline (Field-Tested)",
             "price_history": serie, "is_container": False}]
    relatorio = backtest.avaliar(itens, horizon_days=5, intervalo_dias=1.0,
                                 agora=serie[-1]["time"])
    assert relatorio["n"] > 10
    assert relatorio["spearman"] is not None
    # Mais barato (nota mais alta) correlaciona com retorno melhor --
    # IC negativo na convenção "preço absoluto" dos comentários de
    # signals.py seria sobre PREÇO; aqui é sobre NOTA, que já embute o
    # sinal invertido (nota alta = barato), então o esperado é positivo.
    assert relatorio["spearman"] > 0


def test_avaliar_vazio_sem_itens():
    relatorio = backtest.avaliar([], horizon_days=90)
    assert relatorio == {"n": 0, "spearman": None, "pearson": None,
                         "horizon_days": 90}


def test_comparar_on_off_chama_ligar_e_desligar_na_ordem_certa():
    chamadas = []
    serie = _serie_diaria(60, lambda i: 100.0 - i * 0.3)
    itens = [{"name": "AK-47 | Redline (Field-Tested)",
             "price_history": serie, "is_container": False}]
    resultado = backtest.comparar_on_off(
        itens, horizon_days=10,
        ligar=lambda: chamadas.append("on"),
        desligar=lambda: chamadas.append("off"),
        intervalo_dias=5.0, agora=serie[-1]["time"])
    assert chamadas == ["off", "on", "off"]
    assert "on" in resultado and "off" in resultado
