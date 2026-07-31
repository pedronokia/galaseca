"""Componentes reutilizaveis do esqueleto navegacional (F11).

Breadcrumb + Footer + SegmentedControl + Toast + EmptyState + LineIcon +
ActivityFeed + Avatar + ToggleSwitch + demais widgets de layout.
Sidebar e Card/StatCard estao em .sidebar e .cards respectivamente.
"""
from __future__ import annotations

import re

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .cards import Card, StatCard
from .sidebar import _SidebarItem, Sidebar


class SortableItem(QTableWidgetItem):
    """Celula de tabela que ordena pelo VALOR, nao pelo texto exibido.

    `QTableWidgetItem` compara por DisplayRole, entao qualquer coluna
    formatada ordenava como string. Medido em 2026-07-30 nos 25 trades
    reais, ordenando P&L decrescente:

        R$ -7,54 | R$ -1,96 | R$ -1,94 | R$ 1,63 | R$ -0,85 ...

    O maior PREJUIZO aparecia no topo, porque '7' > '1' como caractere.
    Data ordenava por dia do mes (30/04/2026 antes de 29/05/2026) e
    R$ 16,49 ficava abaixo de R$ 9,66.

    `key` e' o valor cru (float, int ou timestamp). Use float("-inf") pra
    ausente, pra ele cair no fim da ordem decrescente.
    """

    def __init__(self, text: str, key) -> None:
        super().__init__(text)
        self._sort_key = key

    def __lt__(self, other) -> bool:
        outro = getattr(other, "_sort_key", None)
        if outro is None:
            return super().__lt__(other)
        try:
            return self._sort_key < outro
        except TypeError:
            return str(self._sort_key) < str(outro)


_RE_BRL = re.compile(r"^R\$\s*(-?[\d.]+,\d{2})$")
_RE_PCT = re.compile(r"^([+-]?\d+(?:[.,]\d+)?)\s*%$")
# Duas grafias convivem: as tabelas usam DD/MM/AAAA e o Historico usa
# DD/MM/AA. Ambas precisam ordenar, e entre si tambem.
_RE_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{2}|\d{4})$")
_RE_INT = re.compile(r"^[+-]?\d+$")


def sort_key_from_text(texto: str):
    """Deriva chave de ordenacao do texto ja' formatado. None se nao der.

    Existe pras tabelas genericas (Historico, Scanner) que montam a linha
    a partir de strings prontas e nao tem mais o valor cru na mao. Passar
    a chave por ali exigiria refatorar todos os segmentos; derivar do
    texto cobre os tres formatos que os helpers do projeto produzem --
    `t.brl`, `_fmt_date` e f"{x:+.1f}%".

    Formato desconhecido devolve None e a celula volta a ordenar por
    texto, que e' o comportamento antigo. Nunca piora.
    """
    if not texto:
        return None
    s = texto.strip()
    m = _RE_BRL.match(s)
    if m:
        try:
            return float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            return None
    m = _RE_PCT.match(s)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    m = _RE_DATA.match(s)
    if m:
        d, mes, a = (int(g) for g in m.groups())
        if a < 100:                # DD/MM/AA -> seculo 21
            a += 2000
        return a * 10000 + mes * 100 + d      # AAAAMMDD, ordena igual data
    if _RE_INT.match(s):
        try:
            return int(s)
        except ValueError:
            return None
    return None


def auto_cell(texto: str):
    """Celula que se ordena sozinha quando o texto e' reconhecivel."""
    chave = sort_key_from_text(texto)
    return QTableWidgetItem(texto) if chave is None else SortableItem(
        texto, chave)


def num_cell(text: str, key, color: str | None = None):
    """Celula numerica: alinhada a' direita e ordenada por valor.

    `key` None vira -inf: linha sem valor vai pro fim na ordem
    decrescente, em vez de se misturar com os numeros.
    """
    from PyQt6.QtGui import QBrush
    item = SortableItem(text, float("-inf") if key is None else key)
    item.setTextAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if color:
        item.setForeground(QBrush(QColor(color)))
    return item


def score_table_item(current_score, score_ts):
    """Celula de tabela para o score persistido pelo "Validar score".

    Vive aqui porque duas telas mostram o mesmo numero -- Watchlist e
    Inventario. A regra de cor e os numeros empiricos do tooltip sao
    conhecimento medido (ver AGENTS.md #4b); duplicar seria deixar as duas
    telas divergirem na proxima recalibragem.

    Score desatualizado fica ambar independente do valor: um 90 de tres
    semanas atras nao e' uma oportunidade, e' um dado velho.
    """
    from PyQt6.QtGui import QBrush
    from PyQt6.QtWidgets import QTableWidgetItem

    from skinvault import signals
    from skinvault.ui import theme as t

    if current_score is None:
        item = SortableItem("—", float("-inf"))
        item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
        item.setToolTip("Clique em 'Validar score' para calcular.")
        return item

    item = SortableItem(str(int(current_score)), int(current_score))
    stale = signals.is_score_stale(score_ts)
    if stale:
        color = t.WARN
    elif current_score >= 70:
        color = t.POSITIVE
    elif current_score >= 45:
        color = t.WARN
    else:
        color = t.DANGER
    item.setForeground(QBrush(QColor(color)))
    age_txt = signals.score_age_text(score_ts)
    stale_tag = " [DESATUALIZADO]" if stale else ""
    item.setToolTip(
        f"Score {int(current_score)} — calculado {age_txt}."
        f"{stale_tag}\n"
        f"Empíricamente:\n"
        f"  70-84 containers → +33%, skins → +8% em 90d\n"
        f"  85+ containers → +52%, skins → +21% em 90d"
    )
    return item


