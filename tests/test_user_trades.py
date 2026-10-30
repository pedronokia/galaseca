"""Testes de user_trades.py (trades pessoais, site público)."""
from __future__ import annotations

from galaseca.public_site import user_trades


def test_load_trades_vazio(tmp_path):
    p = tmp_path / "x.db"
    assert user_trades.load_trades("1", path=p) == []


def test_add_trade(tmp_path):
    p = tmp_path / "x.db"
    out = user_trades.add_trade("1", "AK-47", 10.0, 15.0, 2, "nota", path=p)
    assert len(out) == 1
    t = out[0]
    assert t["name"] == "AK-47"
    assert t["buy_cost"] == 10.0
    assert t["sell_price"] == 15.0
    assert t["quantity"] == 2
    assert t["notes"] == "nota"
    assert t["cost_total"] == 20.0
    assert t["pnl"] == round(15.0 / 1.15 * 2 - 20.0, 2)


def test_add_trade_acumula(tmp_path):
    p = tmp_path / "x.db"
    user_trades.add_trade("1", "AK-47", 10.0, 15.0, path=p)
    out = user_trades.add_trade("1", "M4A4", 5.0, 8.0, path=p)
    assert len(out) == 2


def test_remove_trade(tmp_path):
    p = tmp_path / "x.db"
    user_trades.add_trade("1", "AK-47", 10.0, 15.0, path=p)
    user_trades.add_trade("1", "M4A4", 5.0, 8.0, path=p)
    out = user_trades.remove_trade("1", 0, path=p)
    assert len(out) == 1
    assert out[0]["name"] == "M4A4"


def test_remove_trade_indice_invalido(tmp_path):
    p = tmp_path / "x.db"
    user_trades.add_trade("1", "AK-47", 10.0, 15.0, path=p)
    assert user_trades.remove_trade("1", 5, path=p) is None
    assert len(user_trades.load_trades("1", path=p)) == 1


def test_trades_isolados_por_usuario(tmp_path):
    p = tmp_path / "x.db"
    user_trades.add_trade("1", "AK-47", 10.0, 15.0, path=p)
    user_trades.add_trade("2", "M4A4", 5.0, 8.0, path=p)
    assert [t["name"] for t in user_trades.load_trades("1", path=p)] == ["AK-47"]
    assert [t["name"] for t in user_trades.load_trades("2", path=p)] == ["M4A4"]
