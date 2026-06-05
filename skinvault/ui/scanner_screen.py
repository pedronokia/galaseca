"""Tela 3 — Scanner Premium (F11 mockup).

Mockup com QGraphicsBlurEffect sobre cards de preview + LockOverlay.
Se settings['scanner_unlocked'] for True, overlay some e blur remove.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from skinvault._paths import DATA_DIR
from skinvault.settings import load_settings, save_settings
from skinvault.ui import theme as t
from skinvault.ui.components import Card, LockOverlay, StatCard


_LEAD_PATH = DATA_DIR / "lead_scanner.json"


def _register_lead() -> None:
    try:
        _LEAD_PATH.parent.mkdir(parents=True, exist_ok=True)
        leads: list[dict] = []
        if _LEAD_PATH.exists():
            raw = _LEAD_PATH.read_text(encoding="utf-8")
            if raw.strip():
                leads = json.loads(raw)
        leads.append({"interested_at": time.time()})
        _LEAD_PATH.write_text(
            json.dumps(leads[-50:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _preview_card(title: str, rows: list[str]) -> Card:
    c = Card(padding=(16, 14, 16, 14))
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED}; font-weight: 600;"
        f" font-family: {t.FONT_FAMILY}; letter-spacing: 1px;"
    )
    c.layout().addWidget(title_lbl)
    for text in rows:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        c.layout().addWidget(lbl)
    return c


class ScannerScreen(QWidget):
    """Tela 3 — Scanner Premium mockup com blur + LockOverlay."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Mockup content (fica atras do overlay)
        self._content = QWidget(self)
        self._content.setGraphicsEffect(QGraphicsBlurEffect())
        body = QVBoxLayout(self._content)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(16)

        header = QLabel("Scanner de oportunidades")
        header.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(header)

        sub = QLabel(
            "Identifique skins, caixas e adesivos antes da valorizacao. "
            "Scanner premium chega em breve."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(sub)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        for sc in [
            ("oportunidades hoje", "—"),
            ("Score medio", "—"),
            ("Sinais ativos", "—"),
        ]:
            c = StatCard(sc[0], sc[1], accent=t.STEAM_BLUE)
            stats.addWidget(c, 1)
        body.addLayout(stats)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        cards_row.addWidget(
            _preview_card("MAIOR SCORE", [
                "AK-47 | Redline (FT)  \u25b8  87",
                "AWP | Asiimov (WW)    \u25b8  82",
                "Desert Eagle | Blaze   \u25b8  79",
            ]), 1)
        cards_row.addWidget(
            _preview_card("MAIS LIQUIDAS", [
                "\u2605 Bayonet | Doppler    \u25b8  R$ 1.240",
                "AK-47 | Vulcan (MW)    \u25b8  R$ 480",
                "M4A4 | Howl (FT)       \u25b8  R$ 2.100",
            ]), 1)
        cards_row.addWidget(
            _preview_card("CAIXAS", [
                "Fracture Case           \u25b8  R$ 3,20",
                "Dreams & Nightmares     \u25b8  R$ 5,80",
                "Revolution Case         \u25b8  R$ 2,40",
            ]), 1)
        body.addLayout(cards_row)

        self._disclaimer = QLabel(
            "Dados ilustrativos. Conecte-se e aguarde o lancamento "
            "do scanner para analises em tempo real."
        )
        self._disclaimer.setWordWrap(True)
        self._disclaimer.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        body.addWidget(self._disclaimer)
        body.addStretch(1)

        root.addWidget(self._content, 1)

        # Overlay premium
        self._overlay = LockOverlay(self)
        self._overlay.cta_clicked.connect(self._on_cta)
        root.addWidget(self._overlay, 1)

        self._overlay.raise_()

        # License checkpoint
        settings = load_settings()
        if settings.get("scanner_unlocked", False):
            self._unlock()

    def _unlock(self) -> None:
        self._overlay.setVisible(False)
        self._content.setGraphicsEffect(None)
        self._disclaimer.setText(
            "Scanner premium ativo. Dados reais chegam na F12."
        )
        self._disclaimer.setStyleSheet(
            f"color: {t.ACCENT}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )

    def _on_cta(self) -> None:
        _register_lead()
        QMessageBox.information(
            self, "Interesse registrado",
            "Voce sera avisado quando o Scanner Premium for lancado.\n\n"
            "Enquanto isso, explore as telas Minha Conta e Historico.",
        )
