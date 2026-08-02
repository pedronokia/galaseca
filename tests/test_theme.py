"""Testes do theme — funcoes de style (todas sem QApp)."""
from __future__ import annotations

from skinvault.ui.theme import (
    brl,
    btn_danger,
    btn_ghost,
    btn_primary,
    btn_secondary,
    btn_steam,
    input_style,
    table_style,
)


def test_brl_formats_value():
    assert "R$" in brl(1234.56)


def test_brl_none_returns_emdash():
    assert brl(None) == "\u2014"


def test_input_style_returns_string():
    assert "QLineEdit" in input_style()


def test_btn_primary_returns_string():
    assert "QPushButton" in btn_primary()


def test_btn_primary_disabled_contains_disabled_state():
    s = btn_primary(disabled=True)
    assert ":disabled" in s


def test_btn_steam_returns_string():
    assert "QPushButton" in btn_steam()


def test_btn_secondary_returns_string():
    assert "QPushButton" in btn_secondary()


def test_btn_danger_returns_string():
    assert "QPushButton" in btn_danger()


def test_all_btn_helpers_have_focus_ring():
    # Acessibilidade keyboard (Frente C): todo botao sinaliza foco
    for style in (btn_primary(), btn_steam(), btn_secondary(),
                  btn_danger(), btn_ghost()):
        assert ":focus" in style


def test_all_btn_helpers_have_pressed_state():
    # Microinteracoes: clique precisa de feedback proprio, distinto do
    # hover (senao apertar o botao parece nao ter feito nada).
    for style in (btn_primary(), btn_steam(), btn_secondary(),
                  btn_danger(), btn_ghost()):
        assert ":pressed" in style


def test_pressed_state_differs_from_hover():
    # Cada :pressed usa uma cor propria, nao repete o valor do :hover --
    # senao clicar e passar o mouse ficariam visualmente identicos.
    import re
    for style in (btn_primary(), btn_steam(), btn_secondary(), btn_danger()):
        hover_bg = re.search(r":hover \{ background: ([^;]+);", style).group(1)
        pressed_bg = re.search(r":pressed \{ background: ([^;]+);", style).group(1)
        assert hover_bg != pressed_bg


def test_table_style_header_has_hover_and_pressed():
    # Cabecalho de coluna e' clicavel (ordena) mas nao dava nenhum feedback
    # visual ao passar o mouse ou clicar -- parecia rotulo estatico.
    s = table_style()
    assert "QHeaderView::section:hover" in s
    assert "QHeaderView::section:pressed" in s


def test_input_style_has_focus_ring():
    assert ":focus" in input_style()
