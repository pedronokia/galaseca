"""Paleta + tipografia + helpers de stylesheet (F11).

Substitui as constantes/helpers que viviam em gui.py. Visual: dark
Windows 11 com accent verde SkinVault e azul Steam pra elementos de
sync/conta.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QAbstractItemView, QTableWidget

# ── Paleta — tons do YouTube (monocromático) ─────────────────
BG          = "#0F0F0F"   # fundo principal (YouTube)
BG_ELEVATED = "#212121"   # sidebar, cards (YouTube secondary)
SURFACE     = "#272727"   # surface sobre card (input, hover, chip)
BORDER      = "#303030"   # bordas finas (YouTube divider)
TEXT        = "#F1F1F1"
TEXT_MUTED  = "#AAAAAA"
# ACCENT (cor de destaque de MARCA/UI) e' configuravel desde a Etapa 2
# (seletor em Configuracoes). Default: verde SkinVault historico
# (pre-F11), restaurado em 2026-08-03. Os valores abaixo sao da paleta
# default; ACCENTS + _apply_accent() recalcula os tokens ao trocar.
ACCENT      = "#22C55E"
ACCENT_DIM  = "rgba(34,197,94,0.16)"
ACCENT_HOV  = "rgba(34,197,94,0.26)"
ACCENT_PRESSED = "rgba(34,197,94,0.36)"
# CTA solido — YouTube clean: botao primario INVERTE o contraste do fundo
# (branco no tema escuro, preto no claro). Desacoplado de ACCENT porque
# o fill cheio exige par proprio de fg/bg/hover/focus.
PRIMARY_BG     = "#F1F1F1"
PRIMARY_FG     = "#0F0F0F"
PRIMARY_BORDER = "#F1F1F1"
PRIMARY_HOV    = "#E4E4E4"
PRIMARY_PRESSED = "#D6D6D6"  # um degrau alem do hover -- feedback de clique
PRIMARY_FOCUS  = "#9A9A9A"   # ring sobre o fill branco (visivel no CTA solido)
STEAM_BLUE  = "#66C0F4"   # azul Steam (conta/sync)
STEAM_DIM   = "rgba(102,192,244,0.14)"
STEAM_HOV   = "rgba(102,192,244,0.24)"
STEAM_PRESSED = "rgba(102,192,244,0.34)"
DANGER      = "#EF4444"
DANGER_DIM  = "rgba(239,68,68,0.16)"
DANGER_HOV  = "rgba(239,68,68,0.26)"
DANGER_PRESSED = "rgba(239,68,68,0.36)"
WARN        = "#F59E0B"

# Semantico de mercado/P&L — verde = lucro/alta/bom, DESACOPLADO do
# ACCENT de marca (a cor de destaque nao muda o verde de P&L). Use
# POSITIVE para "lucro/compra/bom" e DANGER para "prejuizo/queda/ruim".
POSITIVE     = "#3FB950"
POSITIVE_DIM = "rgba(63,185,80,0.16)"
POSITIVE_HOV = "rgba(63,185,80,0.26)"

# Focus ring (navegacao por teclado) — versao clareada da cor base de
# cada familia de botao. Qt6 QSS nao suporta `outline`; o focus e
# sinalizado trocando a cor da borda 1px ja reservada (zero layout
# shift) + bg igual ao hover.
FOCUS_GREEN = "#4ADE80"   # focus ring do ACCENT (verde clareado; segue a paleta)
FOCUS_STEAM = "#8FD3F8"   # STEAM_BLUE clareado
FOCUS_RED   = "#F87171"   # DANGER clareado

# ── Paletas de Accent Color (Etapa 2) ─────────────────────────
# Cor de destaque de MARCA/UI configuravel em Configuracoes ->
# Aparencia (seletor com swatches). Cada paleta define o hex base +
# alphas dos estados translucidos + hex do focus ring (versao
# clareada da base). _apply_accent() recalcula os tokens derivados
# (ACCENT, ACCENT_DIM/HOV/PRESSED, FOCUS_GREEN) sem restart.
ACCENTS: dict[str, dict] = {
    "verde": {
        "label": "Verde SkinVault",
        "accent": "#22C55E",
        "dim": 0.16,
        "hov": 0.26,
        "pressed": 0.36,
        "focus": "#4ADE80",
    },
    "azul": {
        "label": "Azul Neon",
        "accent": "#3B82F6",
        "dim": 0.16,
        "hov": 0.26,
        "pressed": 0.36,
        "focus": "#60A5FA",
    },
    "laranja": {
        "label": "Laranja Cyberpunk",
        "accent": "#F97316",
        "dim": 0.16,
        "hov": 0.26,
        "pressed": 0.36,
        "focus": "#FB923C",
    },
    "roxo": {
        "label": "Roxo/Magenta",
        "accent": "#A855F7",
        "dim": 0.16,
        "hov": 0.26,
        "pressed": 0.36,
        "focus": "#C084FC",
    },
    "neutro": {
        "label": "Neutro (clássico)",
        "accent": "#F1F1F1",
        "dim": 0.13,
        "hov": 0.22,
        "pressed": 0.32,
        "focus": "#FFFFFF",
    },
}
DEFAULT_ACCENT = "verde"

_current_accent_key = DEFAULT_ACCENT

# Chart overlays (technical analysis)
CHART_YELLOW = "#FACC15"  # support/resistance, spread
CHART_INDIGO = "#818CF8"  # SMA, moving averages

# Warning palette (extraido do regime banner do scanner)
WARN_BG     = "#2A2410"
WARN_BORDER = "#6B5A1A"
WARN_TEXT   = "#D8C267"

# Hover surface (row-hover, item:hover)
SURFACE_HOV = "#3F3F3F"
SURFACE_PRESSED = "#4A4A4A"  # um degrau alem do hover -- feedback de clique
# Linha alternada da tabela. Era "#21212B" cravado no table_style() -- um
# azulado que sobrou da paleta anterior e destoava do monocromatico.
ROW_ALT     = "#1A1A1A"

# Scrollbar (global, fina)
SCROLL_THUMB    = "#383838"
SCROLL_THUMB_HOV = "#484848"

# Overlay (LockOverlay, modals semi-transparentes)
BG_OVERLAY  = "rgba(15, 15, 15, 0.88)"

# ── Spacing scale ────────────────────────────────────────────
# Use em setContentsMargins() e setSpacing() ao inves de magic numbers
SPACE_XS  = 4
SPACE_SM  = 8
SPACE_MD  = 12
SPACE_LG  = 16
SPACE_XL  = 24
SPACE_2XL = 32

# ── Size tokens ──────────────────────────────────────────────
# Use em setFixedHeight/setFixedWidth/setMinimumHeight
SIZE_INPUT_H    = 32
SIZE_BTN_H      = 34
SIZE_ROW_H      = 32   # altura de linha em QTableWidget (Win11 density) --
                       # e' o mesmo valor de TABLE_ROW_H["standard"], mantido
                       # pra nao quebrar quem ainda le' SIZE_ROW_H direto.
SIZE_ICON_SM    = 14
SIZE_ICON_MD    = 18
SIZE_ICON_LG    = 22
SIZE_AVATAR     = 72
SIZE_PROGRESS_H = 6
SIZE_SEPARATOR  = 1
SIZE_CHART_H    = 120
SIZE_SIDEBAR_W  = 220
SIZE_SIDEBAR_RAIL = 64
SIZE_HEADER_H   = 40
SIZE_FOOTER_H   = 32

# ── Radius ───────────────────────────────────────────────────
# Consolida o param `radius=...` espalhado em Card/StatCard/etc.
# Bump 2026-07-31 (refresh modern clean): cantos mais generosos, mas
# longe de pill — pills so' em chips/toggle, nao em botoes/cards grandes.
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16

# Padding interno de Card por densidade visual.
# LG = default (Card init); MD = cards compactos; SM = chips/strips.
CARD_PAD_SM = (14, 10, 14, 10)
CARD_PAD_MD = (16, 14, 16, 14)
CARD_PAD_LG = (20, 18, 20, 18)

def _reload_palette(theme: str, accent: str | None = None) -> None:
    """Atualiza as constantes deste modulo a partir de THEMES.
    Chamado por gui.set_theme() para live reload sem restart.
    `accent`: chave de ACCENTS; None mantem a paleta de destaque atual.
    NOTA: assume execucao na UI thread; nao usar de threads paralelas."""
    from skinvault.gui import THEMES as _T
    pal = _T.get(theme, _T["dark"])
    global BG, BG_ELEVATED, SURFACE, BORDER, TEXT, TEXT_MUTED
    global STEAM_BLUE, DANGER, ROW_ALT
    global PRIMARY_BG, PRIMARY_FG, PRIMARY_BORDER, PRIMARY_HOV, PRIMARY_FOCUS
    BG = pal["bg"]
    BG_ELEVATED = pal["surface"]
    SURFACE = pal.get("surface2", pal["surface"])
    ROW_ALT = "#F7F7F7" if theme == "light" else "#1A1A1A"
    TEXT = pal["text"]
    TEXT_MUTED = pal["muted"]
    BORDER = "#3A3A44" if theme == "light" else "#303030"
    DANGER = "#EF4444"
    STEAM_BLUE = "#66C0F4"
    if theme == "light":
        # CTA solido inverte: fundo claro pede botao escuro
        PRIMARY_BG = "#1C1C1C"
        PRIMARY_FG = "#FFFFFF"
        PRIMARY_BORDER = "#1C1C1C"
        PRIMARY_HOV = "#2F2F2F"
        PRIMARY_FOCUS = "#FFFFFF"
    else:
        PRIMARY_BG = "#F1F1F1"
        PRIMARY_FG = "#0F0F0F"
        PRIMARY_BORDER = "#F1F1F1"
        PRIMARY_HOV = "#E4E4E4"
        PRIMARY_FOCUS = "#9A9A9A"
    _apply_accent(accent)


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    """'#RRGGBB' -> (r, g, b). A ordem dos canais importa pro rgba()."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _apply_accent(key: str | None = None) -> None:
    """Recalcula ACCENT/ACCENT_DIM/ACCENT_HOV/ACCENT_PRESSED/FOCUS_GREEN
    a partir da paleta `key` de ACCENTS. key None ou invalida cai na
    paleta default. Chamado por gui.set_theme() e no load do MainWindow.
    """
    global ACCENT, ACCENT_DIM, ACCENT_HOV, ACCENT_PRESSED, FOCUS_GREEN
    global _current_accent_key
    if key is None:
        key = _current_accent_key
    pal = ACCENTS.get(key)
    if pal is None:
        pal = ACCENTS[DEFAULT_ACCENT]
    _current_accent_key = DEFAULT_ACCENT if key not in ACCENTS else key
    r, g, b = _hex_rgb(pal["accent"])
    ACCENT = pal["accent"]
    ACCENT_DIM = f"rgba({r},{g},{b},{pal['dim']:.2f})"
    ACCENT_HOV = f"rgba({r},{g},{b},{pal['hov']:.2f})"
    ACCENT_PRESSED = f"rgba({r},{g},{b},{pal['pressed']:.2f})"
    FOCUS_GREEN = pal["focus"]


