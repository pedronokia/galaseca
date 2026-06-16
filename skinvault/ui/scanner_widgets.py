"""Widgets auxiliares do scanner — _FactorBar, _ScatterPlot, bridges, bucket data."""

from __future__ import annotations

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from skinvault.ui import theme as t


_MAX_FACTOR_DELTA = 35.0

_BUCKET_HISTORY_90D: dict[tuple[int, int], dict] = {
    (0, 30):   {"avg": 2.19,  "hit": 53, "n": 152},
    (30, 50):  {"avg": 9.91,  "hit": 58, "n": 3174},
    (50, 70):  {"avg": 15.92, "hit": 59, "n": 4845},
    (70, 85):  {"avg": 26.99, "hit": 62, "n": 1639},
    (85, 101): {"avg": 50.26, "hit": 75, "n": 186},
}

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


def bucket_for_score(score: int) -> tuple[int, int] | None:
    for (lo, hi) in _BUCKET_HISTORY_90D:
        if lo <= score < hi:
            return (lo, hi)
    return None


def bucket_history() -> dict[tuple[int, int], dict]:
    return _BUCKET_HISTORY_90D


def bucket_history_skin() -> dict[tuple[int, int], dict]:
    return _BUCKET_HISTORY_90D_SKIN


def bucket_history_container() -> dict[tuple[int, int], dict]:
    return _BUCKET_HISTORY_90D_CONTAINER


class _FactorBar(QWidget):
    def __init__(self, delta: float,
                 max_delta: float = _MAX_FACTOR_DELTA,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._delta = float(delta)
        self._max = float(max_delta)
        self.setFixedHeight(18)
        self.setMinimumWidth(180)

    def paintEvent(self, _evt) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx = w // 2
        p.setPen(QPen(QColor(t.BORDER), 1))
        p.drawLine(cx, 1, cx, h - 1)
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


class _ScatterPlot(QWidget):
    _Y_CLAMP = 150.0

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

    def paintEvent(self, _evt) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        margin_l, margin_r = 48, 12
        margin_t, margin_b = 14, 22
        plot_w = w - margin_l - margin_r
        plot_h = h - margin_t - margin_b

        p.fillRect(margin_l, margin_t, plot_w, plot_h, QColor(t.SURFACE))

        if not self._samples or plot_w <= 0 or plot_h <= 0:
            p.setPen(QPen(QColor(t.TEXT_MUTED), 1))
            p.setFont(QFont(t.FONT_FAMILY, 9))
            p.drawText(margin_l + 10, margin_t + plot_h // 2, "Sem amostras")
            p.end()
            return

        clamped = [
            max(min(s["return_pct"], self._Y_CLAMP), -self._Y_CLAMP)
            for s in self._samples
        ]
        y_lo = min(clamped + [0])
        y_hi = max(clamped + [0])
        span = max(y_hi - y_lo, 1.0)
        y_lo -= span * 0.05
        y_hi += span * 0.05

        def to_x(score: float) -> int:
            return int(margin_l + (score / 100.0) * plot_w)

        def to_y(ret: float) -> int:
            return int(margin_t + plot_h
                       - ((ret - y_lo) / (y_hi - y_lo)) * plot_h)

        p.setPen(QPen(QColor(t.BORDER), 1))
        p.drawLine(margin_l, margin_t + plot_h,
                   margin_l + plot_w, margin_t + plot_h)
        p.drawLine(margin_l, margin_t, margin_l, margin_t + plot_h)

        p.setPen(QPen(QColor(t.BORDER), 1, Qt.PenStyle.DotLine))
        for sb in (30, 50, 70, 85):
            x = to_x(sb)
            p.drawLine(x, margin_t, x, margin_t + plot_h)

        if y_lo < 0 < y_hi:
            y0 = to_y(0)
            p.setPen(QPen(QColor(t.TEXT_MUTED), 1, Qt.PenStyle.DashLine))
            p.drawLine(margin_l, y0, margin_l + plot_w, y0)

        p.setPen(Qt.PenStyle.NoPen)
        for sample, ret_clamp in zip(self._samples, clamped):
            color = self._bucket_color(int(sample["score"]))
            conf = sample.get("confidence", 1.0)
            alpha = max(50, min(200, int(50 + conf * 150)))
            color.setAlpha(alpha)
            p.setBrush(QBrush(color))
            cx = to_x(sample["score"])
            cy = to_y(ret_clamp)
            p.drawEllipse(cx - 3, cy - 3, 6, 6)

        p.setPen(QPen(QColor(t.TEXT_MUTED), 1))
        p.setFont(QFont(t.FONT_FAMILY, 8))
        p.drawText(2, margin_t + 8, f"{y_hi:+.0f}%")
        p.drawText(2, margin_t + plot_h, f"{y_lo:+.0f}%")
        if y_lo < 0 < y_hi:
            p.drawText(4, to_y(0) - 2, "0%")
        for sb in (0, 30, 50, 70, 85, 100):
            x = to_x(sb)
            p.drawText(x - 8, margin_t + plot_h + 16, str(sb))

        p.end()


class _ScannerBridge(QObject):
    result_ready = pyqtSignal(dict)
    progress = pyqtSignal(str)


class _ValidationBridge(QObject):
    samples_ready = pyqtSignal(list)
    progress = pyqtSignal(str)
    finished = pyqtSignal()
