"""Etapa 2 — Accent Color.

Paletas de cor de destaque em theme.py, persistencia em settings.json e
seletor visual na tela de Configuracoes com aplicacao ao vivo. Cobre:
tokens derivados recalculados por _apply_accent(), preservacao ao trocar
de tema, default verde SkinVault, swatches e hooks do MainWindow.
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from skinvault import settings as settings_mod
from skinvault.ui import theme as t


@pytest.fixture(autouse=True)
def _qapp():
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    for w in list(app.topLevelWidgets()):
        w.deleteLater()
    app.processEvents()
    app.quit()


# ── theme: paletas e tokens derivados ─────────────────────────

def test_default_accent_e_o_verde_skinvault():
    assert t.DEFAULT_ACCENT == "verde"
    assert t.ACCENTS["verde"]["accent"] == "#22C55E"
    # Tokens de modulo nascem com a paleta default (sem chamar nada).
    assert t.ACCENT == "#22C55E"
    assert t.FOCUS_GREEN == "#4ADE80"
    assert t.ACCENT_DIM == "rgba(34,197,94,0.16)"


def test_paletas_tem_tokens_obrigatorios():
    for pal in t.ACCENTS.values():
        assert pal["accent"].startswith("#")
        assert pal["focus"].startswith("#")
        assert 0 < pal["dim"] < 1
        assert 0 < pal["hov"] < 1
        assert 0 < pal["pressed"] < 1
    # Default fica na frente (ordem dos swatches no seletor).
    assert list(t.ACCENTS)[0] == t.DEFAULT_ACCENT


def test_apply_accent_switch_para_azul():
    try:
        t._apply_accent("azul")
        assert t.ACCENT == t.ACCENTS["azul"]["accent"]
        assert t.ACCENT_DIM == "rgba(59,130,246,0.16)"
        assert t.ACCENT_HOV == "rgba(59,130,246,0.26)"
        assert t.ACCENT_PRESSED == "rgba(59,130,246,0.36)"
        assert t.FOCUS_GREEN == t.ACCENTS["azul"]["focus"]
    finally:
        t._apply_accent(t.DEFAULT_ACCENT)


def test_apply_accent_invalido_cai_no_default():
    try:
        t._apply_accent("nao_existe")
        assert t.ACCENT == t.ACCENTS["verde"]["accent"]
    finally:
        t._apply_accent(t.DEFAULT_ACCENT)


def test_reload_palette_preserva_accent_escolhido():
    try:
        t._apply_accent("roxo")
        t._reload_palette("light")
        assert t.ACCENT == t.ACCENTS["roxo"]["accent"]
        t._reload_palette("dark")
        assert t.ACCENT == t.ACCENTS["roxo"]["accent"]
    finally:
        t._apply_accent(t.DEFAULT_ACCENT)


def test_reload_palette_aceita_accent_novo():
    try:
        t._reload_palette("dark", "laranja")
        assert t.ACCENT == t.ACCENTS["laranja"]["accent"]
    finally:
        t._apply_accent(t.DEFAULT_ACCENT)


# ── settings: persistencia ────────────────────────────────────

def test_accent_color_default_no_settings():
    s = settings_mod.load_settings(path="nonexistent.json")
    assert s["accent_color"] == "verde"


def test_accent_color_round_trip(tmp_path):
    p = tmp_path / "settings.json"
    settings_mod.save_settings({"accent_color": "azul"}, path=p)
    loaded = settings_mod.load_settings(path=p)
    assert loaded["accent_color"] == "azul"


# ── seletor na tela de Configuracoes ──────────────────────────

def test_settings_accent_carrega_do_settings(monkeypatch):
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {"accent_color": "azul"})
    from skinvault.ui.settings_screen import SettingsScreen
    screen = SettingsScreen()
    assert screen._accent_w.current_key() == "azul"


def test_settings_accent_default_quando_sem_settings(monkeypatch):
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    from skinvault.ui.settings_screen import SettingsScreen
    screen = SettingsScreen()
    assert screen._accent_w.current_key() == "verde"


def test_settings_accent_salva_ao_clicar(monkeypatch):
    saved = []
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda s, *a, **kw: saved.append(s))
    from skinvault.ui.settings_screen import SettingsScreen
    screen = SettingsScreen()
    screen._accent_w._btns["laranja"].click()
    assert saved and saved[-1]["accent_color"] == "laranja"
    assert screen._accent_w.current_key() == "laranja"


def test_settings_accent_chama_hook_da_janela(monkeypatch):
    """Trocar a cor de destaque reaplica ao vivo via _on_theme_changed."""
    from PyQt6.QtWidgets import QWidget
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda *a, **kw: None)
    from skinvault.ui.settings_screen import SettingsScreen
    called = []
    parent = QWidget()
    parent._on_theme_changed = lambda: called.append(True)
    screen = SettingsScreen(parent)
    screen._accent_w._btns["azul"].click()
    assert called == [True]


def test_settings_accent_swatches_cobrem_todas_as_paletas(monkeypatch):
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    from skinvault.ui.settings_screen import SettingsScreen
    screen = SettingsScreen()
    assert set(screen._accent_w._btns) == set(t.ACCENTS)


def test_settings_accent_reset_volta_ao_verde(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    saved = []
    state = {"accent_color": "azul"}
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: state)
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda s, *a, **kw: (state.update(s), saved.append(s)))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.Yes)
    from skinvault.ui import settings_screen as ss
    monkeypatch.setattr(ss.Toast, "show_toast",
                        classmethod(lambda cls, *a, **kw: None))
    screen = ss.SettingsScreen()
    screen._on_reset()
    assert saved and saved[-1]["accent_color"] == ss.DEFAULTS["accent_color"]
    assert screen._accent_w.current_key() == "verde"


def test_swatch_pinta_a_bolinha_da_paleta():
    """O swatch desenha a propria cor (preview), nao o ACCENT corrente."""
    from PyQt6.QtGui import QColor, QPixmap
    from skinvault.ui.settings_screen import _SwatchButton
    btn = _SwatchButton("azul", "Azul", "#3B82F6")
    btn.resize(120, 34)
    pm = QPixmap(120, 34)
    pm.fill(Qt.GlobalColor.transparent)
    btn.render(pm)
    img = pm.toImage()
    x, y = 17, btn.height() // 2
    cor = QColor(img.pixel(x, y))
    assert abs(cor.red() - 0x3B) < 30, cor
    assert abs(cor.green() - 0x82) < 30, cor
    assert abs(cor.blue() - 0xF6) < 30, cor


# ── restyle ao vivo (sidebar + segmented) ─────────────────────

def test_sidebar_restyle_reaplica_accent(monkeypatch):
    from skinvault.ui.sidebar import Sidebar
    sb = Sidebar()
    sb.add_item("account", "user", "Minha Conta")
    sb.add_item("settings", "gear", "Configurações")
    sb.select("account")
    try:
        t._apply_accent("roxo")
        sb.restyle()
        item = sb._items["account"]
        # QSS reaplicado embute os tokens novos (ACCENT_DIM + FOCUS_GREEN).
        assert t.ACCENT_DIM in item.styleSheet()
        assert t.FOCUS_GREEN in item.styleSheet()
        # O icone ativo volta a usar o ACCENT novo.
        assert item._icon._color == t.ACCENT
    finally:
        t._apply_accent(t.DEFAULT_ACCENT)


def test_segmented_control_restyle_reaplica_accent():
    from skinvault.ui.components import SegmentedControl
    seg = SegmentedControl()
    seg.add("dark", "Escuro")
    seg.add("light", "Claro")
    try:
        t._apply_accent("azul")
        seg.restyle()
        assert t.ACCENT in seg._items["dark"].styleSheet()
        assert t.FOCUS_GREEN in seg._items["dark"].styleSheet()
    finally:
        t._apply_accent(t.DEFAULT_ACCENT)
