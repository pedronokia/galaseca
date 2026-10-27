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


# A cobertura de "scanner nao mostra codigo cru" mora em
# test_scan_engine.py::test_scan_item_sucesso -- é lá que a tradução de
# verdade acontece (scan_engine.scan_item), não em scanner_screen.py.
# Removido 2026-10-27: o teste que existia aqui testava só os aliases
# _SPREAD_TXT/_BOOK_TXT/_TREND_TXT de scanner_screen.py, que nunca
# chegaram a ser usados por nenhum código de exibição -- a tradução
# migrou pra scan_engine.py em algum ponto e os aliases ficaram
# vestigiais, sem que o teste notasse (ele testava os próprios aliases,
# não o pipeline real).


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


def test_cartao_mercado_conta_pelo_codigo_e_nao_pelo_texto(monkeypatch):
    """Regressao: "trend" virou texto de tela ("Subindo") e o market_breadth,
    que conta "rising"/"falling", passou a devolver vazio -- cartao Mercado
    sempre em "—". A logica usa "trend_code"."""
    from PyQt6.QtCore import Qt
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    # Guardar a referencia: "QApplication.instance() or QApplication([])"
    # solto numa linha cria o app e o Python o destroi na hora (ninguem o
    # segura). A tela criada depois, sem app, faz o Qt abortar o processo
    # sem mensagem (0xC0000409).
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from skinvault import settings
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(settings, "load_settings", lambda: {})

    def _r(nome, codigo):
        return {"name": nome, "price": 10.0, "price_str": "R$ 10,00",
                "median": 11.0, "score": 60, "breakdown": [],
                "verdict": "abaixo do típico", "verdict_color": "#fff",
                "spread": "", "book": "",
                "trend": textos.TREND[codigo], "trend_code": codigo,
                "sd_label": "", "data_quality": {}, "score_tooltip": "",
                "pump_risk": {"level": "low", "reasons": []}}

    tela = ScannerScreen(PriceCache(ttl=3600))
    tela._scan_results = [_r("A", "rising"), _r("B", "rising"),
                          _r("C", "falling"), _r("D", "stable")]
    tela._populate()
    valor = tela._stat_breadth._value.text()
    assert valor != "—"
    assert "50% ↑" in valor and "25% ↓" in valor
