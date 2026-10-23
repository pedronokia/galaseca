"""Testes de fumaça da tela de Recomendações."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import pytest

from skinvault.ui.recommendations_screen import RecommendationsScreen


@pytest.fixture(autouse=True)
def _qapp():
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    for w in list(app.topLevelWidgets()):
        w.deleteLater()
    app.processEvents()


def test_builds_empty_sem_scan_sem_portfolio(monkeypatch):
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    screen = RecommendationsScreen()
    assert screen._buy == []
    assert screen._sell == []
    # isVisible() exige a janela mostrada (show()); isHidden() reflete o
    # setVisible() explicito que _populate_* chamou, sem depender disso.
    assert not screen._empty_buy.isHidden()
    assert not screen._empty_sell.isHidden()
    assert screen._table_buy.isHidden()
    assert screen._table_sell.isHidden()


def test_buy_candidates_populam_tabela(monkeypatch):
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    monkeypatch.setattr(
        "skinvault.scan_store.load_last_scan",
        lambda: {
            "ts": 0.0, "category": "Facas",
            "results": [
                {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
                 "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
                 "breakdown": [{"factor": "mediana", "delta": 20,
                               "label": "Preço baixo (+20)"}]},
            ],
        },
    )
    screen = RecommendationsScreen()
    assert len(screen._buy) == 1
    assert not screen._table_buy.isHidden()
    assert screen._empty_buy.isHidden()
    assert screen._table_buy.rowCount() == 1
    # localize_name traduz "(Field-Tested)" -> "(Testada em Campo)" pra
    # exibicao -- mesmo comportamento do Scanner.
    assert screen._table_buy.item(0, screen.COL_B_NAME).text() == (
        "AK-47 | Redline (Testada em Campo)")


def test_abrir_mercado_emite_sinal_com_item_selecionado(monkeypatch):
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    monkeypatch.setattr(
        "skinvault.scan_store.load_last_scan",
        lambda: {"ts": 0.0, "category": "", "results": [
            {"name": "Item X", "score": 70, "breakdown": [],
             "pump_risk": {"level": "low"}},
        ]},
    )
    screen = RecommendationsScreen()
    recebido = []
    screen.abrir_mercado.connect(recebido.append)
    screen._table_buy.selectRow(0)
    screen._on_open_market_selected()
    assert recebido == ["Item X"]


def test_sell_watch_posicao_no_topo_fica_destacada(monkeypatch):
    monkeypatch.setattr(
        "skinvault.portfolio.load_portfolio",
        lambda: [{
            "name": "Caixa Antiga", "quantity": 2,
            "exit_ctx": {"pct_of_ath": 0.95, "ath": 10.0, "current": 9.5,
                        "at_launch": False},
        }],
    )
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    screen = RecommendationsScreen()
    assert len(screen._sell) == 1
    assert screen._sell[0]["exit_context"]["level"] == "topo"
    assert not screen._table_sell.isHidden()
    assert screen._table_sell.rowCount() == 1


def test_abrir_inventario_emite_sinal_com_item_selecionado(monkeypatch):
    monkeypatch.setattr(
        "skinvault.portfolio.load_portfolio",
        lambda: [{
            "name": "Caixa Antiga",
            "exit_ctx": {"pct_of_ath": 0.95, "ath": 10.0, "current": 9.5,
                        "at_launch": False},
        }],
    )
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    screen = RecommendationsScreen()
    recebido = []
    screen.abrir_inventario.connect(recebido.append)
    screen._table_sell.selectRow(0)
    screen._on_open_inventory_selected()
    assert recebido == ["Caixa Antiga"]


def test_refresh_relhe_estado_sem_quebrar(monkeypatch):
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    screen = RecommendationsScreen()
    screen.refresh()
    assert screen._buy == []
