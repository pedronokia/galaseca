"""Card de metas financeiras + dialog de edição.

A barra de progresso usa a ACCENT de marca (`t.ACCENT`, que muda com a
configuração de aparencia) — chunk verde por padrão. O card mostra o
progresso factual de cada meta; "Editar metas" abre o dialog que cria,
ajusta o alvo ou remove.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault import goals
from skinvault.ui import theme as t
from skinvault.ui.toast import ToastManager


class GoalsCard(QFrame):
    """Card reativo: `refresh_from(totals)` recalcula as barras."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._totals: dict = {}
        self.setStyleSheet(t.card_style(t.RADIUS_LG))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*t.CARD_PAD_MD)
        lay.setSpacing(t.SPACE_SM)

        cab = QHBoxLayout()
        cab.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Metas financeiras")
        title.setStyleSheet(t.label_section())
        cab.addWidget(title)
        cab.addStretch(1)
        self._edit_btn = QPushButton("Editar metas")
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(t.btn_ghost(padding="4px 12px",
                                                 fs=t.FS_MUTED))
        self._edit_btn.setToolTip(
            "Cria, edita ou remove metas (valor, lucro ou nº de itens).\n"
            "Mostra só quanto já foi atingido, nunca previsão."
        )
        self._edit_btn.clicked.connect(self._on_edit)
        cab.addWidget(self._edit_btn)
        lay.addLayout(cab)

        self._sub = QLabel(
            "Progresso em direção aos seus objetivos — atualiza a cada "
            "avaliação.")
        self._sub.setStyleSheet(t.label_caption())
        self._sub.setWordWrap(True)
        lay.addWidget(self._sub)

        self._goals_lay = QVBoxLayout()
        self._goals_lay.setSpacing(t.SPACE_MD)
        lay.addLayout(self._goals_lay)

        self._empty = QLabel(
            "Nenhuma meta definida ainda. Crie a primeira para acompanhar "
            "o progresso da carteira.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(t.label_caption())
        lay.addWidget(self._empty)

        # Empty state interativo: o CTA leva direto pro dialog de edição,
        # em vez de exigir que o usuário ache o "Editar metas" no header.
        self._empty_cta = QPushButton("Criar primeira meta")
        self._empty_cta.setCursor(Qt.CursorShape.PointingHandCursor)
        self._empty_cta.setStyleSheet(
            t.btn_primary(padding="6px 16px", fs=t.FS_MUTED))
        self._empty_cta.setToolTip(
            "Abre o editor de metas para criar o seu primeiro objetivo "
            "(valor líquido, de mercado, lucro ou total de itens).")
        self._empty_cta.clicked.connect(self._on_edit)
        lay.addWidget(self._empty_cta)

        self.refresh_from({})

    # ── conteúdo ──────────────────────────────────────────
    def refresh_from(self, totals: dict) -> None:
        self._totals = totals
        self._rows_clear()
        meta_rows = goals.goal_rows(totals)
        vazio = not meta_rows
        self._empty.setVisible(vazio)
        self._empty_cta.setVisible(vazio)
        for meta in meta_rows:
            self._goals_lay.addWidget(self._goal_widget(meta))

    def _goal_widget(self, meta: dict) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        nome = QLabel(meta["label"])
        nome.setStyleSheet(t.label_caption_bold())
        nome.setToolTip(
            f"Alvo: {goals.metric_label(meta['metric'])}.")
        linha.addWidget(nome)
        linha.addStretch(1)
        if meta["done"]:
            status = QLabel("atingida")
            status.setStyleSheet(
                f"color: {t.POSITIVE}; font-size: {t.FS_MUTED};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};")
        else:
            status = QLabel(f"{meta['pct']:.0f}%")
            status.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
                f" font-weight: 600; font-family: {t.FONT_FAMILY};")
        linha.addWidget(status)
        col.addLayout(linha)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(meta["pct"]))
        bar.setFixedHeight(8)
        bar.setTextVisible(False)
        bar.setStyleSheet(self._bar_style())
        bar.setToolTip(
            f"{t.brl(meta['current'])} de {t.brl(meta['target'])} "
            f"({meta['pct']:.1f}%).")
        col.addWidget(bar)

        rot = QLabel(self._caption(meta))
        rot.setStyleSheet(t.label_caption())
        col.addWidget(rot)
        return wrap

    def _caption(self, meta: dict) -> str:
        metric = goals.metric_label(meta["metric"])
        if meta["metric"] == "items":
            atual = f"{meta['current']:.0f}"
            alvo = f"{meta['target']:.0f}"
        else:
            atual, alvo = t.brl(meta["current"]), t.brl(meta["target"])
        return f"{metric}: {atual} de {alvo}"

    def _rows_clear(self) -> None:
        while self._goals_lay.count():
            item = self._goals_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _bar_style(self) -> str:
        return (
            f"QProgressBar {{ background: {t.SURFACE}; border: none;"
            f" border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {t.ACCENT};"
            f" border-radius: 4px; }}"
        )

    def restyle(self) -> None:
        """Reaplica ACCENT (chamado quando a cor de destaque muda)."""
        self.setStyleSheet(t.card_style(t.RADIUS_LG))
        for i in range(self._goals_lay.count()):
            w = self._goals_lay.itemAt(i).widget()
            if w is not None:
                bar = w.findChild(QProgressBar)
                if bar is not None:
                    bar.setStyleSheet(self._bar_style())

    def _on_edit(self) -> None:
        dlg = GoalsEditDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.refresh_from(self._totals)
        ToastManager.instance().show_success(
            self.window(), "Metas atualizadas!")


