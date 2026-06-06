"""Testes do theme — funcoes de style (todas sem QApp)."""
from __future__ import annotations

from skinvault.ui.theme import (
    brl,
    btn_danger,
    btn_primary,
    btn_secondary,
    btn_steam,
    input_style,
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
