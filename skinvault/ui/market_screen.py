"""Tela — Market (F11).

Consulta preco ao vivo, fair value verdict, order book e sparkline.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault import signals, steam_api
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.components import Card, StatCard
from skinvault.ui.widgets import MiniSparkline, DepthChart


class _MarketBridge(QObject):
    data_ready = pyqtSignal(dict)


class MarketScreen(QWidget):
    """Tela de consulta de precos do Market."""

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._bridge = _MarketBridge()
        self._bridge.data_ready.connect(self._on_data)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        title = QLabel("Market")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
        )
        root.addWidget(title)

        # Search
        search_row = QHBoxLayout()
        self._search_inp = QLineEdit()
        self._search_inp.setPlaceholderText(
            "Ex: AK-47 | Redline (Field-Tested)"
        )
        self._search_inp.setStyleSheet(t.input_style())
        self._search_inp.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_inp, 1)

        self._search_btn = QPushButton("Consultar")
        self._search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_btn.setStyleSheet(t.btn_primary())
        self._search_btn.clicked.connect(self._on_search)
        search_row.addWidget(self._search_btn)
        root.addLayout(search_row)

        # Stat cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_lowest = StatCard("Menor preco", "—")
        self._stat_median = StatCard("Mediana", "—")
        self._stat_volume = StatCard("Volume (24h)", "—")
        self._stat_verdict = StatCard("Veredito", "—")
        for sc in (self._stat_lowest, self._stat_median, self._stat_volume,
                   self._stat_verdict):
            stats_row.addWidget(sc, 1)
        root.addLayout(stats_row)

        # Cards: sparkline + depth chart
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)

        spark_card = Card(self, padding=(16, 14, 16, 14))
        spark_lay = QVBoxLayout()
        spark_lay.setSpacing(8)
        spark_lbl = QLabel("Historico de precos")
        spark_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        spark_lay.addWidget(spark_lbl)
        self._sparkline = MiniSparkline(parent=spark_card)
        self._sparkline.setMinimumHeight(140)
        spark_lay.addWidget(self._sparkline, 1)
        spark_card.layout().addLayout(spark_lay)
        charts_row.addWidget(spark_card, 1)

        depth_card = Card(self, padding=(16, 14, 16, 14))
        depth_lay = QVBoxLayout()
        depth_lay.setSpacing(8)
        depth_lbl = QLabel("Order book")
        depth_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        depth_lay.addWidget(depth_lbl)
        self._depth = DepthChart(parent=depth_card)
        self._depth.setMinimumHeight(140)
        depth_lay.addWidget(self._depth, 1)
        depth_card.layout().addLayout(depth_lay)
        charts_row.addWidget(depth_card, 1)

        root.addLayout(charts_row)

        # Detail card
        detail_card = Card(self, padding=(16, 14, 16, 14))
        self._detail_lay = QVBoxLayout()
        self._detail_lbl = QLabel("Consulte um item para ver detalhes.")
        self._detail_lbl.setWordWrap(True)
        self._detail_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
        )
        self._detail_lay.addWidget(self._detail_lbl)
        detail_card.layout().addLayout(self._detail_lay)
        root.addWidget(detail_card)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        root.addWidget(self._status)

    def _on_search(self) -> None:
        name = self._search_inp.text().strip()
        if not name:
            return
        self._status.setText("Consultando...")
        self._search_btn.setEnabled(False)

        import threading

        def _worker():
            data = {}
            overview = steam_api.get_market_overview(name)
            if overview:
                data["overview"] = overview
            page = steam_api.get_market_page_data(name)
            if page:
                data["page"] = page
            data["name"] = name
            self._bridge.data_ready.emit(data)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_data(self, data: dict) -> None:
        self._search_btn.setEnabled(True)
        name = data.get("name", "")
        overview = data.get("overview")
        page = data.get("page")

        if not overview and not page:
            self._status.setText(
                "Nao foi possivel obter dados. Verifique o nome do item."
            )
            return

        if overview:
            lowest = overview.get("lowest")
            median = overview.get("median")
            volume = overview.get("volume")
            verdict = steam_api.fair_value_verdict(lowest, median)
            self._stat_lowest.set_value(t.brl(lowest))
            self._stat_median.set_value(t.brl(median))
            self._stat_volume.set_value(str(volume) if volume else "—")
            v_color = t.ACCENT if verdict.get("diff_pct", 0) <= 0 else t.DANGER
            self._stat_verdict.set_value(verdict.get("label", "—"),
                                         accent=v_color)
            self._cache.put(name, lowest)

        if page:
            price_history = page.get("price_history", [])
            order_book = page.get("order_book")

            if price_history:
                prices_list = [x["price"] for x in price_history if "price" in x]
                if prices_list:
                    self._sparkline.set_series(prices_list[-100:])
                    sma_vals = signals.sma(prices_list, period=7)
                    if sma_vals:
                        self._sparkline.set_sma(sma_vals[-100:])
                    sr = signals.find_support_resistance(price_history[-100:])
                    if sr:
                        self._sparkline.set_sr(sr)

            if order_book:
                self._depth.set_data(order_book)

        # Detail
        lines = [f"Item: {name}"]
        if overview:
            lines.append(f"Menor listagem: {t.brl(overview.get('lowest'))}")
            lines.append(f"Mediana: {t.brl(overview.get('median'))}")
            lines.append(f"Volume 24h: {overview.get('volume', '—')}")
        if page:
            lines.append(
                f"Historico: {len(page.get('price_history', []))} pontos"
            )
            ob = page.get("order_book", {})
            buys = len(ob.get("buy", [])) if ob else 0
            sells = len(ob.get("sell", [])) if ob else 0
            lines.append(f"Ordens de compra: {buys} | Venda: {sells}")
        self._detail_lbl.setText("\n".join(lines))
        self._status.setText(f"Atualizado: {name}")
