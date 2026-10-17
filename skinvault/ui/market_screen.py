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
    QCompleter,
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
from skinvault._paths import DATA_DIR, atomic_write_text
from skinvault.prices import PriceCache
from skinvault.ui import textos
from skinvault.ui import theme as t
from skinvault.ui.components import (
    Card,
    EmptyState,
    LoadingState,
    PageHeader,
    SectionHeader,
    SegmentedControl,
    StatCard,
    Toast,
    set_button_loading,
)
from skinvault.ui.widgets import DepthChart, PriceHistoryChart


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
        atomic_write_text(_RECENT_PATH, json.dumps(items[:8]))
    except OSError:
        pass


_MEDIAN_LABEL = "Preço típico (24h)"
_MEDIAN_LABEL_FALLBACK = "Preço típico (último dia com venda)"

_THROTTLED_MSG = (
    "A Steam limitou as consultas de preço agora. O histórico e o livro de "
    "ofertas vieram da página do item; menor listagem, volume 24h e o "
    "veredito voltam sozinhos quando o limite passar."
)

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
        self._instalar_autocomplete()
        search_row.addWidget(self._search_inp, 1)

        self._search_btn = QPushButton("Consultar item")
        self._search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._search_btn.setStyleSheet(t.btn_primary())
        self._search_btn.setToolTip(
            "Busca o menor preço, o preço típico, quantos foram vendidos "
            "em 24h, o histórico e a fila de ofertas.\nCada consulta leva "
            "uns segundos: a Steam limita quantas podemos fazer."
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
            "o desgaste (ex.: Field-Tested) e StatTrak/Souvenir quando "
            "houver. Atalho: Ctrl+L."
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
        self._stat_median = StatCard(_MEDIAN_LABEL, "—", icon="chart")
        self._stat_median.setToolTip(
            "O preço pelo qual o item costuma ser vendido nas últimas 24h. Serve de referência para saber se está caro ou barato."
        )
        self._stat_volume = StatCard("Volume 24h", "—", icon="archive")
        self._stat_volume.setToolTip(
            "Quantas unidades foram vendidas nas últimas 24h. Acima de "
            "~2000 é fácil vender. Fica marcado quando foge muito (2x) do "
            "normal."
        )
        self._stat_verdict = StatCard("Avaliação", "—", icon="radar")
        self._stat_verdict.setToolTip(
            "Resumo do preço de agora comparado ao preço típico, à fila "
            "de ofertas e à tendência dos últimos dias."
        )
        self._stat_sd = StatCard("Procura × Oferta", "—", icon="chart")
        self._stat_sd_tooltip = (
            "Quantos itens são vendidos por dia comparado a quantos "
            "estão à venda. Abaixo de 1 = tem mais gente vendendo do que "
            "comprando."
        )
        self._stat_sd.setToolTip(self._stat_sd_tooltip)
        for sc in (self._stat_lowest, self._stat_median, self._stat_volume,
                   self._stat_verdict, self._stat_sd):
            sc.setMaximumWidth(280)
            sc.setMaximumHeight(110)
            stats_row.addWidget(sc)
        stats_row.addStretch(1)
        content_lay.addLayout(stats_row)

        # ── Charts ────────────────────────────────────────
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)

        spark_card = Card(self)
        spark_card.setFixedHeight(320)
        spark_lay = QVBoxLayout()
        spark_lay.setSpacing(8)
        # Criado antes do header de proposito: o segmented de intervalo
        # conecta set_range nele, e `connect` resolve o atributo na hora.
        self._price_chart = PriceHistoryChart(parent=spark_card)
        self._price_chart.setMinimumHeight(150)
        spark_hdr = QHBoxLayout()
        spark_lbl = QLabel("Histórico de preços")
        spark_lbl.setStyleSheet(t.label_caption())
        # Tooltip de ajuda fica no label do header — o chart em si mostra
        # tooltip dinâmico (preço + data) ao passar o mouse nos pontos.
        spark_lbl.setToolTip(
            "Série diária completa que a Steam serve, com eixo de preço.\n"
            "Linha tracejada = SMA 7 dias. Linhas horizontais = suporte e "
            "resistência aproximados.\n"
            "Barras embaixo = volume de vendas do dia (verde sobe, vermelho "
            "cai).\n"
            "Passe o mouse sobre o gráfico para ver preço, data e volume."
        )
        spark_hdr.addWidget(spark_lbl)
        spark_hdr.addStretch(1)
        self._range_seg = SegmentedControl()
        self._range_seg.add("7d", "7d")
        self._range_seg.add("30d", "30d")
        self._range_seg.add("all", "Tudo")
        self._range_seg.setToolTip(
            "Janela do histórico: últimos 7 dias, 30 dias ou a série toda "
            "que a Steam mostra.\nCada ponto é um dia: o preço médio "
            "das vendas daquele dia."
        )
        # Conecta ANTES do select: o emit sincrono do select cai no
        # set_range e o chart abre no mesmo intervalo do segmentado.
        # (Nada dispara aqui no Market porque o chart jah existe — este
        # order-of-operations so' importa onde o handler mexe em widget
        # que ainda nao nasceu, ver inventory_screen._apply_view_pref.)
        self._range_seg.segment_changed.connect(self._price_chart.set_range)
        self._range_seg.select("30d")
        spark_hdr.addWidget(self._range_seg)
        self._spark_meta = QLabel("")
        self._spark_meta.setStyleSheet(t.label_caption())
        spark_hdr.addWidget(self._spark_meta)
        spark_lay.addLayout(spark_hdr)
        spark_lay.addWidget(self._price_chart, 1)
        spark_card.layout().addLayout(spark_lay)
        charts_row.addWidget(spark_card)

        depth_card = Card(self)
        depth_card.setFixedHeight(320)
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

    def _nomes_conhecidos(self) -> list:
        """Nomes CRUS que o app ja' conhece: carteira + watchlist.

        Cru e nao localizado de proposito -- e' o `market_hash_name` que a
        Steam entende, e a tela pede exatamente isso.
        """
        nomes = set()
        try:
            from skinvault import portfolio, watchlist
            for p in portfolio.load_portfolio():
                if p.get("name"):
                    nomes.add(p["name"])
            for w in watchlist.load_watchlist():
                if isinstance(w, dict) and w.get("name"):
                    nomes.add(w["name"])
        except Exception:
            # Autocomplete e' conveniencia: se a leitura falhar, o campo
            # continua aceitando o nome digitado.
            return []
        return sorted(nomes)

    def _instalar_autocomplete(self) -> None:
        """Sugere itens da propria carteira enquanto se digita.

        A tela exige o `market_hash_name` EXATO -- com wear e StatTrak no
        lugar certo -- e errar um caractere devolve "sem dados", que se
        confunde com item sem historico. Os 31 itens do dono ja' estao em
        disco; nao ha' motivo pra faze-lo digitar de novo.
        """
        nomes = self._nomes_conhecidos()
        if not nomes:
            return
        comp = QCompleter(nomes, self._search_inp)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # "redline" tem que achar "AK-47 | Redline (Field-Tested)": o nome
        # comeca pela ARMA, e um match so' por prefixo nunca acharia.
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.setMaxVisibleItems(12)
        popup = comp.popup()
        popup.setStyleSheet(
            f"background: {t.BG_ELEVATED}; color: {t.TEXT};"
            f" border: 1px solid {t.BORDER};"
            f" selection-background-color: {t.SURFACE_HOV};"
            f" font-family: {t.FONT_FAMILY}; font-size: {t.FS_BODY};")
        self._search_inp.setCompleter(comp)
        self._completer = comp

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

    def _reset_median_card(self) -> None:
        """Devolve o cartao de mediana ao significado padrao.

        Rotulo e badge sobrevivem entre consultas: sem este reset, um item
        consultado durante o rate limit deixaria "último dia com venda"
        colado no cartao do proximo item, que veio com mediana 24h de fato.
        """
        self._stat_median.set_label(_MEDIAN_LABEL)
        self._stat_median.clear_badge()
        self._stat_median.setToolTip(
            "O preço pelo qual o item costuma ser vendido nas últimas 24h. Serve de referência para saber se está caro ou barato."
        )

    def _fill_median_from_page(self, page: dict) -> None:
        """Preenche a mediana com o último dia do histórico da página.

        Não é a mediana de 24h: é a do último dia em que houve venda, que
        pode ser mais antigo. O rótulo e o badge dizem isso — um número com
        o rótulo errado seria pior que travessão.
        """
        diario = signals.daily_series(page.get("price_history") or [])
        if not diario:
            return
        ultimo = diario[-1]
        preco = ultimo.get("price_median")
        if preco is None:
            return
        self._stat_median.set_label(_MEDIAN_LABEL_FALLBACK)
        self._stat_median.set_value(t.brl(preco), accent=t.TEXT)
        self._stat_median.set_badge("do histórico")
        quando = time.strftime("%d/%m/%Y", time.localtime(ultimo["time"])) \
            if ultimo.get("time") else "data desconhecida"
        self._stat_median.setToolTip(
            "A Steam limitou as consultas de preço, então este valor vem "
            "do histórico da página do item.\n"
            f"Refere-se a {quando}, não às últimas 24h."
        )

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
                    f" (os dados guardados de {_cache_age_label(age)} "
                    "serão atualizados)"
                )
        from skinvault.localization import localize_name as _ln
        self._status.setText(f"Consultando {_ln(name)}…{cache_msg}")
        set_button_loading(self._search_btn, True, "Consultando…")
        self._content.setVisible(False)
        self._empty.setVisible(False)
        self._loading.setVisible(True)
        # Grafico em esqueleto shimmer enquanto a consulta roda; o _on_data
        # desliga quando os dados chegam (via set_data/set_loading False).
        self._price_chart.set_loading(True)
        self._started_at = time.time()

        def _worker():
            # try/except/finally: get_market_page_data faz parsing pesado de
            # SSR (HTML/dict da Steam) com formato que pode mudar sem aviso;
            # uma excecao aqui matava a thread ANTES de emitir data_ready,
            # e o botao "Consultar item" + o spinner ficavam presos pra
            # sempre com a tela em branco (achado no diagnostico da Fase 2).
            data: dict = {"name": name}
            try:
                overview = steam_api.get_market_overview(name)
                if overview:
                    data["overview"] = overview
                page = steam_api.get_market_page_data(name)
                if page:
                    data["page"] = page
            except Exception as exc:
                data["error"] = str(exc)
            finally:
                self._bridge.data_ready.emit(data)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_clear(self) -> None:
        self._search_inp.clear()
        self._search_inp.setFocus()
        self._loading.setVisible(False)
        self._empty.setVisible(False)
        self._content.setVisible(True)
        for sc in (self._stat_lowest, self._stat_median, self._stat_volume,
                   self._stat_verdict, self._stat_sd):
            sc.set_value("—", accent=t.TEXT)
        self._stat_sd.setToolTip(self._stat_sd_tooltip)
        self._reset_median_card()
        self._price_chart.set_loading(False)
        self._price_chart.set_data([])
        self._depth.set_data({})
        self._spark_meta.setText("")
        self._spark_meta.setToolTip("")
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
        # set_button_loading(False) roda incondicionalmente, ANTES de
        # olhar sucesso/erro -- o _worker agora tem try/finally e sempre
        # chega aqui, entao o botao nunca mais fica preso desabilitado.
        set_button_loading(self._search_btn, False)
        self._loading.setVisible(False)
        self._price_chart.set_loading(False)
        name = data.get("name", "")
        overview = data.get("overview")
        page = data.get("page")
        elapsed = time.time() - self._started_at if self._started_at else 0.0

        if not overview and not page:
            self._content.setVisible(False)
            self._empty.setVisible(True)
            erro = data.get("error")
            msg = (
                f"Erro ao consultar “{name}”: {erro}" if erro else
                f"Não foi possível obter dados de “{name}”. "
                "Verifique o nome (wear, StatTrak, espaços) ou tente novamente."
            )
            Toast.show_toast(self, msg, "error")
            return

        self._empty.setVisible(False)
        self._content.setVisible(True)

        # Stats
        verdict: dict = {}
        # `page` sem `overview` significa que o nome existe (a pagina do item
        # resolveu) mas o priceoverview nao respondeu -- rate limit ou rede,
        # nunca item invalido. Da' pra mostrar algo em vez de quatro
        # travessoes e um "dados insuficientes" que sugere culpa do usuario.
        throttled = bool(page) and not overview
        self._reset_median_card()
        volume = None
        supply = None
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
        elif throttled:
            self._fill_median_from_page(page)

        # Charts
        if page:
            price_history = page.get("price_history", [])
            order_book = page.get("order_book")

            if price_history:
                # Entries SSR: {time: unix, price_median: float, purchases}
                # A Steam serve pontos HORARIOS nos ultimos ~28 dias e
                # DIARIOS no antigo -- fatiar por contagem mostraria ~4 dias
                # no lugar de ~100, e a SMA de 7 periodos viraria media de 7
                # horas. Agrega por dia quando ha' timestamp; sem timestamp,
                # mantem o corte antigo (ultimos 100 pontos crus).
                diario = signals.daily_series(price_history)
                if diario:
                    todos = [d["price_median"] for d in diario]
                    sma_vals = signals.sma(todos, period=7)
                    sr = signals.find_support_resistance(diario[-100:])
                    self._price_chart.set_data(diario)
                    self._price_chart.set_sma(sma_vals)
                    if sr:
                        self._price_chart.set_sr(sr)
                else:
                    recent = [(x.get("time"), x["price_median"],
                               x.get("purchases"))
                              for x in price_history
                              if "price_median" in x]
                    recent = recent[-100:]
                    pts = [{"time": ts, "price_median": pr, "purchases": v}
                           for ts, pr, v in recent]
                    if len(pts) >= 2:
                        self._price_chart.set_data(pts)
                self._spark_meta.setText(
                    f"{len(price_history)} pontos"
                )
                # Z-score: testado como fator de score e descartado
                # (drawdown ja' captura o mesmo sinal); segue disponivel
                # como dado bruto informativo, sem influenciar o veredito.
                zs = signals.price_zscore(price_history)
                if zs:
                    self._spark_meta.setToolTip(
                        f"{zs['label']} vs média móvel de "
                        f"{zs['window_used']}d (R$ {zs['mean']:.2f} ± "
                        f"{zs['std']:.2f}).\nNão é fator do veredito — "
                        "descreve o desvio estatístico, não prevê."
                    )
                else:
                    self._spark_meta.setToolTip("")

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

        # Oferta/Demanda: precisa de volume (overview) e supply (order
        # book), calculados em blocos separados acima -- so' da' pra
        # montar depois dos dois.
        sd = signals.supply_demand_ratio(volume, supply)
        if sd.get("ratio"):
            self._stat_sd.set_value(sd["label"])
            tip = self._stat_sd_tooltip
            if supply:
                depth = signals.liquidity_depth(
                    supply, signals.load_item_volume(name))
                if depth:
                    tip = f"{tip}\n\n{depth['label']}"
            self._stat_sd.setToolTip(tip)

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
        elif throttled:
            self._detail_msg.setText(_THROTTLED_MSG)
            self._detail_msg.setStyleSheet(
                f"color: {t.WARN}; font-size: {t.FS_BODY};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            )
        else:
            self._detail_msg.setText("Dados insuficientes para um veredito.")
            self._detail_msg.setStyleSheet(t.label_body_muted())

        self._clear_detail_grid()
        if overview:
            self._add_detail_row("Menor anúncio",
                             t.brl(overview.get("lowest")))
            self._add_detail_row("Preço típico (24h)",
                             t.brl(overview.get("median")))
            vol = overview.get("volume")
            self._add_detail_row("Volume 24h",
                             str(vol) if vol else "—")
            diff = verdict.get("diff_pct")
            if diff is not None:
                color = t.POSITIVE if diff <= 0 else (
                    t.WARN if diff <= 20 else t.DANGER
                )
                self._add_detail_row("Diferença vs preço típico",
                                 f"{diff:+.1f}%", color=color)
        if page:
            ob = page.get("order_book") or {}
            buys = ob.get("buy_count") or 0
            sells = ob.get("sell_count") or 0
            approx = bool(page.get("order_book_approx"))
            approx_tag = "  (aprox. — outro desgaste)" if approx else ""
            self._add_detail_row("Pedidos de compra",
                             f"{buys}{approx_tag}",
                             color=t.WARN if approx else None)
            self._add_detail_row("Anúncios à venda",
                             f"{sells}{approx_tag}",
                             color=t.WARN if approx else None)
            if verdict.get("spread_verdict"):
                self._add_detail_row(
                    "Diferença compra/venda",
                    textos.traduz(textos.SPREAD, verdict["spread_verdict"]))
            if verdict.get("book_verdict"):
                self._add_detail_row(
                    "Fila de ofertas",
                    textos.traduz(textos.BOOK, verdict["book_verdict"]))
            if verdict.get("trend_verdict"):
                self._add_detail_row(
                    "Tendência recente",
                    textos.traduz(textos.TREND, verdict["trend_verdict"]))

        if name:
            self._push_recent(name)
        dur = f" em {elapsed:.1f}s" if elapsed > 0 else ""
        from skinvault.localization import localize_name as _ln
        self._status.setText(f"Atualizado: {_ln(name)}{dur}.")
