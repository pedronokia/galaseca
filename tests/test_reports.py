"""Exportação de relatórios — serializadores puros (reports.py)."""
from __future__ import annotations

import json

from skinvault import reports

ROWS = [
    {"name": "AK-47 | Redline (Field-Tested)", "cost": 80.0, "quantity": 2,
     "price": 100.0, "has_cost": True, "cost_total": 160.0,
     "market": 200.0, "net_if_sold": 173.91, "pnl": 13.91, "pnl_pct": 8.7},
    {"name": "★ Karambit", "cost": 0.0, "quantity": 1,
     "price": 500.0, "has_cost": False, "cost_total": 0.0,
     "market": 500.0, "net_if_sold": 434.78, "pnl": None, "pnl_pct": None},
]

POS = [
    {"name": "AK-47 | Redline (Field-Tested)", "cost": 80.0, "quantity": 2,
     "source": "manual"},
    {"name": "★ Karambit", "cost": 0.0, "quantity": 1,
     "source": "steam_sync"},
]

MERCADOS = {
    "AK-47 | Redline (Field-Tested)": [
        {"source": "skinport", "net_brl": 105.0, "fee": 0.12},
        {"source": "csgotm", "net_brl": 100.0, "fee": 0.05},
    ],
}

SERIES = [
    {"ts": 1750000000, "total": 100.0},
    {"ts": 1750086400, "total": 120.0},
    {"ts": 1750172800, "total": 110.0},
]


# ── inventário ───────────────────────────────────────────────


def test_inventory_records_mapping():
    recs = reports.inventory_records(ROWS, POS, MERCADOS)
    r0 = recs[0]
    assert r0["nome"] == "AK-47 | Redline (Field-Tested)"
    assert r0["quantidade"] == 2
    assert r0["preco_unitario"] == 100.0
    assert r0["valor_bruto"] == 200.0
    assert r0["liquido_steam"] == 173.91
    # melhor fora totaliza o lote (105 * 2)
    assert r0["melhor_fora"] == 210.0
    assert r0["onde"] == "Skinport"
    assert r0["custo"] == 80.0
    assert r0["pnl"] == 13.91
    assert r0["origem"] == "Manual"
    assert r0["categoria"] == "Skins"


def test_inventory_records_sem_custo_e_origem_sync():
    recs = reports.inventory_records(ROWS, POS, MERCADOS)
    r1 = recs[1]
    assert r1["custo"] is None
    assert r1["pnl"] is None
    assert r1["origem"] == "Steam"
    assert r1["melhor_fora"] is None  # sem cotação externa


def test_inventory_csv_header_e_valores_ptbr():
    txt = reports.inventory_csv(ROWS, POS, MERCADOS)
    linhas = txt.strip().splitlines()
    assert "Item" in linhas[0]
    assert linhas[0].count(";") == 10  # 11 colunas
    assert "AK-47 | Redline (Field-Tested);2;100,00;200,00;173,91;210,00;" \
           "Skinport;80,00;13,91;Manual;Skins" in txt
    assert "\ufeff" not in txt  # BOM entra só no write_export


def test_inventory_csv_sem_mercados():
    txt = reports.inventory_csv(ROWS, POS)
    linhas = txt.strip().splitlines()
    assert len(linhas) == 3  # header + 2 itens
    assert linhas[1].count(";") == 10
    # "Melhor fora" e "Onde" ficam vazios; custo e P&L preservados
    assert ";;Skinport" not in txt
    assert "80,00;13,91;Manual;Skins" in txt


def test_inventory_json_parseable_sem_ascii():
    payload = reports.inventory_json(ROWS, POS, MERCADOS)
    data = json.loads(payload)
    assert len(data) == 2
    assert data[0]["nome"] == "AK-47 | Redline (Field-Tested)"
    assert "|" in data[0]["nome"]
    assert any(ord(c) > 127 for c in payload) or "Field-Tested" in payload


# ── histórico ────────────────────────────────────────────────


def test_history_records_data_formatada():
    import re
    recs = reports.history_records(SERIES)
    assert recs[0]["total"] == 100.0
    assert re.match(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$", recs[0]["date"])


def test_history_csv():
    txt = reports.history_csv(SERIES)
    assert txt.splitlines()[0] == "Data;Total"
    assert len(txt.strip().splitlines()) == 4


def test_history_json():
    data = json.loads(reports.history_json(SERIES))
    assert len(data) == 3
    assert "date" in data[0]


# ── relatório HTML ───────────────────────────────────────────


def test_html_report_inventario_e_resumo():
    totals = {"market": 700.0, "net_if_sold": 608.69, "pnl": 13.91,
              "cost_known": 160.0, "positions": 2}
    html = reports.html_report(ROWS, SERIES, totals, POS, MERCADOS)
    assert "SkinVault" in html
    assert "R$ 700,00" in html
    assert "AK-47 | Redline (Field-Tested)" in html
    assert "Histórico do valor da carteira" in html
    assert "svg" in html


def test_html_report_deriva_totals_das_linhas():
    html = reports.html_report(ROWS, [], None, POS, MERCADOS)
    assert "R$ 700,00" in html  # 200 + 500
    assert "P&amp;L total" in html  # & escapado no HTML


def test_html_report_vazio_renderiza_placeholder():
    html = reports.html_report([], [], {})
    assert "Sem itens." in html
    assert "Histórico do valor da carteira" not in html


def test_html_report_escapa_nome():
    rows = [dict(ROWS[0], name='AK-47 | Redline & Friends (FT)')]
    html = reports.html_report(rows, [], {})
    assert "&amp;" in html
    assert "Redline &amp; Friends" in html


# ── gravação ─────────────────────────────────────────────────


def test_write_export_csv_adiciona_bom(tmp_path):
    p = tmp_path / "out.csv"
    reports.write_export(p, "A;B\n1;2", "csv")
    raw = p.read_text(encoding="utf-8")
    assert raw.startswith("\ufeff")
    assert "A;B\n1;2" in raw


def test_write_export_json_sem_bom(tmp_path):
    p = tmp_path / "out.json"
    reports.write_export(p, "{}", "json")
    assert p.read_text(encoding="utf-8") == "{}"


def test_write_export_cria_subdiretorio(tmp_path):
    p = tmp_path / "sub" / "out.csv"
    reports.write_export(p, "x", "csv")
    assert p.exists()