# ── Tipografia ───────────────────────────────────────────────
FONT_FAMILY = '"Segoe UI Variable Display", "Segoe UI", system-ui'
FS_MUTED = "9pt"
FS_BODY = "10pt"
FS_INPUT = "11pt"
FS_TITLE_SM = "13pt"
FS_TITLE_MD = "16pt"   # PageHeader title (compacto, entre FS_TITLE_SM e FS_TITLE)
FS_STAT = "18pt"
FS_TITLE = "24pt"
FS_HERO = "28pt"   # hero title (welcome dialog, large modals)

# Icon / display font sizes (mais raros, semanticos)
FS_ICON_HERO = "64pt"   # EmptyState glyph
FS_ICON_LG   = "48pt"   # Avatar / OverlayLock / LoginGate hero
FS_DISPLAY   = "36pt"   # Big number (score display)
FS_ICON_MD   = "32pt"   # Welcome feature card icon
FS_ICON_SM   = "22pt"   # Avatar fallback


# ── Helpers de formato ──────────────────────────────────────
def brl(v: float | None) -> str:
    """Formata BRL pt-BR. None vira '—'."""
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ── Stylesheet helpers ───────────────────────────────────────
def menu_style() -> str:
    """Estilo de QMenu, aplicado UMA vez no stylesheet da janela.

    Sem isto o QMenu herda o tema claro do Qt: popup branco sobre app
    escuro, com o item selecionado em azul-sistema e texto quase
    ilegivel. Ate' 2026-07-30 so' o menu da bandeja era estilizado, na
    mao, e os 6 QMenu das telas (trades, scanner, history, market e os
    dois de contexto de tabela) apareciam claros.

    Como QMenu e' popup (janela propria), ele NAO herda o stylesheet do
    widget pai -- por isso a regra tem que estar na QMainWindow, que e' a
    raiz da cadeia de estilo pra todos os popups filhos dela.
    """
    return (
        f"QMenu {{ background: {BG_ELEVATED}; color: {TEXT};"
        f" border: 1px solid {BORDER}; border-radius: {RADIUS_MD}px;"
        f" padding: 4px; }}"
        f"QMenu::item {{ padding: 7px 22px; border-radius: 6px;"
        f" margin: 1px 4px; }}"
        f"QMenu::item:selected {{ background: {SURFACE}; color: {TEXT}; }}"
        f"QMenu::item:disabled {{ color: {TEXT_MUTED}; }}"
        f"QMenu::separator {{ height: 1px; background: {BORDER};"
        f" margin: 4px 8px; }}"
    )


