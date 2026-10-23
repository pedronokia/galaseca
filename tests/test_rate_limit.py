"""Testes de rate_limit.py (limite de tentativas por IP, em memória)."""
from __future__ import annotations

from skinvault.public_site import rate_limit


def test_allow_dentro_do_limite():
    for _ in range(5):
        assert rate_limit.allow("k", max_hits=5, window_seconds=60, now=1.0)


def test_allow_estoura_o_limite():
    for _ in range(5):
        rate_limit.allow("k", max_hits=5, window_seconds=60, now=1.0)
    assert rate_limit.allow("k", max_hits=5, window_seconds=60, now=1.0) is False


def test_janela_deslizante_libera_depois_do_tempo():
    for _ in range(5):
        rate_limit.allow("k", max_hits=5, window_seconds=60, now=0.0)
    assert rate_limit.allow("k", max_hits=5, window_seconds=60, now=0.0) is False
    # 61s depois, os 5 hits antigos ja' saem da janela de 60s.
    assert rate_limit.allow("k", max_hits=5, window_seconds=60, now=61.0) is True


def test_chaves_diferentes_nao_se_misturam():
    for _ in range(5):
        rate_limit.allow("a", max_hits=5, window_seconds=60, now=1.0)
    assert rate_limit.allow("a", max_hits=5, window_seconds=60, now=1.0) is False
    assert rate_limit.allow("b", max_hits=5, window_seconds=60, now=1.0) is True


def test_reset_limpa_tudo():
    for _ in range(5):
        rate_limit.allow("k", max_hits=5, window_seconds=60, now=1.0)
    rate_limit.reset()
    assert rate_limit.allow("k", max_hits=5, window_seconds=60, now=1.0) is True
