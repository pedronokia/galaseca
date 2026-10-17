"""Linguagem da tela: codigos internos traduzidos e botoes do Qt em pt-BR."""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QDialogButtonBox

from skinvault.ui import textos


def test_codigos_do_veredito_viram_portugues():
    assert textos.traduz(textos.SPREAD, "tight") == "Pequena"
    assert textos.traduz(textos.BOOK, "buyer_dominant") == "Mais compradores"
    assert textos.traduz(textos.BOOK, "seller_dominant") == "Mais vendedores"
    assert textos.traduz(textos.TREND, "rising") == "Subindo"
    assert textos.traduz(textos.TREND, "falling") == "Caindo"


def test_codigo_desconhecido_ou_vazio():
    assert textos.traduz(textos.TREND, "novo_codigo") == "novo_codigo"
    assert textos.traduz(textos.TREND, "") == ""
    assert textos.traduz(textos.TREND, None) == ""


def test_scanner_nao_mostra_codigo_cru():
    """Antes de 2026-10-17 a celula mostrava 'tight'/'buyer_dominant'."""
    from skinvault.ui import scanner_screen
    for mapa in (scanner_screen._SPREAD_TXT, scanner_screen._BOOK_TXT,
                 scanner_screen._TREND_TXT):
        for codigo, texto in mapa.items():
            assert "_" not in texto and texto != codigo


def test_botoes_padrao_do_qt_em_portugues():
    from skinvault import gui
    app = QApplication.instance() or QApplication([])
    ok = gui._instalar_traducao_qt(app)
    try:
        assert ok
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        texto = bb.button(QDialogButtonBox.StandardButton.Close).text()
        assert texto.replace("&", "") == "Fechar"
    finally:
        tr = getattr(app, "_sv_tradutor_qt", None)
        if tr is not None:
            app.removeTranslator(tr)
            del app._sv_tradutor_qt


def test_traducao_que_falha_nao_impede_o_app():
    """App de teste (sem installTranslator) nao pode derrubar o launch()."""
    from skinvault import gui
    assert gui._instalar_traducao_qt(object()) is False
