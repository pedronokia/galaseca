"""Tela — Watchlist + Alertas (F11).

Tabela de itens monitorados com preço alvo, regras configuráveis,
e log de alertas disparados.
"""
from __future__ import annotations

import json
import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
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
from skinvault.ui.components import (
    EmptyState, FormRow, LoadingState, PageHeader, SectionHeader, StatCard,
    ToggleSwitch, score_table_item, SortableItem, auto_cell,
)


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
        cancel.setToolTip("Fecha o dialogo sem salvar.")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Salvar")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setToolTip("Salva as regras de alerta e fecha.")
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
            # Pontos percentuais 0-100 (convencao AGENTS.md #1) — a engine
            # avalia `change <= -abs(price_drop_pct)`, entao 10 = queda de 10%.
            rules["price_drop_pct"] = v
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
    COL_DISTANCE = 2
    COL_PRICE = 3
    COL_STATUS = 4
    COL_RULES = 5
    COL_SCORE = 6
    COL_CONFIDENCE = 7

    # Sinal emitido quando um alerta dispara durante Validar score.
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

        self._validate_btn = QPushButton("Validar score")
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
            " dados do cache. Mais rápido que Validar score — sem dialog."
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
        self._stat_total = StatCard("Itens monitorados", "0",
                                     icon="eye")
        self._stat_rules = StatCard("Com regras ativas", "0",
                                     accent=t.STEAM_BLUE, icon="gear")
        self._stat_triggered = StatCard("Disparados agora", "0",
                                         accent=t.POSITIVE, icon="info")
        self._stat_recent = StatCard("Alertas em 24h", "0",
                                       accent=t.WARN, icon="history")
        for sc in (self._stat_total, self._stat_rules,
                   self._stat_triggered, self._stat_recent):
            sc.setMaximumWidth(280)
            stats_row.addWidget(sc)
        self._stat_total.setToolTip(
            "Itens atualmente na watchlist.\n"
            "Clique com o botão direito numa linha para editar regras, "
            "alterar o preço alvo ou remover o item.")
        self._stat_rules.setToolTip(
            "Itens com pelo menos uma regra ativa (preço, queda, volume, "
            "oferta ou score).")
        self._stat_triggered.setToolTip(
            "Itens com alerta disparado agora.\n"
            "Verifique a coluna Status e o log de alertas em "
            "data/alerts_log.json.")
        self._stat_recent.setToolTip(
            "Alertas registrados nas últimas 24h.\n"
            "Inclui disparos que já foram resetados.")
        stats_row.addStretch(1)
        root.addLayout(stats_row)

        # Filtro de confiança (mesmo padrão do Scanner)
        filt_row = QHBoxLayout()
        self._hide_low_conf_cb = ToggleSwitch()
        self._hide_low_conf_cb.setToolTip(
            "Oculta itens onde a confiança dos dados é 'low' ou 'very_low'."
            " Disponivel apenas apos 'Validar score'."
        )
        self._hide_low_conf_cb.toggled.connect(self._on_hide_low_conf_toggle)
        filt_row.addWidget(self._hide_low_conf_cb)
        _lbl = QLabel("Baixa confiança")
        _lbl.setStyleSheet(t.label_caption())
        _lbl.setToolTip(
            "Oculta itens com confiança 'low' ou 'very_low'."
        )
        filt_row.addWidget(_lbl)
        filt_row.addStretch(1)

        # Busca por nome (mesmo padrão do Inventário/Histórico). Ctrl+F
        # foca o campo; Esc limpa — o gui.py `_focus_filter` também pega
        # via duck-typing do atributo `_search_inp`.
        self._search_inp = QLineEdit()
        self._search_inp.setPlaceholderText("Filtrar por nome do item...")
        self._search_inp.setClearButtonEnabled(True)
        self._search_inp.setMaximumWidth(320)
        self._search_inp.setStyleSheet(t.input_style())
        self._search_inp.textChanged.connect(self._apply_confidence_filter)
        filt_row.addWidget(self._search_inp)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self._search_inp.setFocus)
        QShortcut(QKeySequence("Esc"), self).activated.connect(
            self._clear_search)

        root.addLayout(filt_row)

        # Loading state (mostrado durante validacao)
        self._loading = LoadingState(parent=self)
        self._loading.setVisible(False)
        root.addWidget(self._loading, 0, Qt.AlignmentFlag.AlignCenter)

        # Tabela
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["Item", "Preço alvo", "Distância ao alvo", "Preço atual",
             "Status", "Regras", "Score", "Confiança"]
        )
        t.configure_table(self._table)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in (self.COL_TARGET, self.COL_DISTANCE, self.COL_PRICE,
                    self.COL_STATUS, self.COL_RULES):
            hh.setSectionResizeMode(col,
                                    QHeaderView.ResizeMode.Interactive)
        # Garante que padding QSS ignorado no sizeHint nao trunque headers
        t._ensure_header_width(self._table, hh)
        # Score e Confianca: ocultos ate Validar score
        self._table.setColumnHidden(self.COL_SCORE, True)
        self._table.setColumnHidden(self.COL_CONFIDENCE, True)
        # Acoes por linha: menu de contexto (padrao de edicao pesada) +
        # Delete para remover a linha selecionada (padrao do Trades).
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_row_menu)
        QShortcut(QKeySequence("Delete"), self._table).activated.connect(
            self._on_delete_selected)
        root.addWidget(self._table, 1)

        # Empty state (mostrado quando watchlist vazia)
        self._empty_hero = EmptyState(
            icon="◇",
            title="Sua watchlist está vazia",
            subtitle=("Adicione itens pra monitorar preços\n"
                       "e configurar alertas personalizados."),
            steps=["Adicione um item digitando o nome exato da skin.",
                   "Configure regras de alerta (preço alvo, queda, volume).",
                   "Receba notificações nativas quando o mercado se mexer.",
                   "Depois de adicionado, clique com o botão direito na "
                   "linha para editar regras e alvo."],
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
                                       accent=t.POSITIVE if triggered else t.TEXT_MUTED)
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

            # Nome (display localizado; nome original fica no UserRole pra
            # as acoes da linha funcionarem mesmo com nome traduzido)
            from skinvault.localization import localize_name as _ln
            _name_item = QTableWidgetItem(_ln(name))
            _name_item.setData(Qt.ItemDataRole.UserRole, name)
            self._table.setItem(i, self.COL_NAME, _name_item)

            # Target (auto_cell pra ordenar por valor, nao por texto)
            self._table.setItem(i, self.COL_TARGET,
                                auto_cell(t.brl(target) if target else "—"))

            # Distancia ao alvo
            price_curr = self._cache.get(name)
            if target and price_curr:
                dist_pct = (price_curr - target) / target * 100
                dist_txt = f"{dist_pct:+.1f}%".replace(".", ",")
                dist_item = SortableItem(dist_txt, dist_pct)
                if price_curr <= target:
                    # Favoravel pra compra (atual <= alvo)
                    dist_item.setForeground(QBrush(QColor(t.POSITIVE)))
                else:
                    dist_item.setForeground(QBrush(QColor(t.DANGER)))
                dist_item.setToolTip(
                    "Distância percentual entre o preço atual e o alvo.\n"
                    "Valores negativos ou zero = item abaixo do alvo "
                    "(favorável pra compra).\n"
                    "Valores positivos = item acima do alvo."
                )
            else:
                # -inf: linha sem distancia vai pro fim, nao se mistura
                dist_item = SortableItem("—", float("-inf"))
                dist_item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
            self._table.setItem(i, self.COL_DISTANCE, dist_item)

            # Preco atual (try cache)
            price_item = SortableItem(
                t.brl(price_curr) if price_curr else "Consultando…",
                price_curr if price_curr else float("-inf"),
            )
            if price_curr:
                price_item.setForeground(QBrush(QColor(t.TEXT)))
            self._table.setItem(i, self.COL_PRICE, price_item)

            # Status (3 estados)
            if triggered:
                status_txt = "Disparado"
                st = QTableWidgetItem(status_txt)
                st.setForeground(QBrush(QColor(t.WARN)))
                st.setToolTip(
                    "Regra(s) disparada(s). Verifique o log de alertas."
                )
            elif not rules:
                status_txt = "Sem regras"
                st = QTableWidgetItem(status_txt)
                st.setForeground(QBrush(QColor(t.TEXT_MUTED)))
                st.setToolTip(
                    "Sem regras configuradas. Edite o item para definir "
                    "alertas de preço, queda ou volume."
                )
            else:
                status_txt = "Monitorando"
                st = QTableWidgetItem(status_txt)
                st.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                st.setToolTip(
                    "Regras ativas e dentro do esperado."
                )
            self._table.setItem(i, self.COL_STATUS, st)

            # Regras summary + tooltip verboso com o breakdown por regra
            self._table.setItem(
                i, self.COL_RULES,
                self._rules_cell(item, rules),
            )

            # Score atual (persistido pelo Validar score). A celula e'
            # compartilhada com o Inventario -- ver components.
            self._table.setItem(i, self.COL_SCORE, score_table_item(
                item.get("current_score"), item.get("score_ts")))

            # Confianca (data quality)
            dq = item.get("data_quality") or {}
            conf_level = dq.get("level", "none")
            conf_labels = {"high": "Alta", "medium": "Média",
                           "low": "Baixa", "very_low": "Muito baixa",
                           "none": "—"}
            conf_colors = {"high": t.POSITIVE, "medium": t.WARN,
                           "low": t.DANGER, "very_low": t.DANGER,
                           "none": t.TEXT_MUTED}
            conf_item = QTableWidgetItem(conf_labels.get(conf_level, conf_level))
            conf_item.setForeground(
                QBrush(QColor(conf_colors.get(conf_level, t.TEXT_MUTED)))
            )
            conf_item.setToolTip(dq.get("label", ""))
            self._table.setItem(i, self.COL_CONFIDENCE, conf_item)

            # Acoes por linha vivem no menu de contexto (_on_row_menu) e no
            # Delete — editar regras, editar alvo, resetar alerta, remover.
        # Alinhamento por coluna: preco → direita, status → centro
        right_cols = {self.COL_TARGET, self.COL_DISTANCE, self.COL_PRICE}
        center_cols = {self.COL_STATUS}
        t.align_table_columns(self._table, right=right_cols, center=center_cols)
        self._table.setSortingEnabled(was_sorting)
        self._status.setText(
            f"{len(self._items)} itens • "
            f"{len([x for x in self._items if x.get('triggered')])} alertas ativos"
        )
        self._apply_confidence_filter()

    # ── Acoes por linha (menu de contexto + Delete) ──────
    def _rules_cell(self, item: dict, rules: dict) -> QTableWidgetItem:
        cell = QTableWidgetItem(alerts.format_rules_summary(rules))
        cell.setToolTip(self._rules_tooltip(item, rules))
        return cell

    def _rules_tooltip(self, item: dict, rules: dict) -> str:
        if not rules:
            return ("Sem regras configuradas.\n"
                    "Clique com o botão direito na linha para adicionar "
                    "alertas de preço, queda, volume ou score.")
        lines = ["Regras ativas:"]
        target = item.get("target") or rules.get("price_below")
        if target:
            lines.append(f"• Preço abaixo de {t.brl(target)}")
        if rules.get("price_drop_pct"):
            lines.append(
                f"• Queda de {rules['price_drop_pct']:g}% vs baseline")
        if rules.get("volume_spike"):
            lines.append(
                f"• Volume {rules['volume_spike']:g}x acima da média")
        if rules.get("supply_drop"):
            lines.append(f"• Oferta caindo {rules['supply_drop']:g}x")
        if rules.get("score_above"):
            lines.append(
                f"• Score acima de {int(rules['score_above'])}")
        lines.append("\nBotão direito na linha para editar.")
        return "\n".join(lines)

    def _item_from_row(self, row: int) -> dict | None:
        cell = self._table.item(row, self.COL_NAME)
        if not cell:
            return None
        name = cell.data(Qt.ItemDataRole.UserRole) or cell.text()
        for it in (self._items or []):
            if it.get("name") == name:
                return it
        return None

    def _on_row_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._item_from_row(row)
        if item is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: {t.BG_ELEVATED};"
                           f" color: {t.TEXT}; border: 1px solid {t.BORDER};"
                           " padding: 6px; }}")
        act_rules = menu.addAction("Editar regras")
        act_target = menu.addAction("Editar preço alvo")
        act_reset = menu.addAction("Resetar alerta")
        act_reset.setEnabled(bool(item.get("triggered")))
        menu.addSeparator()
        act_remove = menu.addAction("Remover item")
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act_rules:
            self._on_edit_rules(item)
        elif chosen is act_target:
            self._on_edit_target(item)
        elif chosen is act_reset:
            self._on_reset_trigger(item)
        elif chosen is act_remove:
            self._on_remove_item(item)

    def _on_edit_rules(self, item: dict) -> None:
        dlg = _RulesDialog(item, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        rules = dlg.get_rules()
        if rules:
            item["rules"] = rules
        else:
            item.pop("rules", None)
        wl.save_watchlist(self._items)
        self.refresh()

    def _on_edit_target(self, item: dict) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Editar preço alvo")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        target_inp = QDoubleSpinBox()
        target_inp.setRange(0, 99999)
        target_inp.setPrefix("R$ ")
        target_inp.setDecimals(2)
        target_inp.setValue(item.get("target", 0) or 0)
        target_inp.setStyleSheet(t.input_style())
        lay.addWidget(FormRow("Preço alvo:", target_inp))

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.setStyleSheet(t.btn_ghost())
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setToolTip("Fecha o dialogo sem salvar.")
        cancel.clicked.connect(dlg.reject)
        ok = QPushButton("Salvar")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setToolTip("Salva o novo preço alvo.")

        def on_save():
            val = target_inp.value()
            if val <= 0:
                return
            wl.update_target(item["name"], val)
            self.refresh()
            dlg.accept()

        ok.clicked.connect(on_save)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)
        dlg.exec()

    def _on_reset_trigger(self, item: dict) -> None:
        wl.reset_trigger(item["name"])
        self.refresh()

    def _on_remove_item(self, item: dict) -> None:
        idx = next((i for i, it in enumerate(self._items)
                    if it.get("name") == item["name"]), None)
        if idx is not None:
            wl.remove_watch(idx)
            self.refresh()

    def _on_delete_selected(self) -> None:
        names: list[str] = []
        for idx in self._table.selectedIndexes():
            item = self._item_from_row(idx.row())
            if item is not None and item["name"] not in names:
                names.append(item["name"])
        if not names:
            return
        for name in names:
            pos = next((i for i, it in enumerate(self._items)
                        if it.get("name") == name), None)
            if pos is not None:
                # remove_watch opera por indice do arquivo; reload a cada
                # remocao mantem os indices validos.
                wl.remove_watch(pos)
                self._items = wl.load_watchlist()
        self.refresh()
        self._status.setText(
            f"{len(names)} item(ns) removido(s) da watchlist.")

    def _clear_search(self) -> None:
        self._search_inp.clear()
        self._table.clearFocus()

    # ── Validar score + Avaliar alertas ───────────────────
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
            self._refresh_mode = False
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
                    except Exception as e:
                        print(f"WARNING: watchlist price_history({name}) failed: {e}",
                              file=__import__('sys').stderr)
                        ph = None
                    if not ph:
                        if not hit:
                            time.sleep(2.0)
                        continue
                    # Backtest samples (igual antes)
                    try:
                        samples = backtest_mod.simulate_item(name, ph)
                    except Exception as e:
                        print(f"WARNING: watchlist simulate({name}) failed: {e}",
                              file=__import__('sys').stderr)
                        samples = []
                    if samples:
                        bridge.samples_ready.emit(samples)
                    # Score atual = enhanced_score com a historia inteira.
                    # Fair-value via mediana 30d, igual ao _mock_verdict_from_history.
                    try:
                        current_score = backtest_mod.score_from_history(
                            name, ph,
                        )
                    except Exception as e:
                        print(f"WARNING: watchlist score({name}) failed: {e}",
                              file=__import__('sys').stderr)
                        current_score = None
                    # Persiste score por item (pra coluna mostrar)
                    item = items_by_name.get(name)
                    if item and current_score is not None:
                        item["current_score"] = int(current_score)
                        item["score_ts"] = time.time()
                    # Data quality (confiança) — computada do mesmo price_history
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

    # ── Filtro de confiança + busca ─────────────────────
    def _apply_confidence_filter(self) -> int:
        """Aplica os dois filtros da tabela: baixa confiança e busca.

        Unificados no mesmo passe porque ambos usam setRowHidden — um
        sobrescreveria o outro se rodassem separados.
        """
        if not hasattr(self, "_hide_low_conf_cb"):
            return 0
        active = self._hide_low_conf_cb.isChecked()
        q = self._search_inp.text().strip().lower()
        hidden = 0
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            if not cell:
                continue
            name = cell.data(Qt.ItemDataRole.UserRole) or cell.text()
            dq = None
            for it in (self._items or []):
                if it.get("name") == name:
                    dq = it.get("data_quality") or {}
                    break
            level = dq.get("level", "none") if dq else "none"
            low_conf = active and level in ("low", "very_low")
            not_matching = bool(q) and q not in cell.text().lower()
            should_hide = low_conf or not_matching
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

    def _on_add(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Adicionar a Watchlist")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)

        name_inp = QLineEdit()
        name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        name_inp.setStyleSheet(t.input_style())
        lay.addWidget(FormRow("Nome do item:", name_inp))

        target_inp = QDoubleSpinBox()
        target_inp.setRange(0, 99999)
        target_inp.setPrefix("R$ ")
        target_inp.setDecimals(2)
        target_inp.setSpecialValueText("R$ 0,00 — sem alvo")
        target_inp.setToolTip(
            "Preço que dispara o alerta de queda. Deixe em R$ 0,00 para "
            "monitorar apenas por regras (queda %, volume, oferta, score).")
        target_inp.setStyleSheet(t.input_style())
        lay.addWidget(FormRow("Preço alvo:", target_inp))

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.setStyleSheet(t.btn_ghost())
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setToolTip("Fecha o dialogo sem adicionar.")
        cancel.clicked.connect(dlg.reject)
        ok = QPushButton("Adicionar")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setToolTip("Adiciona o item à watchlist e fecha.")

        def on_ok():
            name = name_inp.text().strip()
            target = target_inp.value()
            if not name:
                return
            if any(it.get("name") == name for it in self._items):
                self._status.setText(
                    f"“{name}” já está na watchlist — edite as regras pelo "
                    "menu de contexto da linha.")
                dlg.accept()
                return
            wl.add_watch(name, target)
            self.refresh()
            dlg.accept()
            # Regras sao o que faz a watchlist vigiar: oferece configurar
            # na hora, em vez de deixar o item monitorado sem regra.
            item = next((it for it in self._items
                         if it.get("name") == name), None)
            if item is not None:
                rules_dlg = _RulesDialog(item, parent=self)
                if rules_dlg.exec() == QDialog.DialogCode.Accepted:
                    rules = rules_dlg.get_rules()
                    if rules:
                        item["rules"] = rules
                    else:
                        item.pop("rules", None)
                    wl.save_watchlist(self._items)
                    self.refresh()
            self._status.setText(
                "Item adicionado. Clique com o botão direito na linha para "
                "editar regras e preço alvo.")

        ok.clicked.connect(on_ok)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)
        dlg.exec()
