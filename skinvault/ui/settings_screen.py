"""Tela — Configuracoes (Frente K).

Migra o antigo SettingsDialog (modal) para uma tela navegavel pelo
sidebar, em 3 secoes (Aparencia / Comportamento / Avancado). Cada
controle e' auto-aplicado: salva no settings.json na hora. Tema e
largura da sidebar tem preview ao vivo (via hooks do MainWindow). O
botao "Restaurar padroes" reseta SO' as chaves expostas aqui — nao
mexe em welcome_seen/scanner_unlocked/geometria/etc.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from skinvault import backup as backup_mod
from skinvault.settings import DEFAULTS, load_settings, save_settings
from skinvault.ui import theme as t
from skinvault.ui.components import (
    Card,
    FormRow,
    PageHeader,
    SectionHeader,
    SegmentedControl,
    Toast,
)


# Chaves que esta tela gerencia — o reset so' toca nestas.
_KEYS = (
    "theme",
    "sidebar_width",
    "auto_backup",
    "keep_backups",
    "start_minimized",
    "minimize_to_tray_on_close",
    "cache_ttl_hours",
    "fee_rate",
)


class SettingsScreen(QWidget):
    """Configuracoes em tela: Aparencia, Comportamento, Avancado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Guarda contra os change-handlers dispararem durante o load
        # inicial / refresh (setValue/select emitem sinais).
        self._loading = False
        self._build()
        self._load_into_controls()

    # ── construcao ────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        reset_btn = QPushButton("Restaurar padrões")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(t.btn_secondary())
        reset_btn.setToolTip(
            "Volta as configurações desta tela aos valores padrão.\n"
            "Não afeta seus dados (inventário, trades, watchlist)."
        )
        reset_btn.clicked.connect(self._on_reset)

        root.addWidget(PageHeader(
            "Configurações",
            "Ajustes de aparência, comportamento e dados. As alterações "
            "são salvas automaticamente.",
            actions=[reset_btn],
        ))

        root.addWidget(self._build_appearance())
        root.addWidget(self._build_behavior())
        root.addWidget(self._build_advanced())
        root.addStretch(1)

    def _build_appearance(self) -> Card:
        card = Card(self)
        lay = card.layout()
        lay.addWidget(SectionHeader(
            "Aparência",
            "Tema de cores e largura da barra lateral.",
        ))

        self._theme_seg = SegmentedControl()
        self._theme_seg.add("dark", "Escuro")
        self._theme_seg.add("light", "Claro")
        self._theme_seg.segment_changed.connect(self._on_theme_segment)
        lay.addWidget(FormRow(
            "Tema", self._theme_seg,
            tooltip="Alterna entre o tema escuro e o claro. O preview é "
                    "imediato no chrome da janela; algumas telas só "
                    "refletem 100% após reabrir.",
        ))

        self._sidebar_w = QSpinBox()
        self._sidebar_w.setRange(160, 400)
        self._sidebar_w.setSingleStep(10)
        self._sidebar_w.setSuffix(" px")
        self._sidebar_w.setStyleSheet(t.spin_style())
        self._sidebar_w.valueChanged.connect(self._on_sidebar_width)
        lay.addWidget(FormRow(
            "Largura da barra lateral", self._sidebar_w,
            tooltip="Largura em pixels da barra de navegação à esquerda.",
        ))
        return card

    def _build_behavior(self) -> Card:
        card = Card(self)
        lay = card.layout()
        lay.addWidget(SectionHeader(
            "Comportamento",
            "Janela, bandeja do sistema e backups automáticos.",
        ))

        self._auto_backup = QCheckBox("Fazer backup automático dos dados")
        self._auto_backup.setStyleSheet(t.checkbox_style())
        self._auto_backup.setToolTip(
            "Cria um backup dos arquivos de dados periodicamente."
        )
        self._auto_backup.toggled.connect(
            lambda v: self._set("auto_backup", v))
        lay.addWidget(self._auto_backup)

        self._keep_backups = QSpinBox()
        self._keep_backups.setRange(0, 100)
        self._keep_backups.setStyleSheet(t.spin_style())
        self._keep_backups.valueChanged.connect(
            lambda v: self._set("keep_backups", v))
        lay.addWidget(FormRow(
            "Backups a manter", self._keep_backups,
            tooltip="Quantos backups guardar antes de apagar os mais "
                    "antigos.",
        ))

        btn_row = QVBoxLayout()
        btn_row.setSpacing(8)
        self._backup_btn = QPushButton("Fazer backup manual agora")
        self._backup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._backup_btn.setStyleSheet(t.btn_secondary())
        self._backup_btn.setToolTip(
            "Cria um backup ZIP de todos os arquivos de dados "
            "(prices, portfolio, trades, watchlist, etc.) na pasta "
            "data/backups/."
        )
        self._backup_btn.clicked.connect(self._on_manual_backup)
        btn_row.addWidget(self._backup_btn)

        self._restore_btn = QPushButton("Restaurar backup...")
        self._restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restore_btn.setStyleSheet(t.btn_ghost())
        self._restore_btn.setToolTip(
            "Abre um seletor de backup para restaurar dados de um "
            "ponto anterior. Os dados atuais sao substituidos."
        )
        self._restore_btn.clicked.connect(self._on_restore_backup)
        btn_row.addWidget(self._restore_btn)
        lay.addLayout(btn_row)

        self._start_min = QCheckBox("Iniciar minimizado na bandeja")
        self._start_min.setStyleSheet(t.checkbox_style())
        self._start_min.setToolTip(
            "Ao abrir, o app vai direto para a bandeja do sistema."
        )
        self._start_min.toggled.connect(
            lambda v: self._set("start_minimized", v))
        lay.addWidget(self._start_min)

        self._min_to_tray = QCheckBox(
            "Minimizar para a bandeja ao fechar (o X não encerra o app)"
        )
        self._min_to_tray.setStyleSheet(t.checkbox_style())
        self._min_to_tray.setToolTip(
            "Fechar pela barra de título esconde o app na bandeja em vez "
            "de encerrá-lo."
        )
        self._min_to_tray.toggled.connect(
            lambda v: self._set("minimize_to_tray_on_close", v))
        lay.addWidget(self._min_to_tray)

        # Ate' 29/07/2026 esta opcao so' existia no menu de contexto da
        # bandeja. Ela muda o comportamento da JANELA (sempre no topo, sem
        # roubar foco), e ligada por engano o sintoma que aparece e' "o
        # alt+tab parou de funcionar" -- sem nada na UI apontando a causa.
        self._overlay = QCheckBox(
            "Modo overlay — janela sempre no topo (para CS2 em tela cheia)"
        )
        self._overlay.setStyleSheet(t.checkbox_style())
        self._overlay.setToolTip(
            "Mantém a janela acima das outras e impede que ela roube o foco "
            "do jogo.\n"
            "Efeito colateral: ligado, o alt+tab não tira o SkinVault da "
            "frente.\n"
            "Deixe desligado se você não usa o app sobre o CS2 em tela cheia."
        )
        self._overlay.toggled.connect(self._on_overlay_toggled)
        lay.addWidget(self._overlay)
        return card

    def _on_overlay_toggled(self, value: bool) -> None:
        """Aplica ao vivo quando ha' MainWindow.

        `set_overlay_mode` ja' persiste e refaz as flags da janela --
        chamar `_set` junto so' gravaria duas vezes.
        """
        if self._loading:
            return
        w = self.window()
        if hasattr(w, "set_overlay_mode"):
            w.set_overlay_mode(value)
        else:
            self._set("overlay_mode", value)

    def _build_advanced(self) -> Card:
        card = Card(self)
        lay = card.layout()
        lay.addWidget(SectionHeader(
            "Avançado",
            "Cache de preços e taxa do Steam Market.",
        ))

        self._cache_ttl = QSpinBox()
        self._cache_ttl.setRange(1, 168)
        self._cache_ttl.setSuffix(" h")
        self._cache_ttl.setStyleSheet(t.spin_style())
        self._cache_ttl.valueChanged.connect(
            lambda v: self._set("cache_ttl_hours", v))
        lay.addWidget(FormRow(
            "Validade do cache de preços", self._cache_ttl,
            tooltip="Por quanto tempo um preço consultado é reaproveitado "
                    "antes de buscar de novo na Steam.",
        ))

        self._fee_rate = QDoubleSpinBox()
        self._fee_rate.setRange(0.0, 1.0)
        self._fee_rate.setSingleStep(0.01)
        self._fee_rate.setDecimals(2)
        self._fee_rate.setStyleSheet(t.spin_style())
        self._fee_rate.valueChanged.connect(
            lambda v: self._set("fee_rate", v))
        lay.addWidget(FormRow(
            "Taxa do Steam Market", self._fee_rate,
            tooltip="Fração descontada pela Steam em cada venda "
                    "(0,15 = 15%). Usada no P&L líquido e no simulador.",
        ))
        return card

    # ── persistencia / aplicacao ao vivo ──────────────────
    def _set(self, key: str, value: object) -> None:
        if self._loading:
            return
        s = load_settings()
        s[key] = value
        save_settings(s)

    def _on_theme_segment(self, key: str) -> None:
        if self._loading:
            return
        self._set("theme", key)
        self._apply_theme_live()

    def _on_sidebar_width(self, value: int) -> None:
        if self._loading:
            return
        self._set("sidebar_width", value)
        w = self.window()
        if hasattr(w, "_apply_sidebar_width"):
            w._apply_sidebar_width(value)

    def _apply_theme_live(self) -> None:
        # MainWindow._on_theme_changed recarrega settings, invoca
        # theme._reload_palette() e re-aplica o stylesheet global.
        w = self.window()
        if hasattr(w, "_on_theme_changed"):
            w._on_theme_changed()

    def _on_manual_backup(self) -> None:
        from skinvault.backup import make_backup
        try:
            path = make_backup()
            Toast.show_toast(
                self, f"Backup criado: {path.name}", "success",
            )
        except Exception as e:
            Toast.show_toast(self, f"Falha ao criar backup: {e}", "error")

    def _on_restore_backup(self) -> None:
        from skinvault.backup import list_backups, restore_backup
        backups = list_backups()
        if not backups:
            Toast.show_toast(self, "Nenhum backup encontrado.", "warning")
            return
        items = [f"{b['ts']:%d/%m/%Y %H:%M} ({b['path'].name})"
                 for b in backups]
        from PyQt6.QtWidgets import QInputDialog
        choice, ok = QInputDialog.getItem(
            self, "Restaurar backup",
            "Selecione o backup para restaurar:",
            items, 0, False,
        )
        if not ok:
            return
        idx = items.index(choice)
        path = backups[idx]["path"]
        confirm = QMessageBox.question(
            self, "Confirmar restauração",
            f"Restaurar o backup {path.name}?\n"
            "Os dados atuais SERÃO SUBSTITUÍDOS.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            count = restore_backup(path)
            Toast.show_toast(
                self, f"Restaurados {count} arquivos.", "success",
            )
        except Exception as e:
            Toast.show_toast(self, f"Falha ao restaurar: {e}", "error")

    def _on_reset(self) -> None:
        confirm = QMessageBox.question(
            self, "Restaurar padrões",
            "Restaurar as configurações desta tela para os valores "
            "padrão?\nSeus dados (inventário, trades, watchlist) não "
            "são afetados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        s = load_settings()
        for key in _KEYS:
            s[key] = DEFAULTS[key]
        save_settings(s)
        self._load_into_controls()
        self._apply_theme_live()
        w = self.window()
        if hasattr(w, "_apply_sidebar_width"):
            w._apply_sidebar_width(DEFAULTS["sidebar_width"])
        Toast.show_toast(
            self, "Configurações restauradas para o padrão.", "success",
        )

    # ── carga ─────────────────────────────────────────────
    def refresh(self) -> None:
        """Recarrega os controles a partir do settings.json (chamado
        pelo router ao navegar — settings podem mudar fora da tela, ex.:
        toggle de overlay pela bandeja)."""
        self._load_into_controls()

    def _load_into_controls(self) -> None:
        self._loading = True
        try:
            s = load_settings()
            theme = "dark" if s.get("theme", "dark") == "dark" else "light"
            self._theme_seg.select(theme)
            self._sidebar_w.setValue(int(s.get("sidebar_width", 220)))
            self._auto_backup.setChecked(bool(s.get("auto_backup", True)))
            self._keep_backups.setValue(int(s.get("keep_backups", 10)))
            self._start_min.setChecked(
                bool(s.get("start_minimized", False)))
            self._min_to_tray.setChecked(
                bool(s.get("minimize_to_tray_on_close", True)))
            self._overlay.setChecked(bool(s.get("overlay_mode", False)))
            self._cache_ttl.setValue(int(s.get("cache_ttl_hours", 6)))
            self._fee_rate.setValue(float(s.get("fee_rate", 0.15)))
        finally:
            self._loading = False
