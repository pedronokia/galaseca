"""Larguras da tabela do Historico.

A coluna "Item" era Stretch: numa janela de 1900px ela engolia ~900px e
jogava o valor pra borda oposta -- ler "quanto rendeu este item" custava
atravessar a linha inteira.
"""
from __future__ import annotations

import pytest

from skinvault.ui.history_screen import HistoryScreen


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


# ── quem pode esticar ──────────────────────────────────────────────


def test_coluna_de_dinheiro_e_reconhecida():
    for h in ("Valor", "Preço", "Lucro/prejuízo", "Lucro (sem taxa)",
              "Retorno %",
              "Preço de compra", "Preço atual", "Compra", "Venda", "Qtd"):
        assert HistoryScreen._e_coluna_numerica(h) is True, h


def test_coluna_de_texto_nao_e_numerica():
    for h in ("Origem", "Item", "Data", "Tipo", "Status", "Adicionado",
              "Listing ID", "Trade Offer ID", "Operação"):
        assert HistoryScreen._e_coluna_numerica(h) is False, h


def test_sem_header_nao_quebra():
    assert HistoryScreen._e_coluna_numerica("") is False
    assert HistoryScreen._e_coluna_numerica(None) is False


# ── a regra que isso protege ───────────────────────────────────────


def test_pareados_e_abertas_terminam_em_numero():
    """Nesses dois a ultima coluna NAO pode esticar: e' o numero que
    importa, e estica-lo o manda pra longe do nome do item."""
    assert HistoryScreen._e_coluna_numerica("Retorno %") is True
    assert HistoryScreen._e_coluna_numerica("Lucro se vender hoje") is True


def test_todos_e_trades_terminam_em_texto():
    """Nesses a ultima coluna estica e o fundo da linha cobre a largura."""
    assert HistoryScreen._e_coluna_numerica("Origem") is False


def test_teto_da_coluna_item_e_menor_que_a_janela():
    """O teto existe justamente pra ela nao engolir a largura toda."""
    assert HistoryScreen._ITEM_COL_MIN < HistoryScreen._ITEM_COL_MAX
    assert HistoryScreen._ITEM_COL_MAX <= 600
