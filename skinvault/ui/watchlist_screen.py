"""Tela — Watchlist + Alertas (F11).

Tabela de itens monitorados com preco alvo, regras configur井eis,
e log de alertas disparados.
"""
from __future__ import annotations

import json
import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import (
    alerts,
    backtest as backtest_mod,
    signals,
    ssr_cache,
    steam_api,
    watchlist as wl,
)
from skinvault._paths import DATA_DIR
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.components import EmptyState, FormRow, LoadingState, PageHeader, SectionHeader, StatCard


class _RulesDialog(QDialog):
    """Dialog para configurar regras de alerta de um item."""

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar regras - " + item["name"])
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._item = item
        self._build()

    def _build(self) -> None:
        rules = self._item.get("rules") or {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Price below target
        self._below_target = QDoubleSpinBox()
        self._below_target.setRange(0, 99999)
        self._below_target.setPrefix("R$ ")
        self._below_target.setValue(rules.get("price_below", 0))
        self._below_target.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Alerta abaixo de:", self._below_target))

        # Drop %
        self._drop_pct = QDoubleSpinBox()
        self._drop_pct.setRange(0, 100)
        self._drop_pct.setSuffix(" %")
        self._drop_pct.setValue(rules.get("price_drop_pct", 0))
        self._drop_pct.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Queda percentual:", self._drop_pct))

        # Volume spike
        self._volume_spike = QDoubleSpinBox()
        self._volume_spike.setRange(0, 100)
        self._volume_spike.setValue(rules.get("volume_spike", 0))
        self._volume_spike.setSpecialValueText("Desligado")
        self._volume_spike.setStyleSheet(t.input_style())
        layout.addWidget(FormRow("Volume anomalia (x):", self._volume_spike))

        # Supply drop
        qb = QGroupBox("Supply drop")
        qb.setStyleSheet(
            f"QGroupBox {{ color: {t.TEXT}; font-family: {t.FONT_FAMILY};"
            f" font-size: {t.FS_BODY}; border: 1px solid {t.BORDER};"
            f" border-radius: 8px; margin-top: 12px; padding: 14px 12px 10px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin;"
            f" left: 12px; padding: 0 6px; }}"
        )
        qb_lay = QVBoxLayout(qb)
        self._supply_drop = QDoubleSpinBox()
        self._supply_drop.setRange(0, 100)
        self._supply_drop.setValue(rules.get("supply_drop", 0))
        self._supply_drop.setSpecialValueText("Desligado")
        self._supply_drop.setStyleSheet(t.input_style())
        qb_lay.addWidget(QLabel("Limiar de queda na oferta:"))
        qb_lay.addWidget(self._supply_drop)
        layout.addWidget(qb)

        # Score above (validado empiricamente: 85+ retorna +50% em 90d)
        self._score_above = QSpinBox()
        self._score_above.setRange(0, 100)
        self._score_above.setValue(int(rules.get("score_above", 0)))
        self._score_above.setSpecialValueText("Desligado")
        self._score_above.setStyleSheet(t.input_style())
        self._score_above.setToolTip(
            "Dispara quando o enhanced_score atingir o valor (0-100)."
            " Empíricamente: score >=85 retorna +50% em 90d (containers)."
            " Recomendado: 85 pra alta convicção, 70 pra ampla cobertura."
        )
        layout.addWidget(FormRow("Score atingir:", self._score_above))

        self._rules_instr = QLabel(
            "Regras com valor 0 ou 'Desligado' ficam inativas."
        )
        self._rules_instr.setStyleSheet(t.label_caption())
        layout.addWidget(self._rules_instr)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.setStyleSheet(t.btn_ghost())
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Salvar")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def get_rules(self) -> dict:
        rules = {}
        v = self._below_target.value()
        if v > 0:
            rules["price_below"] = v
        v = self._drop_pct.value()
        if v > 0:
            rules["price_drop_pct"] = v / 100.0
        v = self._volume_spike.value()
        if v > 0:
            rules["volume_spike"] = v
        v = self._supply_drop.value()
        if v > 0:
            rules["supply_drop"] = v
        v = self._score_above.value()
        if v > 0:
            rules["score_above"] = v
        return rules


# _current_score_from_history movido pra backtest.score_from_history.
# Mantido aqui como alias pra back-compat com testes existentes.
_current_score_from_history = backtest_mod.score_from_history


class _WatchlistValidationBridge(QObject):
    samples_ready = pyqtSignal(list)
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    alert_fired = pyqtSignal(str, dict)  # name, alert dict


class WatchlistScreen(QWidget):
    """Watchlist + Alertas."""

    COL_NAME = 0
    COL_TARGET = 1
    COL_PRICE = 2
    COL_STATUS = 3
    COL_RULES = 4
    COL_SCORE = 5
    COL_CONFIDENCE = 6

    # Sinal emitido quando um alerta dispara durante Validar Score.
    # (title, body, severity). Router conecta -> MainWindow conecta -> tray.
    notification_requested = pyqtSignal(str, str, str)

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._items: list[dict] = []
        self._alerts_log: list[dict] = []
        self._validate_bridge = _WatchlistValidationBridge()
        self._validate_bridge.samples_ready.connect(
            self._on_validate_samples,
        )
        self._validate_bridge.progress.connect(self._on_validate_progress)
        self._validate_bridge.finished.connect(self._on_validate_finished)
        self._validate_bridge.alert_fired.connect(self._on_alert_fired)
        self._validate_samples: list[dict] = []
        self._validate_items_count: int = 0
        self._validating = False
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._on_refresh_scores)
        self._build()
        self.refresh()
        self._start_schedule()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        # Header: PageHeader + acoes
        self._add_btn = QPushButton("+ Adicionar item")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(t.btn_primary())
        self._add_btn.setToolTip(
            "Adiciona um item para monitoramento e dispara alertas quando"
            " a regra escolhida for satisfeita."
        )
        self._add_btn.clicked.connect(self._on_add)

        self._validate_btn = QPushButton("Validar Score")
        self._validate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._validate_btn.setStyleSheet(t.btn_secondary(padding="10px 18px",
                                                          fs=t.FS_INPUT))
        self._validate_btn.setToolTip(
            "Roda backtest histórico (90d) nos itens monitorados."
            " Mostra se o score realmente prediz retornos pra esses itens."
            " Usa cache 24h, então reruns são rápidos."
        )
        self._validate_btn.clicked.connect(self._on_validate_watchlist)

        self._refresh_btn = QPushButton("Atualizar scores+alertas")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(t.btn_ghost())
        self._refresh_btn.setToolTip(
            "Recomputa scores e reavalia alertas de todos os itens usando"
            " dados do cache. Mais rápido que Validar Score — sem dialog."
        )
        self._refresh_btn.clicked.connect(self._on_refresh_scores)

        root.addWidget(PageHeader(
            "Watchlist e Alertas",
            "Monitore preços de skins selecionadas e receba alertas quando "
            "regras forem atendidas (queda, volume anormal, oferta baixa).",
            actions=[self._add_btn, self._validate_btn, self._refresh_btn],
        ))

        # Stat cards: total + com regras + disparados + recentes 24h
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self._stat_total = StatCard("Itens monitorados", "0")
        self._stat_rules = StatCard("Com regras ativas", "0",
                                     accent=t.STEAM_BLUE)
        self._stat_triggered = StatCard("Disparados agora", "0",
                                         accent=t.ACCENT)
        self._stat_recent = StatCard("Alertas em 24h", "0",
                                       accent=t.WARN)
        for sc in (self._stat_total, self._stat_rules,
                   self._stat_triggered, self._stat_recent):
            sc.setMaximumWidth(280)
            stats_row.addWidget(sc)
        stats_row.addStretch(1)
        root.addLayout(stats_row)

        # Filtro de confianca (mesmo padrao do Scanner)
        filt_row = QHBoxLayout()
        self._hide_low_conf_cb = QCheckBox("Esconder baixa confian\u00e7a")
        self._hide_low_conf_cb.setToolTip(
            "Oculta itens onde a confianca dos dados e 'low' ou 'very_low'."
            " Disponivel apenas apos 'Validar Score'."
        )
        self._hide_low_conf_cb.setStyleSheet(
            f"QCheckBox {{ color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QCheckBox:focus {{ color: {t.TEXT}; }}"
        )
        self._hide_low_conf_cb.toggled.connect(self._on_hide_low_conf_toggle)
        filt_row.addWidget(self._hide_low_conf_cb)
        filt_row.addStretch(1)
        root.addLayout(filt_row)

        # Loading state (mostrado durante validacao)
        self._loading = LoadingState(parent=self)
        self._loading.setVisible(False)
        root.addWidget(self._loading, 0, Qt.AlignmentFlag.AlignCenter)

        # Tabela
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Preco alvo", "Preco atual", "Status", "Regras",
             "Score", "Confiança"]
        )
        t.configure_table(self._table)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(self.COL_TARGET,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_PRICE,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_STATUS,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_RULES,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_SCORE,
                                QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_CONFIDENCE,
                                QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table, 1)

        # Empty state (mostrado quando watchlist vazia)
        self._empty_hero = EmptyState(
            icon="☆",
            title="Sua watchlist está vazia",
            subtitle=("Adicione itens pra monitorar preços e receber alertas\n"
                       "quando o mercado se mexer."),
            cta_label="+ Adicionar item",
            on_cta=self._on_add,
        )
        root.addWidget(self._empty_hero, 1)
        self._empty_hero.setVisible(False)

        self._status = QLabel("")
        self._status.setStyleSheet(t.label_caption())
        root.addWidget(self._status)

    def refresh(self) -> None:
        import time as _time
        self._items = wl.load_watchlist()
        self._alerts_log = alerts.load_alerts_log()
        is_empty = not self._items
        self._table.setVisible(not is_empty)
        self._empty_hero.setVisible(is_empty)
        # Stats
        total = len(self._items)
        with_rules = sum(1 for it in self._items if it.get("rules"))
        triggered = sum(1 for it in self._items if it.get("triggered"))
        cutoff_24h = _time.time() - 86400
        recent = sum(1 for a in self._alerts_log
                     if a.get("ts", 0) >= cutoff_24h)
        self._stat_total.set_value(str(total))
        self._stat_rules.set_value(str(with_rules))
        self._stat_triggered.set_value(str(triggered),
                                       accent=t.ACCENT if triggered else t.TEXT_MUTED)
        self._stat_recent.set_value(str(recent),
                                    accent=t.WARN if recent else t.TEXT_MUTED)
        # Contexto: timestamp do ultimo alerta
        if self._alerts_log:
            _last_ts = self._alerts_log[-1].get("ts", 0)
            if _last_ts:
                _last_str = time.strftime("%H:%M",
                                          time.localtime(_last_ts))
                self._stat_recent.set_delta(None,
                                            label=f"último: {_last_str}")
            else:
                self._stat_recent.set_delta(None)
        else:
            self._stat_recent.set_delta(None)
        self._populate()

    def _populate(self) -> None:
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, item in enumerate(self._items):
            self._table.insertRow(i)
            name = item["name"]
            target = item.get("target", 0)
            triggered = item.get("triggered", False)
            rules = item.get("rules") or {}
            baseline = item.get("baseline_price")

            # Nome (display localizado; nome original fica no dict do item)
            from skinvault.localization import localize_name as _ln
            self._table.setItem(i, self.COL_NAME, QTableWidgetItem(_ln(name)))

            # Target
            self._table.setItem(i, self.COL_TARGET,
                                QTableWidgetItem(t.brl(target) if target else "—"))

            # Preco atual (try cache)
            price = self._cache.get(name)
            price_item = QTableWidgetItem(
                t.brl(price) if price else "Consultando…"
            )
            if price:
                color = t.DANGER if price <= target else t.ACCENT
                price_item.setForeground(Qt.GlobalColor.white)
            self._table.setItem(i, self.COL_PRICE, price_item)

            # Status
            status_txt = "Alerta!" if triggered else "OK"
            st = QTableWidgetItem(status_txt)
            if triggered:
                st.setForeground(QBrush(QColor(t.DANGER)))
            else:
                st.setForeground(QBrush(QColor(t.ACCENT)))
            self._table.setItem(i, self.COL_STATUS, st)

            # Regras summary
            self._table.setItem(
                i, self.COL_RULES,
                QTableWidgetItem(alerts.format_rules_summary(rules)),
            )

            # Score atual (persistido pelo Validar Score)
            cur_score = item.get("current_score")
            score_ts = item.get("score_ts")
            if cur_score is None:
                score_item = QTableWidgetItem("—")
                score_item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
                score_item.setToolTip(
                    "Clique em 'Validar Score' para calcular."
                )
            else:
                score_item = QTableWidgetItem(str(int(cur_score)))
                stale = signals.is_score_stale(score_ts)
                if stale:
                    color = t.WARN
                elif cur_score >= 70:
                    color = t.ACCENT
                elif cur_score >= 45:
                    color = t.WARN
                else:
                    color = t.DANGER
                score_item.setForeground(QBrush(QColor(color)))
                age_txt = signals.score_age_text(score_ts)
                stale_tag = " [DESATUALIZADO]" if stale else ""
                score_item.setToolTip(
                    f"Score {int(cur_score)} — calculado {age_txt}."
                    f"{stale_tag}\n"
                    f"Empíricamente:\n"
                    f"  70-84 containers → +33%, skins → +8% em 90d\n"
                    f"  85+ containers → +52%, skins → +21% em 90d"
                )
            self._table.setItem(i, self.COL_SCORE, score_item)

            # Confianca (data quality)
            dq = item.get("data_quality") or {}
            conf_level = dq.get("level", "none")
            conf_labels = {"high": "Alta", "medium": "Média",
                           "low": "Baixa", "very_low": "Muito baixa",
                           "none": "—"}
            conf_colors = {"high": t.ACCENT, "medium": t.WARN,
                           "low": t.DANGER, "very_low": t.DANGER,
                           "none": t.TEXT_MUTED}
            conf_item = QTableWidgetItem(conf_labels.get(conf_level, conf_level))
            conf_item.setForeground(
                QBrush(QColor(conf_colors.get(conf_level, t.TEXT_MUTED)))
            )
            conf_item.setToolTip(dq.get("label", ""))
            self._table.setItem(i, self.COL_CONFIDENCE, conf_item)

            # Acoes (context menu via botoes na ultima coluna ou botoes inline)
            # Usa botoes simples: Editar e Remover
        # Alinhamento por coluna: preco → direita, status → centro
        right_cols = {self.COL_TARGET, self.COL_PRICE}
        center_cols = {self.COL_STATUS, self.COL_SCORE, self.COL_CONFIDENCE}
        t.align_table_columns(self._table, right=right_cols, center=center_cols)
        self._table.setSortingEnabled(was_sorting)
        self._status.setText(
            f"{len(self._items)} itens • "
            f"{len([x for x in self._items if x.get('triggered')])} alertas ativos"
        )
        self._apply_confidence_filter()

    # ── Validar Score + Avaliar alertas ───────────────────
    def _on_validate_watchlist(self) -> None:
        if self._validating:
            return
        items_full = self._items or wl.load_watchlist()
        items_by_name = {i["name"]: i for i in items_full
                          if i.get("name")}
        names = sorted(items_by_name.keys())
        if not names:
            self._status.setText(
                "Watchlist vazia. Adicione itens antes de validar."
            )
            return
        self._validate_samples = []
        self._validate_items_count = len(names)
        self._validate_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._add_btn.setEnabled(False)
        self._loading.set_label(f"Validando {len(names)} itens...")
        self._loading.setVisible(True)
        bridge = self._validate_bridge
        cache = ssr_cache.PriceHistoryCache()
        items_snapshot = items_full  # pra salvar de volta depois

        def _worker() -> None:
            try:
                fired_alerts: list[tuple[str, dict]] = []
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
                    if not ph:
                        if not hit:
                            time.sleep(2.0)
                        continue
                    # Backtest samples (igual antes)
                    try:
                        samples = backtest_mod.simulate_item(name, ph)
                    except Exception:
                        samples = []
                    if samples:
                        bridge.samples_ready.emit(samples)
                    # Score atual = enhanced_score com a historia inteira.
                    # Fair-value via mediana 30d, igual ao _mock_verdict_from_history.
                    try:
                        current_score = backtest_mod.score_from_history(
                            name, ph,
                        )
                    except Exception:
                        current_score = None
                    # Persiste score por item (pra coluna mostrar)
                    item = items_by_name.get(name)
                    if item and current_score is not None:
                        item["current_score"] = int(current_score)
                        item["score_ts"] = time.time()
                    # Data quality (confianca) — computada do mesmo price_history
                    if item and ph:
                        try:
                            dq = signals.data_quality(ph)
                            item["data_quality"] = dq
                        except Exception:
                            pass
                    # Avalia alertas com score atual
                    if item and current_score is not None:
                        fresh = alerts.evaluate_item(
                            item, current_price=None,
                            current_score=current_score,
                        )
                        new = alerts.diff_new_alerts(item, fresh)
                        for a in new:
                            alerts.record_alert(name, a)
                            fired_alerts.append((name, a))
                            # Emit pra UI mostrar notificacao
                            bridge.alert_fired.emit(name, a)
                        item["triggered"] = bool(item.get("triggered_rules"))
                    if not hit:
                        time.sleep(2.0)
                # Persiste estado atualizado da watchlist
                try:
                    wl.save_watchlist(items_snapshot)
                except Exception:
                    pass
                if fired_alerts:
                    bridge.progress.emit(
                        f"⚡ {len(fired_alerts)} alerta(s) novo(s) disparado(s)"
                    )
            finally:
                bridge.finished.emit()

        self._validating = True
        threading.Thread(target=_worker, daemon=True).start()

    def _on_validate_progress(self, msg: str) -> None:
        self._loading.set_label(msg)
        self._status.setText(msg)

    def _on_validate_samples(self, samples: list) -> None:
        self._validate_samples.extend(samples)

    def _on_alert_fired(self, name: str, alert: dict) -> None:
        """Recebe alert do worker e emite notification_requested.

        Respeita settings.tray_notifications (off => silencioso).
        """
        from skinvault.settings import load_settings as _ls
        if not _ls().get("tray_notifications", True):
            return
        rule = alert.get("rule", "")
        label = alert.get("label", "")
        from skinvault.localization import localize_name as _ln
        body = f"{_ln(name)}\n{label}"
        title = "SkinVault: oportunidade detectada"
        severity = alert.get("severity", "info")
        self.notification_requested.emit(title, body, severity)

    # ── Filtro de confianca ─────────────────────────────
    def _apply_confidence_filter(self) -> int:
        if not hasattr(self, "_hide_low_conf_cb"):
            return 0
        active = self._hide_low_conf_cb.isChecked()
        hidden = 0
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            if not cell:
                continue
            dq = None
            item_name = cell.text()
            for it in (self._items or []):
                if it.get("name") == item_name:
                    dq = it.get("data_quality") or {}
                    break
            level = dq.get("level", "none") if dq else "none"
            should_hide = active and level in ("low", "very_low")
            self._table.setRowHidden(row, should_hide)
            if should_hide:
                hidden += 1
        return hidden

    def _on_hide_low_conf_toggle(self, checked: bool) -> None:
        hidden = self._apply_confidence_filter()
        n = len(self._items or [])
        if hidden:
            self._status.setText(
                f"{n} itens ({hidden} ocultos por baixa confian\u00e7a)"
            )
        else:
            self._status.setText(f"{n} itens")

    def _on_refresh_scores(self) -> None:
        """Atualiza scores+alertas silenciosamente (sem dialog)."""
        self._refresh_mode = True
        self._on_validate_watchlist()

    def _on_validate_finished(self) -> None:
        self._validating = False
        self._loading.setVisible(False)
        self._validate_btn.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        self._add_btn.setEnabled(True)
        n = len(self._validate_samples)
        items_n = self._validate_items_count
        self._status.setText(
            f"Validação concluída: {n} amostras de {items_n} itens"
        )
        refresh = getattr(self, "_refresh_mode", False)
        if refresh:
            self._refresh_mode = False
            self.refresh()
            return
        from skinvault.ui.scanner_screen import _BacktestResultDialog
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

    def _on_add(self) -> None:
        # Dialog simples para adicionar
        dlg = QDialog(self)
        dlg.setWindowTitle("Adicionar a Watchlist")
        dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        name_inp = QLineEdit()
        name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        form.addRow("Nome do item:", name_inp)

        target_inp = QDoubleSpinBox()
        target_inp.setRange(0, 99999)
        target_inp.setPrefix("R$ ")
        target_inp.setDecimals(2)
        form.addRow("Preco alvo:", target_inp)

        lay.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        def on_ok():
            name = name_inp.text().strip()
            target = target_inp.value()
            if not name:
                return
            wl.add_watch(name, target)
            self.refresh()
            dlg.accept()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.exec()
