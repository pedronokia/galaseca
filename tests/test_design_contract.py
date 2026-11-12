"""Contrato de design do site público -- trava os tokens da identidade
Apple lendo `style.css` do disco (sem navegador, roda na suíte normal).

A regressão visual (`tests/visual/visual_regression.py`) pega MUDANÇAS
de renderização; este teste pega mudanças de FONTE -- alguém trocar
`--accent`, o corpo de 17px, o raio dos cards etc. e não perceber. Se
um token mudar de propósito, o teste muda junto: é o documento vivo da
identidade visual (valores conferidos com apple.com em 2026-11-12).
"""
from __future__ import annotations

import re
from pathlib import Path

STYLE = (
    Path(__file__).resolve().parents[1]
    / "galaseca" / "public_site" / "static" / "style.css"
)


def _css() -> str:
    return STYLE.read_text(encoding="utf-8")


def _bloco(css: str, seletor: str) -> str:
    """Texto da PRIMEIRA regra `seletor { ... }` (do abre-chaves ao
    primeiro fecha-chaves). Suficiente para regras simples da folha --
    blocos com @media aninhado não passam por aqui."""
    início = css.find(f"{seletor} {{")
    assert início >= 0, f"regra não encontrada: {seletor}"
    fim = css.find("}", início)
    return css[início:fim]


def test_tokens_de_superficie_apple():
    css = _css()
    assert "--bg-elevated: #f5f5f7" in css
    assert "--surface-sunken: #f5f5f7" in css
    assert "--surface-escura: #1d1d1f" in css
    assert "--text: #1d1d1f" in css
    assert "--text-muted: #6e6e73" in css
    assert "--border: rgba(0, 0, 0, 0.12)" in css


def test_azul_de_acao_da_apple():
    css = _css()
    assert "--accent: #0071e3" in css
    # Hover do botão pílula clareia (#0077ed), como em apple.com.
    assert "--accent-hover: #0077ed" in css
    assert "background: var(--accent-hover);" in css


def test_raios_da_apple():
    css = _css()
    # Pílula de 980px (botões/chips) e cards com raio 18px.
    assert "--radius-pill: 980px" in css
    assert "--radius-md: 18px" in css
    # A grade usa as medidas da Apple: 980px de conteúdo.
    assert "--largura-conteudo: 980px" in css
    # Pelo menos um botão/chip usa a pílula (não um raio menor).
    assert "border-radius: var(--radius-pill);" in css


def test_corpo_tipografico_17px():
    css = _css()
    assert "--fs-base: 1.0625rem" in css  # 17px
    corpo = _bloco(css, "body")
    assert "font-size: var(--fs-base);" in corpo
    # 25/17 ≈ 1.47 (25px de entrelinha em corpo de 17px).
    assert "line-height: 1.47;" in corpo
    # tracking da Apple no corpo de 17px.
    assert "letter-spacing: -0.022em;" in corpo


def test_titulos_600_e_escala_32_48_64():
    css = _css()
    titulos = _bloco(css, "h1, h2, h3")
    assert "font-weight: 600;" in titulos
    assert "--fs-xl: 2rem" in css      # 32px
    assert "--fs-2xl: 3rem" in css     # 48px
    assert "--fs-display: 4rem" in css  # 64px


def test_rodape_cinza_claro_12px():
    css = _css()
    rodape = _bloco(css, "footer.rodape")
    assert "background: var(--bg-elevated);" in rodape  # #f5f5f7
    assert "font-size: var(--fs-2xs);" in rodape        # 12px
    assert "--fs-2xs: 0.75rem" in css


def test_cards_sem_sombra_com_fio_de_1px():
    css = _css()
    card = _bloco(css, ".cartao-item")
    assert "border: 1px solid var(--border);" in card
    assert "border-radius: var(--radius-md);" in card
    # A Apple quase não usa sombra: o card não "levanta".
    assert "box-shadow" not in card


def test_respeita_reduced_motion():
    css = _css()
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_sem_estilo_inline_no_css():
    """O CSP não permite estilos inline (AGENTS.md): a folha não pode
    nem ela mesma normalizar `style=""` em lugar nenhum."""
    css = _css()
    sem_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    assert not re.search(r'\bstyle\s*=\s*"', sem_comentarios)
