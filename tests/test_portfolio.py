"""Testes do portfolio fee-aware -- a matematica honesta da taxa do Steam."""
from __future__ import annotations

import pytest

from skinvault import portfolio


def test_net_proceeds_and_break_even():
    # taxa 15%: listo a 115 -> recebo 100; pra receber 100 de volta, listo a 115
    assert portfolio.net_proceeds(115.0) == pytest.approx(100.0)
    assert portfolio.break_even_price(100.0) == pytest.approx(115.0)


def test_position_que_PARECE_lucro_mas_e_prejuizo():
    # paguei 100, "vale" 110 -> parece +10. Mas recebo 110/1.15 = 95.65 -> -4.35
    d = portfolio.position_pnl(cost=100.0, current_price=110.0)
    assert d["market"] == pytest.approx(110.0)
    assert d["net_if_sold"] == pytest.approx(95.65, abs=0.01)
    assert d["pnl"] == pytest.approx(-4.35, abs=0.01)
    assert d["status"] == "loss"                      # a verdade
    assert d["break_even"] == pytest.approx(115.0)    # precisa vender a 115+


def test_position_lucro_real():
    # paguei 100, vale 150 -> recebo 130.43 -> +30.43 de fato
    d = portfolio.position_pnl(cost=100.0, current_price=150.0)
    assert d["pnl"] == pytest.approx(30.43, abs=0.01)
    assert d["status"] == "profit"


def test_position_com_quantidade():
    d = portfolio.position_pnl(cost=10.0, current_price=11.5, quantity=4)
    assert d["cost_total"] == pytest.approx(40.0)
    assert d["net_if_sold"] == pytest.approx(40.0, abs=0.01)  # 11.5/1.15*4 = 40
    assert d["status"] == "even"


def test_evaluate_portfolio_totais_e_sem_preco():
    positions = [
        {"name": "AK", "cost": 100.0, "quantity": 1},
        {"name": "AWP", "cost": 700.0, "quantity": 1},
        {"name": "SemPreco", "cost": 5.0, "quantity": 1},
    ]
    prices = {"AK": 150.0, "AWP": 805.0, "SemPreco": None}
    res = portfolio.evaluate_portfolio(positions, lambda n: prices[n])
    by = {r["name"]: r for r in res["rows"]}
    assert by["SemPreco"]["pnl"] is None
    # totais ignoram o item sem preco
    assert res["totals"]["cost"] == pytest.approx(800.0)
    # AK: net 130.43 (+30.43) ; AWP: net 700.0 (even)
    assert res["totals"]["net_if_sold"] == pytest.approx(130.43 + 700.0, abs=0.02)
    assert res["totals"]["pnl"] == pytest.approx(30.43, abs=0.02)


def test_persistencia_roundtrip(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("AK-47 | Redline (FT)", 180.0, 1, path=p)
    portfolio.add_position("AWP | Asiimov (FT)", 700.0, 2, path=p)
    loaded = portfolio.load_portfolio(path=p)
    assert [x["name"] for x in loaded] == ["AK-47 | Redline (FT)", "AWP | Asiimov (FT)"]
    assert loaded[1]["quantity"] == 2 and loaded[1]["cost"] == 700.0


def test_import_csv_basic(tmp_path):
    p = tmp_path / "pf.json"
    csv = (
        "AK-47 | Redline (Field-Tested), 200, 1\n"
        "AWP | Asiimov (FT), 650.50\n"
    )
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 2
    assert r["errors"] == []
    loaded = portfolio.load_portfolio(p)
    assert loaded[0]["name"] == "AK-47 | Redline (Field-Tested)"
    assert loaded[0]["cost"] == 200.0
    assert loaded[1]["cost"] == 650.50
    assert loaded[1]["quantity"] == 1


def test_import_csv_skips_comments_and_empty(tmp_path):
    p = tmp_path / "pf.json"
    csv = "# comentario\n\nAK-47, 200\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 1
    assert r["skipped"] == 2


def test_import_csv_invalid_line(tmp_path):
    p = tmp_path / "pf.json"
    csv = "AK-47\nSoName\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 0
    assert len(r["errors"]) == 2


def test_import_csv_with_r_prefix(tmp_path):
    p = tmp_path / "pf.json"
    csv = "AK-47, R$ 200, 1\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 1
    assert r["errors"] == []
