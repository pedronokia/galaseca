"""Sidebar vertical com items (F11)."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from skinvault.ui import theme as t


class _SidebarItem(QPushButton):
    def __init__(self, icon: str, label: str, checkable: bool = True,
                 parent: QWidget | None = None, rail: bool = False):
        super().__init__(parent)
        self._rail = rail
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if checkable:
            self.setCheckable(True)
            self.setAutoExclusive(True)
        if rail:
            self.setText("")
            self.setFixedWidth(64)
            self.setToolTip(label)
        else:
            self.setText(label)
        self.setMinimumHeight(40)
        self.setStyleSheet(self._style_idle())
        from skinvault.ui.components import LineIcon
        self._icon = LineIcon(icon, t.TEXT_MUTED, self)
        self._icon.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        if checkable:
            self.toggled.connect(self._on_toggled)

    def _style_idle(self) -> str:
        if self._rail:
            return (
                f"QPushButton {{ background: transparent; border: none;"
                f" border-radius: 10px; }}"
                f"QPushButton:hover {{ background: {t.ACCENT_DIM}; }}"
                f"QPushButton:checked {{ background: {t.ACCENT_DIM}; }}"
                f"QPushButton:focus {{ background: {t.ACCENT_DIM}; }}"
            )
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid transparent; text-align: left;"
            f" padding-left: 42px; border-radius: 8px;"
            f" margin: 1px 6px;"
            f" font-size: {t.FS_BODY}; font-weight: 500;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border: 1px solid transparent; }}"
            f"QPushButton:checked {{ color: {t.TEXT}; background: {t.ACCENT_DIM};"
            f" font-weight: 700;"
            f" border: 1px solid transparent; }}"
            f"QPushButton:focus {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border: 1px solid {t.TEXT_MUTED}; }}"
            f"QPushButton:checked:focus {{ color: {t.TEXT};"
            f" background: {t.ACCENT_DIM};"
            f" border: 1px solid {t.FOCUS_GREEN}; }}"
        )

    def _on_toggled(self, checked: bool) -> None:
        self._icon.set_color(t.ACCENT if checked else t.TEXT_MUTED)

    def restyle(self) -> None:
        """Reaplica QSS + cor do icone apos troca de tema/accent."""
        self.setStyleSheet(self._style_idle())
        self._icon.set_color(t.ACCENT if self.isChecked() else t.TEXT_MUTED)

    def resizeEvent(self, evt) -> None:
        super().resizeEvent(evt)
        y = (self.height() - self._icon.height()) // 2
        if self._rail:
            x = (self.width() - self._icon.width()) // 2
        else:
            x = 14
        self._icon.move(x, y)

    def enterEvent(self, evt) -> None:
        if not self.isChecked():
            self._icon.set_color(t.TEXT)
        super().enterEvent(evt)

    def leaveEvent(self, evt) -> None:
        if not self.isChecked():
            self._icon.set_color(t.TEXT_MUTED)
        super().leaveEvent(evt)


class Sidebar(QWidget):
    item_selected = pyqtSignal(str)

    def __init__(self, width: int = 220, parent: QWidget | None = None,
                 rail: bool = False) -> None:
        super().__init__(parent)
        self._rail = rail
        self.setFixedWidth(width)
        self.setObjectName("Sidebar")
        self.setStyleSheet(f"QWidget#Sidebar {{ background: {t.BG_ELEVATED}; }}")
        self._items: dict[str, _SidebarItem] = {}
        self._lay = QVBoxLayout(self)
        if rail:
            self._lay.setContentsMargins(0, 16, 0, 16)
            self._lay.setSpacing(4)
            self._lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self._lay.setContentsMargins(8, 16, 8, 16)
            self._lay.setSpacing(2)

        if rail:
            brand = QLabel("SV")
            brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
            brand.setStyleSheet(
                f"color: {t.TEXT}; font-size: 12pt; font-weight: 700;"
                f" font-family: {t.FONT_FAMILY}; padding: 6px 0 18px 0;"
            )
        else:
            brand = QLabel("SkinVault")
            brand.setStyleSheet(
                f"color: {t.TEXT}; font-size: 14pt; font-weight: 600;"
                f" font-family: {t.FONT_FAMILY}; padding: 6px 12px 18px 14px;"
            )
        self._lay.addWidget(brand)

    def add_item(self, key: str, icon: str, label: str) -> None:
        btn = _SidebarItem(icon, label, parent=self, rail=self._rail)
        btn.clicked.connect(lambda: self.item_selected.emit(key))
        self._items[key] = btn
        self._lay.addWidget(btn)

    def add_action(self, icon: str, label: str,
                   callback: Callable[[], None]) -> _SidebarItem:
        btn = _SidebarItem(icon, label, checkable=False, parent=self,
                           rail=self._rail)
        btn.clicked.connect(lambda: callback())
        self._lay.addWidget(btn)
        return btn

    def add_stretch(self) -> None:
        self._lay.addStretch(1)

    def add_widget(self, w: QWidget) -> None:
        self._lay.addWidget(w)

    def add_session_chip(self) -> None:
        self._chip = QWidget()
        self._chip.setObjectName("SessionChip")
        self._chip.setCursor(Qt.CursorShape.PointingHandCursor)
        if self._rail:
            self._chip.setFixedSize(32, 32)
            self._chip.setStyleSheet(
                f"QWidget#SessionChip {{ background: {t.SURFACE};"
                f" border: 1px solid {t.BORDER}; border-radius: 16px; }}"
                f"QWidget#SessionChip:hover {{"
                f" border: 1px solid {t.TEXT_MUTED}; }}"
            )
            lay = QHBoxLayout(self._chip)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._chip_dot = QWidget()
            self._chip_dot.setFixedSize(8, 8)
            self._chip_dot.setStyleSheet(
                f"background: {t.ACCENT}; border-radius: 4px;"
            )
            lay.addWidget(self._chip_dot)
            self._chip.setVisible(False)
            self._lay.addWidget(self._chip, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            self._chip.setStyleSheet(
                f"QWidget#SessionChip {{ background: {t.SURFACE};"
                f" border: 1px solid {t.BORDER}; border-radius: 8px; }}"
                f"QWidget#SessionChip:hover {{"
                f" border: 1px solid {t.TEXT_MUTED}; }}"
            )
            lay = QHBoxLayout(self._chip)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.setSpacing(8)
            self._chip_dot = QWidget()
            self._chip_dot.setFixedSize(8, 8)
            self._chip_dot.setStyleSheet(
                f"background: {t.ACCENT}; border-radius: 4px;"
            )
            lay.addWidget(self._chip_dot)
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(0)
            self._chip_name = QLabel("—")
            self._chip_name.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_MUTED}; font-weight: 600;"
                f" font-family: {t.FONT_FAMILY};"
            )
            self._chip_sub = QLabel("Steam")
            self._chip_sub.setStyleSheet(t.label_caption())
            col.addWidget(self._chip_name)
            col.addWidget(self._chip_sub)
            lay.addLayout(col, 1)
            self._chip.setVisible(False)
            self._lay.addWidget(self._chip)
        self._chip.mousePressEvent = (
            lambda _evt: self.item_selected.emit("account")
        )

    def set_session(self, name: str, steamid: str) -> None:
        chip = getattr(self, "_chip", None)
        if chip is None:
            return
        if not name and not steamid:
            chip.setVisible(False)
            return
        if self._rail:
            tooltip = name or steamid
            if steamid:
                tooltip += f" (SteamID: {steamid})"
            chip.setToolTip(tooltip)
            chip.setVisible(True)
        else:
            if name:
                display = name
            elif len(steamid) >= 12:
                display = f"{steamid[:8]}…{steamid[-4:]}"
            else:
                display = steamid
            self._chip_name.setText(display)
            chip.setToolTip(f"SteamID: {steamid}" if steamid else "")
            chip.setVisible(True)

    def select(self, key: str) -> None:
        btn = self._items.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def restyle(self) -> None:
        """Reaplica QSS dos itens e do dot de sessao (tokens de accent
        podem ter mudado ao vivo). Chamado por gui apos trocar
        tema/cor de destaque."""
        for btn in self._items.values():
            btn.restyle()
        dot = getattr(self, "_chip_dot", None)
        if dot is not None:
            dot.setStyleSheet(
                f"background: {t.ACCENT}; border-radius: 4px;"
            )
