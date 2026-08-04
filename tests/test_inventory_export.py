"""Exportação — wiring nas telas (InventoryScreen + AccountScreen).

Os serializadores são cobertos em test_reports.py; aqui se prova que o
botão chama o reports com os dados da tela e que o resultado sai pelo
fluxo save_export (mockado, sem QFileDialog real).
"""
from __future__ import annotations

import pytest

from skinvault.ui.inventory_screen import InventoryScreen


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


@pytest.fixture
def tela(monkeypatch):
    gravado = {}
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s, *a, **k: gravado.update(s))
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: dict(gravado))
    tela = InventoryScreen()
    return tela


ROWS = [
    {"name": "AK-47 | Redline (Field-Tested)", "quantity": 2,
     "price": 100.0, "market": 200.0, "net_if_sold": 173.91,
     "pnl": 13.91, "has_cost": True, "cost_total": 160.0},
    {"name": "★ Karambit", "quantity": 1,
     "price": 500.0, "market": 500.0, "net_if_sold": 434.78,
     "pnl": None, "has_cost": False, "cost_total": 0.0},
]
POS = [{"source": "manual", "cost": 80.0, "quantity": 2},
       {"source": "steam_sync", "cost": 0.0, "quantity": 1}]
MERCADOS = {"AK-47 | Redline (Field-Tested)": [
    {"source": "skinport", "net_brl": 105.0, "fee": 0.12}]}


def _monta(tela):
    tela._rows = list(ROWS)
    tela._positions = list(POS)
    tela._mercados = dict(MERCADOS)
    return tela


def test_export_vazio_avisa_status(tela, monkeypatch):
    captura = {}
    monkeypatch.setattr("skinvault.ui.inventory_screen.save_export",
                        lambda *a, **k: captura.setdefault("chamado", True))
    tela._on_export_menu()
    assert "vazio" in tela._status.text()
    assert "chamado" not in captura


def test_export_csv_usa_dados_da_tela(tela, monkeypatch):
    _monta(tela)
    captura = {}
    monkeypatch.setattr(
        "skinvault.ui.inventory_screen.save_export",
        lambda parent, nome, kind, conteudo: captura.update(
            {"nome": nome, "kind": kind, "conteudo": conteudo}) or ("x.csv", None))
    tela._do_export("csv")
    assert captura["kind"] == "csv"
    assert "AK-47 | Redline (Field-Tested)" in captura["conteudo"]
    assert "Skinport" in captura["conteudo"]
    assert tela._status.text().startswith("Exportado: x.csv")


def test_export_json(tela, monkeypatch):
    _monta(tela)
    captura = {}
    monkeypatch.setattr(
        "skinvault.ui.inventory_screen.save_export",
        lambda parent, nome, kind, conteudo: captura.update(
            {"kind": kind, "conteudo": conteudo}) or ("x.json", None))
    tela._do_export("json")
    assert captura["kind"] == "json"
    assert "melhor_fora" in captura["conteudo"]


def test_export_html(tela, monkeypatch):
    _monta(tela)
    captura = {}
    monkeypatch.setattr(
        "skinvault.ui.inventory_screen.save_export",
        lambda parent, nome, kind, conteudo: captura.update(
            {"kind": kind, "conteudo": conteudo}) or ("x.html", None))
    tela._do_export("html")
    assert captura["kind"] == "html"
    assert "SkinVault" in captura["conteudo"]


def test_export_erro_mostra_status(tela, monkeypatch):
    _monta(tela)
    monkeypatch.setattr("skinvault.ui.inventory_screen.save_export",
                        lambda *a, **k: (None, "disco cheio"))
    tela._do_export("csv")
    assert "Erro ao exportar" in tela._status.text()


# ── AccountScreen: histórico do portfólio ─────────────────────


@pytest.fixture
def conta(tmp_path, monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    monkeypatch.setattr("skinvault.history.load_history",
                        lambda *a, **k: [])
    return AccountScreen(PriceCache(tmp_path / "p.json", ttl=3600))


def test_conta_exporta_historico_csv(conta, monkeypatch):
    conta._series_export = [
        {"ts": 1750000000, "total": 100.0},
        {"ts": 1750086400, "total": 120.0},
    ]
    captura = {}
    monkeypatch.setattr(
        "skinvault.ui.account_screen.save_export",
        lambda parent, nome, kind, conteudo: captura.update(
            {"nome": nome, "kind": kind, "conteudo": conteudo}) or ("h.csv", None))
    conta._do_export_history("csv", conta._series_export)
    assert captura["kind"] == "csv"
    assert captura["conteudo"].splitlines()[0] == "Data;Total"
    assert conta._status.text().startswith("Exportado: h.csv")


def test_conta_sem_serie_avisa(conta, monkeypatch):
    captura = {}
    monkeypatch.setattr("skinvault.ui.account_screen.save_export",
                        lambda *a, **k: captura.setdefault("chamado", True))
    conta._series_export = []
    conta._on_export_history()
    assert "Nada para exportar" in conta._status.text()
    assert "chamado" not in captura