def input_style() -> str:
    return (
        f"QLineEdit, QDoubleSpinBox, QSpinBox"
        f" {{ background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: 10px; padding: 10px 12px; font-size: {FS_INPUT};"
        f" color: {TEXT}; font-family: {FONT_FAMILY}; }}"
        f"QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus"
        f" {{ border: 1px solid {ACCENT}; }}"
    )


def input_style_error() -> str:
    """Input com borda DANGER para feedback de validacao.

    O :focus volta ao ACCENT padrao — o usuario recebe feedback
    visual do erro ate interagir com o campo.
    """
    return (
        f"QLineEdit, QDoubleSpinBox, QSpinBox"
        f" {{ background: {SURFACE}; border: 1px solid {DANGER};"
        f" border-radius: 10px; padding: 10px 12px; font-size: {FS_INPUT};"
        f" color: {TEXT}; font-family: {FONT_FAMILY}; }}"
        f"QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus"
        f" {{ border: 1px solid {ACCENT}; }}"
    )


def btn_primary(padding: str = "10px 22px", fs: str = FS_INPUT,
                disabled: bool = False) -> str:
    """CTA solido (YouTube clean): fill cheio, contraste invertido.

    Tema escuro: botao branco com texto escuro. Tema claro: botao preto
    com texto claro. O ring de focus e' PRIMARY_FOCUS porque FOCUS_GREEN
    (branco) sumiria sobre o fill branco do CTA no tema escuro.
    """
    s = (
        f"QPushButton {{ color: {PRIMARY_FG}; background: {PRIMARY_BG};"
        f" border: 1px solid {PRIMARY_BORDER}; border-radius: 10px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {PRIMARY_HOV}; }}"
        f"QPushButton:pressed {{ background: {PRIMARY_PRESSED}; }}"
        f"QPushButton:focus {{ border: 1px solid {PRIMARY_FOCUS};"
        f" background: {PRIMARY_HOV}; }}"
    )
    if disabled:
        s += (
            "QPushButton:disabled { color: #777; border-color: #333;"
            " background: #1a1a20; }"
        )
    return s


