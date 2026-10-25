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