def fade_in(widget: QWidget, duration_ms: int = 150) -> None:
    """Fade-in suave de um widget via QGraphicsOpacityEffect.

    O effect e removido ao final: render com effect tem custo (todo
    paint passa por buffer offscreen — pesa em telas com tabela grande).
    A remocao e deferida com singleShot(0) porque setGraphicsEffect(None)
    deleta o effect, e a anim e filha dele — deletar dentro da emissao
    de finished derrubaria o objeto no meio do proprio sinal.
    """
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", eff)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _cleanup() -> None:
        try:
            widget.setGraphicsEffect(None)
        except RuntimeError:
            pass  # objeto C++ deletado, ignorar

    anim.finished.connect(lambda: QTimer.singleShot(0, _cleanup))
    anim.start()


class EmptyState(QWidget):
    """Hero centralizado pra empty states. Icone + headline + sub + CTA opcional.

    Glifos canonicos (use SOMENTE estes dois):
    - "◇" (U+25C7) para "ainda sem dados" — esperando o usuario popular.
      Telas: Account, History, Trades, Watchlist, Market (sem busca).
    - "◎" (U+25CE) para "pronto pra agir" — empty state com CTA imediato.
      Telas: Scanner e similares.

    Uso:
        es = EmptyState("◇", "Nenhum item ainda",
                         subtitle="Adicione manualmente ou sincronize.",
                         cta_label="+ Adicionar", on_cta=callback)

        es = EmptyState("◎", "Pronto pra escanear",
                         steps=["1. Escolha uma categoria", "2. Clique em Escanear"])
    """

    cta_clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, subtitle: str = "",
                 cta_label: str | None = None,
                 on_cta=None,
                 steps: list[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        ic = QLabel(icon)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_ICON_HERO};"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(ic)

        ttl = QLabel(title)
        ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ttl.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(ttl)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setWordWrap(True)
            sub.setStyleSheet(t.label_body_muted())
            lay.addWidget(sub)

        if steps:
            steps_w = QWidget()
            steps_lay = QVBoxLayout(steps_w)
            steps_lay.setSpacing(8)
            steps_lay.setContentsMargins(0, 0, 0, 0)
            for i, step in enumerate(steps, 1):
                row = QHBoxLayout()
                row.setSpacing(10)
                num = QLabel(str(i))
                num.setFixedSize(20, 20)
                num.setAlignment(Qt.AlignmentFlag.AlignCenter)
                num.setStyleSheet(
                    f"background: {t.ACCENT_DIM}; color: {t.TEXT};"
                    f" font-size: {t.FS_MUTED}; font-weight: 600;"
                    f" border-radius: 10px; font-family: {t.FONT_FAMILY};"
                )
                row.addWidget(num)
                txt = QLabel(step)
                txt.setWordWrap(True)
                txt.setStyleSheet(t.label_body_muted())
                row.addWidget(txt, 1)
                steps_lay.addLayout(row)
            lay.addWidget(steps_w, 0, Qt.AlignmentFlag.AlignHCenter)

        if cta_label:
            cta = QPushButton(cta_label)
            cta.setCursor(Qt.CursorShape.PointingHandCursor)
            cta.setStyleSheet(t.btn_primary(padding="12px 28px", fs=t.FS_INPUT))
            cta.setToolTip(cta_label)
            cta.clicked.connect(self.cta_clicked.emit)
            if on_cta is not None:
                self.cta_clicked.connect(on_cta)
            lay.addWidget(cta, 0, Qt.AlignmentFlag.AlignCenter)


