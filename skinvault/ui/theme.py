"""Paleta + tipografia + helpers de stylesheet (F11).

Substitui as constantes/helpers que viviam em gui.py. Visual: dark
Windows 11 com accent verde SkinVault e azul Steam pra elementos de
sync/conta.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QTableWidget

# ── Paleta ───────────────────────────────────────────────────
BG          = "#0E0E12"   # fundo principal
BG_ELEVATED = "#16161C"   # sidebar, cards
SURFACE     = "#1C1C24"   # surface sobre card (input, hover)
BORDER      = "#2A2A33"   # bordas finas
TEXT        = "#E6E6EA"
TEXT_MUTED  = "#9D9DA8"
ACCENT      = "#22C55E"   # verde SkinVault
ACCENT_DIM  = "rgba(34,197,94,0.16)"
ACCENT_HOV  = "rgba(34,197,94,0.26)"
STEAM_BLUE  = "#66C0F4"   # azul Steam (conta/sync)
STEAM_DIM   = "rgba(102,192,244,0.14)"
STEAM_HOV   = "rgba(102,192,244,0.24)"
DANGER      = "#EF4444"
DANGER_DIM  = "rgba(239,68,68,0.16)"
DANGER_HOV  = "rgba(239,68,68,0.26)"
WARN        = "#F59E0B"

# Focus ring (navegacao por teclado) — versao clareada da cor base de
# cada familia de botao. Qt6 QSS nao suporta `outline`; o focus e
# sinalizado trocando a cor da borda 1px ja reservada (zero layout
# shift) + bg igual ao hover.
FOCUS_GREEN = "#4ADE80"   # ACCENT clareado
FOCUS_STEAM = "#8FD3F8"   # STEAM_BLUE clareado
FOCUS_RED   = "#F87171"   # DANGER clareado

# Chart overlays (technical analysis)
CHART_YELLOW = "#FACC15"  # support/resistance, spread
CHART_INDIGO = "#818CF8"  # SMA, moving averages

# Warning palette (extraido do regime banner do scanner)
WARN_BG     = "#2A2410"
WARN_BORDER = "#6B5A1A"
WARN_TEXT   = "#D8C267"

# Hover surface (row-hover, item:hover)
SURFACE_HOV = "#23232D"

# Overlay (LockOverlay, modals semi-transparentes)
BG_OVERLAY  = "rgba(14, 14, 18, 0.88)"

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
SIZE_ROW_H      = 32   # altura de linha em QTableWidget (Win11 density)
SIZE_ICON_SM    = 14
SIZE_ICON_MD    = 18
SIZE_ICON_LG    = 22
SIZE_AVATAR     = 72
SIZE_PROGRESS_H = 6
SIZE_SEPARATOR  = 1
SIZE_CHART_H    = 120
SIZE_SIDEBAR_W  = 220
SIZE_HEADER_H   = 40
SIZE_FOOTER_H   = 32

# ── Radius ───────────────────────────────────────────────────
# Consolida o param `radius=...` espalhado em Card/StatCard/etc
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14

# Padding interno de Card por densidade visual.
# LG = default (Card init); MD = cards compactos; SM = chips/strips.
CARD_PAD_SM = (14, 10, 14, 10)
CARD_PAD_MD = (16, 14, 16, 14)
CARD_PAD_LG = (20, 18, 20, 18)

# Alias backward compat com gui.py legado
_BG = BG
_SURFACE = BG_ELEVATED
_TEXT = TEXT
_MUTED = TEXT_MUTED
_GREEN = ACCENT
_RED = DANGER


def _reload_palette(theme: str) -> None:
    """Atualiza as constantes deste modulo a partir de THEMES.
    Chamado por gui.set_theme() para live reload sem restart.
    NOTA: assume execucao na UI thread; nao usar de threads paralelas."""
    from skinvault.gui import THEMES as _T
    pal = _T.get(theme, _T["dark"])
    global BG, BG_ELEVATED, SURFACE, BORDER, TEXT, TEXT_MUTED
    global ACCENT, ACCENT_DIM, ACCENT_HOV, STEAM_BLUE, DANGER
    global _BG, _SURFACE, _TEXT, _MUTED, _GREEN, _RED
    BG = pal["bg"]
    BG_ELEVATED = SURFACE = pal["surface"]
    TEXT = pal["text"]
    TEXT_MUTED = pal["muted"]
    BORDER = "#3A3A44" if theme == "light" else "#2A2A33"
    ACCENT = "#22C55E"
    DANGER = "#EF4444"
    ACCENT_DIM = "rgba(34,197,94,0.16)"
    ACCENT_HOV = "rgba(34,197,94,0.26)"
    STEAM_BLUE = "#66C0F4"
    _BG = BG
    _SURFACE = BG_ELEVATED
    _TEXT = TEXT
    _MUTED = TEXT_MUTED
    _GREEN = ACCENT
    _RED = DANGER


# ── Tipografia ───────────────────────────────────────────────
FONT_FAMILY = '"Segoe UI Variable Display", "Segoe UI", system-ui'
FS_MUTED = "9pt"
FS_BODY = "10pt"
FS_INPUT = "11pt"
FS_TITLE_SM = "13pt"
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
def input_style() -> str:
    return (
        f"QLineEdit, QDoubleSpinBox, QSpinBox"
        f" {{ background: {SURFACE}; border: 1px solid {BORDER};"
        f" border-radius: 8px; padding: 10px 12px; font-size: {FS_INPUT};"
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
        f" border-radius: 8px; padding: 10px 12px; font-size: {FS_INPUT};"
        f" color: {TEXT}; font-family: {FONT_FAMILY}; }}"
        f"QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus"
        f" {{ border: 1px solid {ACCENT}; }}"
    )


def btn_primary(padding: str = "10px 22px", fs: str = FS_INPUT,
                disabled: bool = False) -> str:
    s = (
        f"QPushButton {{ color: #DCFFE6; background: {ACCENT_DIM};"
        f" border: 1px solid {ACCENT}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {ACCENT_HOV}; }}"
        f"QPushButton:focus {{ border: 1px solid {FOCUS_GREEN};"
        f" background: {ACCENT_HOV}; }}"
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
        f" border: 1px solid {STEAM_BLUE}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {STEAM_HOV}; }}"
        f"QPushButton:focus {{ border: 1px solid {FOCUS_STEAM};"
        f" background: {STEAM_HOV}; }}"
    )


def btn_secondary(padding: str = "8px 18px", fs: str = FS_BODY) -> str:
    return (
        f"QPushButton {{ color: {TEXT};"
        " background: rgba(255,255,255,0.06);"
        f" border: 1px solid #3A3A44; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        "QPushButton:hover { background: rgba(255,255,255,0.12); }"
        f"QPushButton:focus {{ border: 1px solid {TEXT_MUTED};"
        " background: rgba(255,255,255,0.12); }"
    )


def btn_danger(padding: str = "8px 18px", fs: str = FS_BODY) -> str:
    return (
        f"QPushButton {{ color: #FFE6E6; background: {DANGER_DIM};"
        f" border: 1px solid {DANGER}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {DANGER_HOV}; }}"
        f"QPushButton:focus {{ border: 1px solid {FOCUS_RED};"
        f" background: {DANGER_HOV}; }}"
    )


def btn_ghost(padding: str = "6px 14px", fs: str = FS_MUTED) -> str:
    """Botao flat sem borda — estilo Win11 toolbar."""
    return (
        f"QPushButton {{ color: {TEXT_MUTED}; background: transparent;"
        f" border: 1px solid transparent; border-radius: 6px;"
        f" padding: {padding}; font-size: {fs};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ color: {TEXT}; background: {SURFACE};"
        f" border: 1px solid {BORDER}; }}"
        f"QPushButton:focus {{ color: {TEXT}; background: {SURFACE};"
        f" border: 1px solid {TEXT_MUTED}; }}"
    )


def table_style() -> str:
    return (
        f"QTableWidget {{ background: {BG_ELEVATED};"
        f" alternate-background-color: #21212B;"
        f" gridline-color: transparent; border: 1px solid {BORDER};"
        f" border-radius: 10px; color: {TEXT}; font-size: {FS_BODY};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QTableWidget::item {{ padding: 8px 12px; }}"
        f"QHeaderView::section {{ background: {BG_ELEVATED};"
        f" color: {TEXT_MUTED}; border: none;"
        f" border-bottom: 1px solid {BORDER};"
        f" padding: 10px 16px 10px 12px;"
        f" font-weight: 600; font-size: {FS_MUTED}; }}"
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


def card_style(radius: int = 10) -> str:
    return (
        f"QWidget#Card {{ background: {BG_ELEVATED};"
        f" border: 1px solid {BORDER};"
        f" border-top: 1px solid #30303A;"
        f" border-radius: {radius}px; }}"
    )


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


def configure_table(table: QTableWidget) -> None:
    """Aplica os defaults visuais Win11 trading-app a uma QTableWidget.

    Consolida ~7 linhas de boilerplate duplicadas em todas as telas com
    tabela (account, history, scanner, trades, watchlist). Ponto unico
    de controle pra futuros polishes (ex: setShowGrid, focus row).

    Configuracoes especificas (sort, header resize modes, selection mode
    custom) continuam inline na tela.
    """
    h = table.verticalHeader()
    h.setVisible(False)
    h.setDefaultSectionSize(SIZE_ROW_H)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(
        QAbstractItemView.SelectionBehavior.SelectRows
    )
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.setStyleSheet(table_style())
