"""Dialogs do scanner — _ScoreBreakdownDialog e _BacktestResultDialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import backtest
from skinvault.ui import theme as t
from skinvault.ui.scanner_widgets import (
    _BUCKET_HISTORY_90D,
    _BUCKET_HISTORY_90D_CONTAINER,
    _BUCKET_HISTORY_90D_SKIN,
    _FactorBar,
    _ScatterPlot,
    bucket_for_score,
)


class _ScoreBreakdownDialog(QDialog):
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
            verdict_label, vcolor = "COMPRA", t.POSITIVE
        elif score >= 45:
            verdict_label, vcolor = "ATENÇÃO", t.WARN
        else:
            verdict_label, vcolor = "EVITAR", t.DANGER

        breakdown = item.get("breakdown") or []
        delta_sum = sum(b["delta"] for b in breakdown)

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
        formula.setStyleSheet(t.label_caption())
        info_col.addWidget(formula)
        hdr.addLayout(info_col, 1)

        score_lbl = QLabel(str(score))
        score_lbl.setStyleSheet(
            f"color: {vcolor}; font-size: {t.FS_DISPLAY}; font-weight: 700;"
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

        dq = item.get("data_quality") or {}
        if dq:
            level = dq.get("level", "none")
            level_colors = {
                "high":     (t.POSITIVE,   "Confiança alta"),
                "medium":   (t.WARN,       "Confiança média"),
                "low":      (t.DANGER,     "Confiança BAIXA"),
                "very_low": (t.DANGER,     "Confiança MUITO BAIXA"),
                "none":     (t.TEXT_MUTED, "Sem dados"),
            }
            color, lbl_txt = level_colors.get(level, (t.TEXT_MUTED, level))
            conf = dq.get("confidence", 0)
            n = dq.get("n", 0)
            badge = QLabel(
                f"<b style='color:{color}'>{lbl_txt}</b> "
                f"({conf:.2f}, n={n} pontos no histórico)"
            )
            badge.setTextFormat(Qt.TextFormat.RichText)
            badge.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY}; padding: 4px 0;"
            )
            layout.addWidget(badge)
            if level in ("low", "very_low"):
                warn = QLabel(
                    "⚠ Score nesta faixa de confiança é estatisticamente "
                    "anti-preditivo nos backtests (corr -0.14 em n=75). "
                    "Trate com ceticismo."
                )
                warn.setStyleSheet(
                    f"color: {t.DANGER}; font-size: {t.FS_MUTED};"
                    f" font-family: {t.FONT_FAMILY}; font-weight: 600;"
                )
                warn.setWordWrap(True)
                layout.addWidget(warn)

        if not breakdown:
            empty = QLabel(
                "Sem fatores relevantes — score ficou na base neutra (50)."
            )
            empty.setStyleSheet(t.label_body_muted())
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
                d_color = t.POSITIVE if d > 0 else t.DANGER
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

        bucket = bucket_for_score(score)
        if bucket:
            stats = _BUCKET_HISTORY_90D[bucket]
            lo, hi = bucket
            hi_label = min(hi - 1, 100)
            avg = stats["avg"]
            hit = stats["hit"]
            n = stats["n"]
            color = t.POSITIVE if avg > 5 else (t.WARN if avg > 0 else t.DANGER)
            insufficient = " (amostra pequena)" if n < 30 else ""
            hist_lbl = QLabel(
                f"Histórico em 90 dias: itens com score {lo}-{hi_label} "
                f"retornaram em média <b style='color:{color}'>"
                f"{avg:+.1f}%</b>, com {hit}% de acertos "
                f"(n={n} amostras{insufficient})."
            )
            hist_lbl.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY}; padding: 6px 0;"
            )
            hist_lbl.setWordWrap(True)
            hist_lbl.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(hist_lbl)

            is_cont = item.get("is_container")
            if is_cont is not None:
                type_dict = (_BUCKET_HISTORY_90D_CONTAINER if is_cont
                             else _BUCKET_HISTORY_90D_SKIN)
                type_stats = type_dict.get(bucket, {})
                type_avg = type_stats.get("avg", 0)
                type_hit = type_stats.get("hit", 0)
                type_n = type_stats.get("n", 0)
                if type_n >= 30:
                    type_color = (t.POSITIVE if type_avg > 5
                                  else (t.WARN if type_avg > 0
                                        else t.DANGER))
                    type_label = "containers" if is_cont else "skins"
                    type_lbl = QLabel(
                        f"<b>Específico para {type_label}:</b> "
                        f"<b style='color:{type_color}'>"
                        f"{type_avg:+.1f}%</b> avg, {type_hit}% hit rate "
                        f"(n={type_n}). "
                        f"Score 70-84 em containers retorna ~+33%; "
                        f"em skins, ~+8%."
                    )
                    type_lbl.setTextFormat(Qt.TextFormat.RichText)
                    type_lbl.setStyleSheet(
                        f"color: {t.TEXT}; font-size: {t.FS_MUTED};"
                        f" font-family: {t.FONT_FAMILY}; padding: 2px 0;"
                    )
                    type_lbl.setWordWrap(True)
                    layout.addWidget(type_lbl)

            hist_src = QLabel(
                "Fonte: backtest agregado em 44 itens (rifles, pistolas, "
                "AWPs, SMG, 25 cases — 9996 amostras, 2026-06-07, "
                "fator rel_ath universal). Não é garantia — descreve "
                "comportamento passado."
            )
            hist_src.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
                f" font-family: {t.FONT_FAMILY}; font-style: italic;"
            )
            hist_src.setWordWrap(True)
            layout.addWidget(hist_src)

            sep3 = QFrame()
            sep3.setFrameShape(QFrame.Shape.HLine)
            sep3.setStyleSheet(f"color: {t.BORDER}; background: {t.BORDER};")
            sep3.setFixedHeight(1)
            layout.addWidget(sep3)

        legend = QLabel(
            "Como interpretar:\n"
            "  •  Score 70–100 → COMPRA   •   45–69 → ATENÇÃO   •   "
            "<45 → EVITAR\n"
            "  •  Base 50 é o ponto neutro. Cada fator soma ou subtrai "
            "pontos do score.\n"
            "  •  Lista ordenada do fator mais impactante ao menos."
        )
        legend.setStyleSheet(t.label_caption())
        legend.setWordWrap(True)
        layout.addWidget(legend)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            t.btn_secondary()
        )
        layout.addWidget(bb)


class _BacktestResultDialog(QDialog):
    def __init__(self, samples: list[dict], items_count: int,
                 horizon_days: int = 90,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples = samples
        self._items_count = items_count
        self._horizon = horizon_days
        self.setWindowTitle(
            f"Validação do score — {len(samples)} amostras de "
            f"{items_count} itens"
        )
        self.setMinimumWidth(640)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel(
            f"Backtest dos itens escaneados (horizonte {self._horizon}d)"
        )
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        layout.addWidget(title)

        if not self._samples:
            empty = QLabel(
                "Nenhuma amostra gerada. Itens podem ter histórico curto demais "
                "ou Steam não respondeu."
            )
            empty.setStyleSheet(t.label_body_muted())
            empty.setWordWrap(True)
            layout.addWidget(empty)
            self._add_close(layout)
            return

        buckets = backtest.aggregate_by_bucket(self._samples)
        spearman_corr = backtest.correlation(self._samples)
        pearson_corr = backtest.pearson_correlation(self._samples)
        bucket70 = backtest.correlation_by_bucket(self._samples, 70, 101)

        bucket_table = QTableWidget(len(buckets), 4)
        bucket_table.setHorizontalHeaderLabels(
            ["Bucket de score", "N amostras", "Retorno médio", "Hit rate"]
        )
        bucket_table.verticalHeader().setVisible(False)
        bucket_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        bucket_table.setStyleSheet(t.table_style())
        hh = bucket_table.horizontalHeader()
        for i in range(4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        for row, b in enumerate(buckets):
            avg = b["avg_return_pct"]
            color = (t.POSITIVE if avg > 5 else
                     (t.WARN if avg > 0 else t.DANGER))
            bucket_table.setItem(row, 0, QTableWidgetItem(b["bucket"]))
            bucket_table.setItem(row, 1, QTableWidgetItem(str(b["n"])))
            avg_item = QTableWidgetItem(f"{avg:+.2f}%")
            if b["n"] > 0:
                avg_item.setForeground(QBrush(QColor(color)))
            bucket_table.setItem(row, 2, avg_item)
            hit_item = QTableWidgetItem(
                f"{b['hit_rate']:.1f}%" if b["n"] > 0 else "—"
            )
            bucket_table.setItem(row, 3, hit_item)

        bucket_table.setMinimumHeight(180)
        layout.addWidget(bucket_table)

        scatter_lbl = QLabel(
            "Distribuição score × retorno — cor = bucket, "
            "opacidade = confiança (pontos esmaecidos = baixa confiança):"
        )
        scatter_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; padding-top: 4px;"
        )
        layout.addWidget(scatter_lbl)
        scatter = _ScatterPlot(self._samples)
        layout.addWidget(scatter)

        if spearman_corr is not None:
            scolor = (t.POSITIVE if spearman_corr > 0.05 else
                      (t.WARN if spearman_corr > 0 else t.DANGER))
            s_lbl = QLabel(
                f"<b>Spearman (score × retorno) — default:</b> "
                f"<span style='color:{scolor}'>{spearman_corr:+.4f}</span>"
            )
            s_lbl.setTextFormat(Qt.TextFormat.RichText)
            s_lbl.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY}; padding: 4px 0;"
            )
            layout.addWidget(s_lbl)

        if pearson_corr is not None:
            pcolor = (t.POSITIVE if pearson_corr > 0.05 else
                      (t.WARN if pearson_corr > 0 else t.DANGER))
            p_lbl = QLabel(
                f"<b>Pearson (score × retorno):</b> "
                f"<span style='color:{pcolor}'>{pearson_corr:+.4f}</span>"
            )
            p_lbl.setTextFormat(Qt.TextFormat.RichText)
            p_lbl.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY}; padding: 2px 0;"
            )
            layout.addWidget(p_lbl)

        if bucket70["n"] >= 3:
            b70_text = (
                f"<b>Bucket 70+ (n={bucket70['n']}):</b> "
                f"Spearman {bucket70['spearman']:+.4f}, "
                f"Pearson {bucket70['pearson']:+.4f}"
            )
            b70_lbl = QLabel(b70_text)
            b70_lbl.setTextFormat(Qt.TextFormat.RichText)
            b70_lbl.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY}; padding: 2px 0;"
            )
            layout.addWidget(b70_lbl)

        if spearman_corr is not None or pearson_corr is not None:
            interp = QLabel(
                "Valores > 0 indicam que score maior se associa a "
                "retorno maior — o score está prevendo. < 0 seria "
                "anti-sinal. Valores entre ±0.05 são fracos. "
                "Spearman é a métrica default desde 08/06/2026 — "
                "mais robusto que Pearson quando a relação é "
                "S-shaped (fraca no meio, forte nos extremos)."
            )
            interp.setStyleSheet(t.label_caption())
            interp.setWordWrap(True)
            layout.addWidget(interp)

        baseline = QLabel(
            "<i>Comparação:</i> baseline agregado em 44 itens "
            "(2026-06-07, 9996 amostras, rel_ath universal) foi "
            "<b>+0.1173</b>. Valores próximos ou acima indicam que o "
            "score funciona tão bem ou melhor nos seus itens."
        )
        baseline.setTextFormat(Qt.TextFormat.RichText)
        baseline.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; padding-top: 6px;"
        )
        baseline.setWordWrap(True)
        layout.addWidget(baseline)

        self._add_close(layout)

    def _add_close(self, layout: QVBoxLayout) -> None:
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            t.btn_secondary()
        )
        layout.addWidget(bb)