class _ElideLabel(QLabel):
    """QLabel que aplica elide (…) automaticamente quando o texto
    nao cabe na largura disponivel. Mantem altura fixa de uma linha."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = text
        self.setText(text)
        self.setWordWrap(False)

    def setText(self, text: str) -> None:
        self._full = text or ""
        self._apply_elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._apply_elide()

    def _apply_elide(self) -> None:
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(
            self._full, Qt.TextElideMode.ElideRight,
            max(self.width() - 2, 0),
        )
        # Usa o setText do super pra nao recursar
        QLabel.setText(self, elided)

from skinvault.ui import theme as t


# ── Card base ────────────────────────────────────────────────
# ── LineIcon (QPainter) ──────────────────────────────────────
class LineIcon(QWidget):
    """Icone de linha 18x18 desenhado com QPainter (estilo Fluent/Lucide).

    Stroke 1.5px, cap arredondado, sem preenchimento. `set_color()` permite
    acompanhar estado (ex.: ACCENT quando o item do sidebar esta ativo).
    Nome desconhecido cai no fallback (circulo).
    """

    SIZE = 18

    def __init__(self, name: str, color: str = t.TEXT_MUTED,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._color = color
        self.setFixedSize(self.SIZE, self.SIZE)

    def set_color(self, color: str) -> None:
        if color != self._color:
            self._color = color
            self.update()

    def set_icon_name(self, name: str) -> None:
        self.set_name(name)

    def set_name(self, name: str) -> None:
        if name != self._name:
            self._name = name
            self.update()

    def paintEvent(self, _evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(self._color))
        pen.setWidthF(1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        drawer = getattr(self, f"_draw_{self._name}", None)
        if drawer is None:
            self._draw_fallback(p)
        else:
            drawer(p)
        p.end()

    # cada _draw_* trabalha num viewBox 18x18 (area util ~2..16)
    def _draw_user(self, p: QPainter) -> None:
        p.drawEllipse(QRectF(6, 3, 6, 6))            # cabeca
        p.drawArc(QRectF(4, 10.5, 10, 9), 0, 180 * 16)  # ombros (meia elipse)

    def _draw_history(self, p: QPainter) -> None:
        p.drawEllipse(QRectF(3, 3, 12, 12))          # mostrador
        p.drawLine(9, 9, 9, 5)                        # ponteiro hora
        p.drawLine(9, 9, 12, 9)                       # ponteiro minuto

    def _draw_radar(self, p: QPainter) -> None:
        # dois arcos concentricos abrindo do canto inf-esq + dot na origem
        p.drawArc(QRectF(-6, 4, 22, 22), 0, 90 * 16)
        p.drawArc(QRectF(-1, 9, 12, 12), 0, 90 * 16)
        p.setBrush(QColor(self._color))
        p.drawEllipse(QRectF(3.2, 13.2, 1.6, 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_chart(self, p: QPainter) -> None:
        path = QPainterPath()
        for i, (x, y) in enumerate([(3, 13), (7, 8), (11, 11), (15, 4)]):
            path.lineTo(x, y) if i else path.moveTo(x, y)
        p.drawPath(path)

    def _draw_swap(self, p: QPainter) -> None:
        # seta -> em cima, seta <- embaixo
        p.drawLine(4, 6, 14, 6)
        p.drawLine(11, 3, 14, 6)
        p.drawLine(11, 9, 14, 6)
        p.drawLine(14, 12, 4, 12)
        p.drawLine(7, 9, 4, 12)
        p.drawLine(7, 15, 4, 12)

    def _draw_calc(self, p: QPainter) -> None:
        p.drawRoundedRect(QRectF(4, 3, 10, 12), 1.5, 1.5)
        p.drawLine(6, 6, 12, 6)                       # visor
        p.setBrush(QColor(self._color))
        for cx in (7, 11):
            for cy in (9.5, 12.5):
                p.drawEllipse(QRectF(cx - 0.7, cy - 0.7, 1.4, 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_eye(self, p: QPainter) -> None:
        path = QPainterPath()
        path.moveTo(3, 9)
        path.quadTo(9, 3.5, 15, 9)
        path.quadTo(9, 14.5, 3, 9)
        p.drawPath(path)
        p.drawEllipse(QRectF(6.8, 6.8, 4.4, 4.4))     # pupila

    def _draw_gear(self, p: QPainter) -> None:
        import math
        p.drawEllipse(QRectF(5.8, 5.8, 6.4, 6.4))
        for k in range(6):
            ang = math.radians(k * 60)
            dx, dy = math.cos(ang), math.sin(ang)
            # Coords float (QPointF) p/ manter os dentes simetricos — int()
            # truncava assimetrico (lados opostos em raios diferentes).
            p.drawLine(QPointF(9 + dx * 4.3, 9 + dy * 4.3),
                       QPointF(9 + dx * 6.3, 9 + dy * 6.3))

    def _draw_info(self, p: QPainter) -> None:
        p.drawEllipse(QRectF(3, 3, 12, 12))
        p.setBrush(QColor(self._color))
        p.drawEllipse(QRectF(8.2, 5.4, 1.6, 1.6))     # pingo do i
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(9, 8.5), QPointF(9, 12.5))  # corpo do i

    def _draw_archive(self, p: QPainter) -> None:
        p.drawRoundedRect(QRectF(3, 4, 12, 3), 1, 1)  # tampa
        p.drawRoundedRect(QRectF(4, 7, 10, 8), 1, 1)  # corpo
        p.drawLine(QPointF(7.5, 10.5), QPointF(10.5, 10.5))  # alca

    def _draw_sun(self, p: QPainter) -> None:
        # sol: circulo + 8 raios
        p.drawEllipse(QRectF(5.5, 5.5, 7, 7))
        for k in range(8):
            ang = k * 45  # degrees
            import math
            rad = math.radians(ang)
            dx, dy = math.cos(rad), math.sin(rad)
            p.drawLine(QPointF(9 + dx * 5.5, 9 + dy * 5.5),
                       QPointF(9 + dx * 7.5, 9 + dy * 7.5))

    def _draw_moon(self, p: QPainter) -> None:
        # lua crescente: circulo sobreposto por outro deslocado
        p.drawEllipse(QRectF(3.5, 3.5, 11, 11))
        # Sobrepoe um semi-circulo da cor do fundo pra criar a forma crescente.
        # Como nao temos fill, usamos path para desenhar o arco crescente.
        path = QPainterPath()
        path.moveTo(9, 3.5)
        path.quadTo(3, 9, 9, 14.5)
        path.quadTo(13, 9, 9, 3.5)
        p.drawPath(path)

    def _draw_wallet(self, p: QPainter) -> None:
        # carteira: retangulo + aba
        p.drawRoundedRect(QRectF(3, 5, 12, 9), 1.5, 1.5)
        p.drawRoundedRect(QRectF(3, 5, 6, 9), 1.5, 1.5)  # aba frontal

    def _draw_coins(self, p: QPainter) -> None:
        # 2 elipses empilhadas (moedas)
        p.drawEllipse(QRectF(4, 3, 10, 6))
        p.drawEllipse(QRectF(4, 9, 10, 6))

    def _draw_trophy(self, p: QPainter) -> None:
        # taca: corpo + base + 2 alcas
        p.drawRoundedRect(QRectF(6, 4, 6, 7), 1, 1)  # corpo
        p.drawLine(QPointF(5, 11), QPointF(13, 11))  # borda base
        p.drawLine(QPointF(7, 12), QPointF(11, 12))  # base
        p.drawArc(QRectF(2, 4, 6, 6), 0, 90 * 16)    # alca esq
        p.drawArc(QRectF(10, 4, 6, 6), 90 * 16, 90 * 16)  # alca dir

    def _draw_percent(self, p: QPainter) -> None:
        # % com 2 circulos + barra
        p.drawEllipse(QRectF(3, 3, 4.5, 4.5))     # circulo sup
        p.drawEllipse(QRectF(10.5, 10.5, 4.5, 4.5))  # circulo inf
        p.drawLine(QPointF(13, 4), QPointF(5, 14))  # barra

    def _draw_menu(self, p: QPainter) -> None:
        # tres linhas: alterna entre a barra estreita e a com rotulos
        p.drawLine(QPointF(3, 5), QPointF(15, 5))
        p.drawLine(QPointF(3, 9), QPointF(15, 9))
        p.drawLine(QPointF(3, 13), QPointF(15, 13))

    def _draw_calendar(self, p: QPainter) -> None:
        # calendario: retangulo + 2 ticks no topo + linha
        p.drawRoundedRect(QRectF(3, 5, 12, 10), 1.5, 1.5)
        p.drawLine(QPointF(5, 3), QPointF(5, 6))
        p.drawLine(QPointF(13, 3), QPointF(13, 6))
        p.drawLine(QPointF(3, 9), QPointF(15, 9))

    def _draw_steam(self, p: QPainter) -> None:
        # logo Steam simplificado: corpo grande (inf-esq) com nucleo
        # preenchido + pino menor (sup-dir) ligados por um "cano".
        p.drawEllipse(QRectF(2.5, 7, 8, 8))            # corpo grande
        p.setBrush(QColor(self._color))
        p.drawEllipse(QRectF(5.2, 9.7, 2.6, 2.6))      # nucleo preenchido
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(10.5, 2.5, 5, 5))         # pino sup-dir
        p.drawLine(QPointF(6.6, 11), QPointF(13, 5))   # cano ligando os dois

    def _draw_broom(self, p: QPainter) -> None:
        # vassoura: cabo diagonal + cabeca trapezoidal + 2 cerdas
        p.drawLine(QPointF(14.5, 3), QPointF(8.5, 9))
        path = QPainterPath()
        path.moveTo(9.5, 7.5)
        path.lineTo(12.5, 10.5)
        path.lineTo(9, 15)
        path.lineTo(3.5, 12)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(6, 10.5), QPointF(4.6, 13.6))   # cerda esq
        p.drawLine(QPointF(8.6, 11.4), QPointF(7.4, 14.6))  # cerda dir

    def _draw_trash(self, p: QPainter) -> None:
        # lixeira: alca + tampa + corpo afunilado + 2 ranhuras
        p.drawLine(QPointF(7, 4), QPointF(11, 4))          # alca
        p.drawLine(QPointF(3.5, 6), QPointF(14.5, 6))      # tampa
        path = QPainterPath()
        path.moveTo(5, 6)
        path.lineTo(5.9, 15)
        path.lineTo(12.1, 15)
        path.lineTo(13, 6)
        p.drawPath(path)
        p.drawLine(QPointF(7.8, 8.5), QPointF(8, 12.5))
        p.drawLine(QPointF(10.2, 8.5), QPointF(10, 12.5))

    def _draw_fallback(self, p: QPainter) -> None:
        p.drawEllipse(QRectF(3, 3, 12, 12))


def line_icon_pixmap(name: str, color: str = t.TEXT, size: int = 18) -> QPixmap:
    """Renderiza um glifo do LineIcon para QPixmap (ex.: icone em QPushButton).

    Reusa o mesmo desenho QPainter do LineIcon (stroke 1.5px, cap
    arredondado) num pixmap transparente, escalando do viewBox 18x18 pro
    `size` pedido. Util onde se precisa de QIcon e nao de um QWidget.
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    src = LineIcon(name, color)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if size != LineIcon.SIZE:
        s = size / LineIcon.SIZE
        p.scale(s, s)
    drawer = getattr(src, f"_draw_{name}", src._draw_fallback)
    drawer(p)
    p.end()
    src.deleteLater()
    return pm