def btn_steam(padding: str = "10px 22px", fs: str = FS_INPUT) -> str:
    return (
        f"QPushButton {{ color: #DDF4FF; background: {STEAM_DIM};"
        f" border: 1px solid {STEAM_BLUE}; border-radius: 10px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {STEAM_HOV}; }}"
        f"QPushButton:pressed {{ background: {STEAM_PRESSED}; }}"
        f"QPushButton:focus {{ border: 1px solid {FOCUS_STEAM};"
        f" background: {STEAM_HOV}; }}"
    )


def btn_secondary(padding: str = "8px 18px", fs: str = FS_BODY) -> str:
    """Botao de superficie: SURFACE + BORDER, sem tint translucido.

    Antes usava rgba(255,255,255,0.06) cravado + borda #3A3A44 — uma
    meia-tinta que nao acompanhava o tema claro. SURFACE e' token
    theme-aware, entao o botao respira com o tema de graca.
    """
    return (
        f"QPushButton {{ color: {TEXT}; background: {SURFACE};"
        f" border: 1px solid {BORDER}; border-radius: 10px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {SURFACE_HOV}; }}"
        f"QPushButton:pressed {{ background: {SURFACE_PRESSED}; }}"
        f"QPushButton:focus {{ border: 1px solid {TEXT_MUTED};"
        f" background: {SURFACE_HOV}; }}"
    )


