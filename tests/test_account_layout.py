"""Espaco vertical: o inventario e' o conteudo principal da tela.

Bug real visto em 28/07/2026 num monitor 1080p: o grafico vazio ocupava
~200px so' pra escrever "Avalie 2x+" e a lista sobrava com ~5 linhas
visiveis no rodape.
"""
from __future__ import annotations

import pytest

from skinvault.prices import PriceCache


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
def screen(tmp_path, monkeypatch):
    monkeypatch.setattr("skinvault.history.load_history", lambda *a, **k: [])
    from skinvault.ui.account_screen import AccountScreen
    return AccountScreen(PriceCache(tmp_path / "p.json", ttl=3600))


def test_grafico_some_sem_serie(screen):
    """Zero pontos: nem grafico nem legenda ocupam espaco."""
    assert screen._value_chart.isVisibleTo(screen) is False
    assert screen._vc_lbl.isVisibleTo(screen) is False


def test_grafico_some_com_menos_de_tres_pontos(screen, monkeypatch):
    """Dois pontos viram uma reta: nao mostram tendencia nenhuma.

    Com 2 pontos o grafico desenhava uma diagonal vermelha atravessando a
    tela, o que parecia alarme sem informar nada.
    """
    for serie in ([{"total": 100.0}],
                  [{"total": 100.0}, {"total": 120.0}]):
        monkeypatch.setattr("skinvault.history.load_history",
                            lambda *a, **k: serie)
        screen._reload_value_series()
        assert screen._value_chart.isVisibleTo(screen) is False


def test_grafico_aparece_com_tres_pontos(screen, monkeypatch):
    monkeypatch.setattr(
        "skinvault.history.load_history",
        lambda *a, **k: [{"total": 100.0}, {"total": 120.0},
                         {"total": 110.0}])
    screen._reload_value_series()
    assert screen._value_chart.isVisibleTo(screen) is True
    assert screen._vc_lbl.isVisibleTo(screen) is True


def test_grafico_tem_teto_de_altura(screen):
    """Minimo vence maximo no Qt: o piso do ValueChart (120) precisa ter
    sido baixado, senao o teto de 90 nao vale nada."""
    assert screen._value_chart.minimumHeight() == 0
    assert screen._value_chart.maximumHeight() == 90


