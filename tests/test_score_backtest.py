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


# ── bootstrap_ci ──────────────────────────────────────────────────

def test_bootstrap_ci_none_amostra_pequena():
    assert backtest.bootstrap_ci([1], [1]) is None


def test_bootstrap_ci_correlacao_perfeita_fica_estreito_em_1():
    xs = list(range(1, 21))
    ys = list(range(1, 21))
    ci = backtest.bootstrap_ci(xs, ys, n_resamples=200, seed=42)
    assert ci is not None
    assert ci["lower"] == pytest.approx(1.0, abs=0.01)
    assert ci["upper"] == pytest.approx(1.0, abs=0.01)
    assert ci["n_resamples"] == 200


def test_bootstrap_ci_amostra_pequena_sem_correlacao_fica_largo():
    """Com poucos pontos e nenhuma relação real, o IC tem que ser
    largo -- bootstrap não pode fabricar confiança que a amostra não
    tem."""
    rng_xs = [1, 5, 2, 8, 3, 9, 4, 7, 6, 10]
    rng_ys = [7, 2, 9, 1, 8, 3, 6, 4, 10, 5]  # embaralhado, sem relação
    ci = backtest.bootstrap_ci(rng_xs, rng_ys, n_resamples=300, seed=1)
    assert ci is not None
    assert ci["upper"] - ci["lower"] > 0.5


def test_bootstrap_ci_e_deterministico_com_seed():
    xs = [1, 3, 2, 5, 4, 7, 6, 9, 8, 10]
    ys = [2, 1, 4, 3, 6, 5, 8, 7, 10, 9]
    a = backtest.bootstrap_ci(xs, ys, n_resamples=100, seed=7)
    b = backtest.bootstrap_ci(xs, ys, n_resamples=100, seed=7)
    assert a == b


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


def test_avaliar_com_bootstrap_inclui_ci():
    preco_base = 100.0

    def preco_em(i):
        fase = i % 20
        if fase == 10:
            return preco_base * 0.7
        return preco_base

    serie = _serie_diaria(300, preco_em)
    itens = [{"name": "AK-47 | Redline (Field-Tested)",
             "price_history": serie, "is_container": False}]
    sem_ci = backtest.avaliar(itens, horizon_days=5, intervalo_dias=1.0,
                              agora=serie[-1]["time"])
    com_ci = backtest.avaliar(itens, horizon_days=5, intervalo_dias=1.0,
                              agora=serie[-1]["time"], bootstrap=50, seed=1)
    assert "spearman_ci" not in sem_ci
    assert com_ci["spearman_ci"] is not None
    assert com_ci["spearman_ci"]["lower"] <= com_ci["spearman"] <= com_ci["spearman_ci"]["upper"]
    assert com_ci["pearson_ci"] is not None


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


# ── split_itens: holdout item-level, estratificado ──────────────

def _itens_sinteticos(n_skins: int, n_containers: int) -> list:
    serie = _serie_diaria(10, lambda i: 100.0)
    out = [{"name": f"skin-{i}", "price_history": serie, "is_container": False}
           for i in range(n_skins)]
    out += [{"name": f"caixa-{i}", "price_history": serie, "is_container": True}
            for i in range(n_containers)]
    return out


def test_split_itens_nao_perde_nem_duplica_item():
    itens = _itens_sinteticos(14, 6)
    cal, conf = backtest.split_itens(itens, seed=1)
    nomes_cal = {it["name"] for it in cal}
    nomes_conf = {it["name"] for it in conf}
    assert not (nomes_cal & nomes_conf)
    assert nomes_cal | nomes_conf == {it["name"] for it in itens}
    assert len(cal) + len(conf) == len(itens)


def test_split_itens_estratifica_containers_e_skins():
    itens = _itens_sinteticos(20, 10)
    cal, conf = backtest.split_itens(itens, fracao_confirmacao=0.3, seed=1)
    cal_containers = sum(1 for it in cal if it["is_container"])
    conf_containers = sum(1 for it in conf if it["is_container"])
    # 30% de 10 caixas = 3 em confirmação, 7 em calibração -- nenhuma
    # categoria pode ficar ausente ou concentrada de um lado só.
    assert conf_containers == 3
    assert cal_containers == 7
    cal_skins = sum(1 for it in cal if not it["is_container"])
    conf_skins = sum(1 for it in conf if not it["is_container"])
    assert conf_skins == 6
    assert cal_skins == 14


def test_split_itens_reproduzivel_com_mesma_seed():
    itens = _itens_sinteticos(14, 6)
    cal1, conf1 = backtest.split_itens(itens, seed=42)
    cal2, conf2 = backtest.split_itens(itens, seed=42)
    assert [it["name"] for it in cal1] == [it["name"] for it in cal2]
    assert [it["name"] for it in conf1] == [it["name"] for it in conf2]


def test_split_itens_seeds_diferentes_dao_splits_diferentes():
    itens = _itens_sinteticos(20, 20)
    _, conf1 = backtest.split_itens(itens, seed=1)
    _, conf2 = backtest.split_itens(itens, seed=2)
    assert {it["name"] for it in conf1} != {it["name"] for it in conf2}


def test_split_itens_grupo_vazio_nao_quebra():
    itens = _itens_sinteticos(10, 0)  # sem nenhuma caixa
    cal, conf = backtest.split_itens(itens, seed=1)
    assert all(not it["is_container"] for it in cal + conf)
    assert len(cal) + len(conf) == 10


def test_split_itens_sem_itens():
    cal, conf = backtest.split_itens([], seed=1)
    assert cal == [] and conf == []
