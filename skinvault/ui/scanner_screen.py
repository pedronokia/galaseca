"""Tela 3 — Scanner de Investimento (F11).

Escaneia items do Steam Market, calcula score multi-fator,
e permite gerar ranking Top 20.
"""
from __future__ import annotations

import threading
import time

from urllib.parse import quote

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QFont, QPainter, QPen
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

from skinvault import (
    backtest, cases, ranking, signals, ssr_cache, steam_api, valve_events,
)
from skinvault._paths import DATA_DIR
from skinvault.prices import PriceCache
from skinvault.ui import theme as t
from skinvault.ui.components import (
    Card, EmptyState, LoadingState, PageHeader, SectionHeader, StatCard,
    Toast, ToggleSwitch, Toolbar,
)


_MAX_FACTOR_DELTA = 35.0  # peso maximo de qualquer fator no enhanced_score
_CS2_APPID = 730

# Histórico empírico do score por bucket — backtest agregado em 44 itens
# (rifles, pistolas, AWPs, SMG, 25 cases), horizonte 90d, 9996 amostras.
# Atualizado em 2026-06-07 com fator rel_ath UNIVERSAL (skins + containers).
# Correlação agregada: +0.1173.
# (low, high_exclusive): {"avg_return_pct", "hit_rate", "n"}
_BUCKET_HISTORY_90D: dict[tuple[int, int], dict] = {
    (0, 30):   {"avg": 2.19,  "hit": 53, "n": 152},
    (30, 50):  {"avg": 9.91,  "hit": 58, "n": 3174},
    (50, 70):  {"avg": 15.92, "hit": 59, "n": 4845},
    (70, 85):  {"avg": 26.99, "hit": 62, "n": 1639},
    (85, 101): {"avg": 50.26, "hit": 75, "n": 186},
}

# Histórico por tipo de item (skin vs container).
# Score tem magnitudes muito diferentes por tipo:
# - Skins em 70-84 retornam ~+7.5%
# - Containers em 70-84 retornam ~+33%
# Surface essa info pro usuário decidir baseado no tipo do item dele.
_BUCKET_HISTORY_90D_SKIN: dict[tuple[int, int], dict] = {
    (0, 30):   {"avg": 2.19,  "hit": 52, "n": 114},
    (30, 50):  {"avg": 4.60,  "hit": 54, "n": 1868},
    (50, 70):  {"avg": 4.84,  "hit": 53, "n": 2139},
    (70, 85):  {"avg": 7.55,  "hit": 52, "n": 382},
    (85, 101): {"avg": 21.28, "hit": 67, "n": 12},
}
_BUCKET_HISTORY_90D_CONTAINER: dict[tuple[int, int], dict] = {
    (0, 30):   {"avg": 2.20,  "hit": 58, "n": 38},
    (30, 50):  {"avg": 17.52, "hit": 64, "n": 1306},
    (50, 70):  {"avg": 24.68, "hit": 63, "n": 2706},
    (70, 85):  {"avg": 32.90, "hit": 65, "n": 1257},
    (85, 101): {"avg": 52.25, "hit": 76, "n": 174},
}


def _bucket_for_score(score: int) -> tuple[int, int] | None:
    """Retorna (low, high) do bucket histórico ao qual o score pertence."""
    for (lo, hi) in _BUCKET_HISTORY_90D:
        if lo <= score < hi:
            return (lo, hi)
    return None


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
            color = QColor(t.POSITIVE)
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
            verdict_label, vcolor = "COMPRA", t.POSITIVE
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

        # ── Badge de confianca (data_quality) ────────
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

        # ── Breakdown rows ────────────────────────────
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

        # ── Histórico empírico do bucket ─────────────
        bucket = _bucket_for_score(score)
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

            # ── Histórico específico por tipo (skin vs container)
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

        # ── Legenda ───────────────────────────────────
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