# ── Breadcrumb ───────────────────────────────────────────────
class Breadcrumb(QWidget):
    """Barra de breadcrumb 40px no topo do conteudo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Breadcrumb")
        self.setFixedHeight(40)
        self.set_surface(t.BG)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        self._label = QLabel("")
        self._label.setStyleSheet(t.label_body_muted())
        lay.addWidget(self._label, 1)

        self._right = QLabel("")
        self._right.setStyleSheet(t.label_caption())
        lay.addWidget(self._right)

        # Container para acoes trailing (toggle tema, perfil)
        self._actions_widget = QWidget()
        self._actions_lay = QHBoxLayout(self._actions_widget)
        self._actions_lay.setContentsMargins(0, 0, 0, 0)
        self._actions_lay.setSpacing(4)
        self._actions_widget.setVisible(False)
        lay.addWidget(self._actions_widget)

    def set_surface(self, color: str) -> None:
        """Troca a cor de fundo da barra (ex.: superficie unica no login).

        Seletor com objectName e' obrigatorio — sem ele o `background` e a
        `border-bottom` propagam pros filhos (label, acoes), desenhando
        linhas/tarjas espurias (vide pitfall Frente M).
        """
        self.setStyleSheet(
            f"QWidget#Breadcrumb {{ background: {color};"
            f" border-bottom: 1px solid {t.BORDER}; }}"
        )

    def set_path(self, *parts: str) -> None:
        body = "  ›  ".join(p for p in parts if p)
        self._label.setText(body)

    def set_right(self, text: str) -> None:
        self._right.setText(text)

    def set_actions(self, widgets: list[QWidget]) -> None:
        """Adiciona botoes trailing a direita do breadcrumb."""
        while self._actions_lay.count():
            w = self._actions_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        for w in widgets:
            self._actions_lay.addWidget(w)
        self._actions_widget.setVisible(len(widgets) > 0)


# ── Footer ───────────────────────────────────────────────────
class Footer(QWidget):
    """Barra de status no rodape."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet(
            f"background: {t.BG_ELEVATED}; border-top: 1px solid {t.BORDER};"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 20, 0)
        self._left = QLabel("")
        self._right = QLabel("")
        for lbl in (self._left, self._right):
            lbl.setStyleSheet(t.label_caption())
        lay.addWidget(self._left, 1)
        lay.addWidget(self._right)

    def set_left(self, text: str) -> None:
        self._left.setText(text)

    def set_right(self, text: str) -> None:
        self._right.setText(text)


