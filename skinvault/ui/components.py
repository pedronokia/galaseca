"""Componentes reutilizaveis do esqueleto navegacional (F11).

Sidebar + Breadcrumb + Footer + Card + StatCard + SegmentedControl.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from skinvault.ui import theme as t


# ── Card base ────────────────────────────────────────────────
class Card(QFrame):
    """Frame estilizado como card Win11. Use addLayout() ou layout() pra
    inserir conteudo."""

    def __init__(self, parent: QWidget | None = None,
                 padding: tuple[int, int, int, int] = (16, 14, 16, 14),
                 radius: int = 10) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(t.card_style(radius))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*padding)
        lay.setSpacing(10)

    def set_layout(self, layout) -> None:
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
        super().__init__(parent, padding=(16, 12, 16, 12))
        self._label = QLabel(label)
        self._label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        self._value = QLabel(value)
        self._value.setStyleSheet(
            f"color: {accent}; font-size: {t.FS_STAT}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        self.layout().addWidget(self._label)
        self.layout().addWidget(self._value)
        self.setMinimumWidth(140)

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
            f" border: none; text-align: left; padding-left: 14px;"
            f" font-size: {t.FS_BODY}; font-weight: 500;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; background: {t.SURFACE}; }}"
            f"QPushButton:checked {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border-left: 3px solid {t.ACCENT}; padding-left: 11px; }}"
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
        self._label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(self._label, 1)

        self._right = QLabel("")
        self._right.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
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
            lbl.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
                f" font-family: {t.FONT_FAMILY};"
            )
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
        if btn is not None and not btn.isChecked():
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
                           f"color: {t.TEXT_MUTED}; font-size: 22pt;"
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
            f"color: {t.STEAM_BLUE}; font-size: 48pt;"
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
        desc.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(desc)

        cta = QPushButton("Quero ser avisado quando lançar")
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setStyleSheet(t.btn_steam(padding="12px 28px", fs=t.FS_INPUT))
        cta.clicked.connect(self.cta_clicked.emit)
        lay.addWidget(cta, 0, Qt.AlignmentFlag.AlignCenter)