class _ScatterPlot(QWidget):
    """Scatter score (x) vs return_pct (y) com cores por bucket.

    Eixos: x = score 0..100. y = retorno %, auto-scale com clamp em ±150%
    para evitar outliers dominarem. Linha tracejada em y=0.
    """

    _Y_CLAMP = 150.0  # retorno % maximo absoluto mostrado

    def __init__(self, samples: list[dict],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples = samples
        self.setMinimumHeight(220)
        self.setMinimumWidth(560)

    def _bucket_color(self, score: int) -> QColor:
        if score < 30:
            return QColor(t.DANGER)
        if score < 50:
            return QColor(t.WARN)
        if score < 70:
            return QColor(t.TEXT_MUTED)
        return QColor(t.POSITIVE)

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin_l, margin_r = 48, 12
        margin_t, margin_b = 14, 22
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        # Background do plot
        p.fillRect(margin_l, margin_t, plot_w, plot_h, QColor(t.SURFACE))

        if not self._samples or plot_w <= 0 or plot_h <= 0:
            p.setPen(QPen(QColor(t.TEXT_MUTED), 1))
            p.setFont(QFont(t.FONT_FAMILY, 9))
            p.drawText(margin_l + 10, margin_t + plot_h // 2,
                       "Sem amostras")
            p.end()
            return

        clamped = [
            max(min(s["return_pct"], self._Y_CLAMP), -self._Y_CLAMP)
            for s in self._samples
        ]
        y_lo = min(clamped + [0])
        y_hi = max(clamped + [0])
        # padding 10% em cada lado
        span = max(y_hi - y_lo, 1.0)
        y_lo -= span * 0.05
        y_hi += span * 0.05

        def to_x(score: float) -> int:
            return int(margin_l + (score / 100.0) * plot_w)

        def to_y(ret: float) -> int:
            return int(margin_t + plot_h
                       - ((ret - y_lo) / (y_hi - y_lo)) * plot_h)

        # Eixos
        p.setPen(QPen(QColor(t.BORDER), 1))
        p.drawLine(margin_l, margin_t + plot_h,
                   margin_l + plot_w, margin_t + plot_h)
        p.drawLine(margin_l, margin_t, margin_l, margin_t + plot_h)

        # Linhas verticais nos limites dos buckets
        p.setPen(QPen(QColor(t.BORDER), 1, Qt.PenStyle.DotLine))
        for sb in (30, 50, 70, 85):
            x = to_x(sb)
            p.drawLine(x, margin_t, x, margin_t + plot_h)

        # Linha zero (tracejada)
        if y_lo < 0 < y_hi:
            y0 = to_y(0)
            p.setPen(QPen(QColor(t.TEXT_MUTED), 1, Qt.PenStyle.DashLine))
            p.drawLine(margin_l, y0, margin_l + plot_w, y0)

        # Pontos: cor = bucket de score; alpha = confidence
        # (confianca alta -> opaco, baixa -> fantasma).
        p.setPen(Qt.PenStyle.NoPen)
        for sample, ret_clamp in zip(self._samples, clamped):
            color = self._bucket_color(int(sample["score"]))
            conf = sample.get("confidence", 1.0)
            # alpha de 50 (very_low) a 200 (high)
            alpha = max(50, min(200, int(50 + conf * 150)))
            color.setAlpha(alpha)
            p.setBrush(QBrush(color))
            cx = to_x(sample["score"])
            cy = to_y(ret_clamp)
            p.drawEllipse(cx - 3, cy - 3, 6, 6)

        # Labels dos eixos
        p.setPen(QPen(QColor(t.TEXT_MUTED), 1))
        p.setFont(QFont(t.FONT_FAMILY, 8))
        # Y labels (min, 0, max)
        p.drawText(2, margin_t + 8, f"{y_hi:+.0f}%")
        p.drawText(2, margin_t + plot_h, f"{y_lo:+.0f}%")
        if y_lo < 0 < y_hi:
            p.drawText(4, to_y(0) - 2, "0%")
        # X labels (score buckets)
        for sb in (0, 30, 50, 70, 85, 100):
            x = to_x(sb)
            p.drawText(x - 8, margin_t + plot_h + 16, str(sb))

        p.end()


class _BacktestResultDialog(QDialog):
    """Mostra resultado do backtest dos itens escaneados (horizonte 90d).

    Para cada bucket de score: n amostras, retorno médio, hit rate.
    Mostra correlação Pearson agregada (score vs retorno).
    """

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

        # Tabela de buckets
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

        # Scatter plot score × retorno
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

        # Correlação agregada (Spearman é default desde 2026-06-08)
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

        # Comparação com baseline empírico
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
    "Caixas": [
        "CS:GO Weapon Case", "CS:GO Weapon Case 2", "CS:GO Weapon Case 3",
        "Operation Bravo Case", "Winter Offensive Weapon Case",
        "Operation Phoenix Weapon Case",
        "Chroma 2 Case", "Chroma 3 Case",
        "Spectrum Case", "Spectrum 2 Case",
        "Glove Case", "Clutch Case",
        "Prisma Case", "Prisma 2 Case",
        "Fracture Case", "Snakebite Case",
        "Dreams & Nightmares Case", "Recoil Case",
        "Revolution Case", "Kilowatt Case",
        "Gallery Case", "Fever Case",
    ],
    "Cápsulas": cases.list_capsules(),
    "Autographs": cases.list_autograph_capsules(),
    "Stickers (Tournament)": cases.list_tournament_stickers(),
    "Stickers (Autograph)": cases.list_autograph_stickers(),
    "Stickers (Community)": cases.list_community_stickers(),
    "Stickers (Event)": cases.list_event_stickers(),
}


