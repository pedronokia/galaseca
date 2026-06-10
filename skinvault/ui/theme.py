"""Paleta + tipografia + helpers de stylesheet (F11).

Substitui as constantes/helpers que viviam em gui.py. Visual: dark
Windows 11 com accent verde SkinVault e azul Steam pra elementos de
sync/conta.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget

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


def btn_primary(padding: str = "10px 22px", fs: str = FS_INPUT,
                disabled: bool = False) -> str:
    s = (
        f"QPushButton {{ color: #DCFFE6; background: {ACCENT_DIM};"
        f" border: 1px solid {ACCENT}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {ACCENT_HOV}; }}"
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
    )


def btn_secondary(padding: str = "8px 18px", fs: str = FS_BODY) -> str:
    return (
        f"QPushButton {{ color: {TEXT};"
        " background: rgba(255,255,255,0.06);"
        f" border: 1px solid #3A3A44; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        "QPushButton:hover { background: rgba(255,255,255,0.12); }"
    )


def btn_danger(padding: str = "8px 18px", fs: str = FS_BODY) -> str:
    return (
        f"QPushButton {{ color: #FFE6E6; background: {DANGER_DIM};"
        f" border: 1px solid {DANGER}; border-radius: 8px;"
        f" padding: {padding}; font-size: {fs}; font-weight: 600;"
        f" font-family: {FONT_FAMILY}; }}"
        f"QPushButton:hover {{ background: {DANGER_HOV}; }}"
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
    )


def table_style() -> str:
    return (
        f"QTableWidget {{ background: {BG_ELEVATED};"
        f" alternate-background-color: {SURFACE};"
        f" gridline-color: transparent; border: 1px solid {BORDER};"
        f" border-radius: 10px; color: {TEXT}; font-size: {FS_BODY};"
        f" font-family: {FONT_FAMILY}; }}"
        # Item padding 8px (era 4px): rows mais respiraveis (~30px de
        # altura), padrao Win11 trading-app. Alt zebra fica mais visivel
        # com mais area por linha.
        f"QTableWidget::item {{ padding: 8px 12px; }}"
        f"QHeaderView::section {{ background: {BG_ELEVATED};"
        f" color: {TEXT_MUTED}; border: none;"
        f" border-bottom: 1px solid {BORDER}; padding: 10px 12px;"
        f" font-weight: 600; font-size: {FS_MUTED}; }}"
        f"QTableWidget::item:hover {{ background: {SURFACE_HOV}; }}"
        f"QTableWidget::item:selected {{ background: {ACCENT_DIM};"
        f" color: {TEXT}; }}"
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
