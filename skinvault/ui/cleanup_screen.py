"""Tela — Limpeza do Sistema.

Cinco alvos de temporario do Windows (vide `skinvault.cleanup`), cada um
com um ToggleSwitch, e um botao que limpa so' os marcados.

Duas coisas nao acontecem na UI thread: a MEDICAO e a LIMPEZA. Ambas
percorrem arvores de disco -- um %TEMP% real tem dezenas de milhares de
arquivos, e um `os.walk` sincrono ai' congela a janela por segundos. As
duas rodam em worker daemon e voltam por pyqtSignal, como o resto do app.

A selecao persiste em settings (`cleanup_selected`) porque quem limpa
disco costuma repetir a mesma combinacao; a lixeira e' a excecao e nunca
volta marcada -- ver `_load_selection`.
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault import cleanup as cleanup_mod
from skinvault.settings import load_settings, save_settings
from skinvault.ui import theme as t
from skinvault.ui._price_worker import _safe_emit
from skinvault.ui.components import Card, LineIcon, Toast, ToggleSwitch


# ── workers ──────────────────────────────────────────────────
class ScanWorker(QObject):
    """Mede os alvos em background. Emite um dict {key: ScanResult}."""

    done = pyqtSignal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, keys=None) -> None:
        if self._running:
            return
        self._running = True
        sig = self.done

        def worker() -> None:
            try:
                res = cleanup_mod.scan_all(keys)
            except Exception:
                res = {}
            finally:
                self._running = False
            _safe_emit(sig, res)

        threading.Thread(target=worker, daemon=True).start()


class CleanWorker(QObject):
    """Executa a limpeza em background. Emite {key: CleanResult}."""

    done = pyqtSignal(dict)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, keys) -> None:
        if self._running:
            return
        self._running = True
        sig = self.done
        wanted = list(keys)

        def worker() -> None:
            try:
                res = cleanup_mod.clean(wanted)
            except Exception:
                res = {}
            finally:
                self._running = False
            _safe_emit(sig, res)

        threading.Thread(target=worker, daemon=True).start()


# ── linha de alvo ────────────────────────────────────────────
class CleanupRow(Card):
    """Titulo + descricao + tamanho medido + toggle, numa linha."""

    toggled = pyqtSignal(str, bool)

    def __init__(self, target: cleanup_mod.Target,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent, padding=t.CARD_PAD_MD, radius=10)
        self._target = target

        lay = self.layout()
        lay.setSpacing(0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_MD)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)

        self._title = QLabel(target.title)
        color = t.DANGER if target.dangerous else t.TEXT
        self._title.setStyleSheet(
            f"color: {color}; font-size: {t.FS_BODY}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        col.addWidget(self._title)

        self._desc = QLabel(target.description)
        self._desc.setStyleSheet(t.label_caption())
        self._desc.setWordWrap(True)
        col.addWidget(self._desc)
        row.addLayout(col, 1)

        # Tamanho fica a' esquerda do toggle: e' o dado que decide se vale
        # marcar, entao precisa estar no mesmo alcance visual do controle.
        self._size = QLabel("—")
        self._size.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._size.setMinimumWidth(96)
        self._size.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
        )
        row.addWidget(self._size)

        self._toggle = ToggleSwitch()
        self._toggle.toggled.connect(
            lambda v: self.toggled.emit(self._target.key, v))
        row.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(row)

        tip = target.description
        if target.note:
            tip += "\n" + target.note
        if target.needs_admin:
            tip += "\nExige privilégios de administrador para apagar tudo."
        for w in (self, self._title, self._desc, self._toggle, self._size):
            w.setToolTip(tip)

    @property
    def key(self) -> str:
        return self._target.key

    @property
    def target(self) -> cleanup_mod.Target:
        return self._target

    def is_checked(self) -> bool:
        return self._toggle.isChecked()

    def set_checked(self, v: bool) -> None:
        self._toggle.setChecked(v)

    def set_enabled_row(self, enabled: bool) -> None:
        self._toggle.setEnabled(enabled)

    def set_scan(self, result) -> None:
        """Escreve o tamanho medido. Alvo indisponivel desliga a linha."""
        if result is None:
            self._size.setText("—")
            return
        if not result.available:
            self._size.setText("n/d")
            self._size.setToolTip(
                "Este alvo não existe nesta máquina.")
            self._toggle.setChecked(False)
            self._toggle.setEnabled(False)
            return
        n = result.files
        unit = "item" if n == 1 else "itens"
        self._size.setText(
            f"{cleanup_mod.human_bytes(result.bytes)}\n{n} {unit}")


# ── tela ─────────────────────────────────────────────────────
class CleanupScreen(QWidget):
    """Limpeza do Sistema: mede, o usuario marca, confirma, limpa."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self._rows: dict = {}
        self._scan: dict = {}
        self._refresh_pending = False
        self._scan_worker = ScanWorker(self)
        self._scan_worker.done.connect(self._on_scan_done)
        self._clean_worker = CleanWorker(self)
        self._clean_worker.done.connect(self._on_clean_done)
        self._build()
        self._load_selection()

    # ── construcao ────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        root.addWidget(self._build_hero())

        for target in cleanup_mod.TARGETS:
            row = CleanupRow(target, self)
            row.toggled.connect(self._on_row_toggled)
            self._rows[target.key] = row
            root.addWidget(row)

        root.addStretch(1)
        root.addLayout(self._build_footer())

    def _build_hero(self) -> Card:
        card = Card(self)
        lay = card.layout()
        lay.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_LG)

        tile = QWidget()
        tile.setFixedSize(44, 44)
        tile.setStyleSheet(
            f"background: {t.SURFACE}; border-radius: {t.RADIUS_MD}px;")
        tile_lay = QHBoxLayout(tile)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile_lay.addWidget(LineIcon("broom", t.TEXT, tile))
        row.addWidget(tile, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        title = QLabel("Limpeza do Sistema")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_MD}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        col.addWidget(title)
        self._last_lbl = QLabel("Nunca executada")
        self._last_lbl.setStyleSheet(t.label_caption())
        col.addWidget(self._last_lbl)
        row.addLayout(col, 1)

        self._rescan_btn = QPushButton("Recalcular")
        self._rescan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rescan_btn.setStyleSheet(t.btn_ghost())
        self._rescan_btn.setToolTip(
            "Mede de novo quanto cada item ocupa em disco.")
        self._rescan_btn.clicked.connect(lambda: self.refresh())
        row.addWidget(self._rescan_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(row)
        return card

    def _build_footer(self) -> QHBoxLayout:
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(t.SPACE_MD)

        self._total_lbl = QLabel("")
        self._total_lbl.setStyleSheet(t.label_caption())
        foot.addWidget(self._total_lbl)
        foot.addStretch(1)

        self._clean_btn = QPushButton("Limpar Selecionados")
        self._clean_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clean_btn.setStyleSheet(t.btn_primary())
        self._clean_btn.setEnabled(False)
        self._clean_btn.setToolTip("Marque ao menos um item para limpar.")
        self._clean_btn.clicked.connect(self._on_clean_clicked)
        foot.addWidget(self._clean_btn)
        return foot

    # ── selecao ───────────────────────────────────────────
    def selected_keys(self) -> list:
        return [k for k, r in self._rows.items() if r.is_checked()]

    def _load_selection(self) -> None:
        """Restaura os toggles do settings -- menos a lixeira.

        Deixar 'Esvaziar Lixeira' marcada de uma sessao pra outra transforma
        um clique distraido em perda permanente de arquivo. Alvo destrutivo
        sempre comeca desmarcado.
        """
        self._loading = True
        try:
            s = load_settings()
            saved = s.get("cleanup_selected") or []
            if not isinstance(saved, list):
                saved = []
            for key, row in self._rows.items():
                if row.target.dangerous:
                    row.set_checked(False)
                else:
                    row.set_checked(key in saved)
            ts = s.get("cleanup_last_ts") or 0
            self._set_last_label(ts)
        finally:
            self._loading = False
        self._sync_button()

    def _save_selection(self) -> None:
        if self._loading:
            return
        s = load_settings()
        s["cleanup_selected"] = [
            k for k in self.selected_keys()
            if not self._rows[k].target.dangerous
        ]
        save_settings(s)

    def _on_row_toggled(self, _key: str, _value: bool) -> None:
        self._save_selection()
        self._sync_button()

    def _sync_button(self) -> None:
        keys = self.selected_keys()
        busy = self._clean_worker.running
        self._clean_btn.setEnabled(bool(keys) and not busy)
        if not keys:
            self._clean_btn.setToolTip("Marque ao menos um item para limpar.")
            self._total_lbl.setText("")
            return
        total = sum(
            self._scan[k].bytes for k in keys
            if k in self._scan and self._scan[k].available
        )
        titles = ", ".join(self._rows[k].target.title for k in keys)
        self._clean_btn.setToolTip(f"Limpar: {titles}")
        if self._scan:
            self._total_lbl.setText(
                f"Selecionado: {cleanup_mod.human_bytes(total)}")

    def _set_last_label(self, ts) -> None:
        try:
            ts = float(ts or 0)
        except (TypeError, ValueError):
            ts = 0.0
        if ts <= 0:
            self._last_lbl.setText("Nunca executada")
            return
        stamp = time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))
        self._last_lbl.setText(f"Última limpeza: {stamp}")

    # ── medicao ───────────────────────────────────────────
    def refresh(self) -> None:
        """Remede os alvos (chamado pelo router ao navegar, no Recalcular,
        e por `_on_clean_done` pra mostrar o tamanho pós-limpeza)."""
        if self._scan_worker.running:
            # Uma rodada de scan já está em voo (ex. usuário clicou
            # "Recalcular" perto da hora em que a limpeza terminou) --
            # marca que um refresh novo é devido assim que ESSA rodada
            # acabar, em vez de simplesmente descartar o pedido. Sem
            # isto, o refresh automático que `_on_clean_done` dispara no
            # fim podia ser engolido em silêncio, deixando o tamanho
            # exibido desatualizado (pré-limpeza) até o usuário clicar
            # "Recalcular" de novo por conta própria -- achado numa
            # caçada dirigida por essa família de bug, 2026-10-27.
            self._refresh_pending = True
            return
        self._rescan_btn.setEnabled(False)
        for row in self._rows.values():
            row.set_scan(None)
        self._total_lbl.setText("Medindo…")
        self._scan_worker.start()

    def _on_scan_done(self, results: dict) -> None:
        self._scan = results or {}
        for key, row in self._rows.items():
            row.set_scan(self._scan.get(key))
        self._rescan_btn.setEnabled(True)
        self._sync_button()
        if self._refresh_pending:
            self._refresh_pending = False
            self.refresh()

    # ── limpeza ───────────────────────────────────────────
    def _on_clean_clicked(self) -> None:
        keys = self.selected_keys()
        if not keys:
            return
        if not self._confirm(keys):
            return
        self._clean_btn.setEnabled(False)
        self._clean_btn.setText("Limpando…")
        for row in self._rows.values():
            row.set_enabled_row(False)
        self._clean_worker.start(keys)

    def _confirm(self, keys) -> bool:
        """Confirmacao explicita, com o que sai e os avisos que se aplicam."""
        lines = []
        total = 0
        for k in keys:
            tgt = self._rows[k].target
            sc = self._scan.get(k)
            if sc is not None and sc.available:
                total += sc.bytes
                lines.append(
                    f"• {tgt.title} — {cleanup_mod.human_bytes(sc.bytes)}")
            else:
                lines.append(f"• {tgt.title}")

        body = ["Os itens abaixo serão limpos:", "", *lines, ""]
        if total:
            body.append(f"Total estimado: {cleanup_mod.human_bytes(total)}")
            body.append("")
        if any(self._rows[k].target.dangerous for k in keys):
            body.append(
                "ATENÇÃO: esvaziar a Lixeira apaga os arquivos "
                "PERMANENTEMENTE — não há como desfazer.")
            body.append("")
        needs_admin = [k for k in keys if self._rows[k].target.needs_admin]
        if needs_admin and not cleanup_mod.is_admin():
            body.append(
                "O SkinVault não está em modo administrador: arquivos "
                "protegidos do Windows serão pulados.")
            body.append("")
        body.append("Continuar?")

        box = QMessageBox(self)
        box.setWindowTitle("Confirmar limpeza")
        box.setText("\n".join(body))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # Default no No: enter distraido nao pode disparar remocao.
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _on_clean_done(self, results: dict) -> None:
        results = results or {}
        removed = sum(r.removed for r in results.values())
        freed = sum(r.freed for r in results.values())
        skipped = sum(r.skipped for r in results.values())

        self._clean_btn.setText("Limpar Selecionados")
        for row in self._rows.values():
            row.set_enabled_row(True)

        ts = time.time()
        s = load_settings()
        s["cleanup_last_ts"] = ts
        save_settings(s)
        self._set_last_label(ts)

        if not results:
            Toast.show_toast(self, "Nada foi limpo.", "warning")
        else:
            msg = (f"{removed} arquivos removidos · "
                   f"{cleanup_mod.human_bytes(freed)} liberados")
            if skipped:
                msg += f" · {skipped} em uso, pulados"
            Toast.show_toast(self, msg, "success" if removed else "warning")

        self.refresh()
