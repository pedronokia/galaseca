"""Granularidade mista do price_history da Steam (diario + horario).

Medido em 2026-07-28 na serie da AK-47 | Redline (Field-Tested):
4510 intervalos de 86400s e 641 de 3600s, em 5188 pontos. A parte horaria
comecou em 28/06/2026 e cobre ~28 dias -- mas sao 677 PONTOS, entao
qualquer fatia por contagem le' errado.
"""
from __future__ import annotations

from skinvault import signals


DIA = 86400
HORA = 3600
BASE = 1_700_000_000 // DIA * DIA  # alinhado ao inicio de um dia UTC


def _diarios(n, preco=100.0, vol=600, inicio=BASE):
    return [{"time": inicio + i * DIA, "price_median": preco,
             "purchases": vol} for i in range(n)]


def _horarios(n, preco=100.0, vol=3, inicio=BASE):
    return [{"time": inicio + i * HORA, "price_median": preco,
             "purchases": vol} for i in range(n)]


# ── daily_series ───────────────────────────────────────────────────


def test_agrega_horarios_em_um_ponto_por_dia():
    ph = _horarios(48)  # 2 dias de dados horarios
    out = signals.daily_series(ph)
    assert len(out) == 2, "48 pontos horarios tem que virar 2 dias"
    assert out[0]["purchases"] == 24 * 3, "volume do dia e' a soma das horas"


def test_diarios_passam_intactos():
    out = signals.daily_series(_diarios(5))
    assert len(out) == 5
    assert out[0]["purchases"] == 600


def test_serie_mista_conta_dias_e_nao_pontos():
    """O caso real: historico diario seguido de cauda horaria."""
    ph = _diarios(30) + _horarios(24 * 5, inicio=BASE + 30 * DIA)
    out = signals.daily_series(ph)
    assert len(out) == 35, f"esperado 35 dias, veio {len(out)}"
    assert len(ph) == 150, "a serie crua tem 150 pontos -- 4x mais que dias"


def test_preco_ponderado_por_volume():
    """Dia com 2 pontos: preco e' a media ponderada pelas vendas."""
    ph = [
        {"time": BASE, "price_median": 100.0, "purchases": 10},
        {"time": BASE + HORA, "price_median": 200.0, "purchases": 90},
    ]
    out = signals.daily_series(ph)
    assert len(out) == 1
    assert out[0]["price_median"] == 190.0  # (100*10 + 200*90) / 100


def test_sem_volume_usa_media_simples():
    ph = [
        {"time": BASE, "price_median": 100.0, "purchases": 0},
        {"time": BASE + HORA, "price_median": 200.0, "purchases": 0},
    ]
    assert signals.daily_series(ph)[0]["price_median"] == 150.0


def test_corte_por_days_e_temporal():
    ph = _diarios(60)
    out = signals.daily_series(ph, days=15)
    assert len(out) == 15


def test_daily_series_ignora_entry_sem_time():
    ph = [{"price_median": 100.0}, {"time": BASE, "price_median": 50.0}]
    out = signals.daily_series(ph)
    assert len(out) == 1
    assert out[0]["price_median"] == 50.0


def test_daily_series_vazio_e_lixo():
    assert signals.daily_series([]) == []
    assert signals.daily_series([{"price_median": 1}]) == []
    assert signals.daily_series([{"time": "abc", "price_median": 1}]) == []


# ── recent_prices: o fallback importa ──────────────────────────────


def test_recent_prices_usa_tempo_quando_ha_timestamp():
    """5 dias de dados horarios = 5 valores, nao 120."""
    ph = _horarios(24 * 5)
    assert len(signals.recent_prices(ph, days=15)) == 5


def test_recent_prices_cai_pra_contagem_sem_timestamp():
    """Historico legado/sintetico sem `time` mantem comportamento antigo."""
    ph = [{"price_median": float(i)} for i in range(40)]
    out = signals.recent_prices(ph, days=15)
    assert len(out) == 15
    assert out[-1] == 39.0


# ── o bug de fato: momentum ────────────────────────────────────────


def test_momentum_nao_dispara_por_ruido_de_poucas_horas():
    """Alta nas ultimas horas nao pode virar 'acima da media' de 15 dias.

    Antes: [-15:] pegava 15 HORAS, entao qualquer oscilacao intradiaria
    dominava o fator. Agora a janela e' de 15 dias reais.
    """
    v = {"verdict": "fair", "diff_pct": 0}
    # 20 dias estaveis a 100, depois 15 horas a 110 no ultimo dia.
    ph = _diarios(20) + [
        {"time": BASE + 20 * DIA + i * HORA, "price_median": 110.0,
         "purchases": 3} for i in range(15)
    ]
    breakdown = signals.enhanced_score(v, price_history=ph)[1]
    fatores = {b.get("factor") or b.get("label"): b for b in breakdown}
    mom = [b for k, b in fatores.items() if k == "momentum"]
    if mom:
        # O ultimo dia (110) contra 20 dias a 100: a media de 15 dias fica
        # perto de 100, entao subir e' legitimo. O que nao pode acontecer e'
        # a media ser 110 (so' as 15 horas) e o momentum zerar.
        assert mom[0]["delta"] != 0, (
            "media calculada so' sobre as horas recentes anulou o sinal")


def test_momentum_preserva_comportamento_sem_timestamp():
    """Os testes historicos passam serie sem `time` -- nao pode quebrar."""
    v = {"verdict": "fair", "diff_pct": 0}
    ph_up = [{"price_median": 100.0}] * 14 + [{"price_median": 110.0}]
    ph_flat = [{"price_median": 100.0}] * 15
    delta = (signals.scan_score(v, price_history=ph_up)
             - signals.scan_score(v, price_history=ph_flat))
    assert delta == 5