def btn_danger(padding: str = "8px 18px", fs: str = FS_BODY) -> str:
    return (
        f"QPushButton {{ color: #FFE6E6; background: {DANGER_DIM};"
        f" border: 1px solid {DANGER}; border-radius: 10px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {DANGER_HOV}; }}"
        f"QPushButton:pressed {{ background: {DANGER_PRESSED}; }}"
        f"QPushButton:focus {{ border: 1px solid {FOCUS_RED};"
        f" background: {DANGER_HOV}; }}"
    )


def btn_ghost(padding: str = "6px 14px", fs: str = FS_MUTED) -> str:
    """Botao flat sem borda — estilo Win11 toolbar."""
    return (
        f"QPushButton {{ color: {TEXT_MUTED}; background: transparent;"
        f" border: 1px solid transparent; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ color: {TEXT}; background: {SURFACE};"
        f" border: 1px solid {BORDER}; }}"
        f"QPushButton:pressed {{ color: {TEXT}; background: {SURFACE_HOV};"
        f" border: 1px solid {BORDER}; }}"
        f"QPushButton:focus {{ color: {TEXT}; background: {SURFACE};"
        f" border: 1px solid {TEXT_MUTED}; }}"
    )


def spin_style() -> str:
    """QDoubleSpinBox / QSpinBox com setas triangulares CSS.

    Up/down buttons tem 18px de largura, separados por border-left.
    Setas via border-triangle (up-arrow = border-bottom, down-arrow =
    border-top) com width/height 0.
    """
    return (
        f"QDoubleSpinBox, QSpinBox"
        f" {{ background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: {RADIUS_SM}px; padding: 6px 10px;"
        f" font-size: {FS_INPUT}; color: {TEXT};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QDoubleSpinBox:focus, QSpinBox:focus"
        f" {{ border: 1px solid {ACCENT}; }}"
        f"QDoubleSpinBox::up-button, QSpinBox::up-button"
        f" {{ width: 18px; height: 14px; border-left: 1px solid {BORDER};"
        f" subcontrol-position: top right; }}"
        f"QDoubleSpinBox::down-button, QSpinBox::down-button"
        f" {{ width: 18px; height: 14px; border-left: 1px solid {BORDER};"
        f" subcontrol-position: bottom right; }}"
        f"QDoubleSpinBox::up-arrow, QSpinBox::up-arrow"
        f" {{ width: 0; height: 0;"
        f" border-left: 4px solid transparent;"
        f" border-right: 4px solid transparent;"
        f" border-bottom: 5px solid {TEXT_MUTED}; }}"
        f"QDoubleSpinBox::down-arrow, QSpinBox::down-arrow"
        f" {{ width: 0; height: 0;"
        f" border-left: 4px solid transparent;"
        f" border-right: 4px solid transparent;"
        f" border-top: 5px solid {TEXT_MUTED}; }}"
        f"QDoubleSpinBox::up-arrow:hover, QSpinBox::up-arrow:hover"
        f" {{ border-bottom-color: {TEXT}; }}"
        f"QDoubleSpinBox::down-arrow:hover, QSpinBox::down-arrow:hover"
        f" {{ border-top-color: {TEXT}; }}"
    )


def checkbox_style() -> str:
    """QCheckBox com indicator escuro 16x16, checked accent verde.

    Root QCheckBox tem apenas color/font/spacing — SEM border, SEM
    background. A borda vive apenas no ::indicator. Focus usa FOCUS_GREEN
    (Frente C).

    CUIDADO: a ordem do seletor de focus precisa ser subcontrol primeiro
    ('::indicator:focus'). A forma ':focus::indicator' e' malformada e o
    parser do Qt aplica a borda ao widget INTEIRO, incondicionalmente
    (verificado empiricamente em 12/06/2026).
    """
    return (
        f"QCheckBox {{ color: {TEXT_MUTED}; font-size: {FS_MUTED};"
        f" font-family: {FONT_FAMILY}; spacing: 8px; }}"
        f"QCheckBox:focus {{ color: {TEXT}; }}"
        f"QCheckBox::indicator {{ width: 16px; height: 16px;"
        f" border: 1px solid {BORDER}; border-radius: 5px;"
        f" background: {SURFACE}; }}"
        f"QCheckBox::indicator:checked {{ background: {ACCENT};"
        f" border-color: {ACCENT}; }}"
        f"QCheckBox::indicator:focus {{ border: 1px solid {FOCUS_GREEN}; }}"
    )


