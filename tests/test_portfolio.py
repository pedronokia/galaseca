"""Testes do portfolio fee-aware -- a matematica honesta da taxa do Steam."""
from __future__ import annotations

import pytest

from skinvault import portfolio


def test_net_proceeds_and_break_even():
    # taxa 15%: listo a 115 -> recebo 100; pra receber 100 de volta, listo a 115
    assert portfolio.net_proceeds(115.0) == pytest.approx(100.0)
    assert portfolio.break_even_price(100.0) == pytest.approx(115.0)


def test_position_pnl_pct_is_0_100():
    """pnl_pct retorna 0-100, nao fracao."""
    d = portfolio.position_pnl(cost=100.0, current_price=150.0)
    assert d["pnl_pct"] == pytest.approx(30.43, abs=0.01)


def test_evaluate_portfolio_pnl_pct_is_0_100():
    """totals.pnl_pct retorna 0-100, nao fracao."""
    positions = [{"name": "AK", "cost": 100.0, "quantity": 1}]
    res = portfolio.evaluate_portfolio(positions, lambda n: 150.0)
    assert res["totals"]["pnl_pct"] == pytest.approx(30.43, abs=0.01)


def test_simulate_trade_roi_pct_is_0_100():
    """roi_pct retorna 0-100, nao fracao."""
    r = portfolio.simulate_trade(100.0, 150.0)
    assert r["roi_pct"] == pytest.approx(30.43, abs=0.01)


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


def test_update_position_cost_redefine_e_persiste(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("Kilowatt Case", 0.0, 21,
                           source="steam_sync", path=p)
    res = portfolio.update_position_cost("Kilowatt Case", 12.50, path=p)
    assert res is not None
    loaded = portfolio.load_portfolio(p)
    assert loaded[0]["cost"] == pytest.approx(12.50)
    # Declarar custo tira a posicao do "nao sei" do sync: vira manual e
    # passa a ter custo real (zero digitado = drop afirmado).
    assert loaded[0]["source"] == "manual"
    assert portfolio.has_cost_basis(loaded[0]) is True


def test_update_position_cost_nome_inexistente(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("AK-47 | Redline (FT)", 180.0, 1, path=p)
    assert portfolio.update_position_cost("Nao Existe", 10.0, path=p) is None
    assert portfolio.load_portfolio(p)[0]["cost"] == 180.0


def test_update_position_cost_zero_e_drop_declarado(tmp_path):
    """Zero digitado no dialogo = 'eu sei que nao custou nada', nao 'nao sei'."""
    p = tmp_path / "pf.json"
    portfolio.add_position("Drop", 0.0, 1, source="steam_sync", path=p)
    portfolio.update_position_cost("Drop", 0.0, path=p)
    loaded = portfolio.load_portfolio(p)
    assert portfolio.has_cost_basis(loaded[0]) is True


def test_remove_position_existente(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("AK-47 | Redline (FT)", 180.0, 1, path=p)
    portfolio.add_position("AWP | Asiimov (FT)", 650.0, 1, path=p)
    assert portfolio.remove_position("AK-47 | Redline (FT)", path=p) is True
    restantes = portfolio.load_portfolio(p)
    assert len(restantes) == 1
    assert restantes[0]["name"] == "AWP | Asiimov (FT)"


def test_remove_position_inexistente(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("AK-47 | Redline (FT)", 180.0, 1, path=p)
    assert portfolio.remove_position("Nao Existe", path=p) is False
    assert len(portfolio.load_portfolio(p)) == 1


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


def test_import_csv_br_format_full(tmp_path):
    """Formato BR completo: R$ 1.234,50 com milhar separador."""
    p = tmp_path / "pf.json"
    csv = "AK-47, R$ 1.234,50, 1\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 1
    assert r["errors"] == []
    loaded = portfolio.load_portfolio(p)
    assert loaded[0]["cost"] == 1234.50


def test_import_csv_br_format_no_prefix(tmp_path):
    """Formato BR sem R$."""
    p = tmp_path / "pf.json"
    csv = "AK-47, 1.234,50, 1\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 1
    assert r["errors"] == []
    loaded = portfolio.load_portfolio(p)
    assert loaded[0]["cost"] == 1234.50


def test_save_portfolio_oserror_handled(tmp_path):
    """save_portfolio engole OSError sem crash."""
    dir_path = tmp_path / "subdir" / "pf.json"
    # subdir nao existe -> mkdir no save cria; mas se for arquivo, falha
    file_path = tmp_path / "afile"
    file_path.write_text("", encoding="utf-8")
    bad_path = file_path / "pf.json"  # file_path e' arquivo, nao diretorio
    portfolio.save_portfolio([{"name": "X", "cost": 10.0}], path=bad_path)
    # nao crashou


def test_import_csv_invalid_cost(tmp_path):
    """import_csv reporta erro quando custo nao e' numero."""
    p = tmp_path / "pf.json"
    csv = "AK-47, abc, 1\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 0
    assert len(r["errors"]) == 1
    assert "custo invalido" in r["errors"][0]


def test_import_csv_custo_em_branco_vira_desconhecido(tmp_path):
    # Achado real: "0" como placeholder de "nao sei o custo" declarava
    # "foi drop" numa posicao manual (cost=0 != cost=None) -- a tela
    # mostrava "R$ 0,00" pra item que na verdade tem custo desconhecido.
    p = tmp_path / "pf.json"
    csv = "AK-47, , 1\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 1
    assert r["errors"] == []
    loaded = portfolio.load_portfolio(p)
    assert loaded[0]["cost"] is None


def test_import_csv_invalid_qty(tmp_path):
    """import_csv reporta erro quando quantidade nao e' inteiro."""
    p = tmp_path / "pf.json"
    csv = "AK-47, 200, abc\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 0
    assert len(r["errors"]) == 1
    assert "quantidade invalida" in r["errors"][0]


def test_import_csv_br_format_comma_decimal(tmp_path):
    """Virgula como separador decimal sem ponto milhar."""
    p = tmp_path / "pf.json"
    csv = "AK-47, 1234,50, 1\n"
    r = portfolio.import_csv(csv, path=p)
    assert r["imported"] == 1
    assert r["errors"] == []
    loaded = portfolio.load_portfolio(p)
    assert loaded[0]["cost"] == 1234.50


# ── positions_missing_icon / set_icon ──────────────────────────────


def test_positions_missing_icon_ignora_quem_ja_tem(tmp_path):
    positions = [
        {"name": "Item A", "icon": "hash-1"},
        {"name": "Item B"},
        {"name": "Item C", "icon": ""},
    ]
    assert portfolio.positions_missing_icon(positions) == ["Item B", "Item C"]


def test_positions_missing_icon_dedup_preserva_ordem(tmp_path):
    positions = [
        {"name": "Item B"},
        {"name": "Item A"},
        {"name": "Item B"},
    ]
    assert portfolio.positions_missing_icon(positions) == ["Item B", "Item A"]


def test_set_icon_atualiza_so_quem_nao_tem(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.save_portfolio([
        {"name": "Item A", "cost": 10, "quantity": 1},
        {"name": "Item A", "cost": 20, "quantity": 1, "icon": "ja-tinha"},
        {"name": "Item B", "cost": 5, "quantity": 1},
    ], path=p)
    atualizados = portfolio.set_icon("Item A", "hash-novo", path=p)
    assert atualizados == 1
    loaded = portfolio.load_portfolio(p)
    icons_item_a = [x["icon"] for x in loaded if x["name"] == "Item A"]
    assert sorted(icons_item_a) == ["hash-novo", "ja-tinha"]
    assert loaded[2].get("icon") is None
