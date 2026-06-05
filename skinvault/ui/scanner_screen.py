"""Tela 3 — Scanner de Investimento (F11).

Escaneia items do Steam Market, calcula score multi-fator,
e permite gerar ranking Top 20.
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import cases, ranking, signals, steam_api
from skinvault._paths import DATA_DIR
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.components import Card, StatCard


_SCAN_BY_CATEGORY = {
    "Rifles": [
        "AK-47 | Redline (Field-Tested)", "AK-47 | Bloodsport (Field-Tested)",
        "AK-47 | Neon Rider (Field-Tested)", "AK-47 | The Empress (Field-Tested)",
        "AK-47 | Phantom Disruptor (Field-Tested)", "AK-47 | Rat Rod (Field-Tested)",
        "AK-47 | Safari Mesh (Battle-Scarred)", "M4A4 | Howl (Field-Tested)",
        "M4A4 | Asiimov (Field-Tested)", "M4A4 | Dragon King (Minimal Wear)",
        "M4A4 | Neo-Noir (Field-Tested)", "M4A4 | Desolate Space (Field-Tested)",
        "M4A1-S | Master Piece (Field-Tested)", "M4A1-S | Mecha Industries (Field-Tested)",
        "M4A1-S | Decimator (Field-Tested)", "M4A1-S | Golden Coil (Field-Tested)",
        "AWP | Asiimov (Field-Tested)", "AWP | Hyper Beast (Field-Tested)",
        "AWP | Mortis (Field-Tested)", "AWP | Wildfire (Field-Tested)",
    ],
    "Pistolas": [
        "Desert Eagle | Blaze (Factory New)", "Desert Eagle | Code Red (Factory New)",
        "Desert Eagle | Printstream (Factory New)", "Desert Eagle | Hand Cannon (Field-Tested)",
        "USP-S | Kill Confirmed (Field-Tested)", "USP-S | Neo-Noir (Factory New)",
        "Glock-18 | Water Elemental (Minimal Wear)", "Glock-18 | Wasteland Rebel (Field-Tested)",
        "Glock-18 | Neo-Noir (Field-Tested)",
    ],
    "Facas": [
        "Bayonet | Doppler (Factory New)", "Bayonet | Marble Fade (Factory New)",
        "Bayonet | Tiger Tooth (Factory New)", "Bayonet | Rust Coat (Battle-Scarred)",
        "Butterfly Knife | Fade (Factory New)", "Butterfly Knife | Slaughter (Minimal Wear)",
        "Karambit | Doppler (Factory New)", "Karambit | Tiger Tooth (Factory New)",
        "Karambit | Fade (Factory New)", "Flip Knife | Doppler (Factory New)",
        "Flip Knife | Marble Fade (Factory New)",
        "M9 Bayonet | Doppler (Factory New)", "M9 Bayonet | Tiger Tooth (Factory New)",
        "M9 Bayonet | Fade (Factory New)", "Talon Knife | Doppler (Factory New)",
        "Stiletto Knife | Doppler (Factory New)",
    ],
    "Luvas": [
        "Hand Wraps | Cobalt Skull (Field-Tested)",
        "Hand Wraps | Leather (Minimal Wear)", "Hand Wraps | Slaughter (Factory New)",
        "Moto Gloves | Spearmint (Field-Tested)",
        "Moto Gloves | Boom! (Field-Tested)",
        "Bloodhound Gloves | Bronzed (Field-Tested)",
        "Bloodhound Gloves | Charred (Battle-Scarred)",
        "Sport Gloves | Pandora's Box (Field-Tested)",
        "Sport Gloves | Big Game (Field-Tested)",
        "Driver Gloves | Lunar Weave (Field-Tested)",
        "Driver Gloves | King Snake (Factory New)",
        "Specialist Gloves | Mogul (Factory New)",
    ],
    "SMGs": [
        "MAC-10 | Neon Rider (Battle-Scarred)", "MP9 | Rose Iron (Factory New)",
        "P90 | Death by Kitty (Minimal Wear)", "PP-Bizon | Osiris (Factory New)",
        "UMP-45 | Minotaur's Labyrinth (Field-Tested)",
        "MP7 | Neon Ply (Factory New)",
    ],
}


class _ScannerBridge(QObject):
    result_ready = pyqtSignal(dict)
    progress = pyqtSignal(str)


class ScannerScreen(QWidget):
    """Scanner de investimento multi-fator."""

    COL_NAME = 0
    COL_SINAL = 1
    COL_PRECO = 2
    COL_JUSTO = 3
    COL_VEREDITO = 4
    COL_SPREAD = 5
    COL_BOOK = 6
    COL_TREND = 7
    COL_SD = 8
    COL_SCORE = 9

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._bridge = _ScannerBridge()
        self._bridge.result_ready.connect(self._on_item_done)
        self._bridge.progress.connect(self._on_progress)
        self._scan_results: list[dict] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        hdr = QHBoxLayout()
        title = QLabel("Scanner")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
        )
        hdr.addWidget(title)
        hdr.addStretch(1)

        self._cat_combo = QComboBox()
        self._cat_combo.setStyleSheet(
            f"QComboBox {{ background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: 8px; padding: 8px 12px; color: {t.TEXT};"
            f" font-size: {t.FS_INPUT}; min-width: 160px; }}"
            f"QComboBox:drop-down {{ border: none; }}"
            f"QComboBox:down-arrow {{ color: {t.TEXT_MUTED}; }}"
        )
        for cat in _SCAN_BY_CATEGORY:
            self._cat_combo.addItem(cat)
        self._cat_combo.addItem("Todas as categorias")
        hdr.addWidget(self._cat_combo)

        self._scan_btn = QPushButton("Escanear")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(t.btn_primary(padding="10px 24px"))
        self._scan_btn.clicked.connect(self._on_scan)
        hdr.addWidget(self._scan_btn)

        self._rank_btn = QPushButton("Ranking Top 20")
        self._rank_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rank_btn.setStyleSheet(t.btn_steam(padding="10px 24px"))
        self._rank_btn.clicked.connect(self._on_ranking)
        hdr.addWidget(self._rank_btn)
        root.addLayout(hdr)

        # Stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_count = StatCard("Itens escaneados", "0")
        self._stat_best = StatCard("Melhor score", "—")
        self._stat_avg = StatCard("Score medio", "—")
        for sc in (self._stat_count, self._stat_best, self._stat_avg):
            stats_row.addWidget(sc, 1)
        root.addLayout(stats_row)

        # Tabela
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels([
            "Item", "Sinal", "Preco", "Preco justo", "Veredito",
            "Spread", "Book", "Tendencia", "S/D", "Score",
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(t.table_style())
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 10):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        # Progress/status
        self._status = QLabel("Pronto. Selecione uma categoria e clique em Escanear.")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        root.addWidget(self._status)

    def _on_scan(self) -> None:
        cat = self._cat_combo.currentText()
        items: list[str] = []
        if cat == "Todas as categorias":
            for v in _SCAN_BY_CATEGORY.values():
                items.extend(v)
        else:
            items = _SCAN_BY_CATEGORY.get(cat, [])
        if not items:
            return

        self._scan_results.clear()
        self._table.setRowCount(0)
        self._scan_btn.setEnabled(False)
        self._rank_btn.setEnabled(False)
        self._status.setText(f"Escaneando {len(items)} itens...")

        def _worker():
            for i, name in enumerate(items):
                self._bridge.progress.emit(
                    f"[{i+1}/{len(items)}] {name}"
                )
                result = self._scan_item(name)
                if result:
                    self._bridge.result_ready.emit(result)
                time.sleep(2.0)  # rate-limit respect
            self._bridge.progress.emit("FIM")

        threading.Thread(target=_worker, daemon=True).start()

    def _scan_item(self, name: str) -> dict | None:
        try:
            overview = steam_api.get_market_overview(name)
            page = steam_api.get_market_page_data(name)
        except Exception:
            return None
        if not overview:
            return None

        lowest = overview.get("lowest")
        median = overview.get("median")
        volume = overview.get("volume")
        if lowest is None:
            return None

        self._cache.put(name, lowest)

        verdict = steam_api.fair_value_verdict(
            lowest, median,
            spread=page.get("order_book") if page else None,
            buy_count=(len(page["order_book"].get("buy", []))
                       if page and page.get("order_book") else None),
            sell_count=(len(page["order_book"].get("sell", []))
                        if page and page.get("order_book") else None),
            price_history=page.get("price_history") if page else None,
        ) if page else steam_api.fair_value_verdict(lowest, median)
        signals.record_item_price(name, lowest)
        if volume:
            signals.record_item_volume(name, volume)
        supply = (len(page["order_book"].get("sell", []))
                  if page and page.get("order_book") else None)
        if supply is not None:
            signals.record_item_supply(name, supply)

        multi = signals.multi_trend(
            page.get("price_history", [])
        ) if page and page.get("price_history") else None
        cs = cases.case_status(name)

        score, breakdown = signals.enhanced_score(
            verdict, volume, supply,
            multi_trend=multi,
            price_history=page.get("price_history") if page else None,
            case_status=cs,
        )

        return {
            "name": name,
            "price": lowest,
            "median": median,
            "score": score,
            "breakdown": breakdown,
            "verdict": verdict.get("label", "—"),
            "verdict_color": t.ACCENT if verdict.get("diff_pct", 0) <= 0
                             else t.DANGER,
            "spread": verdict.get("spread_verdict", ""),
            "book": verdict.get("book_verdict", ""),
            "trend": verdict.get("trend_verdict", ""),
            "volume": volume,
            "supply": supply,
            "sd_label": signals.supply_demand_ratio(volume, supply).get("label", ""),
            "score_tooltip": signals.format_breakdown(breakdown),
            "case_label": cs.get("label", ""),
        }

    def _on_item_done(self, result: dict) -> None:
        self._scan_results.append(result)
        self._scan_results.sort(key=lambda r: r["score"], reverse=True)
        self._populate()

    def _populate(self) -> None:
        self._table.setRowCount(0)
        for i, r in enumerate(self._scan_results):
            self._table.insertRow(i)
            score = r["score"]
            score_color = t.ACCENT if score >= 70 else (
                t.WARN if score >= 45 else t.DANGER
            )
            label = "COMPRA" if score >= 70 else (
                "ATENCAO" if score >= 45 else "EVITAR"
            )
            cells = [
                (r["name"], None),
                (label, score_color),
                (t.brl(r["price"]), None),
                (t.brl(r["median"]), None),
                (r["verdict"], r["verdict_color"]),
                (r["spread"], None),
                (r["book"], None),
                (r["trend"], None),
                (r["sd_label"], None),
                (str(score), score_color),
            ]
            for col, (val, color) in enumerate(cells):
                item = QTableWidgetItem(str(val))
                if color:
                    item.setForeground(QBrush(QColor(color)))
                self._table.setItem(i, col, item)
            # Score breakdown tooltip
            tip = r.get("score_tooltip", "")
            if tip:
                self._table.item(i, self.COL_SCORE).setToolTip(tip)

        # Stats
        if self._scan_results:
            scores = [r["score"] for r in self._scan_results]
            self._stat_count.set_value(str(len(self._scan_results)))
            self._stat_best.set_value(str(max(scores)),
                                      accent=t.ACCENT)
            self._stat_avg.set_value(str(round(sum(scores)/len(scores))))
        self._status.setText(
            f"{len(self._scan_results)} itens escaneados"
        )

    def _on_progress(self, msg: str) -> None:
        if msg == "FIM":
            self._scan_btn.setEnabled(True)
            self._rank_btn.setEnabled(True)
            self._status.setText(
                f"Scan concluido: {len(self._scan_results)} itens"
            )
        else:
            self._status.setText(msg)

    def _on_ranking(self) -> None:
        if not self._scan_results:
            self._status.setText("Escaneie itens primeiro.")
            return
        top20 = self._scan_results[:20]
        ranking.save_snapshot(top20)
        prev = ranking.previous_snapshot()
        lines = ["=== TOP 20 RANKING ===\n"]
        for i, r in enumerate(top20):
            delta = ranking.position_delta(r["name"], i, prev)
            dp = delta.get("label", "")
            lines.append(
                f"#{i+1} {r['name']}  score {r['score']}  {dp}"
            )
        text = "\n".join(lines)

        from PyQt6.QtWidgets import QMessageBox
        mb = QMessageBox(self)
        mb.setWindowTitle("Ranking Top 20")
        mb.setText(text)
        mb.setStyleSheet(
            f"QMessageBox {{ background: {t.BG_ELEVATED}; color: {t.TEXT};"
            f" font-family: {t.FONT_FAMILY}; }}"
        )
        mb.exec()
        self._status.setText("Ranking salvo!")