# ── Densidade de tabela ──────────────────────────────────────
# 3 niveis: altura de linha + padding de celula mudam juntos (senao o
# texto fica espremido numa linha baixa ou boiando solto numa alta).
# Persistido em settings["table_density"]; aplicado por configure_table()
# na construcao e por set_table_density() pra trocar ao vivo.
TABLE_ROW_H = {
    "compact": 24,
    "standard": SIZE_ROW_H,      # 32 -- default historico, sem mudanca
    "comfortable": 44,
}
TABLE_CELL_PAD = {
    "compact": "4px 10px",
    "standard": "9px 14px",      # default historico, sem mudanca
    "comfortable": "14px 18px",
}
TABLE_DENSITIES = ("compact", "standard", "comfortable")
_DEFAULT_DENSITY = "standard"


def table_style(density: str = _DEFAULT_DENSITY) -> str:
    pad = TABLE_CELL_PAD.get(density, TABLE_CELL_PAD[_DEFAULT_DENSITY])
    return (
        f"QTableWidget {{ background: {BG_ELEVATED};"
        f" alternate-background-color: {ROW_ALT};"
        f" gridline-color: transparent; border: 1px solid {BORDER};"
        f" border-radius: 12px; color: {TEXT}; font-size: {FS_BODY};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QTableWidget::item {{ padding: {pad}; }}"
        # O QHeaderView em si, nao so' a secao: a faixa do cabecalho DEPOIS
        # da ultima coluna cai na paleta do sistema (branca no Windows).
        # So' nao aparecia porque uma coluna esticava e nunca sobrava faixa.
        f"QHeaderView {{ background: {BG_ELEVATED}; border: none; }}"
        f"QHeaderView::section {{ background: {BG_ELEVATED};"
        f" color: {TEXT_MUTED}; border: none;"
        f" border-bottom: 1px solid {BORDER};"
         f" padding: {pad};"
        f" font-weight: 600; font-size: {FS_MUTED}; }}"
        # Cabecalho e' clicavel (ordena a coluna) mas nao dava nenhum
        # feedback ao passar o mouse -- parecia so' rotulo estatico.
        f"QHeaderView::section:hover {{ background: {SURFACE_HOV};"
        f" color: {TEXT}; }}"
        f"QHeaderView::section:pressed {{ background: {SURFACE_PRESSED};"
        f" color: {TEXT}; }}"
        f"QHeaderView::down-arrow {{ width: 8px; height: 8px;"
        f" subcontrol-origin: padding;"
        f" subcontrol-position: center right;"
        f" padding-right: 4px; }}"
        f"QHeaderView::up-arrow {{ width: 8px; height: 8px;"
        f" subcontrol-origin: padding;"
        f" subcontrol-position: center right;"
        f" padding-right: 4px; }}"
        f"QTableWidget::item:hover {{ background: {SURFACE_HOV}; }}"
        f"QTableWidget::item:selected {{ background: {ACCENT_DIM};"
        f" color: {TEXT}; }}"
        f"QTableView::item:selected:hover {{ background: {ACCENT_HOV}; }}"
    )


def tooltip_style() -> str:
    """Estilo do QToolTip, aplicado no QApplication inteiro.

    Sem isso o tooltip cai na paleta do sistema: no Windows sai com fundo
    claro, e como o texto herda a cor clara do tema escuro o resultado e'
    quase invisivel. E' o tooltip que carrega a informacao mais densa do
    app -- as cotacoes de todas as plataformas do item ficam ali.

    `border` explicito porque sem borda o balao se funde com o conteudo
    de tras quando o fundo atras tambem e' escuro.
    """
    return (
        f"QToolTip {{ background: {BG_ELEVATED}; color: {TEXT};"
        f" border: 1px solid {BORDER}; border-radius: {RADIUS_SM}px;"
        f" padding: 6px 8px; font-size: {FS_MUTED};"
        f" font-family: {FONT_FAMILY}; }}"
    )