class GoalsEditDialog(QDialog):
    """Lista editável de metas (rótulo / métrica / alvo / remover)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar metas")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._rows: list[tuple] = []
        self._build()
        for goal in goals.load_goals():
            self._add_goal_row(goal["label"], goal["metric"], goal["target"])

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 18, 20, 18)

        cab = QVBoxLayout()
        cab.setSpacing(2)
        title = QLabel("Metas financeiras")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;"
            f" font-family: {t.FONT_FAMILY};")
        cab.addWidget(title)
        sub = QLabel(
            "Cada meta mede uma métrica da carteira até o alvo. O progresso"
            " é factual — o app nunca prevê se você vai atingir.")
        sub.setWordWrap(True)
        sub.setStyleSheet(t.label_caption())
        cab.addWidget(sub)
        lay.addLayout(cab)

        self._lista = QVBoxLayout()
        self._lista.setSpacing(t.SPACE_SM)
        lay.addLayout(self._lista)

        self._add_btn = QPushButton("Adicionar meta")
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.setStyleSheet(t.btn_ghost())
        self._add_btn.clicked.connect(
            lambda: self._add_goal_row("", goals._DEFAULT_METRIC, ""))
        lay.addWidget(self._add_btn)

        self._erro = QLabel("")
        self._erro.setStyleSheet(t.label_caption())
        self._erro.setVisible(False)
        lay.addWidget(self._erro)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(t.btn_ghost())
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("Salvar")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setStyleSheet(t.btn_primary())
        ok.clicked.connect(self._on_save)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

    def _add_goal_row(self, label: str, metric: str, target) -> None:
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(t.SPACE_SM)

        nome = QLineEdit(str(label))
        nome.setPlaceholderText("Ex.: Saldo suficiente pra férias")
        nome.setStyleSheet(t.input_style())
        rl.addWidget(nome, 2)

        combo = QComboBox()
        for key, lbl in goals.GOAL_METRICS.items():
            combo.addItem(lbl, key)
        idx = combo.findData(metric)
        combo.setCurrentIndex(max(idx, 0))
        combo.setStyleSheet(t.input_style())
        rl.addWidget(combo, 1)

        alvo = QLineEdit(str(target) if target not in (None, "") else "")
        alvo.setPlaceholderText("Alvo (R$ ou nº de itens)")
        alvo.setStyleSheet(t.input_style())
        rl.addWidget(alvo, 1)

        rem = QPushButton("✕")
        rem.setCursor(Qt.CursorShape.PointingHandCursor)
        rem.setStyleSheet(t.btn_ghost(padding="4px 10px", fs=t.FS_MUTED))
        rem.setToolTip("Remove esta meta.")
        rem.clicked.connect(
            lambda: self._remove_row(row))
        rl.addWidget(rem, 0)

        self._lista.addWidget(row)
        self._rows.append((nome, combo, alvo))

    def _remove_row(self, row: QWidget) -> None:
        for i in range(self._lista.count()):
            w = self._lista.itemAt(i).widget()
            if w is row:
                entry = self._rows.pop(i)
                for f in entry:
                    f.deleteLater()
                row.deleteLater()
                break

    def _on_save(self) -> None:
        metas = []
        for nome, combo, alvo in self._rows:
            label = nome.text().strip()
            try:
                target = goals.parse_target(alvo.text())
            except ValueError:
                self._erro.setText(
                    "Alvo inválido em uma das linhas — use número, ex.: 5000"
                    " ou 5.000,00.")
                self._erro.setVisible(True)
                return
            if not label:
                self._erro.setText("Toda meta precisa de um rótulo.")
                self._erro.setVisible(True)
                return
            if target <= 0:
                self._erro.setText("O alvo precisa ser maior que zero.")
                self._erro.setVisible(True)
                return
            metas.append({
                "label": label,
                "metric": combo.currentData(),
                "target": target,
                "enabled": True,
            })
        goals.save_goals(metas)
        self.accept()
