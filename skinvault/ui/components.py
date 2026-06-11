"""Componentes reutilizaveis do esqueleto navegacional (F11).

Sidebar + Breadcrumb + Footer + Card + StatCard + SegmentedControl.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QFont, QFontMetrics, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def fade_in(widget: QWidget, duration_ms: int = 150) -> None:
    """Fade-in suave de um widget via QGraphicsOpacityEffect.

    O effect e removido ao final: render com effect tem custo (todo
    paint passa por buffer offscreen — pesa em telas com tabela grande).
    A remocao e deferida com singleShot(0) porque setGraphicsEffect(None)
    deleta o effect, e a anim e filha dele — deletar dentro da emissao
    de finished derrubaria o objeto no meio do proprio sinal.
    """
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", eff)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _cleanup() -> None:
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            pass  # objeto C++ deletado, ignorar

    anim.finished.connect(lambda: QTimer.singleShot(0, _cleanup))
    anim.start()


class EmptyState(QWidget):
    """Hero centralizado pra empty states. Icone + headline + sub + CTA opcional.

    Uso:
        es = EmptyState("◇", "Nenhum item ainda",
                         "Adicione manualmente ou sincronize.",
                         cta_label="+ Adicionar", on_cta=callback)
    """

    cta_clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, subtitle: str = "",
                 cta_label: str | None = None,
                 on_cta=None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        ic = QLabel(icon)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_ICON_HERO};"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(ic)

        ttl = QLabel(title)
        ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ttl.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(ttl)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            sub.setStyleSheet(t.label_body_muted())
            lay.addWidget(sub)

        if cta_label:
            cta = QPushButton(cta_label)
            cta.setCursor(Qt.CursorShape.PointingHandCursor)
            cta.setStyleSheet(t.btn_primary(padding="12px 28px", fs=t.FS_INPUT))
            cta.clicked.connect(self.cta_clicked.emit)
            if on_cta is not None:
                self.cta_clicked.connect(on_cta)
            lay.addWidget(cta, 0, Qt.AlignmentFlag.AlignCenter)


class _ElideLabel(QLabel):
    """QLabel que aplica elide (…) automaticamente quando o texto
    nao cabe na largura disponivel. Mantem altura fixa de uma linha."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setText(text)
        self.setWordWrap(False)

    def setText(self, text: str) -> None:
        self._full = text or ""
        self._apply_elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._apply_elide()

    def _apply_elide(self) -> None:
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(
            self._full, Qt.TextElideMode.ElideRight,
            max(self.width() - 2, 0),
        )
        # Usa o setText do super pra nao recursar
        QLabel.setText(self, elided)

from skinvault.ui import theme as t


# ── Card base ────────────────────────────────────────────────
class Card(QFrame):
    """Frame estilizado como card Win11. Use addLayout() ou layout() pra
    inserir conteudo."""

    def __init__(self, parent: QWidget | None = None,
                 padding: tuple[int, int, int, int] = t.CARD_PAD_LG,
                 radius: int = 14) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(t.card_style(radius))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*padding)
        lay.setSpacing(10)

    def set_layout(self, layout: QLayout) -> None:
        # Substitui o layout default
        old = self.layout()
        if old is not None:
            QWidget().setLayout(old)
        self.setLayout(layout)


