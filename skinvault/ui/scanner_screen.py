"""Tela 3 — Scanner de Investimento (F11).

Escaneia items do Steam Market, calcula score multi-fator,
e permite gerar ranking Top 20.
"""
from __future__ import annotations

import threading
import time

from urllib.parse import quote

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
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


_MAX_FACTOR_DELTA = 35.0  # peso maximo de qualquer fator no enhanced_score
_CS2_APPID = 730


class _FactorBar(QWidget):
    """Barra horizontal centrada: positivo cresce pra direita (verde),
    negativo pra esquerda (vermelho). Largura proporcional a |delta|/MAX."""

    def __init__(self, delta: float,
                 max_delta: float = _MAX_FACTOR_DELTA,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._delta = float(delta)
        self._max = float(max_delta)
        self.setFixedHeight(18)
        self.setMinimumWidth(180)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx = w // 2
        # Eixo central
        p.setPen(QPen(QColor(t.BORDER), 1))
        p.drawLine(cx, 1, cx, h - 1)
        # Barra
        ratio = min(abs(self._delta) / self._max, 1.0) if self._max else 0
        bar_w = int(ratio * (w / 2 - 4))
        if self._delta >= 0:
            color = QColor(t.ACCENT)
            x = cx + 1
        else:
            color = QColor(t.DANGER)
            x = cx - 1 - bar_w
        p.fillRect(x, 4, bar_w, h - 8, color)
        p.end()


class _ScoreBreakdownDialog(QDialog):
    """Dialog explicativo do enhanced_score com barras por fator."""

    def __init__(self, item: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        name = item.get("name", "Item")
        self.setWindowTitle(f"Por que esse score? — {name}")
        self.setMinimumWidth(580)
        self.setStyleSheet(
            f"QDialog {{ background: {t.BG_ELEVATED}; }}"
        )
        self._build(item)

    def _build(self, item: dict) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        score = int(item.get("score", 0))
        if score >= 70:
            verdict_label, vcolor = "COMPRA", t.ACCENT
        elif score >= 45:
            verdict_label, vcolor = "ATENÇÃO", t.WARN
        else:
            verdict_label, vcolor = "EVITAR", t.DANGER

        breakdown = item.get("breakdown") or []
        delta_sum = sum(b["delta"] for b in breakdown)

        # ── Header ────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(14)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        name_lbl = QLabel(item.get("name", "Item"))
        name_lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        name_lbl.setWordWrap(True)
        info_col.addWidget(name_lbl)
        formula = QLabel(
            f"Base 50  {'+' if delta_sum >= 0 else '−'} "
            f"{abs(delta_sum):.0f} contribuições  =  {score}"
        )
        formula.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        info_col.addWidget(formula)
        hdr.addLayout(info_col, 1)

        score_lbl = QLabel(str(score))
        score_lbl.setStyleSheet(
            f"color: {vcolor}; font-size: 36pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(score_lbl)

        verdict_chip = QLabel(verdict_label)
        verdict_chip.setStyleSheet(
            f"color: {vcolor}; font-size: {t.FS_BODY}; font-weight: 700;"
            f" border: 1px solid {vcolor}; border-radius: 8px;"
            f" padding: 4px 14px; font-family: {t.FONT_FAMILY};"
        )
        verdict_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(verdict_chip)

        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {t.BORDER}; background: {t.BORDER};")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── Breakdown rows ────────────────────────────
        if not breakdown:
            empty = QLabel(
                "Sem fatores relevantes — score ficou na base neutra (50)."
            )
            empty.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY};"
            )
            layout.addWidget(empty)
        else:
            for b in breakdown:
                row = QHBoxLayout()
                row.setSpacing(10)
                lbl = QLabel(b["label"])
                lbl.setStyleSheet(
                    f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                    f" font-family: {t.FONT_FAMILY};"
                )
                lbl.setMinimumWidth(280)
                lbl.setWordWrap(True)
                row.addWidget(lbl)

                bar = _FactorBar(b["delta"])
                row.addWidget(bar, 1)

                d = b["delta"]
                d_color = t.ACCENT if d > 0 else t.DANGER
                val = QLabel(f"{d:+.0f}")
                val.setStyleSheet(
                    f"color: {d_color}; font-weight: 700;"
                    f" font-family: {t.FONT_FAMILY};"
                )
                val.setFixedWidth(40)
                val.setAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )
                row.addWidget(val)

                layout.addLayout(row)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {t.BORDER}; background: {t.BORDER};")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)

        # ── Legenda ───────────────────────────────────
        legend = QLabel(
            "Como interpretar:\n"
            "  •  Score 70–100 → COMPRA   •   45–69 → ATENÇÃO   •   "
            "<45 → EVITAR\n"
            "  •  Base 50 é o ponto neutro. Cada fator soma ou subtrai "
            "pontos do score.\n"
            "  •  Lista ordenada do fator mais impactante ao menos."
        )
        legend.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        legend.setWordWrap(True)
        layout.addWidget(legend)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            t.btn_secondary()
        )
        layout.addWidget(bb)


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
        self._scan_btn.setToolTip(
            "Escaneia todos os itens da categoria, calcula score 0-100"
            " e veredito (COMPRA / ATENCAO / EVITAR)."
        )
        self._scan_btn.clicked.connect(self._on_scan)
        hdr.addWidget(self._scan_btn)

        self._rank_btn = QPushButton("Ranking Top 20")
        self._rank_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rank_btn.setStyleSheet(t.btn_steam(padding="10px 24px"))
        self._rank_btn.setToolTip(
            "Escaneia TODAS as categorias e gera ranking dos 20 melhores"
            " scores. Demora vários minutos pelo rate-limit do Steam."
        )
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
        self._table.setSortingEnabled(True)
        self._table.setStyleSheet(t.table_style())
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 10):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self._table.doubleClicked.connect(
            lambda _idx: self._on_explain_selected()
        )
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.customContextMenuRequested.connect(self._on_ctx_menu)
        root.addWidget(self._table, 1)

        hint = QLabel(
            "Dica: clique duas vezes em uma linha para ver \"Por que esse "
            "score?\" — breakdown visual por fator. Botão direito abre mais "
            "opções."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        root.addWidget(hint)

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
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
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
                if col == self.COL_NAME:
                    item.setData(Qt.ItemDataRole.UserRole, r)
                self._table.setItem(i, col, item)
            # Score breakdown tooltip
            tip = r.get("score_tooltip", "")
            if tip:
                self._table.item(i, self.COL_SCORE).setToolTip(tip)
        self._table.setSortingEnabled(was_sorting)

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

    # ── explicabilidade ─────────────────────────────────
    def _selected_result(self) -> dict | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, self.COL_NAME)
        if item is None:
            return None
        r = item.data(Qt.ItemDataRole.UserRole)
        return r if isinstance(r, dict) else None

    def _on_explain_selected(self) -> None:
        r = self._selected_result()
        if r is None:
            return
        dlg = _ScoreBreakdownDialog(r, self)
        dlg.exec()

    def _on_open_steam(self) -> None:
        r = self._selected_result()
        if r is None:
            return
        name = r.get("name", "")
        if not name:
            return
        url = (
            f"https://steamcommunity.com/market/listings/"
            f"{_CS2_APPID}/{quote(name)}"
        )
        QDesktopServices.openUrl(QUrl(url))

    def _on_ctx_menu(self, pos) -> None:
        if self._table.currentRow() < 0:
            return
        menu = QMenu(self._table)
        act_why = menu.addAction("Por que esse score?")
        act_open = menu.addAction("Ver no Steam Market")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == act_why:
            self._on_explain_selected()
        elif action == act_open:
            self._on_open_steam()

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
