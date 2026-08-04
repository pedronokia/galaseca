"""FeeCalculatorDialog — comportamento da UI da calculadora."""
from __future__ import annotations

import pytest

from skinvault.ui.fee_calculator_dialog import FeeCalculatorDialog


@pytest.fixture
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


def test_dialog_quatro_mercados_com_custo(app):
    dlg = FeeCalculatorDialog(cost="200", margin="10", quantity="1")
    assert dlg._table.rowCount() == 4
    # CS.MONEY lista mais barato (menor taxa)
    assert dlg._table.item(0, 0).text() == "CS.MONEY"


def test_dialog_valores_steam_seller_added(app):
    dlg = FeeCalculatorDialog(cost="200", margin="10", quantity="1")
    from PyQt6.QtWidgets import QHeaderView
    # acha a linha da Steam pela primeira coluna
    linha = next(i for i in range(dlg._table.rowCount())
                 if dlg._table.item(i, 0).text() == "Steam Market")
    assert dlg._table.item(linha, 1).text() == "15%"
    assert dlg._table.item(linha, 6).text() == "saldo Steam"


def test_dialog_recalcula_ao_digitar(app):
    dlg = FeeCalculatorDialog(cost="100", margin="0", quantity="1")
    assert dlg._table.rowCount() == 4
    dlg._cost.setText("")
    assert dlg._table.rowCount() == 0
    assert "maior que zero" in dlg._resumo.text()


def test_dialog_margem_muda_listagem(app):
    dlg0 = FeeCalculatorDialog(cost="100", margin="0", quantity="1")
    dlg1 = FeeCalculatorDialog(cost="100", margin="50", quantity="1")
    lista0 = dlg0._table.item(0, 3).text()
    lista1 = dlg1._table.item(0, 3).text()
    assert lista0 != lista1
