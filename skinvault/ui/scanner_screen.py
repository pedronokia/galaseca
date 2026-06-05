"""Tela 3 — Scanner Premium (F11).

Mostra o ScannerTab funcional por tras de um LockOverlay (paywall).
Quando o usuario clica em "Quero ser avisado", registra o interesse
em data/lead_scanner.json.

Versao futura: remover overlay apos licenca paga.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from skinvault._paths import DATA_DIR
from skinvault.gui import ScannerTab
from skinvault.ui import theme as t
from skinvault.ui.components import LockOverlay


_LEAD_PATH = DATA_DIR / "lead_scanner.json"


def _register_lead() -> None:
    """Salva timestamp de interesse no scanner premium."""
    try:
        _LEAD_PATH.parent.mkdir(parents=True, exist_ok=True)
        leads: list[dict] = []
        if _LEAD_PATH.exists():
            raw = _LEAD_PATH.read_text(encoding="utf-8")
            if raw.strip():
                leads = json.loads(raw)
        leads.append({"interested_at": time.time()})
        # Cap em 50 registros (evita acumulo infinito)
        _LEAD_PATH.write_text(
            json.dumps(leads[-50:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


class ScannerScreen(QWidget):
    """Tela 3 — Scanner Premium com overlay de paywall."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scanner real (funcional) por baixo
        self._scanner = ScannerTab()
        root.addWidget(self._scanner, 1)

        # Overlay premium
        self._overlay = LockOverlay(self)
        self._overlay.cta_clicked.connect(self._on_cta)
        root.addWidget(self._overlay, 1)

        # Comeca com overlay visivel
        self._overlay.raise_()
        self._overlay.setVisible(True)

    def _on_cta(self) -> None:
        _register_lead()
        QMessageBox.information(
            self,
            "Interesse registrado",
            "Você será avisado quando o Scanner Premium for lançado.\n\n"
            "Enquanto isso, explore as telas Minha Conta e Histórico.",
        )