def messagebox_style() -> str:
    """Estilo do QMessageBox, tambem so' alcancavel pelo app-stylesheet.

    Medido em 30/07/2026: o dialogo saia #FFFFFF puro dentro do tema
    escuro. Sao 47 pontos de chamada -- "Sobre", confirmacoes de exclusao,
    erros de sync -- e todos piscavam branco.

    Os botoes precisam de regra propria: dentro do QMessageBox eles nao
    herdam o btn_secondary() que o resto do app aplica widget a widget.
    """
    return (
        f"QMessageBox {{ background: {BG_ELEVATED}; }}"
        f"QMessageBox QLabel {{ color: {TEXT}; background: transparent;"
        f" font-size: {FS_BODY}; font-family: {FONT_FAMILY}; }}"
        f"QMessageBox QPushButton {{ color: {TEXT};"
        f" background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: {RADIUS_SM}px; padding: 6px 18px;"
        f" min-width: 72px; font-size: {FS_BODY};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QMessageBox QPushButton:hover {{ background: {SURFACE_HOV}; }}"
        f"QMessageBox QPushButton:pressed {{ background: {SURFACE_PRESSED}; }}"
        f"QMessageBox QPushButton:focus {{ border: 1px solid {TEXT_MUTED}; }}"
    )


def scrollbar_style() -> str:
    """Barras de rolagem, em todo canto que rola.

    Sem regra elas saem no cinza claro do Windows -- uma faixa clara na
    borda de cada tabela do tema escuro. Nao dava pra resolver junto com
    `table_style()` porque a barra aparece tambem em QScrollArea, na grade
    do inventario e nas telas de configuracao.

    Sem setas: o botao de seta do Windows nao aceita cor por stylesheet e
    ficava como dois quadrados claros nas pontas.
    """
    return (
        "QScrollBar:vertical { background: transparent; width: 10px;"
        " margin: 0; }"
        "QScrollBar:horizontal { background: transparent; height: 10px;"
        " margin: 0; }"
        f"QScrollBar::handle {{ background: {SURFACE_HOV};"
        " border-radius: 5px; min-height: 28px; min-width: 28px; }}"
        f"QScrollBar::handle:hover {{ background: {TEXT_MUTED}; }}"
        "QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0;"
        " border: none; background: none; }"
        "QScrollBar::add-page, QScrollBar::sub-page { background: none; }"
    )


def app_style() -> str:
    """Stylesheet aplicado no QApplication inteiro.

    Entra aqui o que nao da' pra resolver widget a widget: o que abre em
    janela propria (tooltip, message box), fora do alcance do stylesheet
    do dono, e o cromo que aparece em toda tela (barra de rolagem).
    Estilo de UMA tela continua indo no widget dela -- jogar tudo aqui
    faria uma regra de canto vazar pro app inteiro.
    """
    return tooltip_style() + messagebox_style() + scrollbar_style()


def card_style(radius: int = 10) -> str:
    """Card com borda uniforme — sem o bevel antigo (border-top).

    Antes tinha `border-top: #30303A`, um truque de "luz de topo" que
    dava relevo. Modern clean: superficie plana com hairline igual nos 4
    lados; a elevacao vem do tom (BG_ELEVATED sobre BG), nao do bevel.
    """
    return (
        f"QWidget#Card {{ background: {BG_ELEVATED};"
        f" border: 1px solid {BORDER};"
        f" border-radius: {radius}px; }}"
    )


def _ensure_header_width(table: QTableWidget, hh: QHeaderView) -> None:
    """Compensa o padding QSS que QHeaderView ignora no sizeHint.

    O padding declarado em QHeaderView::section (QSS) nao e considerado
    no calculo de ResizeToContents, entao headers com muito texto e
    alinhamento a direita truncam o primeiro caractere.  Esta funcao
    calcula o espaco necessario via fontMetrics e garante sectionSize
    >= text_width + padding_h + sort_indicator_room (~50px).
    """
    fm = table.fontMetrics()
    padding_room = 50
    for col in range(table.columnCount()):
        item = table.horizontalHeaderItem(col)
        if item is None:
            continue
        text_w = fm.horizontalAdvance(item.text())
        needed = max(text_w + padding_room, 120)
        if hh.sectionSize(col) < needed:
            hh.resizeSection(col, needed)


def align_table_columns(
    table: QTableWidget,
    right: set[int] | None = None,
    center: set[int] | None = None,
) -> None:
    """Aplica alinhamento por coluna estilo trading-app (Win11 dark).

    Colunas em `right`: AlignRight | AlignVCenter (dinheiro, numeros).
    Colunas em `center`: AlignCenter (status, categoricos).
    Headers tambem alinham pra bater com cells.
    Deve ser chamado no fim do _populate(), apos inserir todos os rows.
    """
    right = right or set()
    center = center or set()
    for i in range(table.rowCount()):
        for c in range(table.columnCount()):
            cell = table.item(i, c)
            if cell is None:
                continue
            if c in right:
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter,
                )
            elif c in center:
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    for c in right:
        hi = table.horizontalHeaderItem(c)
        if hi is not None:
            hi.setTextAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
            )
    for c in center:
        hi = table.horizontalHeaderItem(c)
        if hi is not None:
            hi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)


