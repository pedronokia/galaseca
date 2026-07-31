"""Widgets que abrem em JANELA PROPRIA caem na paleta do sistema.

Tooltip e message box nao sao alcancados pelo setStyleSheet do widget
dono: sao janelas separadas, e so' o stylesheet de APLICACAO chega neles.
Sem isso saem claros no Windows -- medido em 30/07/2026, o QMessageBox
vinha #FFFFFF puro dentro do tema escuro, em 47 pontos de chamada.

Ja' foi a mesma historia com QScrollArea (viewport branco na grade do
inventario) e QHeaderView (faixa branca depois da ultima coluna).
"""
from __future__ import annotations

import pytest

from skinvault.ui import theme as t


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


def test_app_style_cobre_os_dois(app):
    css = t.app_style()
    assert "QToolTip" in css
    assert "QMessageBox" in css


def test_tooltip_nao_fica_com_fundo_do_sistema(app):
    css = t.tooltip_style()
    assert f"background: {t.BG_ELEVATED}" in css
    assert f"color: {t.TEXT}" in css


def test_messagebox_pinta_fundo_e_texto(app):
    css = t.messagebox_style()
    assert f"QMessageBox {{ background: {t.BG_ELEVATED}; }}" in css
    # O label precisa de regra propria: sem ela o texto fica na cor do
    # sistema sobre o fundo novo.
    assert "QMessageBox QLabel" in css
    # E o botao tambem: dentro do box ele nao herda o btn_secondary que o
    # resto do app aplica widget a widget.
    assert "QMessageBox QPushButton" in css


def test_messagebox_renderiza_escuro_de_verdade(app):
    """Nao basta a regra existir -- ela tem que vencer a paleta."""
    from collections import Counter
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
    app.setStyleSheet(t.app_style())
    box = QMessageBox()
    box.setText("teste")
    box.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    box.show()
    app.processEvents()
    img = box.grab().toImage()
    cores = Counter()
    for y in range(img.height()):
        for x in range(img.width()):
            cores[img.pixel(x, y) & 0xFFFFFF] += 1
    dom = cores.most_common(1)[0][0]
    luz = ((dom >> 16 & 255) + (dom >> 8 & 255) + (dom & 255)) / 3
    assert luz < 128, "QMessageBox voltou a sair claro (#%06X)" % dom
    app.setStyleSheet("")


def test_app_style_segue_o_tema(app):
    """Trocar o tema tem que mudar o CSS -- ele e' montado na chamada."""
    escuro = t.app_style()
    from skinvault.ui.theme import _reload_palette
    try:
        _reload_palette("light")
        claro = t.app_style()
        assert claro != escuro
    finally:
        _reload_palette("dark")