# ── SegmentedControl ─────────────────────────────────────────
class SegmentedControl(QWidget):
    """Tabs estilo pill (Win11 segmented). Emite segment_changed(key)."""

    segment_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: dict[str, QPushButton] = {}
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(4)

    def add(self, key: str, label: str) -> None:
        btn = QPushButton(label)
        btn.setToolTip(label)
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(self._btn_style())
        btn.setMinimumHeight(34)
        btn.clicked.connect(lambda: self.segment_changed.emit(key))
        self._items[key] = btn
        self._lay.addWidget(btn)
        if len(self._items) == 1:
            btn.setChecked(True)

    def select(self, key: str) -> None:
        btn = self._items.get(key)
        if btn is None:
            return
        if not btn.isChecked():
            btn.setChecked(True)
            self.segment_changed.emit(key)

    def _btn_style(self) -> str:
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid {t.BORDER}; border-radius: 8px;"
            f" padding: 6px 18px; font-size: {t.FS_BODY}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; }}"
            f"QPushButton:checked {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border: 1px solid {t.ACCENT}; }}"
            f"QPushButton:focus {{ color: {t.TEXT};"
            f" border: 1px solid {t.TEXT_MUTED}; }}"
            f"QPushButton:checked:focus {{ border: 1px solid {t.FOCUS_GREEN}; }}"
        )


