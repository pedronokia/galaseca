"""Contrato de design do site público -- trava os tokens da identidade
OpenCode lendo `style.css` do disco (sem navegador, roda na suíte normal).

A regressão visual (`tests/visual/visual_regression.py`) pega MUDANÇAS
de renderização; este teste pega mudanças de FONTE -- alguém trocar
`--accent`, o corpo de 17px, o raio dos cards etc. e não perceber. Se
um token mudar de propósito, o teste muda junto: é o documento vivo da
identidade visual (valores conferidos com opencode.ai/brand em 2026-11-12).
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


def test_tokens_de_superficie_opencode():
    css = _css()
    # Tema escuro profundo: fundo quase preto #050505, texto #e5e5e5,
    # texto secundário #9ca3af, bordas #333333.
    assert "--bg: #050505" in css
    assert "--bg-elevated: #111111" in css
    assert "--surface: #111111" in css
    assert "--surface-strong: #050505" in css
    assert "--surface-sunken: #171717" in css
    assert "--surface-escura: #050505" in css
    assert "--text: #e5e5e5" in css
    assert "--text-muted: #9ca3af" in css
    assert "--border: #333333" in css


def test_laranja_da_casa():
    css = _css()
    # Laranja escuro da casa nos botões e pílulas ativas, com texto
    # branco (5.2:1); links em #9a3412 e hover escurecendo (#7c2d0b).
    # O vivo #f97316 fica nos marcadores da marca (--marca).
    assert "--accent: #c2410c" in css
    assert "--accent-bright: #9a3412" in css
    assert "--accent-hover: #7c2d0b" in css
    assert "background: var(--accent-hover);" in css
    # Foco de teclado e item ativo das barras escuras também saem do
    # azul: foco em #c2410c e ativo do chrome em #fb923c.
    assert "--focus: #c2410c" in css
    assert "--chrome-foco: #fb923c" in css
    # Anel de foco dos formulários e selo "novo" acompanham o laranja.
    assert "rgba(194, 65, 12, 0.28)" in css
    assert "rgba(194, 65, 12, 0.1)" in css


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


def test_fonte_inter_autohospedada():
    """A pilha começa pela Inter Variable auto-hospedada (webfont) --
    o site fica IGUAL em qualquer sistema. Contexto (2026-11-12): o
    endpoint de webfont da Apple só atende com Referer do próprio
    apple.com (hotlink testado: 404 fora dele) e a licença da SF Pro
    não permite self-host; Inter é a open source mais próxima."""
    css = _css()
    assert 'font-family: "Inter Variable";' in css
    assert "fonts/inter-latin-opsz-normal.woff2?v=1" in css
    assert 'format("woff2-variations");' in css
    assert "font-weight: 100 900;" in css
    assert "font-display: swap;" in css
    assert '--font-sans: "Inter Variable", "Inter", -apple-system,' in css


def test_arquivos_da_fonte_comitados():
    """Fonte e licença (SIL OFL 1.1) existem no repositório -- sem eles
    o site cai no fallback do sistema e volta a divergir entre
    computadores."""
    pasta = STYLE.parent / "fonts"
    fonte = pasta / "inter-latin-opsz-normal.woff2"
    assert fonte.is_file() and fonte.stat().st_size > 20_000
    assert fonte.read_bytes()[:4] == b"wOF2"
    licenca = (pasta / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in licenca


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
    # Rodapé no tom #f5f5f7 (--surface-sunken): na página branca ainda
    # se destaca como faixa própria.
    assert "background: var(--surface-sunken);" in rodape
    assert "font-size: var(--fs-2xs);" in rodape        # 12px
    assert "--fs-2xs: 0.75rem" in css


def test_cards_sem_fio_sem_sombra():
    css = _css()
    card = _bloco(css, ".cartao-item")
    # Card-tile: sem fio -- o contraste vem da página cinza em volta --
    # e sem sombra (a Apple não faz o card "levantar").
    assert "border: 0;" in card
    assert "border-radius: var(--radius-md);" in card
    assert "box-shadow" not in card


def test_pagina_branca_com_faixa_borda_a_borda():
    """A página inteira é o branco #ffffff e as seções grandes atravessam
    a tela de borda a borda (truque 100vw), com o conteúdo de volta na
    coluna dentro da faixa."""
    css = _css()
    assert "background: var(--bg);" in css  # body na página branca
    faixa = _bloco(css, ".faixa")
    assert "width: 100vw;" in faixa
    assert "margin-left: calc(50% - 50vw);" in faixa
    # O html corta o excedente do 100vw (barra de rolagem).
    html_bloco = _bloco(css, "html")
    assert "overflow-x: clip;" in html_bloco


def test_ficha_do_item_tile_branca():
    css = _css()
    ficha = _bloco(css, ".resumo-cards-item")
    # Painel de métricas vira tile branca na página cinza, com o selo
    # de Nota em caixinha cinza dentro (inverso do layout antigo).
    assert "background: var(--surface);" in ficha
    selo = _bloco(css, ".resumo-cards-item .card-nota-destaque")
    assert "background: var(--surface-strong);" in selo


def test_polimento_da_maquete_v4():
    """Rodada 2026-11-12: laranja como identidade + polimento aprovado
    na maquete v4 (pílulas, abas, faixa de informação, CTA do item e
    rodapé alinhado)."""
    css = _css()
    # Pílulas ativas em laranja (antes brancas com sombra).
    visao = _bloco(css, '.seletor-visao a[aria-current="page"]')
    assert "background: var(--accent);" in visao
    assert "box-shadow" not in visao
    # Abas de categoria: fantasma (transparente + fio) quando inativas,
    # laranja na ativa.
    aba = _bloco(css, ".aba-categoria")
    assert "background: transparent;" in aba
    assert "border: 1px solid var(--border);" in aba
    aba_ativa = _bloco(css, '.aba-categoria[aria-current="page"]')
    assert "background: var(--accent);" in aba_ativa
    # Faixa de informação da home: coleta + comparação do dia numa
    # única tile, cada linha com o fio laranja.
    painel = _bloco(css, ".painel-info")
    assert "background: var(--surface);" in painel
    linhas = _bloco(css, ".painel-info .resumo-do-dia")
    assert "border-left: 2px solid var(--accent);" in linhas
    # CTA laranja da página do item, em pílula com texto branco.
    acao = _bloco(css, ".botao-acao")
    assert "background: var(--accent);" in acao
    assert "border-radius: var(--radius-pill);" in acao
    # Linha de coleta fechando a ficha do item (régua de baixo).
    coleta = _bloco(css, ".resumo-cards-item .card-coleta")
    assert "border-top: 1px solid var(--border);" in coleta
    # Aviso do rodapé alinhado com a grade das colunas (margens auto).
    assert "footer.rodape p { margin: 0 auto var(--sp-2); }" in css


def test_respeita_reduced_motion():
    css = _css()
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_sem_estilo_inline_no_css():
    """O CSP não permite estilos inline (AGENTS.md): a folha não pode
    nem ela mesma normalizar `style=""` em lugar nenhum."""
    css = _css()
    sem_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    assert not re.search(r'\bstyle\s*=\s*"', sem_comentarios)
