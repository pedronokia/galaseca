"""Testes de user_history.py (histórico de valor por usuário)."""
from __future__ import annotations

from skinvault.public_site import user_history


def test_load_history_vazio(tmp_path):
    p = tmp_path / "x.db"
    assert user_history.load_history("1", path=p) == []


def test_record_primeiro_ponto(tmp_path):
    p = tmp_path / "x.db"
    out = user_history.record_if_changed("1", 100.0, path=p, now=1.0)
    assert out == [{"ts": 1.0, "total": 100.0}]


def test_record_ponto_diferente_acumula(tmp_path):
    p = tmp_path / "x.db"
    user_history.record_if_changed("1", 100.0, path=p, now=1.0)
    out = user_history.record_if_changed("1", 150.0, path=p, now=2.0)
    assert out == [
        {"ts": 1.0, "total": 100.0}, {"ts": 2.0, "total": 150.0},
    ]


def test_record_ponto_igual_nao_duplica(tmp_path):
    p = tmp_path / "x.db"
    user_history.record_if_changed("1", 100.0, path=p, now=1.0)
    out = user_history.record_if_changed("1", 100.0, path=p, now=2.0)
    assert len(out) == 1


def test_record_cap_em_500_pontos(tmp_path):
    p = tmp_path / "x.db"
    for i in range(510):
        user_history.record_if_changed("1", float(i), path=p, now=float(i))
    out = user_history.load_history("1", path=p)
    assert len(out) == 500
    assert out[-1]["total"] == 509.0


def test_historico_isolado_por_usuario(tmp_path):
    p = tmp_path / "x.db"
    user_history.record_if_changed("1", 100.0, path=p, now=1.0)
    user_history.record_if_changed("2", 200.0, path=p, now=1.0)
    assert user_history.load_history("1", path=p) == [
        {"ts": 1.0, "total": 100.0}]
    assert user_history.load_history("2", path=p) == [
        {"ts": 1.0, "total": 200.0}]
