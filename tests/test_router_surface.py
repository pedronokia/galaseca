"""Superficie do shell: um tom so', e sem breadcrumb no login.

Bug visual visto em 28/07/2026: a faixa do breadcrumb ficava em
BG_ELEVATED enquanto o resto da tela de login usava BG -- dois tons na
mesma janela. Sobra do desenho antigo, em que o login era uma superficie
unica sem cartao flutuante.
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


@pytest.fixture
def router(tmp_path):
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    return ScreenRouter(PriceCache(tmp_path / "p.json", ttl=3600))


def test_login_esconde_o_breadcrumb(router):
    """"Bem-vindo" nao e' caminho de navegacao -- e' enchimento."""
    router._set_surface(login=True)
    assert router._breadcrumb.isVisibleTo(router) is False


def test_app_mostra_o_breadcrumb(router):
    router._set_surface(login=False)
    assert router._breadcrumb.isVisibleTo(router) is True


def test_login_e_um_tom_so(router):
    """Router e LoginGate no MESMO tom.

    O invariante nao e' "mesmo CSS nos dois estados" -- e' que, dentro do
    login, nao exista diferenca de tom. Qualquer divergencia aqui aparece
    como moldura escura em volta do conteudo, que foi o bug relatado.
    """
    router._set_surface(login=True)
    assert t.BG_ELEVATED in router.styleSheet()
    assert t.BG_ELEVATED in router._login_gate.styleSheet()


def test_app_usa_o_fundo_escuro(router):
    """Fora do login o contraste e' desejado: cards sobre BG."""
    router._set_surface(login=False)
    css = router.styleSheet()
    assert t.BG in css
    assert t.BG_ELEVATED not in css


def test_perfil_continua_escondido_no_login(router):
    router._set_surface(login=True)
    assert router._profile_btn.isVisibleTo(router) is False
    router._set_surface(login=False)
    assert router._profile_btn.isVisibleTo(router) is True
