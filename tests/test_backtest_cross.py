"""Analise cross-item do backtest: IC, IC por fator e spread de quintil."""
from __future__ import annotations

from skinvault import backtest


DIA = 86400
BASE = 1_700_000_000 // DIA * DIA


def _am(ts, score, ret, fatores=None):
    s = {"item": f"i{score}", "ts": ts, "score": score, "return_pct": ret}
    if fatores is not None:
        s["factors"] = fatores
    return s


def _data(ts, pares, fator=None):
    """Uma data com varios itens: pares = [(score, retorno), ...]."""
    return [
        _am(ts, sc, r, {fator: sc} if fator else None) for sc, r in pares
    ]


# ── cross_sectional_ic ─────────────────────────────────────────────


def test_ic_perfeito_quando_score_ordena_o_retorno():
    am = []
    for d in range(6):
        am += _data(BASE + d * 14 * DIA,
                    [(10, 1.0), (30, 2.0), (50, 3.0),
                     (70, 4.0), (85, 5.0), (95, 6.0)])
    r = backtest.cross_sectional_ic(am)
    assert r["n_dates"] == 6
    assert r["ic_mean"] == 1.0
    assert r["pct_positive"] == 100.0


def test_ic_negativo_quando_o_sinal_esta_invertido():
    am = []
    for d in range(6):
        am += _data(BASE + d * 14 * DIA,
                    [(10, 6.0), (30, 5.0), (50, 4.0),
                     (70, 3.0), (85, 2.0), (95, 1.0)])
    assert backtest.cross_sectional_ic(am)["ic_mean"] == -1.0


def test_ic_ignora_data_com_poucos_itens():
    am = _data(BASE, [(10, 1.0), (90, 2.0)])          # 2 itens
    am += _data(BASE + 14 * DIA,
                [(10, 1.0), (30, 2.0), (50, 3.0),
                 (70, 4.0), (85, 5.0), (95, 6.0)])     # 6 itens
    assert backtest.cross_sectional_ic(am)["n_dates"] == 1


def test_ic_ignora_data_com_score_constante():
    """Score igual pra todo mundo nao ranqueia nada."""
    am = _data(BASE, [(50, r) for r in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)])
    assert backtest.cross_sectional_ic(am)["n_dates"] == 0


def test_ic_vazio_e_seguro():
    r = backtest.cross_sectional_ic([])
    assert r["n_dates"] == 0 and r["ic_mean"] is None


def test_ic_calcula_ir():
    am = []
    for d in range(4):
        am += _data(BASE + d * 14 * DIA,
                    [(10, 1.0), (30, 2.0), (50, 3.0),
                     (70, 4.0), (85, 5.0), (95, 6.0)])
    r = backtest.cross_sectional_ic(am)
    assert r["ic_std"] == 0.0
    assert r["ir"] is None  # dp zero: IR indefinido, nao infinito


def test_ic_separa_datas_por_bin():
    """Amostras a 30 dias de distancia nao podem cair na mesma data."""
    am = _data(BASE, [(s, float(s)) for s in (10, 30, 50, 70, 85, 95)])
    am += _data(BASE + 30 * DIA,
                [(s, float(s)) for s in (10, 30, 50, 70, 85, 95)])
    assert backtest.cross_sectional_ic(am, bin_days=14)["n_dates"] == 2


# ── factor_ic ──────────────────────────────────────────────────────


def test_factor_ic_acha_fator_invertido():
    """O caso real: um fator que anda ao contrario do retorno."""
    am = []
    for d in range(6):
        ts = BASE + d * 14 * DIA
        for sc, ret in [(10, 6.0), (30, 5.0), (50, 4.0),
                        (70, 3.0), (85, 2.0), (95, 1.0)]:
            am.append(_am(ts, sc, ret,
                          {"bom": -sc, "ruim": sc}))
    fatores = {f["factor"]: f["ic_mean"] for f in backtest.factor_ic(am)}
    assert fatores["ruim"] == -1.0, "fator invertido nao foi detectado"
    assert fatores["bom"] == 1.0