# ── Label style helpers ─────────────────────────────────────
# Consolida os 3 patterns inline mais comuns de QLabel.setStyleSheet.
# Para variantes raras (ACCENT, DANGER, text-decoration, etc.) manter
# inline.

def label_caption() -> str:
    """Caption/helper text: muted pequeno (FS_MUTED)."""
    return (
        f"color: {TEXT_MUTED}; font-size: {FS_MUTED};"
        f" font-family: {FONT_FAMILY};"
    )


def label_body_muted() -> str:
    """Body text muted: FS_BODY com cor TEXT_MUTED."""
    return (
        f"color: {TEXT_MUTED}; font-size: {FS_BODY};"
        f" font-family: {FONT_FAMILY};"
    )


def label_section() -> str:
    """Section title: TEXT + FS_TITLE_SM + weight 600."""
    return (
        f"color: {TEXT}; font-size: {FS_TITLE_SM}; font-weight: 600;"
        f" font-family: {FONT_FAMILY};"
    )


def label_caption_bold() -> str:
    """Caption pequeno em bold: TEXT_MUTED + FS_MUTED + weight 600.
    Usado em headers de chip-row, eyebrows e badge labels."""
    return (
        f"color: {TEXT_MUTED}; font-size: {FS_MUTED}; font-weight: 600;"
        f" font-family: {FONT_FAMILY};"
    )


def label_hero() -> str:
    """Hero title: TEXT + FS_HERO + weight 700 + letter-spacing -0.5px.
    Usado em modals de boas-vindas e telas de destaque."""
    return (
        f"color: {TEXT}; font-size: {FS_HERO}; font-weight: 700;"
        f" font-family: {FONT_FAMILY}; letter-spacing: -0.5px;"
    )


def row_tint(pnl: float | None) -> QColor | None:
    """Retorna cor de fundo semantica para linha de tabela.

    Lucro (>0) → POSITIVE_DIM (verde translúcido, alpha ~0.16)
    Prejuízo (<0) → DANGER_DIM (vermelho translúcido, alpha ~0.16)
    Zero/None → None (mantém zebra)

    NOTA: QColor do Qt6 nao parseia 'rgba()' CSS — construimos com
    alpha int 0-255 a partir dos hex POSITIVE/DANGER.
    """
    if pnl is None or pnl == 0:
        return None
    if pnl > 0:
        c = QColor(POSITIVE)
        c.setAlpha(41)  # 0.16 * 255
        return c
    c = QColor(DANGER)
    c.setAlpha(41)
    return c


def configure_table(table: QTableWidget,
                    density: str = _DEFAULT_DENSITY) -> None:
    """Aplica os defaults visuais Win11 trading-app a uma QTableWidget.

    Consolida ~7 linhas de boilerplate duplicadas em todas as telas com
    tabela (account, history, scanner, trades, watchlist). Ponto unico
    de controle pra futuros polishes (ex: setShowGrid, focus row).

    `density`: "compact" | "standard" | "comfortable" -- normalmente lido
    de settings["table_density"] pela tela antes de chamar. Configuracoes
    especificas (sort, header resize modes, selection mode custom)
    continuam inline na tela.
    """
    h = table.verticalHeader()
    h.setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    hh = table.horizontalHeader()
    hh.setMinimumSectionSize(120)
    set_table_density(table, density)


def set_table_density(table: QTableWidget,
                      density: str = _DEFAULT_DENSITY) -> None:
    """Reaplica so' a parte dependente de densidade numa tabela JA
    construida -- usado pela troca ao vivo na tela de Configuracoes.

    Nao mexe em edit triggers/selecao/sort: isso e' setup de uma vez so,
    feito por configure_table(). Chamar de novo aqui seria inofensivo mas
    desnecessario.
    """
    if density not in TABLE_DENSITIES:
        density = _DEFAULT_DENSITY
    table.verticalHeader().setDefaultSectionSize(TABLE_ROW_H[density])
    table.setStyleSheet(table_style(density))
