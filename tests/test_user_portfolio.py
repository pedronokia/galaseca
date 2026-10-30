"""Testes de user_portfolio.py (mutação por usuário, site público)."""
from __future__ import annotations

from galaseca.public_site import user_portfolio


def test_add_position(tmp_path):
    p = tmp_path / "x.db"
    out = user_portfolio.add_position("1", "AK-47", 10.0, 2, path=p)
    assert len(out) == 1
    assert out[0]["name"] == "AK-47"
    assert out[0]["cost"] == 10.0
    assert out[0]["quantity"] == 2
    assert out[0]["source"] == "manual"
    assert "added_ts" in out[0]


def test_add_position_sem_custo(tmp_path):
    p = tmp_path / "x.db"
    out = user_portfolio.add_position("1", "AK-47", None, path=p)
    assert out[0]["cost"] is None
    assert out[0]["quantity"] == 1


def test_add_position_duas_vezes_nao_funde(tmp_path):
    p = tmp_path / "x.db"
    user_portfolio.add_position("1", "AK-47", 10.0, path=p)
    out = user_portfolio.add_position("1", "AK-47", 20.0, path=p)
    assert len(out) == 2


def test_load_positions_vazio(tmp_path):
    p = tmp_path / "x.db"
    assert user_portfolio.load_positions("1", path=p) == []


def test_update_position_cost(tmp_path):
    p = tmp_path / "x.db"
    user_portfolio.add_position("1", "AK-47", 10.0, path=p)
    out = user_portfolio.update_position_cost("1", "AK-47", 25.0, path=p)
    assert out[0]["cost"] == 25.0


def test_update_position_cost_atualiza_todas_do_mesmo_nome(tmp_path):
    p = tmp_path / "x.db"
    user_portfolio.add_position("1", "AK-47", 10.0, path=p)
    user_portfolio.add_position("1", "AK-47", 15.0, path=p)
    out = user_portfolio.update_position_cost("1", "AK-47", 30.0, path=p)
    assert all(pos["cost"] == 30.0 for pos in out)


def test_update_position_cost_inexistente_devolve_none(tmp_path):
    p = tmp_path / "x.db"
    user_portfolio.add_position("1", "AK-47", 10.0, path=p)
    assert user_portfolio.update_position_cost("1", "Outro", 5.0, path=p) is None
    # nao mexeu na posicao existente
    assert user_portfolio.load_positions("1", path=p)[0]["cost"] == 10.0


def test_remove_position(tmp_path):
    p = tmp_path / "x.db"
    user_portfolio.add_position("1", "AK-47", 10.0, path=p)
    user_portfolio.add_position("1", "M4A4", 5.0, path=p)
    changed = user_portfolio.remove_position("1", "AK-47", path=p)
    assert changed is True
    restantes = user_portfolio.load_positions("1", path=p)
    assert [p_["name"] for p_ in restantes] == ["M4A4"]


def test_remove_position_inexistente(tmp_path):
    p = tmp_path / "x.db"
    assert user_portfolio.remove_position("1", "Nada", path=p) is False


def test_posicoes_isoladas_por_usuario(tmp_path):
    p = tmp_path / "x.db"
    user_portfolio.add_position("1", "AK-47", 10.0, path=p)
    user_portfolio.add_position("2", "M4A4", 5.0, path=p)
    assert [pos["name"] for pos in user_portfolio.load_positions("1", path=p)] == ["AK-47"]
    assert [pos["name"] for pos in user_portfolio.load_positions("2", path=p)] == ["M4A4"]
