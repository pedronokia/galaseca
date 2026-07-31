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
ACCENT      = "#F1F1F1"   # branco YouTube — accent de MARCA/UI (mono; nao e' lucro)
ACCENT_DIM  = "rgba(241,241,241,0.13)"
ACCENT_HOV  = "rgba(241,241,241,0.22)"
STEAM_BLUE  = "#66C0F4"   # azul Steam (conta/sync)
STEAM_DIM   = "rgba(102,192,244,0.14)"
STEAM_HOV   = "rgba(102,192,244,0.24)"
DANGER      = "#EF4444"
DANGER_DIM  = "rgba(239,68,68,0.16)"
DANGER_HOV  = "rgba(239,68,68,0.26)"
WARN        = "#F59E0B"

# Semantico de mercado/P&L — verde = lucro/alta/bom, DESACOPLADO do
# ACCENT de marca (titanio). Use POSITIVE para "lucro/compra/bom" e
# DANGER para "prejuizo/queda/ruim".
POSITIVE     = "#3FB950"
POSITIVE_DIM = "rgba(63,185,80,0.16)"
POSITIVE_HOV = "rgba(63,185,80,0.26)"

# Focus ring (navegacao por teclado) — versao clareada da cor base de
# cada familia de botao. Qt6 QSS nao suporta `outline`; o focus e
# sinalizado trocando a cor da borda 1px ja reservada (zero layout
# shift) + bg igual ao hover.
FOCUS_GREEN = "#FFFFFF"   # focus ring do ACCENT (branco YouTube)
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
SURFACE_HOV = "#3F3F3F"
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
SIZE_ROW_H      = 32   # altura de linha em QTableWidget (Win11 density)
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
# Consolida o param `radius=...` espalhado em Card/StatCard/etc
RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 16

# Padding interno de Card por densidade visual.
# LG = default (Card init); MD = cards compactos; SM = chips/strips.
CARD_PAD_SM = (14, 10, 14, 10)
CARD_PAD_MD = (16, 14, 16, 14)
CARD_PAD_LG = (20, 18, 20, 18)

def _reload_palette(theme: str) -> None:
    """Atualiza as constantes deste modulo a partir de THEMES.
    Chamado por gui.set_theme() para live reload sem restart.
    NOTA: assume execucao na UI thread; nao usar de threads paralelas."""
    from skinvault.gui import THEMES as _T
    pal = _T.get(theme, _T["dark"])
    global BG, BG_ELEVATED, SURFACE, BORDER, TEXT, TEXT_MUTED
    global ACCENT, ACCENT_DIM, ACCENT_HOV, STEAM_BLUE, DANGER, ROW_ALT
    BG = pal["bg"]
    BG_ELEVATED = pal["surface"]
    SURFACE = pal.get("surface2", pal["surface"])
    ROW_ALT = "#F7F7F7" if theme == "light" else "#1A1A1A"
    TEXT = pal["text"]
    TEXT_MUTED = pal["muted"]
    BORDER = "#3A3A44" if theme == "light" else "#303030"
    ACCENT = "#F1F1F1"
    DANGER = "#EF4444"
    ACCENT_DIM = "rgba(241,241,241,0.13)"
    ACCENT_HOV = "rgba(241,241,241,0.22)"
    STEAM_BLUE = "#66C0F4"


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
        f" border: 1px solid {BORDER}; border-radius: 4px;"
        f" background: {SURFACE}; }}"
        f"QCheckBox::indicator:checked {{ background: {ACCENT};"
        f" border-color: {ACCENT}; }}"
        f"QCheckBox::indicator:focus {{ border: 1px solid {FOCUS_GREEN}; }}"
    )


def table_style() -> str:
    return (
        f"QTableWidget {{ background: {BG_ELEVATED};"
        f" alternate-background-color: {ROW_ALT};"
        f" gridline-color: transparent; border: 1px solid {BORDER};"
        f" border-radius: 10px; color: {TEXT}; font-size: {FS_BODY};"
        f" font-family: {FONT_FAMILY}; }}"
        f"QTableWidget::item {{ padding: 8px 12px; }}"
        # O QHeaderView em si, nao so' a secao: a faixa do cabecalho DEPOIS
        # da ultima coluna cai na paleta do sistema (branca no Windows).
        # So' nao aparecia porque uma coluna esticava e nunca sobrava faixa.
        f"QHeaderView {{ background: {BG_ELEVATED}; border: none; }}"
        f"QHeaderView::section {{ background: {BG_ELEVATED};"
        f" color: {TEXT_MUTED}; border: none;"
        f" border-bottom: 1px solid {BORDER};"
         f" padding: 8px 10px 8px 10px;"
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
    hh = table.horizontalHeader()
    hh.setMinimumSectionSize(120)