class _ScannerBridge(QObject):
    result_ready = pyqtSignal(dict)
    progress = pyqtSignal(str)


class _ValidationBridge(QObject):
    samples_ready = pyqtSignal(list)
    progress = pyqtSignal(str)
    finished = pyqtSignal()


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
    COL_RISCO = 10
    COL_CONFIDENCE = 11

    def __init__(self, cache: PriceCache,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = cache
        self._bridge = _ScannerBridge()
        self._bridge.result_ready.connect(self._on_item_done)
        self._bridge.progress.connect(self._on_progress)
        self._validate_bridge = _ValidationBridge()
        self._validate_bridge.samples_ready.connect(self._on_validate_samples)
        self._validate_bridge.progress.connect(self._on_progress)
        self._validate_bridge.finished.connect(self._on_validate_finished)
        self._scan_results: list[dict] = []
        self._validate_samples: list[dict] = []
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        self._cat_combo = QComboBox()
        self._cat_combo.setStyleSheet(
            f"QComboBox {{ background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: 8px; padding: 8px 12px; color: {t.TEXT};"
            f" font-size: {t.FS_INPUT}; min-width: 160px; }}"
            f"QComboBox:focus {{ border: 1px solid {t.ACCENT}; }}"
            f"QComboBox:drop-down {{ border: none; }}"
            f"QComboBox:down-arrow {{ color: {t.TEXT_MUTED}; }}"
            f"QComboBox QAbstractItemView"
            f" {{ background: {t.BG_ELEVATED}; border: 1px solid {t.BORDER};"
            f" selection-background-color: {t.SURFACE_HOV}; color: {t.TEXT}; }}"
            f"QComboBox QAbstractItemView::item"
            f" {{ padding: 6px 12px; }}"
        )
        for cat in _SCAN_BY_CATEGORY:
            self._cat_combo.addItem(cat)
        self._cat_combo.addItem("Todas as categorias")
        self._cat_combo.currentTextChanged.connect(self._refresh_regime_banner)

        self._scan_btn = QPushButton("Escanear categoria")
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(t.btn_primary(padding="10px 24px"))
        self._scan_btn.setToolTip(
            "Escaneia todos os itens da categoria, calcula score 0-100"
            " e veredito (COMPRA / ATENCAO / EVITAR)."
        )
        self._scan_btn.clicked.connect(self._on_scan)

        self._rank_btn = QPushButton("Ranking Top 20")
        self._rank_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rank_btn.setStyleSheet(t.btn_secondary(padding="10px 18px",
                                                     fs=t.FS_INPUT))
        self._rank_btn.setToolTip(
            "Escaneia TODAS as categorias e gera ranking dos 20 melhores"
            " scores. Demora vários minutos pelo rate-limit do Steam."
        )
        self._rank_btn.clicked.connect(self._on_ranking)

        self._validate_btn = QPushButton("Validar Score")
        self._validate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._validate_btn.setStyleSheet(t.btn_secondary(padding="10px 18px",
                                                          fs=t.FS_INPUT))
        self._validate_btn.setToolTip(
            "Roda backtest histórico nos itens escaneados (horizonte 90d)."
            " Mostra se o score realmente prediz retornos pra esses itens."
            " Demora ~2s por item pelo rate-limit do Steam."
        )
        self._validate_btn.clicked.connect(self._on_validate_score)

        root.addWidget(PageHeader(
            "Scanner de Oportunidades",
            "Análise multi-fator — score 0-100.",
            actions=[self._cat_combo, self._scan_btn, self._rank_btn, self._validate_btn],
        ))

        # Banner de aviso quando update recente da Valve afetou a categoria
        self._regime_banner = QLabel()
        self._regime_banner.setWordWrap(True)
        self._regime_banner.setStyleSheet(
            f"background: {t.WARN_BG}; border: 1px solid {t.WARN_BORDER};"
            f" color: {t.WARN_TEXT}; border-radius: 8px;"
            f" padding: 10px 14px; font-size: {t.FS_INPUT};"
            f" font-family: {t.FONT_FAMILY};"
        )
        self._regime_banner.setVisible(False)
        root.addWidget(self._regime_banner)

        # Stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self._stat_count = StatCard("Itens escaneados", "0", icon="radar")
        self._stat_count.setMaximumWidth(300)
        self._stat_best = StatCard("Melhor score", "—", icon="trophy")
        self._stat_best.setMaximumWidth(300)
        self._stat_avg = StatCard("Score medio", "—", icon="chart")
        self._stat_avg.setMaximumWidth(300)
        for sc in (self._stat_count, self._stat_best, self._stat_avg):
            stats_row.addWidget(sc)
        stats_row.addStretch(1)
        root.addLayout(stats_row)

        # Ghost buttons (Limpar cache SSR, Exportar CSV) — acima da tabela
        ghost_tb = Toolbar()
        self._clear_cache_btn = QPushButton("Limpar cache SSR")
        self._clear_cache_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_cache_btn.setStyleSheet(t.btn_ghost())
        self._clear_cache_btn.setToolTip(
            "Limpa o cache local de dados SSR (PriceHistoryCache)."
            " Útil quando você quer forçar busca nova da Steam na próxima"
            " consulta. O cache expira automaticamente em 24h."
        )
        self._clear_cache_btn.clicked.connect(self._on_clear_ssr_cache)
        ghost_tb.add_right(self._clear_cache_btn)

        self._export_btn = QPushButton("Exportar CSV")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setStyleSheet(t.btn_ghost())
        self._export_btn.setToolTip(
            "Exporta os resultados do scan atual para CSV."
            " Abre dialogo para escolher nome e pasta."
        )
        self._export_btn.clicked.connect(self._on_export_csv)
        self._export_btn.setEnabled(False)
        ghost_tb.add_right(self._export_btn)

        root.addWidget(ghost_tb)

        # Filtros acima da tabela
        from skinvault.settings import load_settings as _load
        _s = _load()
        filt_row = QHBoxLayout()
        filt_row.setSpacing(12)
        self._hide_low_conf_cb = ToggleSwitch(
            checked=bool(_s.get("scanner_hide_low_confidence", False))
        )
        self._hide_low_conf_cb.setToolTip(
            "Itens com score < 45 sao classificados como baixa confianca. "
            "Ative para filtrar ruido visual."
        )
        self._hide_low_conf_cb.toggled.connect(self._on_hide_low_conf_toggle)
        filt_row.addWidget(self._hide_low_conf_cb)
        _lbl1 = QLabel("Baixa confiança")
        _lbl1.setStyleSheet(t.label_caption())
        _lbl1.setToolTip(
            "Itens com score < 45 sao classificados como baixa confianca."
        )
        filt_row.addWidget(_lbl1)

        self._hide_approx_cb = ToggleSwitch(
            checked=bool(_s.get("scanner_hide_approx", False))
        )
        self._hide_approx_cb.setToolTip(
            "Oculta itens onde o order book veio de outro wear do mesmo"
            " skin (aproximação). A Steam não expõe o item_nameid"
            " necessário para o book exato deste wear."
        )
        self._hide_approx_cb.toggled.connect(self._on_hide_approx_toggle)
        filt_row.addWidget(self._hide_approx_cb)
        _lbl2 = QLabel("Order book aprox.")
        _lbl2.setStyleSheet(t.label_caption())
        _lbl2.setToolTip(
            "Itens com order book de wear alternativo (proxy)."
        )
        filt_row.addWidget(_lbl2)
        filt_row.addStretch(1)
        root.addLayout(filt_row)

        # Loading state (mostrado durante scan/validacao)
        self._loading = LoadingState(parent=self)
        self._loading.setVisible(False)
        root.addWidget(self._loading, 0, Qt.AlignmentFlag.AlignCenter)

        # Tabela
        self._table = QTableWidget(0, 12)
        self._table.setHorizontalHeaderLabels([
            "Item", "Sinal", "Preco", "Preco justo", "Veredito",
            "Spread", "Book", "Tendencia", "Oferta/Demanda", "Score", "Risco", "Confiança",
        ])
        t.configure_table(self._table)
        score_hdr = self._table.horizontalHeaderItem(self.COL_SCORE)
        if score_hdr:
            score_hdr.setToolTip(
                "Duplo-clique numa linha para ver o breakdown completo"
                " do score por fator (mediana, spread, book, tendência,"
                " oferta/demanda, etc.)."
            )
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 12):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self._table.doubleClicked.connect(
            lambda _idx: self._on_explain_selected()
        )
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.customContextMenuRequested.connect(self._on_ctx_menu)
        root.addWidget(self._table, 1)

        # Empty state: ainda nao escaneou nenhum item
        self._empty_hero = EmptyState(
            icon="◎",
            title="Pronto pra escanear",
            subtitle=("Escolha uma categoria acima e clique em Escanear\n"
                       "para descobrir oportunidades."),
            steps=["Escolha uma categoria (Rifles, Facas, Luvas…).",
                   "Clique em Escanear para analisar preços e sinais.",
                   "Duplo-clique numa linha para ver o breakdown do score."],
        )
        root.addWidget(self._empty_hero, 1)
        # Estado inicial: hero visivel, tabela escondida
        self._table.setVisible(False)

        # Progress/status
        self._status = QLabel("Pronto. Selecione uma categoria e clique em Escanear.")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
        )
        root.addWidget(self._status)

        # Reflete categoria inicial no banner (ja apos widgets prontos)
        self._refresh_regime_banner(self._cat_combo.currentText())

    def _refresh_regime_banner(self, category: str) -> None:
        """Mostra aviso amarelo quando update recente da Valve mudou regime."""
        ev = valve_events.latest_regime_change(category)
        if ev is None:
            self._regime_banner.setVisible(False)
            return
        from datetime import date as _date
        days_ago = (_date.today() - ev["date"]).days
        if days_ago > 180:
            self._regime_banner.setVisible(False)
            return
        when = ev["date"].strftime("%d/%m/%Y")
        self._regime_banner.setText(
            f"Aviso — update recente da Valve afetou {category}: "
            f"{ev['title']} ({when}, ha {days_ago} dias). "
            f"Regime de mercado pode ter mudado; interprete o score com cautela."
        )
        self._regime_banner.setToolTip(ev["summary"])
        self._regime_banner.setVisible(True)

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
        # Mostra a tabela vazia (vai encher progressivamente) e esconde hero
        self._empty_hero.setVisible(False)
        self._table.setVisible(True)
        self._scan_btn.setEnabled(False)
        self._rank_btn.setEnabled(False)
        self._validate_btn.setEnabled(False)
        self._status.setText(f"Escaneando {len(items)} itens...")
        self._loading.set_label(f"Escaneando {len(items)} itens...")
        self._loading.setVisible(True)

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
            time.sleep(1.0)  # rate-limit entre endpoints
            page = steam_api.get_market_page_data(name)
        except Exception:
            return None

        lowest = overview.get("lowest") if overview else None
        median = overview.get("median") if overview else None
        volume = overview.get("volume") if overview else None
        derived_price = False

        if lowest is None and page and page.get("price_history"):
            ph = page["price_history"]
            last = ph[-1]
            price_val = last.get("price_median")
            if price_val and price_val > 0:
                lowest = price_val
                derived_price = True

        if lowest is None:
            return None

        self._cache.put(name, lowest)

        ob = page.get("order_book") if page else None
        verdict = steam_api.fair_value_verdict(
            lowest, median,
            spread=ob.get("spread") if ob else None,
            buy_count=ob.get("buy_count") if ob else None,
            sell_count=ob.get("sell_count") if ob else None,
            price_history=page.get("price_history") if page else None,
        ) if page else steam_api.fair_value_verdict(lowest, median)
        signals.record_item_price(name, lowest)
        if volume:
            signals.record_item_volume(name, volume)
        supply = ob.get("sell_count") if ob else None
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
            is_container=cases.is_container(name),
        )

        dq = signals.data_quality(
            page.get("price_history") if page else []
        )

        # Deriva categoria para valve_events exclusion no pump_risk
        _item_cat = next(
            (c for c, items in _SCAN_BY_CATEGORY.items() if name in items),
            None,
        )
        pr = signals.pump_risk(
            price_history=page.get("price_history") if page else None,
            volume_history=signals.load_item_volume(name),
            category=_item_cat,
        )

        ob_approx = bool(page.get("order_book_approx")) if page else False
        approx_suffix = " ~" if ob_approx else ""
        price_str = f"{lowest:.2f}{' *' if derived_price else ''}"
        return {
            "name": name,
            "price": lowest,
            "price_str": price_str,
            "median": median,
            "score": score,
            "breakdown": breakdown,
            "data_quality": dq,
            "is_container": cases.is_container(name),
            "verdict": verdict.get("label", "—"),
            "verdict_color": t.POSITIVE if verdict.get("diff_pct", 0) <= 0
                             else t.DANGER,
            "spread": (verdict.get("spread_verdict", "") +
                       (approx_suffix if verdict.get("spread_verdict") else "")),
            "book": (verdict.get("book_verdict", "") +
                     (approx_suffix if verdict.get("book_verdict") else "")),
            "trend": verdict.get("trend_verdict", ""),
            "volume": volume,
            "supply": supply,
            "sd_label": signals.supply_demand_ratio(volume, supply).get("label", ""),
            "score_tooltip": signals.format_breakdown(breakdown),
            "case_label": cs.get("label", ""),
            "pump_risk": pr,
            "order_book_approx": ob_approx,
            "derived_price": derived_price,
        }

    def _on_item_done(self, result: dict) -> None:
        self._scan_results.append(result)
        self._scan_results.sort(key=lambda r: r["score"], reverse=True)
        # Primeira chegada esconde o empty hero
        if self._empty_hero.isVisible():
            self._empty_hero.setVisible(False)
            self._table.setVisible(True)
        self._populate()

    def _populate(self) -> None:
        was_sorting = self._table.isSortingEnabled()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, r in enumerate(self._scan_results):
            self._table.insertRow(i)
            score = r["score"]
            score_color = t.POSITIVE if score >= 70 else (
                t.WARN if score >= 45 else t.DANGER
            )
            label = "COMPRA" if score >= 70 else (
                "ATENCAO" if score >= 45 else "EVITAR"
            )
            from skinvault.localization import localize_name as _ln
            dq = r.get("data_quality") or {}
            dq_level = dq.get("level", "none")
            dq_conf = dq.get("confidence", 0)
            dq_n = dq.get("n", 0)
            _dq_color_map = {
                "high": t.POSITIVE, "medium": t.WARN,
                "low": t.DANGER, "very_low": t.DANGER,
                "none": t.TEXT_MUTED,
            }
            _dq_label_map = {
                "high": "Alta", "medium": "Média",
                "low": "Baixa", "very_low": "Mín.",
                "none": "—",
            }
            dq_color = _dq_color_map.get(dq_level, t.TEXT_MUTED)
            dq_label = _dq_label_map.get(dq_level, "—")
            pr = r.get("pump_risk") or {"level": "low", "reasons": []}
            risk_level = pr.get("level", "low")
            risk_colors = {"low": t.TEXT_MUTED, "medium": t.WARN, "high": t.DANGER}
            risk_labels = {"low": "Baixo", "medium": "Médio", "high": "Alto"}
            risk_color = risk_colors.get(risk_level, t.TEXT_MUTED)
            risk_label = risk_labels.get(risk_level, "—")
            cells = [
                (_ln(r["name"]), None),
                (label, score_color),
                (r.get("price_str", t.brl(r["price"])), None),
                (t.brl(r["median"]), None),
                (r["verdict"], r["verdict_color"]),
                (r["spread"], None),
                (r["book"], None),
                (r["trend"], None),
                (r["sd_label"], None),
                (str(score), score_color),
                (risk_label, risk_color),
                (dq_label, dq_color),
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
            # Tooltip do risco
            if pr.get("reasons"):
                risco_tip = (
                    f"Risco: {risk_level.upper()}\n"
                    + "\n".join(f"• {m}" for m in pr["reasons"])
                    + "\n\nCombinação de sinais factuais de pump-and-dump / "
                    "falling knife. NÃO é penalidade no score — "
                    "apenas informação visual.\n"
                    "Alto = 2+ flags combinadas (ATH + rally + volume)."
                )
                self._table.item(i, self.COL_RISCO).setToolTip(risco_tip)
            # Tooltip da confidence
            if dq:
                conf_tip = (
                    f"Confiança: {dq_label} ({dq_conf:.2f})\n"
                    f"Histórico: {dq_n} pontos\n"
                    f"Empiricamente, score em itens com baixa confiança\n"
                    f"é anti-preditivo (corr -0.14 nos backtests)."
                )
                cell_conf = self._table.item(i, self.COL_CONFIDENCE)
                if cell_conf is not None:
                    cell_conf.setToolTip(conf_tip)
            # Tooltip explicando "~" quando order_book vem de outro wear
            if r.get("order_book_approx"):
                msg = (
                    "Steam só pré-carrega order book de um wear do skin; "
                    "este valor vem de outra variante do mesmo item. "
                    "Use como aproximação — pode diferir do wear exato."
                )
                for c in (self.COL_SPREAD, self.COL_BOOK):
                    cell = self._table.item(i, c)
                    if cell is not None and cell.text():
                        cell.setForeground(QBrush(QColor(t.WARN)))
                        cell.setToolTip(msg)
            # Tooltip para preco derivado do historico (sem overview)
            if r.get("derived_price"):
                prec_cell = self._table.item(i, self.COL_PRECO)
                if prec_cell is not None:
                    prec_cell.setForeground(QBrush(QColor(t.WARN)))
                    prec_cell.setToolTip(
                        "Preço atual indisponível no Steam Market Overview."
                        " Valor aproximado do último ponto do histórico SSR."
                        " Pode diferir do preço real de listagem."
                    )
        # Alinhamento por coluna: dinheiro → direita, status → centro
        right_cols = {self.COL_PRECO, self.COL_JUSTO, self.COL_SCORE}
        center_cols = {
            self.COL_SINAL, self.COL_VEREDITO, self.COL_SPREAD,
            self.COL_BOOK, self.COL_TREND, self.COL_SD,
            self.COL_RISCO, self.COL_CONFIDENCE,
        }
        t.align_table_columns(self._table, right=right_cols, center=center_cols)
        self._table.setSortingEnabled(was_sorting)

        # Aplica filtro de order book approx (so esconde, nunca mostra)
        self._apply_approx_filter()
        # Aplica filtro de baixa confianca (roda por ultimo para nao
        # ser sobrescrito pelo filtro de approx)
        hidden = self._apply_confidence_filter()

        # Stats
        if self._scan_results:
            scores = [r["score"] for r in self._scan_results]
            self._stat_count.set_value(str(len(self._scan_results)))
            self._stat_best.set_value(str(max(scores)),
                                      accent=t.POSITIVE)
            self._stat_avg.set_value(str(round(sum(scores)/len(scores))))
        n = len(self._scan_results)
        if hidden:
            self._status.setText(
                f"{n} itens escaneados ({hidden} ocultos por baixa confiança)"
            )
        else:
            self._status.setText(f"{n} itens escaneados")

    def _apply_confidence_filter(self) -> int:
        """Aplica/remove esconder baixa confianca. Retorna # ocultas."""
        if not hasattr(self, "_hide_low_conf_cb"):
            return 0
        active = self._hide_low_conf_cb.isChecked()
        hidden = 0
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            r = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if not isinstance(r, dict):
                continue
            dq = r.get("data_quality") or {}
            level = dq.get("level", "none")
            should_hide = active and level in ("low", "very_low")
            self._table.setRowHidden(row, should_hide)
            if should_hide:
                hidden += 1
        return hidden

    def _on_hide_low_conf_toggle(self, checked: bool) -> None:
        from skinvault.settings import (
            load_settings as _ls, save_settings as _ss,
        )
        s = _ls()
        s["scanner_hide_low_confidence"] = bool(checked)
        _ss(s)
        hidden = self._apply_confidence_filter()
        n = len(self._scan_results)
        if hidden:
            self._status.setText(
                f"{n} itens escaneados ({hidden} ocultos por baixa confiança)"
            )
        else:
            self._status.setText(f"{n} itens escaneados")

    def _apply_approx_filter(self) -> int:
        """Aplica esconder order book approx. Retorna # ocultas.
        So' esconde (nunca mostra) para nao sobrescrever conf filter."""
        if not hasattr(self, "_hide_approx_cb"):
            return 0
        active = self._hide_approx_cb.isChecked()
        hidden = 0
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            r = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if not isinstance(r, dict):
                continue
            if active and r.get("order_book_approx"):
                self._table.setRowHidden(row, True)
                hidden += 1
        return hidden

    def _on_hide_approx_toggle(self, checked: bool) -> None:
        from skinvault.settings import (
            load_settings as _ls, save_settings as _ss,
        )
        s = _ls()
        s["scanner_hide_approx"] = bool(checked)
        _ss(s)
        if self._scan_results:
            self._populate()

    def _on_progress(self, msg: str) -> None:
        if msg == "FIM":
            self._scan_btn.setEnabled(True)
            self._rank_btn.setEnabled(True)
            self._validate_btn.setEnabled(True)
            self._export_btn.setEnabled(True)
            self._loading.setVisible(False)
            self._status.setText(
                f"Scan concluido: {len(self._scan_results)} itens"
            )
        else:
            self._loading.setVisible(True)
            self._loading.set_label(msg)
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

    # ── limpar cache SSR ────────────────────────────────
    def _on_clear_ssr_cache(self) -> None:
        from PyQt6.QtWidgets import QMessageBox
        cache = ssr_cache.PriceHistoryCache()
        size = cache.size()
        mb = QMessageBox(self)
        mb.setWindowTitle("Limpar cache SSR?")
        mb.setText(
            f"Os dados SSR baixados da Steam serão apagados ({size} itens).\n"
            "Na próxima consulta os dados serão baixados novamente."
        )
        mb.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        mb.setDefaultButton(QMessageBox.StandardButton.No)
        if mb.exec() != QMessageBox.StandardButton.Yes:
            return
        cache.clear()
        Toast.show_toast(self, "Cache SSR limpo. Dados serão baixados na próxima consulta.", "info")

    def _on_export_csv(self) -> None:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        if not self._scan_results:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar CSV", "scan_results.csv",
            "CSV (*.csv);;Todos (*)",
        )
        if not path:
            return
        import csv, io
        cols = [
            "Item", "Score", "Veredito", "Preco", "Justo",
            "Spread", "Book", "Tendencia", "Oferta/Demanda",
            "Confianca", "Categoria", "Risco",
        ]
        try:
            with io.open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in self._scan_results:
                    dq = r.get("data_quality") or {}
                    pr = r.get("pump_risk") or {}
                    risk = pr.get("level", "")
                    case_label = r.get("case_label", "")
                    price_val = r.get("price", "")
                    med_val = r.get("median", "")
                    if isinstance(price_val, (int, float)):
                        price_s = f"{price_val:.2f}"
                    else:
                        price_s = str(price_val)
                    if isinstance(med_val, (int, float)):
                        med_s = f"{med_val:.2f}"
                    else:
                        med_s = str(med_val)
                    w.writerow([
                        r.get("name", ""),
                        r.get("score", ""),
                        r.get("verdict", ""),
                        price_s,
                        med_s,
                        r.get("spread", ""),
                        r.get("book", ""),
                        r.get("trend", ""),
                        r.get("sd_label", ""),
                        dq.get("level", ""),
                        case_label,
                        risk,
                    ])
            Toast.show_toast(self, f"Exportado: {path}", "success")
        except Exception as e:
            Toast.show_toast(self, f"Erro ao exportar: {e}", "error")

    # ── validacao do score (backtest ao vivo) ────────────
    def _on_validate_score(self) -> None:
        if not self._scan_results:
            Toast.show_toast(self, "Escaneie itens antes de validar.", "warning")
            return
        names = [r["name"] for r in self._scan_results]
        self._validate_samples = []
        self._scan_btn.setEnabled(False)
        self._rank_btn.setEnabled(False)
        self._validate_btn.setEnabled(False)
        self._loading.set_label(f"Validando {len(names)} itens...")
        self._loading.setVisible(True)
        bridge = self._validate_bridge
        cache = ssr_cache.PriceHistoryCache()

        def _worker() -> None:
            try:
                for i, name in enumerate(names, start=1):
                    hit = cache.has(name)
                    tag = "cache" if hit else "buscando"
                    bridge.progress.emit(
                        f"Validando [{i}/{len(names)}] {name} ({tag})"
                    )
                    try:
                        price_history = ssr_cache.cached_price_history(
                            name, cache=cache,
                        )
                    except Exception:
                        price_history = None
                    if price_history:
                        try:
                            samples = backtest.simulate_item(
                                name, price_history,
                            )
                        except Exception:
                            samples = []
                        if samples:
                            bridge.samples_ready.emit(samples)
                    # Rate-limit so' em fetch (cache hit nao bate Steam)
                    if not hit:
                        time.sleep(2.0)
            finally:
                bridge.finished.emit()

        threading.Thread(target=_worker, daemon=True).start()

    def _on_validate_samples(self, samples: list) -> None:
        self._validate_samples.extend(samples)

    def _on_validate_finished(self) -> None:
        self._scan_btn.setEnabled(True)
        self._rank_btn.setEnabled(True)
        self._validate_btn.setEnabled(True)
        self._loading.setVisible(False)
        items_count = len(self._scan_results)
        n = len(self._validate_samples)
        self._status.setText(
            f"Validacao concluida: {n} amostras de {items_count} itens"
        )
        dlg = _BacktestResultDialog(
            self._validate_samples, items_count, parent=self,
        )
        dlg.exec()