class StatCard(Card):
    """Card pequeno: label muted em cima, valor grande embaixo."""

    def __init__(self, label: str, value: str = "—",
                 accent: str = t.TEXT,
                 parent: QWidget | None = None) -> None:
        # Padding (20, 16) e ligeiramente mais compacto que CARD_PAD_LG (20, 18)
        # — StatCard mostra apenas label + numero, nao precisa respiro extra.
        super().__init__(parent, padding=(20, 16, 20, 16), radius=t.RADIUS_LG)
        self.layout().setSpacing(4)
        self._label = QLabel(label)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(t.label_caption())
        self._value = QLabel(value)
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value.setStyleSheet(
            f"color: {accent}; font-size: {t.FS_STAT}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        self.layout().addWidget(self._label)
        self.layout().addWidget(self._value)
        self.setMinimumWidth(120)

    def set_value(self, value: str, accent: str | None = None) -> None:
        self._value.setText(value)
        if accent:
            self._value.setStyleSheet(
                f"color: {accent}; font-size: {t.FS_STAT}; font-weight: 600;"
                f" font-family: {t.FONT_FAMILY};"
            )


# ── Sidebar ──────────────────────────────────────────────────
class _SidebarItem(QPushButton):
    def __init__(self, icon: str, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setText(f"  {icon}    {label}")
        self.setStyleSheet(self._style_idle())
        self.setMinimumHeight(40)
        self.toggled.connect(self._on_toggled)

    def _style_idle(self) -> str:
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: none; text-align: left; padding-left: 11px;"
            f" border-left: 3px solid transparent;"
            f" font-size: {t.FS_BODY}; font-weight: 500;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; background: {t.SURFACE}; }}"
            f"QPushButton:checked {{ color: {t.ACCENT}; background: {t.SURFACE};"
            f" font-weight: 700;"
            f" border-left: 3px solid {t.ACCENT}; }}"
            f"QPushButton:focus {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border-left: 3px solid {t.TEXT_MUTED}; }}"
            f"QPushButton:checked:focus {{ color: {t.ACCENT};"
            f" border-left: 3px solid {t.FOCUS_GREEN}; }}"
        )

    def _on_toggled(self, checked: bool) -> None:
        # Estilo aplicado via :checked do qss
        pass


class Sidebar(QWidget):
    """Sidebar vertical com items. Emite item_selected(key)."""

    item_selected = pyqtSignal(str)

    def __init__(self, width: int = 220, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(width)
        self.setStyleSheet(f"background: {t.BG_ELEVATED};")
        self._items: dict[str, _SidebarItem] = {}
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(8, 16, 8, 16)
        self._lay.setSpacing(2)

        # Branding minimal no topo
        brand = QLabel("SkinVault")
        brand.setStyleSheet(
            f"color: {t.TEXT}; font-size: 14pt; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY}; padding: 6px 12px 18px 14px;"
        )
        self._lay.addWidget(brand)

    def add_item(self, key: str, icon: str, label: str) -> None:
        btn = _SidebarItem(icon, label, self)
        btn.clicked.connect(lambda: self.item_selected.emit(key))
        self._items[key] = btn
        self._lay.addWidget(btn)

    def add_stretch(self) -> None:
        self._lay.addStretch(1)

    def add_widget(self, w: QWidget) -> None:
        self._lay.addWidget(w)

    def select(self, key: str) -> None:
        btn = self._items.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)


# ── Breadcrumb ───────────────────────────────────────────────
class Breadcrumb(QWidget):
    """Barra de breadcrumb 40px no topo do conteudo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet(
            f"background: {t.BG}; border-bottom: 1px solid {t.BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        self._label = QLabel("")
        self._label.setStyleSheet(t.label_body_muted())
        lay.addWidget(self._label, 1)

        self._right = QLabel("")
        self._right.setStyleSheet(t.label_caption())
        lay.addWidget(self._right)

    def set_path(self, *parts: str) -> None:
        body = "  ›  ".join(p for p in parts if p)
        self._label.setText(body)

    def set_right(self, text: str) -> None:
        self._right.setText(text)


# ── Footer ───────────────────────────────────────────────────
class Footer(QWidget):
    """Barra de status no rodape."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            f"background: {t.BG_ELEVATED}; border-top: 1px solid {t.BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        self._left = QLabel("")
        self._right = QLabel("")
        for lbl in (self._left, self._right):
            lbl.setStyleSheet(t.label_caption())
        lay.addWidget(self._left, 1)
        lay.addWidget(self._right)

    def set_left(self, text: str) -> None:
        self._left.setText(text)

    def set_right(self, text: str) -> None:
        self._right.setText(text)


# ── SegmentedControl ─────────────────────────────────────────
class SegmentedControl(QWidget):
    """Tabs estilo pill (Win11 segmented). Emite segment_changed(key)."""

    segment_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: dict[str, QPushButton] = {}
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)

    def add(self, key: str, label: str) -> None:
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._btn_style())
        btn.setMinimumHeight(34)
        btn.clicked.connect(lambda: self.segment_changed.emit(key))
        self._items[key] = btn
        self._lay.addWidget(btn)
        if len(self._items) == 1:
            btn.setChecked(True)

    def select(self, key: str) -> None:
        btn = self._items.get(key)
        if btn is None:
            return
        if not btn.isChecked():
            btn.setChecked(True)
            self.segment_changed.emit(key)

    def _btn_style(self) -> str:
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid {t.BORDER}; border-radius: 8px;"
            f" padding: 6px 18px; font-size: {t.FS_BODY}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; }}"
            f"QPushButton:checked {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border: 1px solid {t.ACCENT}; }}"
            f"QPushButton:focus {{ color: {t.TEXT};"
            f" border: 1px solid {t.TEXT_MUTED}; }}"
            f"QPushButton:checked:focus {{ border: 1px solid {t.FOCUS_GREEN}; }}"
        )