# ── Avatar widget ────────────────────────────────────────────
class Avatar(QLabel):
    """QLabel circular pra avatar Steam. Aceita bytes ou path."""

    def __init__(self, size: int = 72, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self.setStyleSheet(
            f"background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: {size // 2}px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Placeholder
        self.setText("?")
        self.setStyleSheet(self.styleSheet() +
                           f"color: {t.TEXT_MUTED}; font-size: {t.FS_ICON_SM};"
                           f" font-family: {t.FONT_FAMILY};")

    def set_image(self, data: bytes | str | None) -> None:
        if not data:
            return
        pix = QPixmap()
        if isinstance(data, bytes):
            pix.loadFromData(data)
        else:
            pix.load(str(data))
        if pix.isNull():
            return
        scaled = pix.scaled(
            self._size, self._size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Mask circular: usar setStyleSheet com border-radius e setPixmap
        self.setText("")
        self.setPixmap(scaled)
        self.setStyleSheet(
            f"background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: {self._size // 2}px;"
        )


# ── Lock overlay ─────────────────────────────────────────────
class LockOverlay(QWidget):
    """Overlay semi-transparente com mensagem de paywall (Tela 3)."""

    cta_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("LockOverlay")
        self.setStyleSheet(f"QWidget#LockOverlay {{ background: rgba(14,14,18,0.88); }}")
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)

        icon = QLabel("🔒")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {t.STEAM_BLUE}; font-size: {t.FS_ICON_LG};"
        )
        lay.addWidget(icon)

        title = QLabel("Scanner Premium — em breve")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(title)

        desc = QLabel(
            "Scanner de skins, caixas e adesivos para identificar\n"
            "oportunidades de compra antes da valorização."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet(t.label_body_muted())
        lay.addWidget(desc)

        cta = QPushButton("Quero ser avisado quando lançar")
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setStyleSheet(t.btn_steam(padding="12px 28px", fs=t.FS_INPUT))
        cta.setToolTip("Registra interesse — avisamos quando o recurso for liberado.")
        cta.clicked.connect(self.cta_clicked.emit)
        lay.addWidget(cta, 0, Qt.AlignmentFlag.AlignCenter)


# ── ActivityFeed ─────────────────────────────────────────────
def _activity_color(name: str) -> str:
    """Mapeia COLOR_* da activity.py para constante do theme."""
    return {
        "green": t.POSITIVE,
        "red": t.DANGER,
        "accent": t.STEAM_BLUE,
        "muted": t.TEXT_MUTED,
    }.get(name, t.TEXT_MUTED)


class _ActivityRow(QWidget):
    """Uma linha do feed: bolinha colorida + (titulo/subtitulo) + tempo."""

    def __init__(self, event: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from skinvault import activity as _act

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        color = _activity_color(event.get("color", "muted"))

        icon = QLabel(event.get("icon", "·"))
        icon.setFixedSize(28, 28)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"color: {color}; background: {t.SURFACE};"
            f" border-radius: 14px; font-size: 12pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(1)
        title = _ElideLabel(event.get("title", ""))
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_BODY};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        title.setToolTip(event.get("title", ""))
        center.addWidget(title)

        sub_color = color if event.get("color") in ("green", "red") else t.TEXT_MUTED
        sub = _ElideLabel(event.get("subtitle", ""))
        sub.setStyleSheet(
            f"color: {sub_color}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        center.addWidget(sub)
        lay.addLayout(center, 1)
        # Altura fixa garante linhas uniformes mesmo com titulos longos
        self.setFixedHeight(44)

        ts_label = QLabel(_act.format_relative_ts(event.get("ts", 0)))
        ts_label.setStyleSheet(t.label_caption())
        lay.addWidget(ts_label, 0, Qt.AlignmentFlag.AlignTop)


class ActivityFeed(Card):
    """Lista vertical estilo "Recent Activity" do Faceit. Agrega trades,
    alertas e snapshots de ranking. Use set_events() pra preencher.

    Tem chips no topo pra filtrar por categoria: tudo/vendas/compras/alertas.
    """

    # Filtros por icone do evento
    _FILTERS = [
        ("all", "Tudo", None),
        ("sell", "↑ Vendas", "↑"),
        ("buy", "↓ Compras", "↓"),
        ("alert", "★ Alertas", "★"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=t.CARD_PAD_MD)
        self.setMinimumWidth(280)
        self.setMaximumWidth(380)

        self._all_events: list[dict] = []
        self._filter: str = "all"
        self._chip_buttons: dict[str, QPushButton] = {}

        title = QLabel("Atividade recente")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        title.setWordWrap(False)
        self.layout().addWidget(title)

        self._chips_w = QWidget()
        chips_row = QHBoxLayout(self._chips_w)
        chips_row.setContentsMargins(0, 2, 0, 4)
        chips_row.setSpacing(4)
        for key, label, _icon in self._FILTERS:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setStyleSheet(self._chip_style())
            btn.setToolTip(f"Filtra a atividade por: {label}.")
            btn.clicked.connect(lambda _checked, k=key: self._set_filter(k))
            if key == "all":
                btn.setChecked(True)
            self._chip_buttons[key] = btn
            chips_row.addWidget(btn)
        chips_row.addStretch(1)
        self.layout().addWidget(self._chips_w)

        self._list_lay = QVBoxLayout()
        self._list_lay.setContentsMargins(0, 4, 0, 0)
        self._list_lay.setSpacing(10)
        self.layout().addLayout(self._list_lay)
        self.layout().addStretch(1)

        self._empty = QLabel("Nenhuma atividade ainda.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._empty.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; padding: 16px 0;"
        )
        self._list_lay.addWidget(self._empty)

        # Comeca compacto (sem eventos); set_events ajusta dinamicamente.
        self._apply_empty_layout(True)

    def _apply_empty_layout(self, is_empty: bool) -> None:
        """Compacta o painel quando vazio: esconde chips e encolhe a largura
        minima de 280 pra 200, evitando que vire orfao na coluna lateral."""
        self._chips_w.setVisible(not is_empty)
        self.setMinimumWidth(200 if is_empty else 280)

    def _chip_style(self) -> str:
        return (
            f"QPushButton {{ color: {t.TEXT_MUTED}; background: transparent;"
            f" border: 1px solid {t.BORDER}; border-radius: 10px;"
            f" padding: 3px 9px; font-size: {t.FS_MUTED}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; }}"
            f"QPushButton:checked {{ color: {t.TEXT}; background: {t.SURFACE};"
            f" border: 1px solid {t.ACCENT}; }}"
            f"QPushButton:focus {{ color: {t.TEXT};"
            f" border: 1px solid {t.TEXT_MUTED}; }}"
            f"QPushButton:checked:focus {{ border: 1px solid {t.FOCUS_GREEN}; }}"
        )

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._render()

    def _filtered_events(self) -> list[dict]:
        if self._filter == "all":
            return self._all_events
        wanted_icon = dict((k, ic) for k, _, ic in self._FILTERS)[self._filter]
        return [e for e in self._all_events if e.get("icon") == wanted_icon]

    def _render(self) -> None:
        # Limpa lista atual
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        events = self._filtered_events()
        if not events:
            if self._filter != "all":
                self._empty.setText("Sem eventos nesse filtro.")
            else:
                self._empty.setText("Nenhuma atividade ainda.")
            self._empty.show()
            self._list_lay.addWidget(self._empty)
            return
        self._empty.hide()
        for ev in events:
            self._list_lay.addWidget(_ActivityRow(ev))

    def set_events(self, events: list[dict]) -> None:
        self._all_events = list(events)
        self._render()
        self._apply_empty_layout(not self._all_events)


# ── RecentMatchesStrip ────────────────────────────────────────
def _streak_summary(trades: list[dict]) -> tuple[str, str] | None:
    """Calcula a sequencia atual de vitorias/derrotas a partir do
    trade mais recente. Trades com pnl == 0 quebram a sequencia.

    Retorna (texto, cor) ou None se nao houver sequencia.
    """
    if not trades:
        return None
    # Trades chegam mais recentes primeiro
    first_pnl = trades[0].get("pnl", 0) or 0
    if first_pnl == 0:
        return None
    is_win = first_pnl > 0
    count = 0
    for t_ in trades:
        p = t_.get("pnl", 0) or 0
        if (p > 0) == is_win and p != 0:
            count += 1
        else:
            break
    if count < 2:
        return None
    plural = "s" if count != 1 else ""
    termo = f"vitória{plural}" if is_win else f"derrota{plural}"
    label = f"{count} {termo} em sequência"
    return (label, t.POSITIVE if is_win else t.DANGER)


class _MatchChip(QLabel):
    """Chip pequeno W/L pra strip de Recent Matches."""

    def __init__(self, trade: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        pnl = trade.get("pnl", 0) or 0
        if pnl > 0:
            text, color = "V", t.POSITIVE
        elif pnl < 0:
            text, color = "D", t.DANGER
        else:
            text, color = "—", t.TEXT_MUTED
        self.setText(text)
        self.setFixedSize(28, 28)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {color}; background: {t.SURFACE};"
            f" border: 1px solid {color}; border-radius: 6px;"
            f" font-size: {t.FS_BODY}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        from skinvault.localization import localize_name as _ln
        name = _ln(trade.get("name") or "")
        ts = trade.get("sell_ts") or trade.get("buy_ts") or 0
        import time as _time
        ts_str = _time.strftime("%d/%m/%Y", _time.localtime(ts)) if ts else ""
        self.setToolTip(
            f"{ts_str} • {name}\nP&L R$ {pnl:+.2f}"
        )


class RecentMatchesStrip(Card):
    """Strip horizontal estilo "Recent Matches" do Faceit: chips W/L
    coloridos pros ultimos trades + streak indicator a direita."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=t.CARD_PAD_SM)

        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        title = QLabel("Últimos resultados")
        title.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
            f" letter-spacing: 1px;"
        )
        outer.addWidget(title)

        self._chip_lay = QHBoxLayout()
        self._chip_lay.setContentsMargins(0, 0, 0, 0)
        self._chip_lay.setSpacing(4)
        outer.addLayout(self._chip_lay)

        outer.addStretch(1)

        self._streak = QLabel("")
        self._streak.setStyleSheet(t.label_caption_bold())
        outer.addWidget(self._streak)

        self._empty = QLabel("Nenhum trade fechado ainda.")
        self._empty.setStyleSheet(t.label_caption())
        self._chip_lay.addWidget(self._empty)

        self.layout().addLayout(outer)

    def set_trades(self, trades: list[dict], limit: int = 15) -> None:
        """trades: lista ordenada do mais recente pro mais antigo."""
        # Limpa
        while self._chip_lay.count():
            item = self._chip_lay.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._empty:
                w.deleteLater()
        recent = trades[:limit]
        if not recent:
            self._empty.show()
            self._chip_lay.addWidget(self._empty)
            self._streak.setText("")
            return
        self._empty.hide()
        for tr in recent:
            self._chip_lay.addWidget(_MatchChip(tr))
        streak = _streak_summary(recent)
        if streak:
            text, color = streak
            self._streak.setText(text)
            self._streak.setStyleSheet(
                f"color: {color}; font-size: {t.FS_MUTED};"
                f" font-weight: 700; font-family: {t.FONT_FAMILY};"
            )
        else:
            self._streak.setText("")


# ── Toast ────────────────────────────────────────────────────
class Toast(QWidget):
    """Notificacao nao-bloqueante, top-right do parent, auto-dismiss.

    Variants: 'info' (accent), 'success' (accent), 'warning' (warn),
    'error' (danger). Auto-stack quando ha multiplos visiveis.
    Uso: Toast.show_toast(parent, "Sincronizado.", "success").
    """

    _VARIANT_BORDER = {
        "info":    "ACCENT",
        "success": "POSITIVE",
        "warning": "WARN",
        "error":   "DANGER",
    }
    _stack: list["Toast"] = []

    def __init__(self, parent: QWidget, text: str,
                 variant: str = "info",
                 duration_ms: int = 3000) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setObjectName("Toast")
        border_attr = self._VARIANT_BORDER.get(variant, "ACCENT")
        border_color = getattr(t, border_attr, t.ACCENT)
        self.setStyleSheet(
            f"QWidget#Toast {{ background: {t.SURFACE};"
            f" border: 1px solid {border_color};"
            f" border-left: 4px solid {border_color};"
            f" border-radius: {t.RADIUS_MD}px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(t.SPACE_LG, t.SPACE_MD, t.SPACE_LG, t.SPACE_MD)
        lay.setSpacing(t.SPACE_MD)
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        self.adjustSize()
        # Min/max width pra nao ficar gigante
        self.setMinimumWidth(240)
        self.setMaximumWidth(420)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._duration_ms = duration_ms
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(200)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_out.finished.connect(self._on_faded_out)

    @classmethod
    def show_toast(cls, parent: QWidget, text: str,
                   variant: str = "info",
                   duration_ms: int = 3000) -> "Toast":
        """Cria, posiciona e exibe. Auto-stack se ja houver toasts."""
        target = parent.window() if parent is not None else None
        if target is None:
            target = parent
        toast = cls(target, text, variant, duration_ms)
        cls._stack.append(toast)
        toast._reposition()
        toast.show()
        # Slide-in sutil (8px de cima) em paralelo com o fade
        end = toast.pos()
        toast.move(end.x(), end.y() - 8)
        toast._slide = QPropertyAnimation(toast, b"pos", toast)
        toast._slide.setDuration(200)
        toast._slide.setStartValue(toast.pos())
        toast._slide.setEndValue(end)
        toast._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        toast._slide.start()
        toast._fade_in.start()
        QTimer.singleShot(duration_ms, toast._begin_dismiss)
        return toast

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = t.SPACE_LG
        # Empilha verticalmente: cada toast 6px abaixo do anterior visivel
        y = margin
        for tst in self._stack:
            if tst is self:
                break
            try:
                if tst.isVisible():
                    y = tst.y() + tst.height() + t.SPACE_SM
            except RuntimeError:
                pass  # objeto C++ deletado, ignorar
        x = max(margin, parent.width() - self.width() - margin)
        self.move(x, y)

    def _begin_dismiss(self) -> None:
        if not self.isVisible():
            return
        self._fade_out.start()

    def _on_faded_out(self) -> None:
        try:
            self._stack.remove(self)
        except ValueError:
            pass
        self.hide()
        self.deleteLater()
        # Reposiciona toasts remanescentes
        for tst in list(self._stack):
            try:
                if tst.isVisible():
                    tst._reposition()
            except RuntimeError:
                pass  # objeto C++ deletado, ignorar


# ── LoadingState ─────────────────────────────────────────────
class LoadingState(QWidget):
    """Spinner simples + label. Use como placeholder durante async."""

    _FRAMES = ["◴", "◷", "◶", "◵"]

    def __init__(self, label: str = "Carregando…",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(t.SPACE_SM)

        self._spin = QLabel(self._FRAMES[0])
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setStyleSheet(
            f"color: {t.ACCENT}; font-size: 28pt;"
            f" font-family: {t.FONT_FAMILY};"
        )
        lay.addWidget(self._spin)

        self._lbl = QLabel(label)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet(t.label_caption())
        lay.addWidget(self._lbl)

        self._idx = 0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self._spin.setText(self._FRAMES[self._idx])

    def set_label(self, text: str) -> None:
        self._lbl.setText(text)

    def hideEvent(self, ev) -> None:
        self._timer.stop()
        super().hideEvent(ev)

    def showEvent(self, ev) -> None:
        if not self._timer.isActive():
            self._timer.start()
        # Spinner surge com fade (crossfade barato, sem tocar as telas).
        # Guard: so anima dentro de janela visivel — mantem _screenshot.py
        # e tests (que nunca dao show() na janela) deterministicos.
        if self.window() is not self and self.window().isVisible():
            fade_in(self, duration_ms=150)
        super().showEvent(ev)


# ── PageHeader ───────────────────────────────────────────────
class PageHeader(QWidget):
    """Cabecalho de pagina: titulo 24pt + subtitulo + acoes a direita.

    Altura total ~64px. Versao bold (botcloud), reverte compactacao
    da Frente N.
    """

    def __init__(self, title: str, subtitle: str = "",
                 actions: list[QWidget] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_SM)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE};"
            f" font-weight: 700; font-family: {t.FONT_FAMILY};"
        )
        text_col.addWidget(self._title_lbl)

        self._sub_lbl = QLabel(subtitle)
        self._sub_lbl.setStyleSheet(t.label_caption())
        self._sub_lbl.setVisible(bool(subtitle))
        text_col.addWidget(self._sub_lbl)

        lay.addLayout(text_col, 1)

        if actions:
            acts = QHBoxLayout()
            acts.setContentsMargins(0, 0, 0, 0)
            acts.setSpacing(t.SPACE_SM)
            for w in actions:
                acts.addWidget(w)
            lay.addLayout(acts)

    def set_title(self, text: str) -> None:
        self._title_lbl.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._sub_lbl.setText(text)
        self._sub_lbl.setVisible(bool(text))


# ── SectionHeader ────────────────────────────────────────────
class SectionHeader(QWidget):
    """Cabecalho de secao: titulo + subtitulo opcional + acao trailing."""

    def __init__(self, title: str, subtitle: str = "",
                 action: QPushButton | None = None,
                 title_fs: str = t.FS_TITLE_SM,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(t.SPACE_MD)

        stack = QVBoxLayout()
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(t.SPACE_XS // 2)

        self._title = QLabel(title)
        self._title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {title_fs};"
            f" font-weight: 600; font-family: {t.FONT_FAMILY};"
        )
        stack.addWidget(self._title)

        self._sub = QLabel(subtitle)
        self._sub.setStyleSheet(t.label_caption())
        self._sub.setVisible(bool(subtitle))
        stack.addWidget(self._sub)

        outer.addLayout(stack, 1)

        self._action: QPushButton | None = None
        if action is not None:
            self.set_action(action)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._sub.setText(text)
        self._sub.setVisible(bool(text))

    def set_action(self, btn: QPushButton) -> None:
        if self._action is not None:
            self._action.setParent(None)
        self._action = btn
        self.layout().addWidget(btn, 0, Qt.AlignmentFlag.AlignRight)


# ── Toolbar ──────────────────────────────────────────────────
class Toolbar(QWidget):
    """Barra horizontal: widgets a esquerda, spacer, widgets a direita."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(t.SPACE_SM)
        self._spacer_idx = 0
        self._lay.addStretch(1)
        self._spacer_idx = 0  # tudo antes do stretch = "left"

    def add_left(self, w: QWidget) -> None:
        # Insere antes do stretch
        self._lay.insertWidget(self._spacer_idx, w)
        self._spacer_idx += 1

    def add_right(self, w: QWidget) -> None:
        self._lay.addWidget(w)

    def add_left_layout(self, layout: QLayout) -> None:
        self._lay.insertLayout(self._spacer_idx, layout)
        self._spacer_idx += 1


# ── FormRow ──────────────────────────────────────────────────
class FormRow(QWidget):
    """Label muted em cima, field embaixo. Espacamento consistente.

    Se tooltip for fornecido, aplica em label + field (acessibilidade).
    """

    def __init__(self, label: str, field: QWidget,
                 tooltip: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(t.SPACE_XS)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(t.label_caption_bold())
        if tooltip:
            self._lbl.setToolTip(tooltip)
            field.setToolTip(tooltip)
        lay.addWidget(self._lbl)
        lay.addWidget(field)
        self._field = field

    def field(self) -> QWidget:
        return self._field

    def set_label(self, text: str) -> None:
        self._lbl.setText(text)


# ── ToggleSwitch ─────────────────────────────────────────────
class ToggleSwitch(QWidget):
    """Switch pílula desenhado com QPainter (estilo botcloud).
    API compatível com QCheckBox: isChecked/setChecked/toggled.

    Tamanho fixo 36×20. Track ON = ACCENT, OFF = SURFACE; thumb = TEXT.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(36, 20)
        self._checked = checked
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, v: bool) -> None:
        if v != self._checked:
            self._checked = v
            self.toggled.emit(v)
            self.update()

    def mousePressEvent(self, evt) -> None:  # noqa: N802
        super().mousePressEvent(evt)
        self.setChecked(not self._checked)

    def paintEvent(self, evt) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = QRectF(1, 3, 34, 14)
        r = 7
        p.setBrush(QColor(t.ACCENT if self._checked else t.SURFACE))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(track, r, r)

        thumb_x = 19 if self._checked else 3
        p.setBrush(QColor(t.TEXT))
        p.drawEllipse(QRectF(thumb_x, 1, 14, 18))





