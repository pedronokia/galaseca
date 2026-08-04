"""Skeleton & shimmer: controller compartilhado, tiles e graficos em loading.

O shimmer usa UM QTimer pra todos os widgets (sao dezenas de tiles). A
regra de ouro dos testes: o timer SO' roda com widget registrado e
visivel, e o teardown para tudo -- senao um timer esquecido vaza de um
teste pro outro.
"""
from __future__ import annotations

import pytest

from skinvault.ui import shimmer


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    shimmer.SHIMMER.clear()
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


# ── controller ─────────────────────────────────────────────────────

def test_registrar_inicia_o_timer_e_desregistrar_para(app):
    from PyQt6.QtWidgets import QWidget
    c = shimmer.SHIMMER
    c.clear()
    w = QWidget()
    c.register(w)
    assert c.is_running()
    assert c.is_animating(w)
    c.unregister(w)
    assert not c.is_running()
    assert not c.is_animating(w)


def test_ultimo_unregister_para_o_timer(app):
    from PyQt6.QtWidgets import QWidget
    c = shimmer.SHIMMER
    c.clear()
    a, b = QWidget(), QWidget()
    c.register(a)
    c.register(b)
    c.unregister(a)
    assert c.is_running()          # ainda tem b
    c.unregister(b)
    assert not c.is_running()      # zerou: para


def test_unregister_de_quem_nao_registrou_nao_quebra(app):
    from PyQt6.QtWidgets import QWidget
    c = shimmer.SHIMMER
    c.clear()
    c.unregister(QWidget())
    assert not c.is_running()


def test_tick_avanca_a_fase_e_repinta(app):
    from PyQt6.QtWidgets import QWidget
    c = shimmer.SHIMMER
    c.clear()
    w = QWidget()
    repintado = []
    w.update = lambda *a: repintado.append(1)
    c.register(w)
    fase0 = c.phase()
    c._tick()
    assert c.phase() == (fase0 + c.STEP) % 1.0
    assert repintado
    c.clear()


def test_tick_descarta_widget_destruido_e_para(app):
    from PyQt6.QtWidgets import QWidget
    c = shimmer.SHIMMER
    c.clear()
    w = QWidget()
    c.register(w)
    # Simula C++ ja' deletado: update() explode e o tick deve descartar.
    def _boom():
        raise RuntimeError("c++ object deleted")
    w.update = _boom
    c._tick()
    assert not c.is_running()
    assert c.registered_count() == 0


def test_clear_para_tudo(app):
    from PyQt6.QtWidgets import QWidget
    c = shimmer.SHIMMER
    c.clear()
    c.register(QWidget())
    c.register(QWidget())
    c.clear()
    assert c.registered_count() == 0
    assert not c.is_running()


# ── SkeletonTile ───────────────────────────────────────────────────

def test_skeleton_tile_pinta_estatico_sem_crash(app):
    from skinvault.ui.inventory_grid import SkeletonTile
    w = SkeletonTile()
    pix = w.grab()
    assert not pix.isNull()
    assert not shimmer.SHIMMER.is_running()   # nunca foi mostrado


def test_skeleton_tile_nao_mostrado_nao_anima(app):
    from skinvault.ui.inventory_grid import InventoryGrid
    g = InventoryGrid()
    g.set_skeleton(5)
    assert g.count() == 5
    assert not shimmer.SHIMMER.is_running()
    assert shimmer.SHIMMER.registered_count() == 0


def test_skeleton_tile_visivel_registra_e_esconde_desregistra(app):
    from PyQt6.QtCore import Qt
    from skinvault.ui.inventory_grid import InventoryGrid
    g = InventoryGrid()
    g.set_skeleton(4)
    g.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    g.show()
    app.processEvents()
    assert shimmer.SHIMMER.is_running()
    assert shimmer.SHIMMER.registered_count() >= 4
    g.hide()
    app.processEvents()
    assert not shimmer.SHIMMER.is_running()


