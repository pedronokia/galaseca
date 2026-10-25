"""Testes do contador de visitas (skinvault/public_site/visits.py)."""
from __future__ import annotations

from skinvault.public_site import visits


def test_registrar_comeca_em_1(tmp_path):
    p = tmp_path / "visitas.json"
    assert visits.registrar(p) == 1


def test_registrar_incrementa(tmp_path):
    p = tmp_path / "visitas.json"
    visits.registrar(p)
    visits.registrar(p)
    assert visits.registrar(p) == 3


def test_total_nao_incrementa(tmp_path):
    p = tmp_path / "visitas.json"
    visits.registrar(p)
    visits.registrar(p)
    assert visits.total(p) == 2
    assert visits.total(p) == 2


def test_total_sem_arquivo_e_zero(tmp_path):
    p = tmp_path / "visitas.json"
    assert visits.total(p) == 0


def test_serie_por_dia_agrupa_pelo_dia(tmp_path):
    p = tmp_path / "visitas.json"
    ts_dia1 = 1000000.0
    ts_dia2 = ts_dia1 + 86400
    visits.registrar(p, now=ts_dia1)
    visits.registrar(p, now=ts_dia1 + 10)
    visits.registrar(p, now=ts_dia2)
    serie = visits.serie_por_dia(p)
    assert len(serie) == 2
    assert serie[0][1] == 2
    assert serie[1][1] == 1


def test_serie_por_dia_sem_arquivo_e_vazia(tmp_path):
    assert visits.serie_por_dia(tmp_path / "nao_existe.json") == []


def test_serie_por_dia_mantem_so_ultimos_60_dias(tmp_path):
    p = tmp_path / "visitas.json"
    for i in range(65):
        visits.registrar(p, now=1000000.0 + i * 86400)
    assert len(visits.serie_por_dia(p)) == visits._DIAS_MANTIDOS
