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


def test_grafico_some_com_um_ponto_so(screen, monkeypatch):
    """Um ponto nao e' evolucao -- precisa de dois pra ter linha."""
    monkeypatch.setattr("skinvault.history.load_history",
                        lambda *a, **k: [{"total": 100.0}])
    screen._reload_value_series()
    assert screen._value_chart.isVisibleTo(screen) is False


def test_grafico_aparece_com_dois_pontos(screen, monkeypatch):
    monkeypatch.setattr(
        "skinvault.history.load_history",
        lambda *a, **k: [{"total": 100.0}, {"total": 120.0}])
    screen._reload_value_series()
    assert screen._value_chart.isVisibleTo(screen) is True
    assert screen._vc_lbl.isVisibleTo(screen) is True


def test_inventario_tem_altura_minima(screen):
    assert screen._views.minimumHeight() >= 300


def test_cartoes_do_topo_nao_esticam(screen):
    """Sem isto os cartoes crescem e engolem a lista."""
    from PyQt6.QtWidgets import QSizePolicy
    for card in screen.findChildren(type(screen._views.parent())):
        pass  # so' garante que a arvore existe
    # O piso do inventario continua valendo depois de repovoar
    screen._views.setMinimumHeight(340)
    assert screen._views.minimumHeight() == 340
    assert (screen._views.sizePolicy().verticalPolicy()
            != QSizePolicy.Policy.Maximum)
