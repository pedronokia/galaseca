"""Tela 1 - Minha Conta + Inventario (F11).

Header: avatar + nome Steam + SteamID + 4 stat cards.
Corpo: filtro + tabela inventario.
Acao: botao "Sincronizar com Steam".

Reusa:
  portfolio.load_portfolio / evaluate_portfolio
  prices.PriceCache
  profile_fetcher.fetch_public_profile
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import backtest as backtest_mod
from skinvault import portfolio as portfolio_mod
from skinvault import history, prices, signals, ssr_cache, steam_session
from skinvault.ui import theme as t
from skinvault.ui._price_worker import PriceWorker
from skinvault.ui.components import ActivityFeed, Avatar, Card, EmptyState, LoadingState, PageHeader, StatCard
from skinvault.ui.widgets import ValueChart
from skinvault.ui.profile_fetcher import (
    fetch_public_profile,
    load_avatar_bytes,
    load_cached_profile,
)


class _AccountBridge(QObject):
    profile_ready = pyqtSignal(dict)


class _PortfolioValidationBridge(QObject):
    samples_ready = pyqtSignal(list)
    progress = pyqtSignal(str)
    finished = pyqtSignal()


class AccountScreen(QWidget):
    """Tela 1 -- Minha Conta + Inventario."""

    COL_NAME = 0
    COL_QTY = 1
    COL_PRICE = 2
    COL_SUBTOTAL = 3
    COL_RECEIVED = 4
    COL_PNL = 5
    COL_ORIGIN = 6
    COL_SCORE = 7

    request_sync = pyqtSignal()

    def __init__(self, cache: prices.PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._session: steam_session.SteamSession | None = None
        self._bridge = _AccountBridge()
        self._bridge.profile_ready.connect(self._on_profile)
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
        self._price_worker = PriceWorker(cache, self)
        self._price_worker.eval_done.connect(self._on_eval)
        self._price_worker.progress.connect(self._on_eval_progress)
        self._build()
        self._reload_activity()
        self._start_schedule()

    def set_session(self, session: steam_session.SteamSession | None) -> None:
        self._session = session
        self._reload_profile()
        self._update_strip()
        self.refresh()

    def _update_strip(self) -> None:
        s = self._session
        if s and s.steamid:
            name = self._name.text()
            if name and name != "—":
                label = f"Conectado como {name}"
            else:
                label = "Conectado com Steam"
            self._strip_status.setText(label)
            self._strip_dot.setStyleSheet(
                f"background: {t.POSITIVE}; border-radius: 4px;"
            )
        else:
            self._strip_status.setText("Não conectado")
            self._strip_dot.setStyleSheet(
                f"background: {t.TEXT_MUTED}; border-radius: 4px;"
            )

    # ── construcao do layout ──────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        # PageHeader
        act_lbl = QHBoxLayout()
        act_lbl.setContentsMargins(0, 0, 0, 0)
        act_lbl.setSpacing(t.SPACE_SM)

        self._validate_btn = QPushButton("Validar Score do Portfolio")
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
            " Mais rápido que Validar Score — não mostra dialog de backtest."
        )
        self._refresh_btn.clicked.connect(self._on_refresh_scores)
        act_lbl.addWidget(self._refresh_btn)

        act_w = QWidget()
        act_w.setLayout(act_lbl)
        root.addWidget(PageHeader(
            "Minha Conta",
            "Inventário, desempenho da carteira e sincronização Steam.",
            actions=[act_w],
        ))

        # Session status strip
        self._strip_card = Card(self, padding=t.CARD_PAD_MD)
        strip_lay = QHBoxLayout()
        strip_lay.setContentsMargins(0, 0, 0, 0)
        strip_lay.setSpacing(10)

        self._strip_dot = QLabel()
        self._strip_dot.setFixedSize(8, 8)
        self._strip_dot.setStyleSheet(
            f"background: {t.TEXT_MUTED}; border-radius: 4px;"
        )
        strip_lay.addWidget(self._strip_dot)

        self._strip_status = QLabel("Não conectado")
        self._strip_status.setStyleSheet(t.label_section())
        strip_lay.addWidget(self._strip_status)

        strip_lay.addStretch(1)

        self._strip_last_sync = QLabel("")
        self._strip_last_sync.setStyleSheet(t.label_caption())
        strip_lay.addWidget(self._strip_last_sync)

        self._strip_sync_btn = QPushButton("Sincronizar com Steam")
        self._strip_sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._strip_sync_btn.setStyleSheet(t.btn_steam())
        self._strip_sync_btn.setToolTip(
            "Puxa seu inventario, market history, listings ativas e trade "
            "offers da Steam. Usa cookies salvos da sessao."
        )
        self._strip_sync_btn.clicked.connect(self.request_sync.emit)
        strip_lay.addWidget(self._strip_sync_btn)

        self._strip_card.layout().addLayout(strip_lay)
        root.addWidget(self._strip_card)

        # Header card (avatar + ident, sem botoes)
        header = Card(self)
        hlay = QHBoxLayout()
        hlay.setSpacing(18)

        self._avatar = Avatar(size=72, parent=header)
        hlay.addWidget(self._avatar)

        ident = QVBoxLayout()
        ident.setSpacing(2)
        self._name = QLabel("—")
        self._name.setStyleSheet(t.label_section())
        ident.addWidget(self._name)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(8)

        self._sub = QLabel("Conecte sua conta para sincronizar.")
        self._sub.setStyleSheet(t.label_caption())
        sub_row.addWidget(self._sub)

        self._profile_link = QLabel("")
        self._profile_link.setStyleSheet(
            f"color: {t.STEAM_BLUE}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; text-decoration: underline;"
        )
        self._profile_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile_link.mousePressEvent = lambda _: self._open_steam_profile()
        sub_row.addWidget(self._profile_link)

        sub_row.addStretch(1)
        ident.addLayout(sub_row)
        ident.addStretch(1)
        hlay.addLayout(ident, 1)

        header.layout().addLayout(hlay)

        # Stat cards row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self._stat_gross = StatCard("Valor bruto (Market)", "—",
                                     icon="wallet")
        self._stat_gross.setMaximumWidth(300)
        self._stat_net = StatCard("Valor líquido (-15%)", "—",
                                   accent=t.STEAM_BLUE, icon="coins")
        self._stat_net.setMaximumWidth(300)
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

        vc_lbl = QLabel("Evolução do valor bruto — cada avaliação grava um ponto")
        vc_lbl.setStyleSheet(t.label_caption())
        bd_lay.addWidget(vc_lbl)
        self._value_chart = ValueChart()
        bd_lay.addWidget(self._value_chart)
        self._reload_value_series()

        breakdown_card.layout().addLayout(bd_lay)
        self._breakdown_card = breakdown_card
        root.addWidget(breakdown_card)

        # Coluna esquerda (filtro + tabela + status) + ActivityFeed lateral
        split = QHBoxLayout()
        split.setSpacing(16)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Filtro
        filt = QLineEdit()
        filt.setPlaceholderText("Filtrar por nome do item...")
        filt.setToolTip(
            "Filtra a tabela por nome (case-insensitive). Ctrl+F foca; Esc limpa."
        )
        filt.setClearButtonEnabled(True)
        filt.setStyleSheet(t.input_style())
        filt.textChanged.connect(self._apply_filter)
        self._filter_inp = filt
        left_col.addWidget(filt)

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

        # Tabela
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels([
            "Item", "Qtd", "Preço atual", "Subtotal", "Recebido (-15%)",
            "P&L", "Origem", "Score",
        ])
        t.configure_table(self._table)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(max(self.COL_QTY, self.COL_SCORE + 1)):
            if i != self.COL_NAME:
                hh.setSectionResizeMode(
                    i, QHeaderView.ResizeMode.ResizeToContents)
        left_col.addWidget(self._table, 1)

        # Empty state: inventario vazio (apos sync, sem itens marketable)
        self._empty_hero = EmptyState(
            icon="○",
            title="Inventário vazio",
            subtitle=("Sincronize sua conta com a Steam pra puxar seu inventário\n"
                       "ou adicione posições manualmente pelo CLI."),
            cta_label="Sincronizar com Steam",
            on_cta=self.request_sync.emit,
        )
        left_col.addWidget(self._empty_hero, 1)
        self._empty_hero.setVisible(False)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(t.label_caption())
        left_col.addWidget(self._status)

        split.addLayout(left_col, 1)

        # Coluna direita: Activity Feed
        self._activity_feed = ActivityFeed(self)
        split.addWidget(self._activity_feed, 0)

        root.addLayout(split, 1)

        from PyQt6.QtGui import QKeySequence, QShortcut
        find_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        find_sc.activated.connect(self._focus_filter)
        esc_sc = QShortcut(QKeySequence("Esc"), self)
        esc_sc.activated.connect(self._filter_inp.clear)

    def _focus_filter(self) -> None:
        self._filter_inp.setFocus()
        self._filter_inp.selectAll()

    # ── perfil ───────────────────────────────────────────
    def _reload_profile(self) -> None:
        s = self._session
        if not s or not s.steamid:
            self._name.setText("—")
            self._sub.setText("Conecte sua conta para sincronizar.")
            return

        # 1. tenta cache imediato (rapido)
        cached = load_cached_profile(s.steamid)
        if cached:
            self._on_profile(cached)

        # 2. atualiza em background
        steamid = s.steamid

        def worker() -> None:
            data = fetch_public_profile(steamid)
            if data:
                self._bridge.profile_ready.emit(data)

        threading.Thread(target=worker, daemon=True).start()

    def _open_steam_profile(self) -> None:
        if self._session and self._session.steamid:
            url = f"https://steamcommunity.com/profiles/{self._session.steamid}"
            QDesktopServices.openUrl(QUrl(url))

    def _on_profile(self, data: dict) -> None:
        steamid = data.get("steamid", "")
        self._name.setText(data.get("name") or "—")
        self._update_strip()
        self._sub.setText(f"SteamID: {steamid}")
        if steamid:
            self._profile_link.setText("Ver perfil na Steam ›")
            self._profile_link.setVisible(True)
        else:
            self._profile_link.setVisible(False)
        path = data.get("avatar_path")
        if path:
            self._avatar.set_image(path)
        else:
            avbytes = load_avatar_bytes(steamid)
            if avbytes:
                self._avatar.set_image(avbytes)

    # ── avaliacao de inventario ──────────────────────────
    def refresh(self) -> None:
        """Avalia portfolio em thread e atualiza tabela + stats."""
        self._progress.setVisible(True)
        self._status.setText("Avaliando inventario...")
        self._price_worker.start()
        self._reload_activity()

    def _reload_activity(self) -> None:
        """Atualiza o feed de atividade recente (sem I/O de rede)."""
        from skinvault import activity as _act
        try:
            events = _act.load_recent_activity(limit=10)
        except Exception:
            events = []
        self._activity_feed.set_events(events)

    def _reload_value_series(self) -> None:
        """Recarrega data/history.json no grafico de evolucao do valor."""
        series = history.load_history()
        self._value_chart.set_series(
            [p.get("total", 0.0) for p in series]
        )

    def _record_value_snapshot(self, total: float) -> None:
        """Grava ponto de valor — pula se igual ao ultimo (o schedule de
        30min re-avalia com cache; sem o dedup o arquivo encheria de
        pontos repetidos)."""
        series = history.load_history()
        if series and series[-1].get("total") == float(total):
            return
        history.record_snapshot(total)

    def _on_eval_progress(self, done: int, total: int) -> None:
        self._status.setText(f"Avaliando inventario... {done}/{total}")

    # ── Validar Score do Portfolio ───────────────────────
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
        self._strip_sync_btn.setEnabled(False)
        self._loading.set_label(f"Validando {len(names)} itens...")
        self._loading.setVisible(True)
        bridge = self._validate_bridge
        cache = ssr_cache.PriceHistoryCache()
        positions_snapshot = positions

        def _worker() -> None:
            try:
                name_to_score: dict[str, tuple[int, float]] = {}
                for i, name in enumerate(names, start=1):
                    hit = cache.has(name)
                    tag = "cache" if hit else "buscando"
                    bridge.progress.emit(
                        f"Validando [{i}/{len(names)}] {name} ({tag})"
                    )
                    try:
                        ph = ssr_cache.cached_price_history(name, cache=cache)
                    except Exception:
                        ph = None
                    if ph:
                        try:
                            samples = backtest_mod.simulate_item(name, ph)
                        except Exception:
                            samples = []
                        if samples:
                            bridge.samples_ready.emit(samples)
                        # Computa current_score pra persistir
                        try:
                            cs = backtest_mod.score_from_history(name, ph)
                        except Exception:
                            cs = None
                        if cs is not None:
                            name_to_score[name] = (int(cs), time.time())
                    if not hit:
                        time.sleep(2.0)
                # Atualiza positions com scores e persiste
                for p in positions_snapshot:
                    n = p.get("name")
                    if n in name_to_score:
                        cs, ts = name_to_score[n]
                        p["current_score"] = cs
                        p["score_ts"] = ts
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
        self._strip_sync_btn.setEnabled(True)
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
            self._populate_table(rows, positions)
            self._on_eval({"rows": rows, "totals": result["totals"],
                          "positions": positions})
            return
        # Reusa o dialog do scanner pra manter UX coerente
        from skinvault.ui.scanner_screen import _BacktestResultDialog
        dlg = _BacktestResultDialog(
            self._validate_samples, items_n, parent=self,
        )
        dlg.exec()

    # ── Schedule automatico ──────────────────────────────
    def _start_schedule(self) -> None:
        from skinvault.settings import load_settings as _ls
        interval = _ls().get("validate_interval_minutes", 30)
        if interval <= 0 or not self._session:
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
        self._table.setVisible(not is_empty)
        self._empty_hero.setVisible(is_empty)
        # Atualiza stats
        self._stat_gross.set_value(t.brl(totals.get("market") or 0))
        # Delta do valor bruto vs penultimo ponto do historico
        _series = history.load_history()
        if len(_series) >= 2:
            _prev = _series[-2].get("total", 0) or 0
            _curr = _series[-1].get("total", 0) or 0
            if _prev and _curr:
                self._stat_gross.set_delta(
                    (_curr - _prev) / _prev * 100)
            else:
                self._stat_gross.set_delta(None)
        else:
            self._stat_gross.set_delta(None)
        self._stat_net.set_value(t.brl(totals.get("net_if_sold") or 0),
                                 accent=t.STEAM_BLUE)
        pnl = totals.get("pnl") or 0
        pnl_color = t.POSITIVE if pnl >= 0 else t.DANGER
        self._stat_pnl.set_value(t.brl(pnl), accent=pnl_color)
        pnl_pct = totals.get("pnl_pct")
        if pnl_pct is not None and len(rows) > 0:
            sign = "+" if pnl_pct >= 0 else ""
            kind = "positive" if pnl_pct >= 0 else "danger"
            self._stat_pnl.set_badge(f"{sign}{pnl_pct:.1f}%", kind)
        else:
            self._stat_pnl.clear_badge()
        self._stat_items.set_value(str(len(rows)))

        # Portfolio breakdown
        total_cost = sum(
            r.get("cost_total", 0) or 0 for r in rows
        )
        profit_items = sum(1 for r in rows if (r.get("pnl") or 0) > 0)
        loss_items = sum(1 for r in rows if (r.get("pnl") or 0) < 0)
        best = max(rows, key=lambda r: r.get("pnl") or 0) if rows else None
        worst = min(rows, key=lambda r: r.get("pnl") or 0) if rows else None
        self._bd_invested.set_value(t.brl(total_cost))
        self._bd_profit_count.set_value(
            f"{profit_items} ({profit_items/len(rows)*100:.0f}%)" if rows else "0",
            accent=t.POSITIVE
        )
        self._bd_loss_count.set_value(
            f"{loss_items} ({loss_items/len(rows)*100:.0f}%)" if rows else "0",
            accent=t.DANGER
        )
        from skinvault.localization import localize_name as _ln
        self._bd_best.set_value(
            t.brl(best['pnl']) if best else "—",
            accent=t.POSITIVE
        )
        self._bd_best.setToolTip(_ln(best.get("name", "")) if best else "")
        self._bd_worst.set_value(
            t.brl(worst['pnl']) if worst else "—",
            accent=t.DANGER
        )
        self._bd_worst.setToolTip(_ln(worst.get("name", "")) if worst else "")

        # Evolucao do valor: grava snapshot (GUI alimenta o mesmo
        # history.json do CLI) e re-renderiza a serie
        total_market = totals.get("market")
        if rows and total_market:
            self._record_value_snapshot(total_market)
        self._reload_value_series()

        # Atualiza tabela
        self._populate_table(rows, data["positions"])
        now = time.strftime('%H:%M')
        self._status.setText(
            f"{len(rows)} item(ns) • atualizado {now}"
        )
        self._strip_last_sync.setText(f"Ultima sync: {now}")

    def _populate_table(self, rows: list[dict],
                        positions: list[dict]) -> None:
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, r in enumerate(rows):
            self._table.insertRow(i)
            pos = positions[i] if i < len(positions) else {}
            src = pos.get("source", "manual")
            origin = "Steam" if src == "steam_sync" else "Manual"
            cur_score = pos.get("current_score")
            score_ts = pos.get("score_ts")
            score_txt = str(int(cur_score)) if cur_score is not None else "—"
            from skinvault.localization import localize_name as _ln
            cells = [
                _ln(r.get("name") or "") or "—",
                str(r.get("quantity") or 1),
                t.brl(r.get("price")),
                t.brl(r.get("market")),
                t.brl(r.get("net_if_sold")),
                t.brl(r.get("pnl")),
                origin,
                score_txt,
            ]
            for col, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if col == self.COL_PNL:
                    pnl = r.get("pnl")
                    if pnl is not None:
                        item.setForeground(
                            QBrush(QColor(t.POSITIVE if pnl >= 0 else t.DANGER))
                        )
                elif col == self.COL_ORIGIN and origin == "Steam":
                    item.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                elif col == self.COL_SCORE:
                    if cur_score is None:
                        item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
                        item.setToolTip(
                            "Clique 'Validar Score do Portfolio' "
                            "para calcular."
                        )
                    else:
                        stale = signals.is_score_stale(score_ts)
                        if stale:
                            color = t.WARN
                        elif cur_score >= 70:
                            color = t.POSITIVE
                        elif cur_score >= 45:
                            color = t.WARN
                        else:
                            color = t.DANGER
                        item.setForeground(QBrush(QColor(color)))
                        age_txt = signals.score_age_text(score_ts)
                        stale_tag = " [DESATUALIZADO]" if stale else ""
                        item.setToolTip(
                            f"Score {int(cur_score)} — calculado "
                            f"{age_txt}.{stale_tag}\n"
                            f"Empíricamente:\n"
                            f"  70-84 containers → +33%, "
                            f"skins → +8% em 90d\n"
                            f"  85+ containers → +52%, "
                            f"skins → +21% em 90d"
                        )
                self._table.setItem(i, col, item)
        # Alinhamento por coluna: qtd/dinheiro → direita, origem → centro
        right_cols = {
            self.COL_QTY, self.COL_PRICE, self.COL_SUBTOTAL,
            self.COL_RECEIVED, self.COL_PNL, self.COL_SCORE,
        }
        center_cols = {self.COL_ORIGIN}
        t.align_table_columns(self._table, right=right_cols, center=center_cols)
        self._table.setSortingEnabled(was_sorting)

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for row in range(self._table.rowCount()):
            name = self._table.item(row, 0)
            visible = not text or (name and text in name.text().lower())
            self._table.setRowHidden(row, not visible)