def test_dados_substituem_o_esqueleto_e_zeram_o_shimmer(app):
    from PyQt6.QtCore import Qt
    from skinvault.ui.inventory_grid import InventoryGrid

    def _item(nome, steam=10.0):
        return {"name": nome, "qty": 1, "icon": None, "type": "Rifle",
                "steam_net": steam, "market_net": 7.0, "premium_pct": 30.0}

    g = InventoryGrid()
    g.set_skeleton(3)
    g.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    g.show()
    app.processEvents()
    assert shimmer.SHIMMER.registered_count() == 3
    g.set_items([_item("a")])
    app.processEvents()
    assert g.count() == 1
    # Os esqueletos sairam do grid; o timer para quando o ultimo e'
    # destruido/desregistrado (deferred delete roda no processEvents).
    assert shimmer.SHIMMER.registered_count() == 0
    assert not shimmer.SHIMMER.is_running()


# ── ValueChart loading ─────────────────────────────────────────────

def test_valuechart_loading_pinta_esqueleto(app):
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(240, 120)
    w.set_loading(True)
    assert w.loading()
    pix = w.grab()
    assert not pix.isNull()


def test_valuechart_loading_nao_visivel_nao_anima(app):
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(240, 120)
    w.set_loading(True)
    assert not shimmer.SHIMMER.is_running()
    assert not shimmer.SHIMMER.is_animating(w)


def test_valuechart_loading_visivel_anima_e_set_series_desliga(app):
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(240, 120)
    w.show()
    app.processEvents()
    w.set_loading(True)
    assert shimmer.SHIMMER.is_running()
    assert shimmer.SHIMMER.is_animating(w)
    w.set_series([100.0, 150.0, 120.0])
    assert not w.loading()
    assert not shimmer.SHIMMER.is_running()
    assert not shimmer.SHIMMER.is_animating(w)


def test_valuechart_set_loading_false_sai_do_esqueleto(app):
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(240, 120)
    w.show()
    app.processEvents()
    w.set_loading(True)
    assert w.loading()
    w.set_loading(False)
    assert not w.loading()
    assert not shimmer.SHIMMER.is_running()
    # Fora do loading o widget volta ao estado vazio, nao ao esqueleto.
    assert not w._loading


def test_valuechart_loading_ocupa_o_lugar_do_grafico(app):
    """Com <3 valores e loading ligado, o estado de loading tem
    precedencia sobre o empty state (senao a tela piscaria mensagens de
    'nenhuma avaliacao' no meio da busca)."""
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(240, 120)
    w.set_loading(True)
    assert not w._values
    assert w._loading


# ── PriceHistoryChart loading ──────────────────────────────────────

def test_pricechart_loading_pinta_esqueleto(app):
    from skinvault.ui.widgets import PriceHistoryChart
    w = PriceHistoryChart()
    w.resize(300, 160)
    w.set_loading(True)
    assert w.loading()
    pix = w.grab()
    assert not pix.isNull()


def test_pricechart_set_data_sai_do_loading(app):
    from skinvault.ui.widgets import PriceHistoryChart
    w = PriceHistoryChart()
    w.resize(300, 160)
    w.show()
    app.processEvents()
    w.set_loading(True)
    assert shimmer.SHIMMER.is_animating(w)
    w.set_data([{"time": 0, "price_median": 1.0, "purchases": 5},
                {"time": 1, "price_median": 2.0, "purchases": 3}])
    assert not w.loading()
    assert not shimmer.SHIMMER.is_animating(w)


def test_pricechart_escondido_desregistra_do_shimmer(app):
    from skinvault.ui.widgets import PriceHistoryChart
    w = PriceHistoryChart()
    w.resize(300, 160)
    w.show()
    app.processEvents()
    w.set_loading(True)
    assert shimmer.SHIMMER.is_animating(w)
    w.hide()
    app.processEvents()
    assert not shimmer.SHIMMER.is_animating(w)
    assert not shimmer.SHIMMER.is_running()


