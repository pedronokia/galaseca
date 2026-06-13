"""Command palette (Ctrl+K) — navegacao e acoes globais com fuzzy match.

Frente V do polish de UI. Dois componentes:
  - palette_rank(): funcao PURA de ranking fuzzy (sem GUI, testavel direto).
  - CommandPalette(QDialog): overlay frameless estilo VS Code / Raycast.

Um "comando" e' um dict: {label, category, icon, run} onde `run` e' um
callable sem argumentos e `icon` e' um nome de LineIcon (components).
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault.ui import theme as t
from skinvault.ui.components import LineIcon


# ── ranking fuzzy (puro) ──────────────────────────────────────
def _fuzzy_score(query: str, text: str) -> int | None:
    """Score de match de `query` em `text` (ambos lowercase).

    Retorna None se `query` nem aparece como subsequencia. Maior score =
    melhor: substring no inicio (prefixo) > substring contigua > subse-
    quencia espalhada. Match mais cedo e com menos lacunas pontua mais.
    """
    if not query:
        return 0
    pos = text.find(query)
    if pos != -1:
        # contiguo: quanto mais cedo, melhor; prefixo ganha bonus forte
        score = 1000 - pos
        if pos == 0:
            score += 500
        return score
    # subsequencia espalhada (cada char de query na ordem)
    first: int | None = None
    last = -1
    gaps = 0
    start = 0
    for ch in query:
        found = text.find(ch, start)
        if found == -1:
            return None
        if first is None:
            first = found
        if last != -1 and found > last + 1:
            gaps += 1
        last = found
        start = found + 1
    return 200 - (first or 0) - gaps * 5


def palette_rank(query: str, items: list[dict]) -> list[dict]:
    """Filtra e ordena `items` por match fuzzy no campo 'label'.

    - query vazia: devolve todos na ordem original.
    - case-insensitive.
    - sem match: item fica de fora.
    - empate de score: mantem a ordem original (estavel).
    """
    q = (query or "").strip().lower()
    if not q:
        return list(items)
    scored: list[tuple[int, int, dict]] = []
    for idx, item in enumerate(items):
        label = (item.get("label") or "").lower()
        score = _fuzzy_score(q, label)
        if score is not None:
            scored.append((score, idx, item))
    scored.sort(key=lambda tup: (-tup[0], tup[1]))
    return [item for _, _, item in scored]


# ── linha de resultado ────────────────────────────────────────
class _ResultRow(QWidget):
    """Linha da lista: LineIcon + label + categoria muted."""

    def __init__(self, command: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        icon = LineIcon(command.get("icon", ""), t.TEXT_MUTED, self)
        lay.addWidget(icon)
        label = QLabel(command.get("label", ""))
        label.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(label, 1)
        cat = QLabel(command.get("category", ""))
        cat.setStyleSheet(t.label_caption())
        lay.addWidget(cat)


# ── dialog ────────────────────────────────────────────────────
class CommandPalette(QDialog):
    """Overlay Ctrl+K: digita pra filtrar, Enter executa, ↑↓ navega.

    `commands`: lista de dicts {label, category, icon, run}.
    """

    def __init__(self, commands: list[dict],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commands = list(commands)
        self._filtered: list[dict] = list(commands)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(560)
        self._build()
        self._refilter("")

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)  # respiro pra sombra

        card = QFrame(self)
        card.setObjectName("PaletteCard")
        card.setStyleSheet(
            f"QFrame#PaletteCard {{ background: {t.BG_ELEVATED};"
            f" border: 1px solid {t.BORDER}; border-radius: 12px; }}"
        )
        # Sombra: excecao consciente a regra anti-shadow (modal unico, nao
        # recorrente) — vide ROADMAP_UI.md Frente V.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(12, 12, 12, 12)
        inner.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Buscar telas e ações…  (Esc fecha)")
        self._input.setStyleSheet(t.input_style())
        self._input.textChanged.connect(self._refilter)
        inner.addWidget(self._input)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none;"
            f" outline: none; }}"
            f"QListWidget::item {{ border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: {t.SURFACE_HOV}; }}"
        )
        self._list.setFixedHeight(320)
        # So' itemClicked: Enter e' tratado no keyPressEvent (verificado).
        # itemActivated dispararia junto no double-click -> run() duplicado.
        self._list.itemClicked.connect(lambda _i: self._execute_current())
        inner.addWidget(self._list)

    def _refilter(self, text: str) -> None:
        self._filtered = palette_rank(text, self._commands)
        self._list.clear()
        for cmd in self._filtered:
            item = QListWidgetItem(self._list)
            row = _ResultRow(cmd)
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
        if self._filtered:
            self._list.setCurrentRow(0)

    def _move(self, delta: int) -> None:
        n = self._list.count()
        if n == 0:
            return
        row = (self._list.currentRow() + delta) % n
        self._list.setCurrentRow(row)

    def _execute_current(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._filtered):
            return
        cmd = self._filtered[row]
        self.accept()  # fecha antes de rodar (ex.: foco pos-navegacao)
        run = cmd.get("run")
        if callable(run):
            run()

    def keyPressEvent(self, evt) -> None:  # noqa: N802
        key = evt.key()
        if key == Qt.Key.Key_Down:
            self._move(1)
        elif key == Qt.Key.Key_Up:
            self._move(-1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._execute_current()
        elif key == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(evt)

    def showEvent(self, evt) -> None:  # noqa: N802
        super().showEvent(evt)
        # Posiciona no topo (~18%) da janela pai (ou tela)
        parent = self.parent()
        if parent is not None and hasattr(parent, "geometry"):
            geo = parent.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + int(geo.height() * 0.18)
            self.move(max(0, x), max(0, y))
        self._input.setFocus()


def build_command_palette(commands: list[dict],
                          parent: QWidget | None = None) -> CommandPalette:
    """Factory (espelha o padrao de build_steam_login_dialog)."""
    return CommandPalette(commands, parent)
