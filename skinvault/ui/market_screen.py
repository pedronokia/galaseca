"""Tela — Market (F11).

Consulta preco ao vivo, fair value verdict, order book e sparkline.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault import cases, signals, steam_api
from skinvault._paths import DATA_DIR
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.components import (
    Card,
    EmptyState,
    LoadingState,
    PageHeader,
    SectionHeader,
    StatCard,
    Toast,
)
from skinvault.ui.widgets import DepthChart, MiniSparkline


_RECENT_CAP = 8
_RECENT_PATH = DATA_DIR / "market_recent.json"


def _load_recent() -> list[str]:
    try:
        data = json.loads(_RECENT_PATH.read_text("utf-8"))
        return data[:8] if isinstance(data, list) else []
    except Exception:
        return []


def _save_recent(items: list[str]) -> None:
    try:
        _RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _RECENT_PATH.write_text(json.dumps(items[:8]), encoding="utf-8")
    except OSError:
        pass


_VERDICT_COLOR = {
    "below_median": t.POSITIVE,
    "fair": t.TEXT,
    "slightly_above": t.WARN,
    "overpriced": t.DANGER,
    "unknown": t.TEXT_MUTED,
}


def _cache_age_label(seconds: float) -> str:
    if seconds < 60:
        return "agora há pouco"
    if seconds < 3600:
        return f"há {int(seconds // 60)}min"
    if seconds < 86400:
        return f"há {int(seconds // 3600)}h"
    return f"há {int(seconds // 86400)}d"


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
        self._recent: list[str] = _load_recent()
        self._started_at: float = 0.0
        self._build()
        self._rebuild_recent_menu()

    # ── construcao ────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        root.addWidget(PageHeader(
            "Consulta de Mercado",
            "Análise de fair value, histórico de preços e profundidade do "
            "livro de ofertas no Steam Community Market.",
        ))

        # ── Search protagonist line ────────────────────────
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self._search_inp = QLineEdit()
        self._search_inp.setMinimumWidth(420)
        self._search_inp.setPlaceholderText(
            "Ex: AK-47 | Redline (Field-Tested)  •  Karambit | Doppler (Factory New)"
        )
        self._search_inp.setClearButtonEnabled(True)
        self._search_inp.setStyleSheet(t.input_style())
        self._search_inp.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search_inp, 1)

        self._search_btn = QPushButton("Consultar item")
        self._search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_btn.setStyleSheet(t.btn_primary())
        self._search_btn.setToolTip(
            "Busca menor preço, mediana, volume 24h, histórico e livro de "
            "ofertas.\nRespeita o rate-limit do Steam (~2s por consulta)."
        )
        self._search_btn.clicked.connect(self._on_search)
        search_row.addWidget(self._search_btn)

        self._recent_act = QAction("▾", self._search_inp)
        self._recent_act.triggered.connect(self._show_recent_menu)
        self._search_inp.addAction(self._recent_act,
                                   QLineEdit.ActionPosition.TrailingPosition)

        self._recent_menu = QMenu(self)
        self._recent_act.setVisible(False)

        root.addLayout(search_row)

        hint = QLabel(
            "Cole o nome exatamente como aparece no Steam Market — incluindo "
            "wear e StatTrak/Souvenir quando aplicável. Atalho: Ctrl+L."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(t.label_caption())
        root.addWidget(hint)

        self._loading = LoadingState("Consultando item…")
        self._loading.setVisible(False)
        self._loading.setMinimumHeight(180)
        root.addWidget(self._loading)

        # ── Content area (shown/hidden as a unit) ──────────
        self._content = QWidget()
        content_lay = QVBoxLayout(self._content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(14)

        # ── Stat cards ────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._stat_lowest = StatCard("Menor listagem ativa", "—",
                                      icon="eye")
        self._stat_lowest.setToolTip(
            "Preço da listagem mais barata disponível agora no Steam Market."
        )
        self._stat_median = StatCard("Mediana 24h", "—", icon="chart")
        self._stat_median.setToolTip(
            "Mediana das vendas das últimas 24h. Referência de \"preço justo\"."
        )
        self._stat_volume = StatCard("Volume 24h", "—", icon="archive")
        self._stat_volume.setToolTip(
            "Unidades vendidas nas últimas 24h. Acima de ~2000 indica "
            "liquidez confortável. Marca anomalia quando desvia 2x da média."
        )
        self._stat_verdict = StatCard("Veredito", "—", icon="radar")
        self._stat_verdict.setToolTip(
            "Análise multi-fator: posição vs mediana, spread, profundidade do "
            "book e tendência recente."
        )
        for sc in (self._stat_lowest, self._stat_median, self._stat_volume,
                   self._stat_verdict):
            sc.setMaximumWidth(280)
            sc.setMaximumHeight(110)
            stats_row.addWidget(sc)
        stats_row.addStretch(1)
        content_lay.addLayout(stats_row)

        # ── Charts ────────────────────────────────────────
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)

        spark_card = Card(self)
        spark_card.setFixedHeight(300)
        spark_lay = QVBoxLayout()
        spark_lay.setSpacing(8)
        spark_hdr = QHBoxLayout()
        spark_lbl = QLabel("Histórico de preços")
        spark_lbl.setStyleSheet(t.label_caption())
        # Tooltip de ajuda fica no label do header — o chart em si mostra
        # tooltip dinâmico (preço + data) ao passar o mouse nos pontos.
        spark_lbl.setToolTip(
            "Últimos ~100 pontos do preço mediano.\n"
            "Linha tracejada = SMA 7 dias. Linhas horizontais = suporte e "
            "resistência aproximados.\n"
            "Passe o mouse sobre o gráfico para ver preço e data por ponto."
        )
        spark_hdr.addWidget(spark_lbl)
        spark_hdr.addStretch(1)
        self._spark_meta = QLabel("")
        self._spark_meta.setStyleSheet(t.label_caption())
        spark_hdr.addWidget(self._spark_meta)
        spark_lay.addLayout(spark_hdr)
        self._sparkline = MiniSparkline(parent=spark_card)
        self._sparkline.setMinimumHeight(140)
        spark_lay.addWidget(self._sparkline, 1)
        spark_card.layout().addLayout(spark_lay)
        charts_row.addWidget(spark_card)

        depth_card = Card(self)
        depth_card.setFixedHeight(300)
        depth_lay = QVBoxLayout()
        depth_lay.setSpacing(8)
        depth_hdr = QHBoxLayout()
        depth_lbl = QLabel("Livro de ofertas")
        depth_lbl.setStyleSheet(t.label_caption())
        depth_hdr.addWidget(depth_lbl)
        depth_hdr.addStretch(1)
        self._depth_meta = QLabel("")
        self._depth_meta.setStyleSheet(t.label_caption())
        depth_hdr.addWidget(self._depth_meta)
        depth_lay.addLayout(depth_hdr)
        self._depth = DepthChart(parent=depth_card)
        self._depth.setMinimumHeight(140)
        self._depth.setToolTip(
            "Profundidade acumulada do book.\n"
            "Verde = ordens de compra (demanda). Vermelho = listagens à venda "
            "(oferta).\nBook carregado de um lado indica pressão de preço."
        )
        depth_lay.addWidget(self._depth, 1)
        depth_card.layout().addLayout(depth_lay)
        charts_row.addWidget(depth_card)

        content_lay.addLayout(charts_row)

        # ── Detail card ───────────────────────────────────
        detail_card = Card(self)
        detail_lay = QVBoxLayout()
        detail_lay.setSpacing(10)

        detail_hdr = QHBoxLayout()
        self._detail_title = QLabel("Detalhes do item")
        self._detail_title.setStyleSheet(t.label_section())
        detail_hdr.addWidget(self._detail_title)
        detail_hdr.addStretch(1)
        self._case_badge = QLabel("")
        self._case_badge.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" border: 1px solid {t.BORDER}; border-radius: 6px;"
            f" padding: 2px 8px; font-family: {t.FONT_FAMILY};"
        )
        self._case_badge.setVisible(False)
        detail_hdr.addWidget(self._case_badge)
        detail_lay.addLayout(detail_hdr)

        self._detail_msg = QLabel(
            "Consulte um item para ver fair value, spread, tendência e "
            "profundidade do livro."
        )
        self._detail_msg.setWordWrap(True)
        self._detail_msg.setStyleSheet(t.label_body_muted())
        detail_lay.addWidget(self._detail_msg)

        self._detail_grid = QGridLayout()
        self._detail_grid.setSpacing(6)
        detail_lay.addLayout(self._detail_grid)

        detail_card.layout().addLayout(detail_lay)
        content_lay.addWidget(detail_card)

        # ── Status ────────────────────────────────────────
        self._status = QLabel(
            "Pronto. Cole o nome de um item e clique em Consultar."
        )
        self._status.setStyleSheet(t.label_caption())
        content_lay.addWidget(self._status)

        # Stretch final: spare space goes to bottom, not into cards
        content_lay.addStretch(1)

        root.addWidget(self._content, 1)

        self._empty = EmptyState(
            "◇", "Nada encontrado",
            "Nenhum dado disponível para este item. Verifique o nome "
            "exato (wear, StatTrak, acentos) ou tente novamente.",
            cta_label="Tentar novamente",
            on_cta=self._on_search,
        )
        self._empty.setVisible(False)
        root.addWidget(self._empty, 1)

        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(
            self._search_inp.setFocus
        )

    # ── helpers ───────────────────────────────────────────
    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        for n in self._recent:
            act = self._recent_menu.addAction(n)
            act.triggered.connect(
                lambda _checked=False, nm=n: self._search_and_run(nm)
            )
        self._recent_act.setVisible(bool(self._recent))

    def _show_recent_menu(self) -> None:
        if self._recent:
            inp = self._search_inp
            self._recent_menu.exec(
                inp.mapToGlobal(inp.geometry().bottomLeft())
            )

    def _push_recent(self, name: str) -> None:
        if name in self._recent:
            self._recent.remove(name)
        self._recent.insert(0, name)
        self._recent = self._recent[:_RECENT_CAP]
        _save_recent(self._recent)
        self._rebuild_recent_menu()

    def _search_and_run(self, name: str) -> None:
        self._search_inp.setText(name)
        self._on_search()

    def _clear_detail_grid(self) -> None:
        while self._detail_grid.count() > 0:
            item = self._detail_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    while sub.count():
                        child = sub.takeAt(0)
                        cw = child.widget()
                        if cw is not None:
                            cw.setParent(None)
                            cw.deleteLater()

    def _add_detail_row(self, label: str, value: str,
                        color: str | None = None) -> None:
        """Adiciona linha ao grid de detalhes: label_caption_bold | valor."""
        row = self._detail_grid.rowCount()
        lbl = QLabel(label)
        lbl.setStyleSheet(t.label_caption_bold())
        val = QLabel(value)
        if color:
            val.setStyleSheet(
                f"color: {color}; font-size: {t.FS_BODY};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            )
        else:
            val.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            )
        self._detail_grid.addWidget(lbl, row, 0)
        self._detail_grid.addWidget(val, row, 1)

    # ── acoes ─────────────────────────────────────────────
    def _on_search(self) -> None:
        name = self._search_inp.text().strip()
        if not name:
            return
        cache_msg = ""
        if self._cache.get(name) is not None:
            age = self._cache.age(name)
            if age is not None:
                cache_msg = (
                    f" (cache de {_cache_age_label(age)} será sobrescrito)"
                )
        from skinvault.localization import localize_name as _ln
        self._status.setText(f"Consultando {_ln(name)}…{cache_msg}")
        self._search_btn.setEnabled(False)
        self._content.setVisible(False)
        self._empty.setVisible(False)
        self._loading.setVisible(True)
        self._started_at = time.time()

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

    def _on_clear(self) -> None:
        self._search_inp.clear()
        self._search_inp.setFocus()
        self._loading.setVisible(False)
        self._empty.setVisible(False)
        self._content.setVisible(True)
        for sc in (self._stat_lowest, self._stat_median, self._stat_volume,
                   self._stat_verdict):
            sc.set_value("—", accent=t.TEXT)
        self._sparkline.set_series([])
        self._sparkline.set_sma([])
        self._sparkline.set_sr({})
        self._depth.set_data({})
        self._spark_meta.setText("")
        self._depth_meta.setText("")
        self._detail_title.setText("Detalhes do item")
        self._detail_msg.setText(
            "Consulte um item para ver fair value, spread, tendência e "
            "profundidade do livro."
        )
        self._detail_msg.setStyleSheet(t.label_body_muted())
        self._case_badge.setVisible(False)
        self._clear_detail_grid()
        self._status.setText(
            "Pronto. Cole o nome de um item e clique em Consultar."
        )

    def _on_data(self, data: dict) -> None:
        self._search_btn.setEnabled(True)
        self._loading.setVisible(False)
        name = data.get("name", "")
        overview = data.get("overview")
        page = data.get("page")
        elapsed = time.time() - self._started_at if self._started_at else 0.0

        if not overview and not page:
            self._content.setVisible(False)
            self._empty.setVisible(True)
            Toast.show_toast(
                self,
                f"Não foi possível obter dados de “{name}”. "
                "Verifique o nome (wear, StatTrak, espaços) ou tente novamente.",
                "error",
            )
            return

        self._empty.setVisible(False)
        self._content.setVisible(True)

        # Stats
        verdict: dict = {}
        if overview:
            lowest = overview.get("lowest")
            median = overview.get("median")
            volume = overview.get("volume")
            ob = page.get("order_book") if page else None
            verdict = steam_api.fair_value_verdict(
                lowest, median,
                spread=ob.get("spread") if ob else None,
                buy_count=ob.get("buy_count") if ob else None,
                sell_count=ob.get("sell_count") if ob else None,
                price_history=page.get("price_history") if page else None,
            )

            v_color = _VERDICT_COLOR.get(verdict.get("verdict", "unknown"),
                                         t.TEXT)
            self._stat_lowest.set_value(t.brl(lowest))
            self._stat_median.set_value(t.brl(median))
            self._stat_verdict.set_value(verdict.get("label", "—"),
                                         accent=v_color)
            self._cache.put(name, lowest)

            # Volume + anomalia
            vol_label = str(volume) if volume else "—"
            vol_color = t.TEXT
            if volume:
                signals.record_item_volume(name, volume)
                hist = signals.load_item_volume(name)
                anom = signals.volume_anomaly(hist)
                if anom.get("is_anomaly"):
                    vol_label = f"{volume}  (anômalo {anom['ratio']:.1f}x)"
                    vol_color = t.WARN
                    self._stat_volume.setToolTip(
                        "Unidades vendidas nas últimas 24h.\n"
                        f"Anomalia detectada: {anom.get('label', '')}"
                    )
            self._stat_volume.set_value(vol_label, accent=vol_color)

        # Charts
        if page:
            price_history = page.get("price_history", [])
            order_book = page.get("order_book")

            if price_history:
                # Entries SSR: {time: unix, price_median: float, purchases}
                series = [(x.get("time"), x["price_median"])
                          for x in price_history if "price_median" in x]
                if series:
                    recent = series[-100:]
                    self._sparkline.set_series(
                        [pr for _, pr in recent],
                        timestamps=[ts for ts, _ in recent],
                    )
                    sma_vals = signals.sma([pr for _, pr in series],
                                           period=7)
                    if sma_vals:
                        self._sparkline.set_sma(sma_vals[-100:])
                    sr = signals.find_support_resistance(price_history[-100:])
                    if sr:
                        self._sparkline.set_sr(sr)
                self._spark_meta.setText(
                    f"{len(price_history)} pontos"
                )

            if order_book:
                self._depth.set_data(order_book)
                buys = order_book.get("buy_count") or 0
                sells = order_book.get("sell_count") or 0
                if buys or sells:
                    supply = sells
                    signals.record_item_supply(name, supply)
                self._depth_meta.setText(
                    f"{buys} compras • {sells} vendas"
                )

        # Detail
        from skinvault.localization import localize_name as _ln
        self._detail_title.setText(_ln(name) if name else "Detalhes do item")
        cs = cases.case_status(name) if name else {}
        cs_label = cs.get("label", "") if cs else ""
        if cs_label:
            self._case_badge.setText(f"Caixa: {cs_label}")
            self._case_badge.setVisible(True)
        else:
            self._case_badge.setVisible(False)

        msg = verdict.get("message") if verdict else None
        if msg:
            self._detail_msg.setText(msg)
            v_color = _VERDICT_COLOR.get(verdict.get("verdict", "unknown"),
                                         t.TEXT)
            self._detail_msg.setStyleSheet(
                f"color: {v_color}; font-size: {t.FS_BODY};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            )
        else:
            self._detail_msg.setText("Dados insuficientes para um veredito.")
            self._detail_msg.setStyleSheet(t.label_body_muted())

        self._clear_detail_grid()
        if overview:
            self._add_detail_row("Menor listagem",
                             t.brl(overview.get("lowest")))
            self._add_detail_row("Mediana 24h",
                             t.brl(overview.get("median")))
            vol = overview.get("volume")
            self._add_detail_row("Volume 24h",
                             str(vol) if vol else "—")
            diff = verdict.get("diff_pct")
            if diff is not None:
                color = t.POSITIVE if diff <= 0 else (
                    t.WARN if diff <= 20 else t.DANGER
                )
                self._add_detail_row("Diferença vs mediana",
                                 f"{diff:+.1f}%", color=color)
        if page:
            ob = page.get("order_book") or {}
            buys = ob.get("buy_count") or 0
            sells = ob.get("sell_count") or 0
            approx = bool(page.get("order_book_approx"))
            approx_tag = "  (aprox. — outro wear)" if approx else ""
            self._add_detail_row("Ordens de compra",
                             f"{buys}{approx_tag}",
                             color=t.WARN if approx else None)
            self._add_detail_row("Listagens à venda",
                             f"{sells}{approx_tag}",
                             color=t.WARN if approx else None)
            if verdict.get("spread_verdict"):
                self._add_detail_row("Spread",
                                 verdict.get("spread_verdict", "—"))
            if verdict.get("book_verdict"):
                self._add_detail_row("Pressão do book",
                                 verdict.get("book_verdict", "—"))
            if verdict.get("trend_verdict"):
                self._add_detail_row("Tendência recente",
                                 verdict.get("trend_verdict", "—"))

        if name:
            self._push_recent(name)
        dur = f" em {elapsed:.1f}s" if elapsed > 0 else ""
        from skinvault.localization import localize_name as _ln
        self._status.setText(f"Atualizado: {_ln(name)}{dur}.")