# ── pintura da faixa (tint accent) ─────────────────────────────────

def test_faixa_do_shimmer_pinta_tint_accent(app):
    """A faixa usa o ACCENT (configuravel na Etapa 2): no meio do
    gradiente o canal verde sobe acima do SURFACE puro."""
    from PyQt6.QtGui import QColor, QPainter, QPixmap
    from skinvault.ui import theme as t
    pm = QPixmap(200, 100)
    pm.fill(QColor(t.SURFACE))
    p = QPainter(pm)
    shimmer.paint_band(p, 200, 100, phase=0.5)
    p.end()
    img = pm.toImage()
    base_verde = QColor(t.SURFACE).green()
    achou = False
    for x in range(70, 130, 2):     # centro da faixa com phase=0.5
        px = QColor(img.pixel(x, 50))
        if px.green() > base_verde + 12:
            achou = True
            break
    assert achou


def test_faixa_respeita_o_accent_configurado(app):
    """Trocar o accent (Etapa 2) muda a cor da faixa: o teste pinta com o
    controller, muda a paleta e confere que o resultado difere."""
    from PyQt6.QtGui import QColor, QPainter, QPixmap
    from skinvault.ui import theme as t
    from skinvault.ui.theme import _reload_palette

    def _amostra():
        pm = QPixmap(200, 100)
        pm.fill(QColor(t.SURFACE))
        p = QPainter(pm)
        shimmer.paint_band(p, 200, 100, phase=0.5)
        p.end()
        return pm.toImage().pixel(100, 50)

    original = _reload_palette
    try:
        t._apply_accent("verde")
        verde = _amostra()
        t._apply_accent("azul")
        azul = _amostra()
        assert verde != azul
    finally:
        original("dark", "verde")


# ── microinteracoes: :pressed ──────────────────────────────────────

def test_segmented_control_tem_pressed(app):
    from skinvault.ui import theme as tt
    from skinvault.ui.components import SegmentedControl
    c = SegmentedControl()
    c.add("a", "A")
    css = c._btn_style()
    assert ":pressed" in css
    assert ":checked:pressed" in css
    assert f"background: {tt.SURFACE}" in css       # pressionar preenche
    assert tt.ACCENT_PRESSED in css                 # e usa a paleta accent


def test_activity_feed_chip_tem_pressed(app):
    from skinvault.ui.components import ActivityFeed
    css = ActivityFeed()._chip_style()
    assert ":pressed" in css
    assert ":checked:pressed" in css


def test_history_chip_tem_pressed(app):
    from skinvault.ui.history_screen import _FilterBar
    css = _FilterBar()._chip_style()
    assert ":pressed" in css
    assert ":checked:pressed" in css


def test_messagebox_pressed_differe_do_hover(app):
    import re
    from skinvault.ui import theme as t
    css = t.messagebox_style()
    assert ":pressed" in css
    hover = re.search(
        r"QMessageBox QPushButton:hover \{ background: ([^;]+);",
        css).group(1)
    pressed = re.search(
        r"QMessageBox QPushButton:pressed \{ background: ([^;]+);",
        css).group(1)
    assert hover != pressed


def test_sidebar_tem_pressed(app):
    from skinvault.ui.sidebar import _SidebarItem
    css_rail = _SidebarItem("scan", "Scanner", rail=True)._style_idle()
    css_full = _SidebarItem("scan", "Scanner")._style_idle()
    assert ":pressed" in css_rail
    assert ":pressed" in css_full


def test_swatch_de_accent_tem_pressed(app):
    from skinvault.ui.settings_screen import _SwatchButton
    css = _SwatchButton("verde", "Verde", "#22C55E")._style()
    assert ":pressed" in css


def test_categoria_do_inventario_tem_pressed(app):
    from skinvault.ui.inventory_screen import InventoryScreen
    btn = InventoryScreen._botao_categoria("Caixas", 3, False)
    assert ":pressed" in btn.styleSheet()