# ── Avatar widget ────────────────────────────────────────────
class Avatar(QLabel):
    """QLabel circular pra avatar Steam. Aceita bytes ou path."""

    def __init__(self, size: int = 72, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self.setStyleSheet(
            f"background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: {size // 2}px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Placeholder
        self.setText("?")
        self.setStyleSheet(self.styleSheet() +
                           f"color: {t.TEXT_MUTED}; font-size: {t.FS_ICON_SM};"
                           f" font-family: {t.FONT_FAMILY};")

    def set_image(self, data: bytes | str | None) -> None:
        if not data:
            return
        pix = QPixmap()
        if isinstance(data, bytes):
            pix.loadFromData(data)
        else:
            pix.load(str(data))
        if pix.isNull():
            return
        scaled = pix.scaled(
            self._size, self._size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Mask circular: usar setStyleSheet com border-radius e setPixmap
        self.setText("")
        self.setPixmap(scaled)
        self.setStyleSheet(
            f"background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: {self._size // 2}px;"
        )


# ── Lock overlay ─────────────────────────────────────────────
class LockOverlay(QWidget):
    """Overlay semi-transparente com mensagem de paywall (Tela 3)."""

    cta_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background: rgba(14,14,18,0.88);")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        icon = QLabel("🔒")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {t.STEAM_BLUE}; font-size: {t.FS_ICON_LG};"
        )
        lay.addWidget(icon)

        title = QLabel("Scanner Premium — em breve")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(title)

        desc = QLabel(
            "Scanner de skins, caixas e adesivos para identificar\n"
            "oportunidades de compra antes da valorização."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(t.label_body_muted())
        lay.addWidget(desc)

        cta = QPushButton("Quero ser avisado quando lançar")
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setStyleSheet(t.btn_steam(padding="12px 28px", fs=t.FS_INPUT))
        cta.clicked.connect(self.cta_clicked.emit)
        lay.addWidget(cta, 0, Qt.AlignmentFlag.AlignCenter)


# ── ActivityFeed ─────────────────────────────────────────────
def _activity_color(name: str) -> str:
    """Mapeia COLOR_* da activity.py para constante do theme."""
    return {
        "green": t.ACCENT,
        "red": t.DANGER,
        "accent": t.STEAM_BLUE,
        "muted": t.TEXT_MUTED,
    }.get(name, t.TEXT_MUTED)


class _ActivityRow(QWidget):
    """Uma linha do feed: bolinha colorida + (titulo/subtitulo) + tempo."""

    def __init__(self, event: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from skinvault import activity as _act

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        color = _activity_color(event.get("color", "muted"))

        icon = QLabel(event.get("icon", "·"))
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {color}; background: {t.SURFACE};"
            f" border-radius: 14px; font-size: 12pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(1)
        title = _ElideLabel(event.get("title", ""))
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_BODY};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        title.setToolTip(event.get("title", ""))
        center.addWidget(title)

        sub_color = color if event.get("color") in ("green", "red") else t.TEXT_MUTED
        sub = _ElideLabel(event.get("subtitle", ""))
        sub.setStyleSheet(
            f"color: {sub_color}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        center.addWidget(sub)
        lay.addLayout(center, 1)
        # Altura fixa garante linhas uniformes mesmo com titulos longos
        self.setFixedHeight(44)

        ts_label = QLabel(_act.format_relative_ts(event.get("ts", 0)))
        ts_label.setStyleSheet(t.label_caption())
        lay.addWidget(ts_label, 0, Qt.AlignmentFlag.AlignTop)


class ActivityFeed(Card):
    """Lista vertical estilo "Recent Activity" do Faceit. Agrega trades,
    alertas e snapshots de ranking. Use set_events() pra preencher.

    Tem chips no topo pra filtrar por categoria: tudo/vendas/compras/alertas.
    """

    # Filtros por icone do evento
    _FILTERS = [
        ("all", "Tudo", None),
        ("sell", "↑ Vendas", "↑"),
        ("buy", "↓ Compras", "↓"),
        ("alert", "★ Alertas", "★"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=t.CARD_PAD_MD)
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)

        self._all_events: list[dict] = []
        self._filter: str = "all"
        self._chip_buttons: dict[str, QPushButton] = {}

        title = QLabel("Atividade recente")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        self.layout().addWidget(title)

        chips_row = QHBoxLayout()
        chips_row.setContentsMargins(0, 2, 0, 4)
        chips_row.setSpacing(4)
        for key, label, _icon in self._FILTERS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setStyleSheet(self._chip_style())
            btn.clicked.connect(lambda _checked, k=key: self._set_filter(k))
            if key == "all":
                btn.setChecked(True)
            self._chip_buttons[key] = btn
            chips_row.addWidget(btn)
        chips_row.addStretch(1)
        self.layout().addLayout(chips_row)

        self._list_lay = QVBoxLayout()
        self._list_lay.setContentsMargins(0, 4, 0, 0)
        self._list_lay.setSpacing(10)
        self.layout().addLayout(self._list_lay)
        self.layout().addStretch(1)

        self._empty = QLabel("Nenhuma atividade ainda.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; padding: 16px 0;"
        )
        self._list_lay.addWidget(self._empty)

    def _chip_style(self) -> str:
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid {t.BORDER}; border-radius: 10px;"
            f" padding: 3px 9px; font-size: {t.FS_MUTED}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; }}"
            f"QPushButton:checked {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border: 1px solid {t.ACCENT}; }}"
            f"QPushButton:focus {{ color: {t.TEXT};"
            f" border: 1px solid {t.TEXT_MUTED}; }}"
            f"QPushButton:checked:focus {{ border: 1px solid {t.FOCUS_GREEN}; }}"
        )

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._render()

    def _filtered_events(self) -> list[dict]:
        if self._filter == "all":
            return self._all_events
        wanted_icon = dict((k, ic) for k, _, ic in self._FILTERS)[self._filter]
        return [e for e in self._all_events if e.get("icon") == wanted_icon]

    def _render(self) -> None:
        # Limpa lista atual
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        events = self._filtered_events()
        if not events:
            if self._filter != "all":
                self._empty.setText("Sem eventos nesse filtro.")
            else:
                self._empty.setText("Nenhuma atividade ainda.")
            self._empty.show()
            self._list_lay.addWidget(self._empty)
            return
        self._empty.hide()
        for ev in events:
            self._list_lay.addWidget(_ActivityRow(ev))

    def set_events(self, events: list[dict]) -> None:
        self._all_events = list(events)
        self._render()


# ── RecentMatchesStrip ────────────────────────────────────────
def _streak_summary(trades: list[dict]) -> tuple[str, str] | None:
    """Calcula a sequencia atual de vitorias/derrotas a partir do
    trade mais recente. Trades com pnl == 0 quebram a sequencia.

    Retorna (texto, cor) ou None se nao houver sequencia.
    """
    if not trades:
        return None
    # Trades chegam mais recentes primeiro
    first_pnl = trades[0].get("pnl", 0) or 0
    if first_pnl == 0:
        return None
    is_win = first_pnl > 0
    count = 0
    for t_ in trades:
        p = t_.get("pnl", 0) or 0
        if (p > 0) == is_win and p != 0:
            count += 1
        else:
            break
    if count < 2:
        return None
    label = f"{count} vitorias em sequencia" if is_win else f"{count} derrotas em sequencia"
    return (label, t.ACCENT if is_win else t.DANGER)


class _MatchChip(QLabel):
    """Chip pequeno W/L pra strip de Recent Matches."""

    def __init__(self, trade: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pnl = trade.get("pnl", 0) or 0
        if pnl > 0:
            text, color = "V", t.ACCENT
        elif pnl < 0:
            text, color = "D", t.DANGER
        else:
            text, color = "—", t.TEXT_MUTED
        self.setText(text)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {color}; background: {t.SURFACE};"
            f" border: 1px solid {color}; border-radius: 6px;"
            f" font-size: {t.FS_BODY}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        from skinvault.localization import localize_name as _ln
        name = _ln(trade.get("name") or "")
        ts = trade.get("sell_ts") or trade.get("buy_ts") or 0
        import time as _time
        ts_str = _time.strftime("%d/%m/%Y", _time.localtime(ts)) if ts else ""
        self.setToolTip(
            f"{ts_str} • {name}\nP&L R$ {pnl:+.2f}"
        )


class RecentMatchesStrip(Card):
    """Strip horizontal estilo "Recent Matches" do Faceit: chips W/L
    coloridos pros ultimos trades + streak indicator a direita."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=t.CARD_PAD_SM)

        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        title = QLabel("Ultimos resultados")
        title.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            f" letter-spacing: 1px;"
        )
        outer.addWidget(title)

        self._chip_lay = QHBoxLayout()
        self._chip_lay.setContentsMargins(0, 0, 0, 0)
        self._chip_lay.setSpacing(4)
        outer.addLayout(self._chip_lay)

        outer.addStretch(1)

        self._streak = QLabel("")
        self._streak.setStyleSheet(t.label_caption_bold())
        outer.addWidget(self._streak)

        self._empty = QLabel("Nenhum trade fechado ainda.")
        self._empty.setStyleSheet(t.label_caption())
        self._chip_lay.addWidget(self._empty)

        self.layout().addLayout(outer)

    def set_trades(self, trades: list[dict], limit: int = 15) -> None:
        """trades: lista ordenada do mais recente pro mais antigo."""
        # Limpa
        while self._chip_lay.count():
            item = self._chip_lay.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        recent = trades[:limit]
        if not recent:
            self._empty.show()
            self._chip_lay.addWidget(self._empty)
            self._streak.setText("")
            return
        self._empty.hide()
        for tr in recent:
            self._chip_lay.addWidget(_MatchChip(tr))
        streak = _streak_summary(recent)
        if streak:
            text, color = streak
            self._streak.setText(text)
            self._streak.setStyleSheet(
                f"color: {color}; font-size: {t.FS_MUTED};"
                f" font-weight: 700; font-family: {t.FONT_FAMILY};"
            )
        else:
            self._streak.setText("")


# ── Toast ────────────────────────────────────────────────────
class Toast(QWidget):
    """Notificacao nao-bloqueante, top-right do parent, auto-dismiss.

    Variants: 'info' (accent), 'success' (accent), 'warning' (warn),
    'error' (danger). Auto-stack quando ha multiplos visiveis.
    Uso: Toast.show_toast(parent, "Sincronizado.", "success").
    """

    _VARIANT_BORDER = {
        "info":    "ACCENT",
        "success": "ACCENT",
        "warning": "WARN",
        "error":   "DANGER",
    }
    _stack: list["Toast"] = []

    def __init__(self, parent: QWidget, text: str,
                 variant: str = "info",
                 duration_ms: int = 3000) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setObjectName("Toast")
        border_attr = self._VARIANT_BORDER.get(variant, "ACCENT")
        border_color = getattr(t, border_attr, t.ACCENT)
        self.setStyleSheet(
            f"QWidget#Toast {{ background: {t.SURFACE};"
            f" border: 1px solid {border_color};"
            f" border-left: 4px solid {border_color};"
            f" border-radius: {t.RADIUS_MD}px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        lay.setSpacing(t.SPACE_MD)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY}; background: transparent;"
            f" border: none;"
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.adjustSize()
        # Min/max width pra nao ficar gigante
        self.setMinimumWidth(240)
        self.setMaximumWidth(420)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._duration_ms = duration_ms
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._on_faded_out)

    @classmethod
    def show_toast(cls, parent: QWidget, text: str,
                   variant: str = "info",
                   duration_ms: int = 3000) -> "Toast":
        """Cria, posiciona e exibe. Auto-stack se ja houver toasts."""
        target = parent.window() if parent is not None else None
        if target is None:
            target = parent
        toast = cls(target, text, variant, duration_ms)
        cls._stack.append(toast)
        toast._reposition()
        toast.show()
        # Slide-in sutil (8px de cima) em paralelo com o fade
        end = toast.pos()
        toast.move(end.x(), end.y() - 8)
        toast._slide = QPropertyAnimation(toast, b"pos", toast)
        toast._slide.setDuration(200)
        toast._slide.setStartValue(toast.pos())
        toast._slide.setEndValue(end)
        toast._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        toast._slide.start()
        toast._fade_in.start()
        QTimer.singleShot(duration_ms, toast._begin_dismiss)
        return toast

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = t.SPACE_LG
        # Empilha verticalmente: cada toast 6px abaixo do anterior visivel
        y = margin
        for tst in self._stack:
            if tst is self:
                break
            try:
                if tst.isVisible():
                    y = tst.y() + tst.height() + t.SPACE_SM
            except RuntimeError:
                pass  # objeto C++ deletado, ignorar
        x = max(margin, parent.width() - self.width() - margin)
        self.move(x, y)

    def _begin_dismiss(self) -> None:
        if not self.isVisible():
            return
        self._fade_out.start()

    def _on_faded_out(self) -> None:
        try:
            self._stack.remove(self)
        except ValueError:
            pass
        self.hide()
        self.deleteLater()
        # Reposiciona toasts remanescentes
        for tst in list(self._stack):
            try:
                if tst.isVisible():
                    tst._reposition()
            except RuntimeError:
                pass  # objeto C++ deletado, ignorar


# ── LoadingState ─────────────────────────────────────────────
class LoadingState(QWidget):
    """Spinner simples + label. Use como placeholder durante async."""

    _FRAMES = ["◴", "◷", "◶", "◵"]

    def __init__(self, label: str = "Carregando…",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(t.SPACE_SM)

        self._spin = QLabel(self._FRAMES[0])
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setStyleSheet(
            f"color: {t.ACCENT}; font-size: 28pt;"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(self._spin)

        self._lbl = QLabel(label)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet(t.label_caption())
        lay.addWidget(self._lbl)

        self._idx = 0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self._spin.setText(self._FRAMES[self._idx])

    def set_label(self, text: str) -> None:
        self._lbl.setText(text)

    def hideEvent(self, ev) -> None:
        self._timer.stop()
        super().hideEvent(ev)

    def showEvent(self, ev) -> None:
        if not self._timer.isActive():
            self._timer.start()
        # Spinner surge com fade (crossfade barato, sem tocar as telas).
        # Guard: so anima dentro de janela visivel — mantem _screenshot.py
        # e tests (que nunca dao show() na janela) deterministicos.
        if self.window() is not self and self.window().isVisible():
            fade_in(self, duration_ms=150)
        super().showEvent(ev)


# ── SectionHeader ────────────────────────────────────────────
class SectionHeader(QWidget):
    """Cabecalho de secao: titulo + subtitulo opcional + acao trailing."""

    def __init__(self, title: str, subtitle: str = "",
                 action: QPushButton | None = None,
                 title_fs: str = t.FS_TITLE_SM,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(t.SPACE_MD)

        stack = QVBoxLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(t.SPACE_XS // 2)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {title_fs};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        stack.addWidget(self._title)

        self._sub = QLabel(subtitle)
        self._sub.setStyleSheet(t.label_caption())
        self._sub.setVisible(bool(subtitle))
        stack.addWidget(self._sub)

        outer.addLayout(stack, 1)

        self._action: QPushButton | None = None
        if action is not None:
            self.set_action(action)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._sub.setText(text)
        self._sub.setVisible(bool(text))

    def set_action(self, btn: QPushButton) -> None:
        if self._action is not None:
            self._action.setParent(None)
        self._action = btn
        self.layout().addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)


# ── Toolbar ──────────────────────────────────────────────────
class Toolbar(QWidget):
    """Barra horizontal: widgets a esquerda, spacer, widgets a direita."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(t.SPACE_SM)
        self._spacer_idx = 0
        self._lay.addStretch(1)
        self._spacer_idx = 0  # tudo antes do stretch = "left"

    def add_left(self, w: QWidget) -> None:
        # Insere antes do stretch
        self._lay.insertWidget(self._spacer_idx, w)
        self._spacer_idx += 1

    def add_right(self, w: QWidget) -> None:
        self._lay.addWidget(w)

    def add_left_layout(self, layout: QLayout) -> None:
        self._lay.insertLayout(self._spacer_idx, layout)
        self._spacer_idx += 1


# ── FormRow ──────────────────────────────────────────────────
class FormRow(QWidget):
    """Label muted em cima, field embaixo. Espacamento consistente.

    Se tooltip for fornecido, aplica em label + field (acessibilidade).
    """

    def __init__(self, label: str, field: QWidget,
                 tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_XS)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(t.label_caption_bold())
        if tooltip:
            self._lbl.setToolTip(tooltip)
            field.setToolTip(tooltip)
        lay.addWidget(self._lbl)
        lay.addWidget(field)
        self._field = field

    def field(self) -> QWidget:
        return self._field

    def set_label(self, text: str) -> None:
        self._lbl.setText(text)
