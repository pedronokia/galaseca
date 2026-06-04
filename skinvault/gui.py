"""UI do SkinVault (PyQt6). Janela local: avalia o inventario e mostra o valor
no tempo. Importa PyQt6 -- so' carregada quando 'python -m skinvault --ui'.

Reaproveita os padroes do Future: tema escuro, valor em fonte tabular, grafico
custom-painted (estilo _Sparkline), worker em thread + signal pra nao travar a UI.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import history, prices, steam_api

_BG = "#0E0E12"
_SURFACE = "#16161C"
_TEXT = "#E6E6EA"
_MUTED = "#9D9DA8"
_GREEN = "#22C55E"
_RED = "#EF4444"


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ValueChart(QWidget):
    """Linha do valor do inventario no tempo (custom paint, sem dependencia)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[float] = []
        self.setMinimumHeight(120)

    def set_series(self, totals: list[float]) -> None:
        self._values = list(totals)
        self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if len(self._values) < 2:
            p.setPen(QColor(_MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Avalie 2x+ pra ver a evolucao do valor")
            p.end()
            return
        vmin, vmax = min(self._values), max(self._values)
        rng = (vmax - vmin) or 1.0
        up = self._values[-1] >= self._values[0]
        pen = QPen(QColor(_GREEN if up else _RED))
        pen.setWidthF(2.0)
        p.setPen(pen)
        n = len(self._values)
        prev = None
        for i, v in enumerate(self._values):
            x = 6 + i * ((w - 12) / (n - 1))
            y = h - 8 - ((v - vmin) / rng) * (h - 24)
            if prev is not None:
                p.drawLine(int(prev[0]), int(prev[1]), int(x), int(y))
            prev = (x, y)
        p.end()


class _Bridge(QObject):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(str, list, float)


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SkinVault -- teu inventario, no teu PC")
        self.resize(720, 640)
        self.setStyleSheet(f"background: {_BG}; color: {_TEXT};"
                           " font-family: 'Segoe UI';")
        self._cache = prices.PriceCache()
        self._build()
        self._refresh_chart()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # --- topo: input + botao -------------------------------------
        top = QHBoxLayout()
        self._sid = QLineEdit()
        self._sid.setPlaceholderText("SteamID64 (17 digitos)")
        self._sid.setStyleSheet(
            f"QLineEdit {{ background: {_SURFACE}; border: 1px solid #2A2A33;"
            " border-radius: 8px; padding: 10px 12px; font-size: 11pt; }"
            f"QLineEdit:focus {{ border: 1px solid {_GREEN}; }}"
        )
        self._sid.returnPressed.connect(self._on_evaluate)
        top.addWidget(self._sid, 1)
        self._btn = QPushButton("Avaliar")
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(
            "QPushButton { color: #DCFFE6; background: rgba(34,197,94,0.16);"
            f" border: 1px solid {_GREEN}; border-radius: 8px;"
            " padding: 10px 22px; font-size: 11pt; font-weight: 600; }"
            "QPushButton:hover { background: rgba(34,197,94,0.26); }"
            "QPushButton:disabled { color: #777; border-color: #333;"
            " background: #1a1a20; }"
        )
        self._btn.clicked.connect(self._on_evaluate)
        top.addWidget(self._btn)
        root.addLayout(top)

        # --- total + privacidade hint --------------------------------
        self._total = QLabel("R$ --")
        f = QFont("Segoe UI", 30, QFont.Weight.DemiBold)
        try:
            f.setStyleHint(QFont.StyleHint.Monospace)
            f.setFeatures({"tnum": 1})  # type: ignore[attr-defined]
        except Exception:
            pass
        self._total.setFont(QFont("Segoe UI", 30, QFont.Weight.DemiBold))
        self._total.setStyleSheet("color: #FFFFFF;")
        root.addWidget(self._total)

        cap = QLabel("Valor total do inventario  -  dado publico, sem login")
        cap.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(cap)

        # --- grafico -------------------------------------------------
        self._chart = ValueChart()
        self._chart.setStyleSheet(f"background: {_SURFACE}; border-radius: 10px;")
        root.addWidget(self._chart)

        # --- progresso -----------------------------------------------
        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(
            "QProgressBar { background: #20202a; border: none; border-radius: 2px; }"
            f"QProgressBar::chunk {{ background: {_GREEN}; border-radius: 2px; }}"
        )
        self._bar.hide()
        root.addWidget(self._bar)

        self._status = QLabel("Digite teu SteamID64 e clique em Avaliar.")
        self._status.setStyleSheet(f"color: {_MUTED}; font-size: 9pt;")
        root.addWidget(self._status)

        # --- tabela --------------------------------------------------
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Item", "Qtd", "Preco", "Total"])
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in (1, 2, 3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {_SURFACE}; border: none;"
            " border-radius: 10px; gridline-color: transparent; }"
            "QTableWidget::item { padding: 6px 10px;"
            " border-bottom: 1px solid rgba(255,255,255,0.04); }"
            "QHeaderView::section { background: transparent; color: #8A8A93;"
            " border: none; padding: 8px 10px; font-weight: 600; }"
        )
        root.addWidget(self._table, 1)

    # ----- acoes -----------------------------------------------------
    def _on_evaluate(self) -> None:
        sid = self._sid.text().strip()
        if not sid.isdigit() or len(sid) < 17:
            self._status.setText("SteamID64 invalido -- sao 17 digitos (use steamid.io).")
            return
        self._btn.setEnabled(False)
        self._bar.setRange(0, 0)  # indeterminado ate ter o total de itens
        self._bar.show()
        self._status.setText("Lendo inventario publico...")

        self._bridge = _Bridge()
        self._bridge.progress.connect(self._on_progress)
        self._bridge.done.connect(self._on_done)

        def work() -> None:
            status, rows, total = prices.value_inventory(
                sid, self._cache,
                progress=lambda i, n, name: self._bridge.progress.emit(i, n, name),
            )
            self._bridge.done.emit(status, rows, total)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, i: int, n: int, name: str) -> None:
        if self._bar.maximum() == 0:
            self._bar.setRange(0, n)
        self._bar.setValue(i)
        self._status.setText(f"Avaliando {i}/{n}: {name}")

    def _on_done(self, status: str, rows: list, total: float) -> None:
        self._btn.setEnabled(True)
        self._bar.hide()
        msgs = {
            steam_api.INV_PRIVATE: "Inventario PRIVADO. Steam > Editar Perfil >"
                                   " Privacidade > Inventario: Publico.",
            steam_api.INV_RATE_LIMITED: "Steam limitou (rate-limit). Espera ~1 min.",
            steam_api.INV_EMPTY: "Inventario publico, mas sem itens marketaveis.",
            steam_api.INV_ERROR: "Nao consegui ler agora (rede/erro).",
        }
        if status != steam_api.INV_OK:
            self._status.setText(msgs.get(status, "Falha desconhecida."))
            return

        self._total.setText(_brl(total))
        self._status.setText(f"{len(rows)} itens avaliados.")
        history.record_snapshot(total)
        self._refresh_chart()

        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(row["name"]))
            self._table.setItem(r, 1, QTableWidgetItem(str(row["qty"])))
            self._table.setItem(r, 2, QTableWidgetItem(_brl(row["price"])))
            self._table.setItem(r, 3, QTableWidgetItem(_brl(row["total"])))

    def _refresh_chart(self) -> None:
        self._chart.set_series([h["total"] for h in history.load_history()])


def launch() -> int:
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    win = MainWindow()
    win.show()
    return app.exec()
