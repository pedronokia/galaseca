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
from skinvault.ui.scanner_widgets import _FactorBar, _ScatterPlot


class _ScoreBreakdownDialog(QDialog):
    def __init__(self, item: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        name = item.get("name", "Item")
        self.setWindowTitle(f"Por que essa nota? — {name}")
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
            f"Começa em 50  {'+' if delta_sum >= 0 else '−'} "
            f"{abs(delta_sum):.0f} pontos dos dados  =  {score}"
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
                "high":     (t.POSITIVE,   "Confiança nos dados: alta"),
                "medium":   (t.WARN,       "Confiança nos dados: média"),
                "low":      (t.DANGER,     "Confiança nos dados: BAIXA"),
                "very_low": (t.DANGER,     "Confiança nos dados: MUITO BAIXA"),
                "none":     (t.TEXT_MUTED, "Sem dados"),
            }
            color, lbl_txt = level_colors.get(level, (t.TEXT_MUTED, level))
            conf = dq.get("confidence", 0)
            n = dq.get("n", 0)
            badge = QLabel(
                f"<b style='color:{color}'>{lbl_txt}</b> "
                f"({n} registros de preço no histórico)"
            )
            badge.setTextFormat(Qt.TextFormat.RichText)
            badge.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_BODY};"
                f" font-family: {t.FONT_FAMILY}; padding: 4px 0;"
            )
            layout.addWidget(badge)
            if level in ("low", "very_low"):
                warn = QLabel(
                    "⚠ Com tão pouco histórico, a nota costuma errar: "
                    "no passado, notas assim acertaram menos que um "
                    "chute. Use com muita cautela."
                )
                warn.setStyleSheet(
                    f"color: {t.DANGER}; font-size: {t.FS_MUTED};"
                    f" font-family: {t.FONT_FAMILY}; font-weight: 600;"
                )
                warn.setWordWrap(True)
                layout.addWidget(warn)

        if not breakdown:
            empty = QLabel(
                "Nada se destacou nos dados: a nota ficou neutra (50)."
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

        # Os retornos por faixa que apareciam aqui vinham do backtest de
        # jun/2026, contaminado pelo lookahead do vintage (AGENTS.md 4b).
        # Pra quem le' "nota 75 -> +27%" aquilo soava como promessa. Fica o
        # que foi medido depois e se sustenta.
        honesto = QLabel(
            "<b>O que a nota é:</b> uma comparação entre itens com os dados "
            "de hoje. No histórico, itens com nota alta subiram mais que os "
            "de nota baixa — mas, em vendas rápidas (90 dias), nem os "
            "melhores cobriram a taxa de 15% da Steam. Ela ajuda a escolher, "
            "não garante lucro."
        )
        honesto.setTextFormat(Qt.TextFormat.RichText)
        honesto.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY}; padding: 6px 0;"
        )
        honesto.setWordWrap(True)
        layout.addWidget(honesto)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet(f"color: {t.BORDER}; background: {t.BORDER};")
        sep3.setFixedHeight(1)
        layout.addWidget(sep3)

        legend = QLabel(
            "Como ler:\n"
            "  •  Nota 70 a 100 → COMPRA   •   45 a 69 → ATENÇÃO   •   "
            "abaixo de 45 → EVITAR\n"
            "  •  Toda nota começa em 50. Cada linha acima soma ou tira "
            "pontos.\n"
            "  •  A lista vai do que mais pesou para o que menos pesou."
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
            f"A nota no passado — {len(samples)} situações de "
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
            f"Se você tivesse seguido a nota: o que aconteceu "
            f"{self._horizon} dias depois"
        )
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        layout.addWidget(title)

        if not self._samples:
            empty = QLabel(
                "Nenhuma amostra gerada: os itens têm pouco histórico ou "
                "a Steam não respondeu."
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
            ["Faixa de nota", "Situações", "Retorno médio",
             "% que subiu"]
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
            "Cada ponto é um item numa data: nota (horizontal) × quanto "
            "rendeu depois (vertical). Pontos apagados = pouco histórico."
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
                f"<b>Acerto da nota</b> (Spearman, de −1 a +1): "
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
                f"<b>Outra medida de acerto</b> (Pearson): "
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
                f"<b>Só notas 70+ ({bucket70['n']} situações):</b> "
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
                "Acima de 0: notas mais altas renderam mais — a nota "
                "ajudou. Abaixo de 0: atrapalhou. Entre −0,05 e +0,05 "
                "o efeito é fraco demais para confiar."
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
