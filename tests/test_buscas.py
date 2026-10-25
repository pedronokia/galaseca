"""Testes do contador de termos buscados (skinvault/public_site/buscas.py)."""
from __future__ import annotations

from skinvault.public_site import buscas


def test_registrar_e_contar(tmp_path):
    p = tmp_path / "buscas.json"
    buscas.registrar("AK-47", p)
    buscas.registrar("ak-47", p)  # normaliza minusculo
    buscas.registrar("awp", p)
    assert buscas.mais_buscados(path=p) == [("ak-47", 2), ("awp", 1)]


def test_registrar_vazio_ignorado(tmp_path):
    p = tmp_path / "buscas.json"
    buscas.registrar("", p)
    buscas.registrar("   ", p)
    assert buscas.mais_buscados(path=p) == []


def test_mais_buscados_respeita_limite(tmp_path):
    p = tmp_path / "buscas.json"
    for i in range(5):
        buscas.registrar(f"item{i}", p)
    assert len(buscas.mais_buscados(limite=3, path=p)) == 3


def test_mais_buscados_sem_arquivo_e_vazio(tmp_path):
    assert buscas.mais_buscados(path=tmp_path / "nao_existe.json") == []
