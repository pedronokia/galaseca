"""Testes de "no ar desde" (skinvault/public_site/uptime.py)."""
from __future__ import annotations

from skinvault.public_site import uptime


def test_primeira_chamada_grava_e_devolve_now(tmp_path):
    p = tmp_path / "no_ar_desde.json"
    assert uptime.no_ar_desde(p, now=1000.0) == 1000.0


def test_chamadas_seguintes_nao_mudam_o_valor(tmp_path):
    p = tmp_path / "no_ar_desde.json"
    uptime.no_ar_desde(p, now=1000.0)
    assert uptime.no_ar_desde(p, now=5000.0) == 1000.0
