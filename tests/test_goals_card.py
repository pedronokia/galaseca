"""GoalsCard + GoalsEditDialog — comportamento e persistência mockada."""
from __future__ import annotations

import pytest

from skinvault import goals
from skinvault.ui.goals_card import GoalsCard, GoalsEditDialog


class _FakeSettings:
    def __init__(self, data: dict):
        self.data = data

    def load_settings(self):
        return self.data

    def save_settings(self, data: dict):
        self.data = data


@pytest.fixture
def st(monkeypatch):
    fake = _FakeSettings({"goals": []})
    monkeypatch.setattr(goals, "_settings", fake)
    return fake


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


TOTALS = {"market": 1200.0, "net_if_sold": 1000.0, "pnl": 200.0,
          "positions": 12}


def test_card_sem_metas_mostra_empty(app, st):
    card = GoalsCard()
    assert card._empty.isVisibleTo(card)
    assert card._goals_lay.count() == 0


def test_card_renderiza_barra_por_meta(app, st):
    goals.upsert_goal("Meta", 1000.0, "net")
    card = GoalsCard()
    card.refresh_from(TOTALS)
    assert card._empty.isVisibleTo(card) is False
    assert card._goals_lay.count() == 1
    from PyQt6.QtWidgets import QProgressBar
    wrap = card._goals_lay.itemAt(0).widget()
    bar = wrap.findChild(QProgressBar)
    assert bar is not None
    assert bar.value() == 100


def test_card_progresso_parcial(app, st):
    goals.upsert_goal("Meta", 2000.0, "market")
    card = GoalsCard()
    card.refresh_from(TOTALS)
    from PyQt6.QtWidgets import QProgressBar
    bar = card._goals_lay.itemAt(0).widget().findChild(QProgressBar)
    assert bar.value() == 60


def test_card_pula_meta_desabilitada(app, st):
    goals.save_goals([{"label": "Off", "metric": "market",
                       "target": 100.0, "enabled": False},
                      {"label": "On", "metric": "items",
                       "target": 10.0, "enabled": True}])
    card = GoalsCard()
    card.refresh_from(TOTALS)
    assert card._goals_lay.count() == 1


def test_edit_dialog_preenche_linhas_existentes(app, st):
    goals.upsert_goal("Meta", 5000.0, "market")
    dlg = GoalsEditDialog()
    assert len(dlg._rows) == 1
    nome, combo, alvo = dlg._rows[0]
    assert nome.text() == "Meta"
    assert combo.currentData() == "market"
    assert alvo.text() == "5000.0"


def test_edit_dialog_salva_metas(app, st):
    goals.upsert_goal("Meta", 5000.0, "market")
    dlg = GoalsEditDialog()
    dlg._add_goal_row("Segunda", "items", "")
    nome, combo, alvo = dlg._rows[1]
    alvo.setText("20")
    dlg._on_save()
    metas = goals.load_goals()
    assert len(metas) == 2
    assert metas[1]["metric"] == "items"
    assert metas[1]["target"] == 20.0


def test_edit_dialog_alvo_invalido_nao_salva(app, st):
    goals.upsert_goal("Meta", 5000.0, "market")
    dlg = GoalsEditDialog()
    nome, combo, alvo = dlg._rows[0]
    alvo.setText("abc")
    dlg._on_save()
    assert dlg._erro.isVisibleTo(dlg)
    # nada mudou no disco
    assert len(goals.load_goals()) == 1
    assert goals.load_goals()[0]["target"] == 5000.0


def test_edit_dialog_remove_linha(app, st):
    goals.save_goals([{"label": "A", "metric": "market", "target": 1.0},
                      {"label": "B", "metric": "items", "target": 2.0}])
    dlg = GoalsEditDialog()
    assert len(dlg._rows) == 2
    row = dlg._lista.itemAt(0).widget()
    dlg._remove_row(row)
    assert len(dlg._rows) == 1
    assert dlg._rows[0][0].text() == "B"


def test_card_restyle_nao_quebra(app, st):
    goals.upsert_goal("Meta", 1000.0, "net")
    card = GoalsCard()
    card.refresh_from(TOTALS)
    card.restyle()
    assert card._goals_lay.count() == 1
