"""Espaco vertical da tela de Conta e o grafico de evolucao.

Historia deste arquivo, porque o contrato virou do avesso e o motivo
importa:

Em 28/07/2026, num monitor 1080p, o grafico vazio ocupava ~200px so' pra
escrever "Avalie 2x+" e a lista do inventario sobrava com ~5 linhas no
rodape. A resposta foi encolher o grafico (teto de 90px) e SUMIR com ele
quando nao havia serie.

Em 30/07/2026 o inventario virou aba propria e a metade de baixo desta
tela ficou vazia. Sem disputa por altura, esconder o grafico deixava um
cartao so' com titulo -- que parece defeito. O grafico agora tem cartao
proprio, altura de verdade, e no lugar de sumir ele DIZ quantos pontos
existem.

O que NAO mudou: com 2 pontos nao se desenha linha. Dois pontos viram uma
diagonal que parece alarme e nao informa tendencia nenhuma.
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


def _tem_linha_colorida(widget) -> bool:
    """A linha do ValueChart e' verde (alta) ou vermelha (queda).

    Varre o pixmap atras dessas cores: e' o jeito de afirmar "nao desenhou
    linha" sem depender de detalhe de implementacao do paintEvent.
    """
    from skinvault.ui import theme as t
    from PyQt6.QtGui import QColor

    widget.resize(240, 120)
    img = widget.grab().toImage()
    alvos = {QColor(t.POSITIVE).rgb(), QColor(t.DANGER).rgb()}
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixel(x, y) in alvos:
                return True
    return False


# ── o grafico nao some mais ────────────────────────────────────────


def test_grafico_continua_visivel_sem_serie(screen):
    """Cartao proprio: sumir deixaria so' o titulo, que parece defeito."""
    assert screen._value_chart.isVisibleTo(screen) is True
    assert screen._vc_lbl.isVisibleTo(screen) is True


def test_legenda_avisa_quantas_avaliacoes_faltam(screen, monkeypatch):
    monkeypatch.setattr("skinvault.history.load_history",
                        lambda *a, **k: [{"total": 100.0}, {"total": 120.0}])
    screen._reload_value_series()
    assert "3 avaliações" in screen._vc_lbl.text()


def test_legenda_normal_com_serie(screen, monkeypatch):
    monkeypatch.setattr(
        "skinvault.history.load_history",
        lambda *a, **k: [{"total": 100.0}, {"total": 120.0},
                         {"total": 110.0}])
    screen._reload_value_series()
    assert "cada avaliação grava um ponto" in screen._vc_lbl.text()


# ── mas continua sem desenhar reta de 2 pontos ─────────────────────


def test_dois_pontos_nao_desenham_linha(screen, monkeypatch):
    """O motivo original: a diagonal de 2 pontos parecia alarme."""
    monkeypatch.setattr("skinvault.history.load_history",
                        lambda *a, **k: [{"total": 100.0}, {"total": 120.0}])
    screen._reload_value_series()
    assert _tem_linha_colorida(screen._value_chart) is False


def test_tres_pontos_desenham_linha(screen, monkeypatch):
    monkeypatch.setattr(
        "skinvault.history.load_history",
        lambda *a, **k: [{"total": 100.0}, {"total": 120.0},
                         {"total": 110.0}])
    screen._reload_value_series()
    assert _tem_linha_colorida(screen._value_chart) is True


def test_grafico_ganhou_altura_de_verdade(screen):
    """O teto de 90px existia pela disputa com a lista, que saiu da tela."""
    assert screen._value_chart.minimumHeight() >= 120