def test_factor_ic_ordena_por_magnitude():
    am = []
    for d in range(6):
        ts = BASE + d * 14 * DIA
        for i, (sc, ret) in enumerate([(10, 1.0), (30, 2.0), (50, 3.0),
                                       (70, 4.0), (85, 5.0), (95, 6.0)]):
            am.append(_am(ts, sc, ret,
                          {"forte": sc, "constante": 7}))
    out = backtest.factor_ic(am)
    assert out[0]["factor"] == "forte"
    # fator constante nao produz IC e sai da lista
    assert all(f["factor"] != "constante" for f in out)


def test_factor_ic_sem_factors_devolve_vazio():
    am = _data(BASE, [(s, float(s)) for s in (10, 30, 50, 70, 85, 95)])
    assert backtest.factor_ic(am) == []


# ── quintile_spread ────────────────────────────────────────────────


def test_quintil_mede_topo_contra_base():
    """Com 10 itens por data, cada quintil pega 2 (10 // 5)."""
    am = []
    for d in range(4):
        ts = BASE + d * 14 * DIA
        am += _data(ts, [(10, -5.0), (20, -5.0), (30, 0.0), (40, 0.0),
                         (50, 0.0), (60, 0.0), (70, 0.0), (80, 0.0),
                         (90, 20.0), (95, 20.0)])
    r = backtest.quintile_spread(am)
    assert r["top_pct"] == 20.0      # scores 90 e 95
    assert r["bottom_pct"] == -5.0   # scores 10 e 20
    assert r["spread_pp"] == 25.0
    assert r["n_top"] == 8           # 2 itens x 4 datas


def test_quintil_com_poucos_itens_pega_um_de_cada_ponta():
    am = _data(BASE, [(10, -3.0), (30, 0.0), (50, 0.0),
                      (70, 0.0), (85, 0.0), (95, 9.0)])
    r = backtest.quintile_spread(am)
    assert r["n_top"] == 1 and r["n_bottom"] == 1
    assert r["spread_pp"] == 12.0


def test_quintil_mediana_resiste_a_outlier():
    """Retorno de skin tem cauda gorda: um item extremo nao pode mandar.

    Caso real medido em 2026-07-28: a media do quintil superior deu 437%
    por causa de itens que sairam de centavos pra reais.
    """
    am = []
    for d in range(4):
        ts = BASE + d * 14 * DIA
        # 15 itens por data -> quintil de 3. Um outlier absurdo no topo.
        pares = [(s, 0.0) for s in range(10, 130, 10)]      # 12 itens a 0%
        pares += [(140, 2.0), (150, 2.0), (160, 16000.0)]   # topo: 3 itens
        am += _data(ts, pares)
    r = backtest.quintile_spread(am)
    assert r["n_top"] == 12, "3 itens x 4 datas"
    # A media do topo e' devorada pelo outlier; a mediana ignora.
    assert r["top_pct"] > 5000, "a media deveria estar contaminada"
    assert r["top_median"] == 2.0, "a mediana deveria resistir"
    assert r["bottom_median"] == 0.0
    assert r["spread_median_pp"] == 2.0
    assert r["spread_median_pp"] < r["spread_pp"]


def test_quintil_vazio_e_seguro():
    r = backtest.quintile_spread([])
    assert r["spread_pp"] is None and r["n_top"] == 0


# ── taxa ───────────────────────────────────────────────────────────


def test_liquido_pos_taxa():
    """A taxa incide sobre a VENDA, nao sobre o lucro."""
    assert backtest.net_after_fee(0.0, 0.15) == -15.0
    assert backtest.net_after_fee(13.64, 0.15) == -3.41
    assert backtest.net_after_fee(13.64, 0.02) == 11.37


def test_breakeven_e_maior_que_a_taxa():
    """15% de taxa exige 17.6% brutos, nao 15%."""
    assert backtest.breakeven_gross(0.15) == 17.65
    assert backtest.breakeven_gross(0.02) == 2.04


def test_net_after_fee_e_breakeven_batem():
    be = backtest.breakeven_gross(0.15)
    assert abs(backtest.net_after_fee(be, 0.15)) < 0.01
