"""Tela 1 - Minha Conta + Inventario (F11).

Header: 4 stat cards da carteira.
Corpo: filtro + tabela inventario.

2026-08-07: a secao de perfil/sessao Steam (avatar, nome, SteamID, botao
"Sincronizar com Steam") foi removida junto com o login (F10 revertido --
ver ROADMAP.md). O portfolio manual + avaliacao via preco publico nunca
dependeram de sessao.

Reusa:
  portfolio.load_portfolio / evaluate_portfolio
  prices.PriceCache
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import backtest as backtest_mod
from skinvault import portfolio as portfolio_mod
from skinvault import (
    cases, history, markets, prices, reports, signals, ssr_cache, steam_api,
)
from skinvault.ui import theme as t
from skinvault.ui._price_worker import PriceWorker
from skinvault.ui.exporter import build_export_menu, save_export
from skinvault.ui.fee_calculator_dialog import FeeCalculatorDialog
from skinvault.ui.goals_card import GoalsCard
from skinvault.ui.inventory_grid import InventoryGrid
from skinvault.ui.components import (
    Card, EmptyState, LoadingState, PageHeader, SegmentedControl,
    StatCard, Toast,
)
from skinvault.ui.toast import ToastManager
from skinvault.ui.widgets import CompositionChart, ValueChart


class _PortfolioValidationBridge(QObject):
    samples_ready = pyqtSignal(list)
    progress = pyqtSignal(str)
    finished = pyqtSignal()


class AccountScreen(QWidget):
    """Tela 1 -- Minha Conta + Inventario."""

    # (rows, positions) ja' avaliados. Quem consome e' a InventoryScreen --
    # esta tela mantem o PriceWorker porque avaliar em dois lugares
    # dobraria o custo num endpoint rate-limited.
    # (rows, positions, rate_limited). O terceiro campo existe porque "31
    # itens sem preco" e "a Steam bloqueou" sao indistinguiveis na tabela.
    inventory_ready = pyqtSignal(list, list, bool)
    # Progresso da avaliacao (done, total). A InventoryScreen precisa disso
    # pra distinguir "ainda avaliando" de "vazio" -- sob rate limit da Steam
    # a avaliacao leva minutos, e o estado intermediario e' o que mais
    # aparece pro usuario.
    inventory_progress = pyqtSignal(int, int)

    def __init__(self, cache: prices.PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._validate_bridge = _PortfolioValidationBridge()
        self._validate_bridge.samples_ready.connect(
            self._on_validate_samples,
        )
        self._validate_bridge.progress.connect(self._on_validate_progress)
        self._validate_bridge.finished.connect(self._on_validate_finished)
        self._validate_samples: list[dict] = []
        self._validate_items_count: int = 0
        self._validating = False
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._on_refresh_scores)
        # Preenchido por _reload_value_series: sem serie desenhada, o
        # ValueChart fica em esqueleto durante a avaliacao.
        self._vc_tem_pontos = False
        self._series_export: list[dict] = []
        self._price_worker = PriceWorker(cache, self)
        self._price_worker.eval_done.connect(self._on_eval)
        self._price_worker.progress.connect(self._on_eval_progress)
        self._build()
        self._reload_activity()
        self._start_schedule()

    # ── construcao do layout ──────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        # PageHeader
        act_lbl = QHBoxLayout()
        act_lbl.setContentsMargins(0, 0, 0, 0)
        act_lbl.setSpacing(t.SPACE_SM)

        self._validate_btn = QPushButton("Validar score")
        self._validate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._validate_btn.setStyleSheet(t.btn_secondary(padding="8px 14px",
                                                          fs=t.FS_INPUT))
        self._validate_btn.setToolTip(
            "Roda backtest histórico (90d) nos itens do seu portfolio."
            " Mostra se o score realmente prediz retornos pros itens"
            " que você possui. Usa cache 24h, então reruns são rápidos."
        )
        self._validate_btn.clicked.connect(self._on_validate_portfolio)
        act_lbl.addWidget(self._validate_btn)

        self._refresh_btn = QPushButton("Atualizar scores")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(t.btn_ghost())
        self._refresh_btn.setToolTip(
            "Recomputa scores de todos os itens usando dados do cache."
            " Mais rápido que Validar score — não mostra dialog de backtest."
        )
        self._refresh_btn.clicked.connect(self._on_refresh_scores)
        act_lbl.addWidget(self._refresh_btn)

        self._calc_btn = QPushButton("Calculadora de taxas")
        self._calc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._calc_btn.setStyleSheet(t.btn_ghost())
        self._calc_btn.setToolTip(
            "Quanto sobra líquido em cada plataforma e por quanto listar\n"
            "pra receber a margem desejada. Steam é saldo — não saca.\n"
            "Taxas são defaults editáveis (Skinport 12%, CS.MONEY 5%)."
        )
        self._calc_btn.clicked.connect(self._on_open_calculator)
        act_lbl.addWidget(self._calc_btn)

        act_w = QWidget()
        act_w.setLayout(act_lbl)
        root.addWidget(PageHeader(
            "Minha Conta",
            "Inventário e desempenho da carteira.",
            actions=[act_w],
        ))

        # Header card (stat cards da carteira)
        header = Card(self)

        # Stat cards row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self._stat_gross = StatCard("Valor bruto", "—",
                                     icon="wallet")
        self._stat_gross.setMaximumWidth(300)
        self._stat_gross.setToolTip(
            "Valor de mercado da carteira (Steam Market).")
        self._stat_net = StatCard("Valor líquido", "—",
                                   accent=t.STEAM_BLUE, icon="coins")
        self._stat_net.setMaximumWidth(300)
        self._stat_net.setToolTip(
            "Valor bruto menos a taxa Steam de 15%.")
        self._stat_pnl = StatCard("P&L total", "—", icon="chart")
        self._stat_pnl.setMaximumWidth(300)
        self._stat_items = StatCard("Total de itens", "0", icon="archive")
        self._stat_items.setMaximumWidth(300)
        for sc in (self._stat_gross, self._stat_net, self._stat_pnl,
                   self._stat_items):
            stats_row.addWidget(sc)
        stats_row.addStretch(1)
        header.layout().addLayout(stats_row)

        root.addWidget(header)

        # Portfolio breakdown card
        breakdown_card = Card(self, padding=t.CARD_PAD_MD)
        bd_lay = QVBoxLayout()
        bd_lay.setSpacing(8)
        bd_title = QLabel("Desempenho da carteira")
        bd_title.setStyleSheet(t.label_section())
        bd_lay.addWidget(bd_title)

        bd_row = QHBoxLayout()
        bd_row.setSpacing(20)
        self._bd_invested = StatCard("Total investido", "—")
        self._bd_invested.setMaximumWidth(300)
        self._bd_profit_count = StatCard("Itens no lucro", "—",
                                         accent=t.POSITIVE)
        self._bd_profit_count.setMaximumWidth(300)
        self._bd_loss_count = StatCard("Itens no prejuizo", "—",
                                       accent=t.DANGER)
        self._bd_loss_count.setMaximumWidth(300)
        self._bd_best = StatCard("Melhor P&L", "—")
        self._bd_best.setMaximumWidth(300)
        self._bd_worst = StatCard("Pior P&L", "—", accent=t.DANGER)
        self._bd_worst.setMaximumWidth(300)
        for sc in (self._bd_invested, self._bd_profit_count,
                   self._bd_loss_count, self._bd_best, self._bd_worst):
            bd_row.addWidget(sc)
        bd_row.addStretch(1)
        bd_lay.addLayout(bd_row)

        breakdown_card.layout().addLayout(bd_lay)
        self._breakdown_card = breakdown_card
        # Os cartoes de cima informam; o inventario e' o objetivo da tela.
        # Sem travar a altura deles, sobravam ~150px pra lista -- 5 linhas
        # visiveis num monitor de 1080p.
        for card in (header, breakdown_card):
            card.setSizePolicy(QSizePolicy.Policy.Preferred,
                               QSizePolicy.Policy.Maximum)
        root.addWidget(breakdown_card)

        # Metas financeiras: barra de progresso por meta, reativa a cada
        # avaliacao (refresh_from(totals) no _on_eval). Altura travada pra
        # nao espremer a faixa de graficos — o card cabe entre o desempenho
        # e a evolucao.
        self._metas_card = GoalsCard(self)
        self._metas_card.setSizePolicy(QSizePolicy.Policy.Preferred,
                                       QSizePolicy.Policy.Maximum)
        root.addWidget(self._metas_card)

        # ── Evolucao + composicao, lado a lado ────────────────
        #
        # Estes dois cartoes ocupam a metade de baixo da tela, que ficou
        # vazia quando o inventario virou aba propria em 28/07. O grafico
        # de valor morava espremido em 90px dentro do cartao de desempenho,
        # teto posto quando ele disputava altura com a lista -- disputa que
        # nao existe mais.
        fundo = QHBoxLayout()
        fundo.setSpacing(16)

        chart_card = Card(self, padding=t.CARD_PAD_MD)
        ch_lay = QVBoxLayout()
        ch_lay.setSpacing(8)
        self._value_chart = ValueChart()
        self._value_chart.setMinimumHeight(150)

        ch_head = QHBoxLayout()
        ch_title = QLabel("Evolução do valor")
        ch_title.setStyleSheet(t.label_section())
        ch_head.addWidget(ch_title)
        ch_head.addStretch(1)
        # Filtro rapido de periodo: recorta a MESMA serie carregada por
        # _reload_value_series, sem re-ler o disco -- so' o que o widget
        # ja' tem em memoria.
        self._vc_range_seg = SegmentedControl()
        self._vc_range_seg.add("1d", "1D")
        self._vc_range_seg.add("7d", "7D")
        self._vc_range_seg.add("30d", "1M")
        self._vc_range_seg.add("365d", "1A")
        self._vc_range_seg.add("all", "Tudo")
        self._vc_range_seg.setToolTip(
            "Filtra o gráfico de evolução do valor por período.")
        self._vc_range_seg.segment_changed.connect(self._value_chart.set_range)
        self._vc_range_seg.select("all")
        ch_head.addWidget(self._vc_range_seg)

        # Exportar a série de valor (CSV/JSON) — o "histórico do portfólio"
        # mora aqui. Ghost: leitura/navegação não pede destaque.
        self._hist_export_btn = QPushButton("Exportar histórico")
        self._hist_export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_export_btn.setStyleSheet(
            t.btn_ghost(padding="4px 12px", fs=t.FS_MUTED))
        self._hist_export_btn.setToolTip(
            "Salva a série de avaliações do valor da carteira "
            "(CSV ou JSON).\nPonto por avaliação — a mesma série do gráfico.")
        self._hist_export_btn.clicked.connect(self._on_export_history)
        ch_head.addWidget(self._hist_export_btn)
        ch_lay.addLayout(ch_head)

        self._vc_lbl = QLabel(
            "Valor bruto da carteira — cada avaliação grava um ponto")
        self._vc_lbl.setStyleSheet(t.label_caption())
        ch_lay.addWidget(self._vc_lbl)
        ch_lay.addWidget(self._value_chart, 1)
        chart_card.layout().addLayout(ch_lay)
        fundo.addWidget(chart_card, 3)

        comp_card = Card(self, padding=t.CARD_PAD_MD)
        cp_lay = QVBoxLayout()
        cp_lay.setSpacing(8)
        cp_title = QLabel("Composição da carteira")
        cp_title.setStyleSheet(t.label_section())
        cp_lay.addWidget(cp_title)
        self._comp_lbl = QLabel("Onde estão os seus itens")
        self._comp_lbl.setStyleSheet(t.label_caption())
        cp_lay.addWidget(self._comp_lbl)
        self._comp_chart = CompositionChart()
        cp_lay.addWidget(self._comp_chart)
        cp_lay.addStretch(1)
        comp_card.layout().addLayout(cp_lay)
        fundo.addWidget(comp_card, 2)

        # Caixas: o unico painel desta tela que continua inteiro sob rate
        # limit -- estado de drop vem do catalogo local, nao da Steam. E' a
        # tese que a pesquisa sustenta (container recem-aposentado).
        cx_card = Card(self, padding=t.CARD_PAD_MD)
        cx_lay = QVBoxLayout()
        cx_lay.setSpacing(8)
        cx_title = QLabel("Caixas e cápsulas")
        cx_title.setStyleSheet(t.label_section())
        cx_lay.addWidget(cx_title)
        self._cx_lbl = QLabel("Containers da carteira e o estado do drop")
        self._cx_lbl.setStyleSheet(t.label_caption())
        cx_lay.addWidget(self._cx_lbl)
        self._cx_lista = QLabel("—")
        self._cx_lista.setTextFormat(Qt.TextFormat.RichText)
        self._cx_lista.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cx_lista.setWordWrap(True)
        self._cx_lista.setStyleSheet(f"font-size: {t.FS_MUTED};")
        cx_lay.addWidget(self._cx_lista)
        cx_lay.addStretch(1)
        cx_card.layout().addLayout(cx_lay)
        fundo.addWidget(cx_card, 2)

        root.addLayout(fundo, 1)
        self._reload_value_series()

        # Coluna esquerda (filtro + tabela + status) + ActivityFeed lateral
        split = QHBoxLayout()
        split.setSpacing(16)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Filtro, grade, tabela e empty state migraram pra InventoryScreen
        # em 28/07/2026. Aqui eles disputavam espaco com perfil, quatro
        # cartoes de valor, cinco de desempenho e um grafico -- sobrava
        # rodape pro conteudo principal. Esta tela agora avalia e repassa
        # via `inventory_ready`.

        # Progress bar (indeterminate, hidden by default)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background: {t.SURFACE}; border: none;"
            f" border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {t.ACCENT};"
            " border-radius: 3px; }}"
        )
        left_col.addWidget(self._progress)

        # Loading state (mostrado durante validacao)
        self._loading = LoadingState(parent=self)
        self._loading.setVisible(False)
        left_col.addWidget(self._loading, 0, Qt.AlignmentFlag.AlignCenter)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(t.label_caption())
        left_col.addWidget(self._status)

        # Sem coluna lateral: o inventario usa a largura inteira.
        #
        # Aqui existia um ActivityFeed. Removido em 28/07/2026 porque tudo
        # que ele mostrava ja' existia com mais contexto em outro lugar --
        # trades e eventos de mercado na tela de Historico, alertas no log
        # da Watchlist, ranking na coluna DeltaPos do Scanner. Numa tela
        # cujo objetivo e' o inventario, ele custava metade da largura pra
        # repetir informacao. O modulo activity.py continua existindo; se
        # voltar, o lugar e' um dashboard, nao esta tela.
        # Sem stretch aqui: quem estica agora e' a faixa de graficos acima.
        # Com o stretch nos dois, o espaco livre ia metade pra um rodape
        # que tem tres widgets de altura fixa.
        split.addLayout(left_col, 1)
        root.addLayout(split, 0)

    def _on_open_calculator(self) -> None:
        dlg = FeeCalculatorDialog(parent=self)
        dlg.exec()

    def _on_export_history(self) -> None:
        if not self._series_export:
            self._status.setText("Nada para exportar — ainda não há avaliações.")
            return
        serie = self._series_export
        menu = build_export_menu(
            self._hist_export_btn,
            [("Exportar CSV", lambda: self._do_export_history("csv", serie)),
             ("Exportar JSON", lambda: self._do_export_history("json", serie))],
        )
        menu.exec(self._hist_export_btn.mapToGlobal(
            self._hist_export_btn.rect().bottomLeft()))

    def _do_export_history(self, kind: str, serie: list[dict]) -> None:
        conteudo = (reports.history_csv(serie) if kind == "csv"
                    else reports.history_json(serie))
        path, erro = save_export(self, "historico_portfolio", kind, conteudo)
        if erro:
            self._status.setText(f"Erro ao exportar: {erro}")
        elif path:
            self._status.setText(f"Exportado: {path}")
            ToastManager.instance().show_success(
                self, "Relatório exportado com sucesso!")

    # ── avaliacao de inventario ──────────────────────────
    def refresh(self) -> None:
        """Avalia portfolio em thread e atualiza tabela + stats."""
        self._progress.setVisible(True)
        self._status.setText("Avaliando inventário...")
        self.inventory_progress.emit(0, 0)
        # Sem serie desenhada ainda, o grafico de valor fica em esqueleto
        # shimmer enquanto a avaliacao roda (ela alimenta o proximo ponto
        # do historico). Com serie na tela, manter a linha -- reavaliar
        # nao deve apagar o que o usuario esta' lendo.
        self._value_chart.set_loading(not self._vc_tem_pontos)
        self._price_worker.start()
        self._reload_activity()

    def _reload_activity(self) -> None:
        """No-op: o feed saiu da tela de conta (ver comentario no _build).

        Mantido como metodo vazio porque e' chamado no __init__ e no ciclo
        de avaliacao; remover as chamadas tambem so' espalharia o diff.
        """
        return

    def _reload_value_series(self) -> None:
        """Recarrega data/history.json no grafico de evolucao do valor.

        O piso pra desenhar e' 3 e nao 2 de proposito: dois pontos viram
        uma reta, que nao informa tendencia nenhuma e ainda aparece como
        uma diagonal vermelha atravessando a tela.

        Abaixo disso o grafico NAO some mais -- ele diz quantos pontos ja'
        existem. Sumir fazia sentido quando ele disputava altura com o
        inventario; agora que tem cartao proprio, esconder deixava um
        cartao so' com titulo, que parece defeito.
        """
        series = history.load_history()
        self._series_export = series
        pontos = [p.get("total", 0.0) for p in series]
        # Timestamp habilita o filtro de periodo (1D/7D/1M/1A/Tudo) no
        # chart -- sem ele set_range() nao teria o que cortar.
        tss = [p.get("ts") for p in series]
        self._vc_tem_pontos = len(pontos) >= 3
        self._value_chart.set_loading(False)
        self._value_chart.set_series(pontos, tss)
        if self._vc_tem_pontos:
            self._vc_lbl.setText(
                "Valor bruto da carteira — cada avaliação grava um ponto")
        else:
            self._vc_lbl.setText(
                "A evolução aparece a partir de 3 avaliações")

    # Cobertura minima pra considerar a avaliacao boa o bastante pro
    # historico. Nao e' 100% porque item sem mercado na Steam existe de
    # verdade (souvenir sem liquidez) e travaria o grafico pra sempre.
    _COBERTURA_MINIMA = 0.9

    @staticmethod
    def _avaliacao_completa(rows: list) -> bool:
        """True se preco suficiente pra o total representar a carteira."""
        if not rows:
            return False
        com_preco = sum(1 for r in rows if r.get("price") is not None)
        return (com_preco / len(rows)) >= AccountScreen._COBERTURA_MINIMA

    def _record_value_snapshot(self, total: float) -> None:
        """Grava ponto de valor — pula se igual ao ultimo (o schedule de
        30min re-avalia com cache; sem o dedup o arquivo encheria de
        pontos repetidos)."""
        series = history.load_history()
        if series and series[-1].get("total") == float(total):
            return
        history.record_snapshot(total)

    def _on_eval_progress(self, done: int, total: int) -> None:
        self._status.setText(f"Avaliando inventário... {done}/{total}")
        self.inventory_progress.emit(done, total)

    # ── Validar score ───────────────────────
    def _on_refresh_scores(self) -> None:
        """Atualiza scores do portfolio silenciosamente (sem dialog)."""
        self._refresh_mode = True
        self._on_validate_portfolio()

    def _on_validate_portfolio(self) -> None:
        if self._validating:
            return
        positions = portfolio_mod.load_portfolio()
        names = sorted({p["name"] for p in positions})
        if not names:
            self._status.setText(
                "Portfolio vazio. Sincronize ou adicione posições primeiro."
            )
            return
        self._validate_samples = []
        self._validate_items_count = len(names)
        self._validate_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._loading.set_label(f"Validando {len(names)} itens...")
        self._loading.setVisible(True)
        bridge = self._validate_bridge
        cache = ssr_cache.PriceHistoryCache()
        positions_snapshot = positions

        def _worker() -> None:
            try:
                name_to_score: dict[str, tuple[int, float]] = {}
                name_to_exit: dict[str, dict] = {}
                for i, name in enumerate(names, start=1):
                    hit = cache.has(name)
                    tag = "cache" if hit else "buscando"
                    bridge.progress.emit(
                        f"Validando [{i}/{len(names)}] {name} ({tag})"
                    )
                    try:
                        ph = ssr_cache.cached_price_history(name, cache=cache)
                    except Exception as e:
                        print(f"WARNING: account price_history({name}) failed: {e}",
                              file=__import__('sys').stderr)
                        ph = None
                    if ph:
                        try:
                            samples = backtest_mod.simulate_item(name, ph)
                        except Exception as e:
                            print(f"WARNING: account simulate({name}) failed: {e}",
                                  file=__import__('sys').stderr)
                            samples = []
                        if samples:
                            bridge.samples_ready.emit(samples)
                        # Computa current_score pra persistir
                        try:
                            cs = backtest_mod.score_from_history(name, ph)
                        except Exception as e:
                            print(f"WARNING: account score({name}) failed: {e}",
                                  file=__import__('sys').stderr)
                            cs = None
                        if cs is not None:
                            name_to_score[name] = (int(cs), time.time())
                        # Contexto de saida (distancia do topo) sai do MESMO
                        # historico -- zero requisicao extra. So' numeros;
                        # o texto e' montado na tela.
                        ctx = signals.exit_context(
                            ph, is_container=cases.is_container(name))
                        if ctx:
                            name_to_exit[name] = {
                                "pct_of_ath": ctx["pct_of_ath"],
                                "ath": ctx["ath"],
                                "current": ctx["current"],
                                "at_launch": ctx["at_launch"],
                                "ts": time.time(),
                            }
                    if not hit:
                        time.sleep(steam_api.RATE_LIMIT_DELAY_S)
                # Atualiza positions com scores e persiste
                for p in positions_snapshot:
                    n = p.get("name")
                    if n in name_to_score:
                        cs, ts = name_to_score[n]
                        p["current_score"] = cs
                        p["score_ts"] = ts
                    if n in name_to_exit:
                        p["exit_ctx"] = name_to_exit[n]
                try:
                    portfolio_mod.save_portfolio(positions_snapshot)
                except Exception:
                    pass
            finally:
                bridge.finished.emit()

        self._validating = True
        threading.Thread(target=_worker, daemon=True).start()

    def _on_validate_progress(self, msg: str) -> None:
        self._loading.set_label(msg)
        self._status.setText(msg)

    def _on_validate_samples(self, samples: list) -> None:
        self._validate_samples.extend(samples)

    def _on_validate_finished(self) -> None:
        self._validating = False
        self._loading.setVisible(False)
        self._validate_btn.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        n = len(self._validate_samples)
        items_n = self._validate_items_count
        self._status.setText(
            f"Validação concluída: {n} amostras de {items_n} itens"
        )
        refresh = getattr(self, "_refresh_mode", False)
        if refresh:
            self._refresh_mode = False
            # Refresh = recalcula scores, persiste, atualiza tabela.
            positions = portfolio_mod.load_portfolio()
            result = portfolio_mod.evaluate_portfolio(positions,
                                                       lambda n: None)
            rows = result["rows"]
            # _on_eval ja' repassa pra InventoryScreen via inventory_ready.
            self._on_eval({"rows": rows, "totals": result["totals"],
                          "positions": positions})
            return
        # Reusa o dialog do scanner pra manter UX coerente
        from skinvault.ui.scanner_dialogs import _BacktestResultDialog
        dlg = _BacktestResultDialog(
            self._validate_samples, items_n, parent=self,
        )
        dlg.exec()

    # ── Schedule automatico ──────────────────────────────
    def _start_schedule(self) -> None:
        from skinvault.settings import load_settings as _ls
        interval = _ls().get("validate_interval_minutes", 30)
        if interval <= 0:
            self._schedule_timer.stop()
            return
        self._schedule_timer.setInterval(interval * 60_000)
        self._schedule_timer.start()

    def _stop_schedule(self) -> None:
        self._schedule_timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._start_schedule()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._stop_schedule()

    def _on_eval(self, data: dict) -> None:
        rows = data["rows"]
        totals = data["totals"]
        positions = data.get("positions", [])
        self._progress.setVisible(False)
        # Toggle empty state: sem rows mostra hero
        is_empty = not rows
        # "Sem cotacao" nao e' "vale zero". Com a Steam racionada todos os
        # precos vem None; exibir R$ 0,00 afirma que a carteira nao vale
        # nada, e um delta do historico colado nesse zero (o "+1,5% vs
        # 04/06") lia-se como variacao do numero exibido.
        com_preco = [r for r in rows if r.get("price") is not None]
        sem_cotacao = bool(rows) and not com_preco
        dica_sem_cotacao = (
            f"Nenhum dos {len(rows)} itens tem preço agora — a Steam não\n"
            "respondeu às consultas. O valor volta quando a cotação voltar.")

        # Atualiza stats
        if sem_cotacao:
            # Legenda visivel, nao so' tooltip: tres cartoes em "—" lado a
            # lado parecem tela quebrada, e ninguem passa o mouse pra
            # descobrir que o motivo e' a Steam.
            self._stat_gross.set_value("—")
            self._stat_gross.set_delta(None, "a Steam não respondeu")
            self._stat_gross.setToolTip(dica_sem_cotacao)
            self._stat_net.set_value("—")
            self._stat_net.set_delta(None, "a Steam não respondeu")
            self._stat_net.setToolTip(dica_sem_cotacao)
        else:
            self._stat_gross.setToolTip(
                "Valor de mercado da carteira (Steam Market).")
            self._stat_net.setToolTip(
                "Valor bruto menos a taxa Steam de 15%.")
            self._stat_net.set_delta(None, "já com a taxa de 15%")
            self._stat_gross.set_value(t.brl(totals.get("market") or 0))
            # Delta do valor bruto vs penultimo ponto do historico
            _series = history.load_history()
            if len(_series) >= 2:
                _prev = _series[-2].get("total", 0) or 0
                _curr = _series[-1].get("total", 0) or 0
                _prev_ts = _series[-2].get("ts", 0)
                if _prev and _curr:
                    # Diz CONTRA O QUE esta' comparando. Sem a data,
                    # "-79,6%" parecia queda de hoje quando comparava dois
                    # pontos de junho.
                    _quando = (time.strftime("%d/%m",
                                             time.localtime(_prev_ts))
                               if _prev_ts else "")
                    self._stat_gross.set_delta(
                        (_curr - _prev) / _prev * 100,
                        f"vs {_quando}" if _quando else "",
                    )
                else:
                    self._stat_gross.set_delta(None)
            else:
                self._stat_gross.set_delta(None)
            self._stat_net.set_value(t.brl(totals.get("net_if_sold") or 0),
                                     accent=t.STEAM_BLUE)
        # P&L so' existe onde ha' custo. Item vindo do sync tem custo
        # DESCONHECIDO (a Steam nao informa), e exibir R$ 0,00 como se fosse
        # o custo transformava o inventario inteiro em "lucro".
        pnl = totals.get("pnl")
        com_custo = [r for r in rows if r.get("has_cost")]
        sem_custo = totals.get("unknown_cost") or 0
        if pnl is None:
            self._stat_pnl.set_value("—")
            self._stat_pnl.clear_badge()
            # Sem legenda ele era o unico travessao mudo da fileira, entre
            # dois vizinhos que ja' dizem o motivo.
            if not com_custo:
                self._stat_pnl.set_delta(None, "precisa de custo declarado")
            elif sem_cotacao:
                self._stat_pnl.set_delta(None, "a Steam não respondeu")
            else:
                self._stat_pnl.set_delta(None, "sem preço para calcular")
            # Duas razoes diferentes zeram o P&L, e dizer a errada manda o
            # dono cadastrar um custo que ele ja' cadastrou.
            if not com_custo:
                self._stat_pnl.setToolTip(
                    f"Nenhum dos {len(rows)} itens tem custo registrado.\n"
                    "Itens vindos do sync não trazem quanto você pagou — sem\n"
                    "isso não dá pra dizer se houve lucro ou prejuízo.\n"
                    "Informe o custo na aba Inventário, coluna Custo.")
            elif not any(r.get("price") is not None for r in com_custo):
                self._stat_pnl.setToolTip(
                    f"{len(com_custo)} de {len(rows)} itens tem custo "
                    "registrado, mas\nnenhum deles tem preço agora — a Steam "
                    "não respondeu.\nO P&L volta quando a cotação voltar.")
            else:
                self._stat_pnl.setToolTip(
                    f"Calculado sobre {len(com_custo)} de {len(rows)} itens.\n"
                    f"{sem_custo} sem custo registrado ficaram de fora.")
        else:
            # Com P&L de verdade, o badge de porcentagem ja' diz tudo -- a
            # legenda do ramo vazio nao pode sobrar aqui.
            self._stat_pnl.set_delta(None)
            self._stat_pnl.set_value(
                t.brl(pnl), accent=t.POSITIVE if pnl >= 0 else t.DANGER)
            pnl_pct = totals.get("pnl_pct")
            if pnl_pct is not None:
                sign = "+" if pnl_pct >= 0 else ""
                self._stat_pnl.set_badge(
                    f"{sign}{pnl_pct:.1f}%",
                    "positive" if pnl_pct >= 0 else "danger")
            else:
                self._stat_pnl.clear_badge()
            self._stat_pnl.setToolTip(
                f"Calculado sobre {len(com_custo)} de {len(rows)} itens.\n"
                f"{sem_custo} sem custo registrado ficaram de fora.")
        self._stat_items.set_value(str(len(rows)))
        # "31" sozinho nao diz se e' carteira concentrada ou espalhada; a
        # composicao ja' esta' calculada logo abaixo.
        _cats = len(portfolio_mod.composition(rows))
        self._stat_items.set_delta(
            None, f"em {_cats} categoria{'s' if _cats != 1 else ''}"
            if _cats else "")

        # Portfolio breakdown -- tudo aqui e' sobre P&L, entao so' conta
        # item com custo conhecido. Denominador tambem: "0 de 25" mentiria.
        #
        # Mas "0 de 2" sozinho tambem mentia, por omissao: lido de relance
        # parece que a carteira tem 2 itens, quando tem 31 e apenas 2 com
        # custo declarado. O numero fica; o denominador ganha a legenda que
        # diz de onde ele saiu.
        n = len(com_custo)
        total_pos = len(rows)
        # `cost_known` soma o custo declarado mesmo sem cotacao; somar as
        # linhas so' funciona porque elas passaram a carregar `cost_total`
        # tambem quando o preco falta. O fallback cobre totals de fora.
        total_cost = totals.get("cost_known")
        if total_cost is None:
            total_cost = sum(r.get("cost_total", 0) or 0 for r in com_custo)
        profit_items = sum(1 for r in com_custo if (r.get("pnl") or 0) > 0)
        loss_items = sum(1 for r in com_custo if (r.get("pnl") or 0) < 0)
        best = max(com_custo, key=lambda r: r.get("pnl") or 0) if n else None
        worst = min(com_custo, key=lambda r: r.get("pnl") or 0) if n else None

        if not total_pos:
            legenda = invest_legenda = dica = ""
        elif not n:
            legenda = invest_legenda = (
                f"nenhum dos {total_pos} itens tem custo declarado")
            dica = ("Sem custo declarado não há lucro nem prejuízo a "
                    "medir.\nInforme o custo na aba Inventário, coluna "
                    "Custo.")
        elif sem_custo:
            legenda = f"entre os {n} com custo declarado"
            invest_legenda = f"{n} de {total_pos} itens com custo declarado"
            dica = (f"{n} de {total_pos} itens tem custo declarado.\n"
                    f"{sem_custo} vieram do sync, que não informa quanto "
                    "você pagou —\nesses ficam de fora da conta de lucro e "
                    "prejuízo.\nInforme o custo na aba Inventário, coluna "
                    "Custo.")
        else:
            # Todo item tem custo: o denominador ja' e' o inventario todo e
            # legenda nenhuma acrescenta fato.
            legenda = invest_legenda = dica = ""

        self._bd_invested.set_value(t.brl(total_cost) if n else "—")
        self._bd_invested.set_delta(None, invest_legenda)
        self._bd_invested.setToolTip(dica)
        self._bd_profit_count.set_value(
            f"{profit_items} de {n}" if n else "—", accent=t.POSITIVE)
        self._bd_profit_count.set_delta(None, legenda)
        self._bd_profit_count.setToolTip(dica)
        self._bd_loss_count.set_value(
            f"{loss_items} de {n}" if n else "—", accent=t.DANGER)
        self._bd_loss_count.set_delta(None, legenda)
        self._bd_loss_count.setToolTip(dica)
        # Melhor/Pior P&L ficavam como "—" mudos. Um travessao sem legenda
        # nao distingue "nao ha' o que medir" de "a tela falhou" -- e aqui
        # ha' DUAS causas distintas, custo ausente e cotacao ausente.
        from skinvault.localization import localize_name as _ln
        tem_pnl = best is not None and best.get("pnl") is not None
        if tem_pnl:
            extremo_legenda = f"entre os {n} com custo declarado"
        elif not n:
            extremo_legenda = "precisa de custo declarado"
        else:
            extremo_legenda = "sem preço para calcular"

        self._bd_best.set_value(
            t.brl(best["pnl"]) if tem_pnl else "—", accent=t.POSITIVE)
        self._bd_best.set_delta(None, "" if tem_pnl else extremo_legenda)
        self._bd_best.setToolTip(
            _ln(best.get("name", "")) if tem_pnl else dica)
        tem_pior = worst is not None and worst.get("pnl") is not None
        self._bd_worst.set_value(
            t.brl(worst["pnl"]) if tem_pior else "—", accent=t.DANGER)
        self._bd_worst.set_delta(None, "" if tem_pior else extremo_legenda)
        self._bd_worst.setToolTip(
            _ln(worst.get("name", "")) if tem_pior else dica)

        grupos = portfolio_mod.composition(rows)
        self._comp_chart.set_groups(grupos)
        # O rotulo declara a unidade da barra: com a Steam racionada nao ha'
        # valor, e a barra passa a medir contagem.
        tem_valor = any((g.get("value") or 0) > 0 for g in grupos)
        self._comp_lbl.setText(
            "Participação por valor de mercado" if tem_valor
            else "Quantidade por categoria — sem preço no momento")
        self._comp_chart.setToolTip(
            "\n".join(f"{g['label']}: {g['count']} item(ns)" for g in grupos))

        caixas = portfolio_mod.containers(rows)
        if not caixas:
            self._cx_lista.setText(
                f"<span style='color:{t.TEXT_MUTED}'>Nenhum container "
                "mapeado na carteira.</span>")
        else:
            n_desc = sum(1 for c in caixas if c["discontinued"])
            self._cx_lbl.setText(
                f"{len(caixas)} tipos · {n_desc} não caem mais em drop"
                if n_desc else f"{len(caixas)} tipos · todos ainda em drop")
            linhas = []
            for c in caixas[:8]:
                estado = ("não cai mais" if c["discontinued"]
                          else "em drop")
                cor = t.TEXT if c["discontinued"] else t.TEXT_MUTED
                ano = f" · {c['year']}" if c.get("year") else ""
                linhas.append(
                    f"<div style='margin-bottom:4px'>"
                    f"<span style='color:{t.TEXT}'>{c['name']}</span>"
                    f"<span style='color:{t.TEXT_MUTED}'> ×{c['qty']}</span>"
                    f"<br><span style='color:{cor}'>{estado}</span>"
                    f"<span style='color:{t.TEXT_MUTED}'>{ano}</span></div>")
            self._cx_lista.setText("".join(linhas))

        # Evolucao do valor: grava snapshot (GUI alimenta o mesmo
        # history.json do CLI) e re-renderiza a serie.
        #
        # So' grava avaliacao COMPLETA. Uma parcial vira um ponto que
        # parece queda da carteira: em 11/06/2026 entrou um R$ 200,00 no
        # history.json (poucos itens com preco em cache) logo depois de um
        # R$ 979,42 completo, e o cartao passou a exibir "-79,6%" -- uma
        # perda que nunca aconteceu.
        total_market = totals.get("market")
        if rows and total_market and self._avaliacao_completa(rows):
            self._record_value_snapshot(total_market)
        self._reload_value_series()

        # Metas: cada avaliação recalcula o progresso (mesmo sem preço —
        # a métrica "items" não depende de cotação).
        self._metas_card.refresh_from(totals)

        # O inventario vive na aba propria desde 28/07/2026; aqui so' se
        # avalia e se repassa.
        rate_limited = bool(data.get("rate_limited"))
        self.inventory_ready.emit(
            list(rows), list(data["positions"]), rate_limited)
        now = time.strftime('%H:%M')
        if rate_limited:
            # "Mostrando o que estava em cache" com a tela inteira em "—"
            # promete um dado que nao existe. Sob 429 o cache pode estar
            # vazio, e ai' o certo e' dizer isso.
            if com_preco:
                self._status.setText(
                    f"{len(rows)} item(ns) • a Steam limitou as consultas "
                    f"de preço; {len(com_preco)} vieram do cache ({now})"
                )
            else:
                self._status.setText(
                    f"{len(rows)} item(ns) • a Steam limitou as consultas "
                    f"de preço e não havia nada em cache ({now})"
                )
        else:
            self._status.setText(
                f"{len(rows)} item(ns) • atualizado {now}"
            )

