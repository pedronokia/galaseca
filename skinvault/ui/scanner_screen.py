"""Tela 3 — Scanner de Investimento (F11).

Escaneia items do Steam Market, calcula score multi-fator,
e permite gerar ranking Top 20.
"""
from __future__ import annotations

import sys
import threading
import time

from urllib.parse import quote

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QBrush, QColor, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import (
    backtest, cases, discovery, portfolio as portfolio_mod, ranking,
    settings as sv_settings, signals, ssr_cache, steam_api, valve_events,
)
from skinvault._paths import DATA_DIR
from skinvault.ui.components import SortableItem, auto_cell
from skinvault.prices import PriceCache
from skinvault.ui import textos
from skinvault.ui import theme as t
from skinvault.ui.components import (
    Card, EmptyState, LoadingState, PageHeader, SectionHeader, StatCard,
    Toast, ToggleSwitch, sync_bar,
)
from skinvault.ui.scanner_dialogs import _BacktestResultDialog, _ScoreBreakdownDialog
from skinvault.ui.scanner_widgets import _ScannerBridge, _ValidationBridge


_CS2_APPID = 730

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
    "Cápsulas de autógrafo": cases.list_autograph_capsules(),
    "Adesivos de torneio": cases.list_tournament_stickers(),
    "Adesivos de autógrafo": cases.list_autograph_stickers(),
    "Adesivos da comunidade": cases.list_community_stickers(),
    "Adesivos de evento": cases.list_event_stickers(),
}

# Codigos internos do veredito -> texto da tela (ver ui/textos.py).
_SPREAD_TXT = textos.SPREAD
_BOOK_TXT = textos.BOOK
_TREND_TXT = textos.TREND
# CSV exportado: mesmo vocabulario da tela, nao o codigo interno.
_CONF_CSV = {"high": "Alta", "medium": "Média", "low": "Baixa",
             "very_low": "Mínima", "none": ""}
_RISCO_CSV = {"low": "Baixo", "medium": "Médio", "high": "Alto"}


class ScannerScreen(QWidget):
    """Scanner de investimento multi-fator."""

    COL_NAME = 0
    # Nota + resumo ("100 · COMPRA") numa coluna so', a 1. Antes eram duas
    # colunas dizendo a mesma coisa ("COMPRA" na 1, "100" na 10), e o
    # espaco fazia falta pro nome do item. COL_SINAL e COL_SCORE apontam
    # pra mesma coluna; a 10 segue existindo, oculta (indices estaveis).
    COL_SCORE = 1
    COL_SINAL = 1
    COL_PRECO = 2
    COL_JUSTO = 3
    # "Compre ate'" fica colado no "Preço justo" porque deriva dele: e' o
    # maximo a pagar pra, revendendo na mediana, sobrar a margem.
    COL_COMPRAR = 4
    COL_VEREDITO = 5
    COL_SPREAD = 6
    COL_BOOK = 7
    COL_TREND = 8
    COL_SD = 9
    COL_SCORE_OCULTA = 10
    COL_RISCO = 11
    COL_CONFIDENCE = 12

    # Margem-alvo da coluna "Compre ate'". 20% e' folgado o bastante pra
    # cobrir o break-even de 15% da Steam e ainda sobrar -- o quintil
    # superior do score rende +13,64% brutos, que NAO cobre a taxa
    # (AGENTS.md 4b). Comprar com desconto e' o que fecha a conta.
    MARGEM_ALVO_PCT = 20.0

    # Largura minima de coluna. As colunas curtas ("Nota" = "87") nao
    # precisam dos 120px do piso global.
    _PISO_COLUNA = 56

    # Nome do item nunca abaixo disto; em janela estreita estas colunas
    # somem (nesta ordem) ate' caber -- o detalhe delas segue no "Por que
    # essa nota?". A 1366x768 o nome virava "M4A4 ..." (2026-10-17).
    _NOME_MIN = 220

    def _ajustar_colunas(self) -> None:
        t.ajustar_colunas(
            self._table, self.COL_NAME, self._NOME_MIN,
            opcionais=[self.COL_CONFIDENCE, self.COL_SD, self.COL_BOOK,
                       self.COL_SPREAD, self.COL_COMPRAR],
            piso=self._PISO_COLUNA)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._table.isVisible():
            self._ajustar_colunas()

    def showEvent(self, event) -> None:
        # Ajuste feito com a tela ainda oculta usava a largura de
        # nascimento da tabela e escondia colunas que cabiam.
        super().showEvent(event)
        QTimer.singleShot(0, self._ajustar_colunas)

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
        self._scan_cancelled = False
        self._scanning = False
        self._build()

    def hideEvent(self, event) -> None:
        self._scan_cancelled = True
        super().hideEvent(event)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        self._cat_combo = QComboBox()
        self._cat_combo.setStyleSheet(
            f"QComboBox {{ background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: 8px; padding: 8px 12px; color: {t.TEXT};"
            f" font-size: {t.FS_INPUT}; min-width: 160px;"
            f" font-family: {t.FONT_FAMILY}; }}"
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
            "Analisa todos os itens da categoria e dá a cada um uma nota"
            " de 0 a 100 com um resumo: COMPRA, ATENÇÃO ou EVITAR."
        )
        self._scan_tooltip = self._scan_btn.toolTip()
        self._scan_btn.clicked.connect(self._on_scan)
        # Ctrl+Enter dispara o scan direto do teclado (foco nao importa).
        sc = QShortcut(QKeySequence("Ctrl+Return"), self)
        sc.activated.connect(self._on_scan)

        # Acoes secundarias agrupadas em menu ⋯ (Frente CC: max 2 botoes
        # diretos no header).
        self._more_btn = QPushButton("⋯")
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.setStyleSheet(t.btn_ghost(padding="10px 14px",
                                                  fs=t.FS_INPUT))
        self._more_btn.setToolTip("Mais ações.")
        self._more_menu = QMenu(self._more_btn)

        self._rank_btn = self._more_menu.addAction("Ranking Top 20")
        self._rank_btn.setToolTip(
            "Analisa TODAS as categorias e lista as 20 melhores notas."
            " Demora vários minutos: a Steam limita quantas consultas"
            " podemos fazer."
        )
        self._rank_btn.triggered.connect(self._on_ranking)

        self._validate_btn = self._more_menu.addAction("Testar a nota no passado")
        self._validate_btn.setToolTip(
            "Volta no histórico dos itens analisados e confere se as notas"
            " altas de antes subiram mais nos 90 dias seguintes."
            " Demora uns segundos por item."
        )
        self._validate_btn.triggered.connect(self._on_validate_score)

        self._more_menu.addSeparator()

        self._clear_cache_btn = self._more_menu.addAction("Apagar preços guardados")
        self._clear_cache_btn.setToolTip(
            "Apaga o histórico de preços guardado no computador, para"
            " buscar tudo de novo na Steam. Normalmente não é preciso: ele"
            " se renova sozinho a cada 24h, e buscar de novo é lento."
        )
        self._clear_cache_btn.triggered.connect(self._on_clear_ssr_cache)

        self._export_btn = self._more_menu.addAction("Exportar CSV")
        self._export_btn.setToolTip(
            "Salva os resultados numa planilha (CSV)."
            " Você escolhe o nome e a pasta."
        )
        self._export_btn.triggered.connect(self._on_export_csv)
        self._export_btn.setEnabled(False)

        self._more_btn.setMenu(self._more_menu)

        root.addWidget(PageHeader(
            "Scanner de Oportunidades",
            "Dá uma nota de 0 a 100 para cada item com base nos dados de preço.",
            actions=[self._cat_combo, self._scan_btn, self._more_btn],
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
        self._stat_count.setToolTip(
            "Total de itens da categoria que o scan conseguiu avaliar."
        )
        self._stat_best = StatCard("Melhor nota", "—", icon="trophy")
        self._stat_best.setToolTip(
            "A maior nota entre os itens analisados. Nota alta = preço"
            " abaixo do típico e fácil de comprar e vender."
        )
        self._stat_avg = StatCard("Nota média", "—", icon="chart")
        self._stat_avg.setToolTip(
            "A média das notas da categoria. Compare com a melhor nota:"
            " se as duas são altas, a categoria toda está bem; se só a"
            " melhor é alta, é um item específico."
        )
        self._stat_breadth = StatCard("Mercado", "—", icon="chart")
        self._stat_breadth_tooltip = (
            "Quantos dos itens analisados estão subindo, caindo ou"
            " parados nos últimos dias. Vale só para esta categoria, não"
            " para o mercado todo, e não diz o que vai acontecer."
        )
        self._stat_breadth.setToolTip(self._stat_breadth_tooltip)
        for sc in (self._stat_count, self._stat_best, self._stat_avg,
                   self._stat_breadth):
            # Mesmo peso pros quatro: ocupam a largura toda. Antes ficavam
            # presos a 300px a' esquerda com um vazio grande a' direita.
            stats_row.addWidget(sc, 1)
        root.addLayout(stats_row)

        # Filtros acima da tabela
        from skinvault.settings import load_settings as _load
        _s = _load()
        filt_row = QHBoxLayout()
        filt_row.setSpacing(12)
        self._hide_low_conf_cb = ToggleSwitch(
            checked=bool(_s.get("scanner_hide_low_confidence", False))
        )
        self._hide_low_conf_cb.setToolTip(
            "Esconde os itens com nota abaixo de 45."
        )
        self._hide_low_conf_cb.toggled.connect(self._on_hide_low_conf_toggle)
        filt_row.addWidget(self._hide_low_conf_cb)
        _lbl1 = QLabel("Baixa confiança")
        _lbl1.setStyleSheet(t.label_caption())
        _lbl1.setToolTip(
            "Esconde os itens com nota abaixo de 45."
        )
        filt_row.addWidget(_lbl1)

        self._hide_approx_cb = ToggleSwitch(
            checked=bool(_s.get("scanner_hide_approx", False))
        )
        self._hide_approx_cb.setToolTip(
            "Esconde os itens cuja fila de ofertas veio de outro"
            " desgaste do mesmo skin (dado aproximado). A Steam não"
            " mostra a fila exata de cada desgaste."
        )
        self._hide_approx_cb.toggled.connect(self._on_hide_approx_toggle)
        filt_row.addWidget(self._hide_approx_cb)
        _lbl2 = QLabel("Dados aproximados")
        _lbl2.setStyleSheet(t.label_caption())
        _lbl2.setToolTip(
            "Itens com a fila de ofertas de outro desgaste do mesmo"
            " skin."
        )
        filt_row.addWidget(_lbl2)

        self._price_filter_cb = QComboBox()
        self._price_filter_cb.setStyleSheet(
            f"QComboBox {{ background: {t.SURFACE}; border: 1px solid {t.BORDER};"
            f" border-radius: 8px; padding: 8px 12px; color: {t.TEXT};"
            f" font-size: {t.FS_INPUT}; min-width: 160px;"
            f" font-family: {t.FONT_FAMILY}; }}"
            f"QComboBox:focus {{ border: 1px solid {t.ACCENT}; }}"
            f"QComboBox:drop-down {{ border: none; }}"
            f"QComboBox:down-arrow {{ color: {t.TEXT_MUTED}; }}"
            f"QComboBox QAbstractItemView"
            f" {{ background: {t.BG_ELEVATED}; border: 1px solid {t.BORDER};"
            f" selection-background-color: {t.SURFACE_HOV}; color: {t.TEXT}; }}"
            f"QComboBox QAbstractItemView::item"
            f" {{ padding: 6px 12px; }}"
        )
        self._price_filter_cb.addItem("Todos os preços")
        for _rotulo in signals.price_band_labels():
            self._price_filter_cb.addItem(_rotulo)
        _saved_price_filter = _s.get("scanner_price_filter", "Todos os preços")
        _idx = self._price_filter_cb.findText(_saved_price_filter)
        if _idx >= 0:
            self._price_filter_cb.setCurrentIndex(_idx)
        self._price_filter_cb.setToolTip(
            "Mostra só itens nessa faixa de preço. Não refaz a análise,"
            " só esconde linhas."
        )
        self._price_filter_cb.currentTextChanged.connect(
            self._on_price_filter_change)
        filt_row.addWidget(self._price_filter_cb)

        self._search_inp = QLineEdit()
        self._search_inp.setPlaceholderText("Buscar por nome do item...")
        self._search_inp.setClearButtonEnabled(True)
        self._search_inp.setFixedWidth(260)
        self._search_inp.setStyleSheet(t.input_style())
        self._search_inp.setToolTip(
            "Filtra a tabela pelo nome do item. Não afeta o que foi "
            "escaneado — só esconde linhas, e as outras colunas de "
            "filtro (baixa confiança, dados aproximados) continuam "
            "valendo.\nCtrl+F foca o campo, Esc limpa."
        )
        self._search_inp.textChanged.connect(self._apply_search_filter)
        filt_row.addWidget(self._search_inp)
        filt_row.addStretch(1)
        root.addLayout(filt_row)

        # Ctrl+F / Esc: mesmo gesto das outras telas (inventário, histórico).
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self._focar_busca)
        QShortcut(QKeySequence("Esc"), self).activated.connect(
            self._limpar_busca)

        # Loading state (mostrado durante scan/validacao)
        self._loading = LoadingState(parent=self)
        self._loading.setVisible(False)
        root.addWidget(self._loading, 0, Qt.AlignmentFlag.AlignCenter)

        # Barra fina de sincronizacao: a tabela ja mostra resultado
        # progressivamente durante o scan (streaming linha a linha), entao
        # cobrir tudo com o LoadingState grande nao caberia aqui -- a barra
        # avisa "ainda rodando" sem esconder o que ja' chegou.
        self._sync_bar = sync_bar(self)
        root.addWidget(self._sync_bar)

        # Tabela
        self._table = QTableWidget(0, 13)
        # Titulos longos em duas linhas: 13 colunas nao cabem numa tela
        # comum com "Diferenca compra/venda" numa linha so'.
        self._table.setHorizontalHeaderLabels([
            "Item", "Nota", "Preço", "Preço\ntípico", "Compre\naté",
            "Avaliação", "Diferença\ncompra/venda", "Fila de\nofertas",
            "Tendência", "Procura ×\nOferta", "Nota (número)", "Risco",
            "Confiança\nnos dados",
        ])
        t.configure_table(
            self._table,
            density=sv_settings.load_settings().get(
                "table_density", "standard"))
        # O piso global de 120px por coluna (configure_table) somava
        # 13 x 120 = 1560px so' de minimo -- "Nota" mostra "87".
        self._table.horizontalHeader().setMinimumSectionSize(
            self._PISO_COLUNA)
        compra_hdr = self._table.horizontalHeaderItem(self.COL_COMPRAR)
        if compra_hdr:
            compra_hdr.setToolTip(
                "O máximo que vale pagar hoje para, revendendo pelo "
                f"preço típico, ainda sobrar {self.MARGEM_ALVO_PCT:.0f}% "
                "de lucro.\n"
                "Já desconta a taxa de 15% da Steam: se você anuncia por "
                "R$ 115, recebe R$ 100.\n"
                "Fica verde quando o preço de agora está abaixo desse "
                "valor."
            )
        score_hdr = self._table.horizontalHeaderItem(self.COL_SCORE)
        if score_hdr:
            score_hdr.setToolTip(
                "Nota de 0 a 100 que resume os dados do item, com o"
                " resumo: COMPRA (70 ou mais), ATENÇÃO (45 a 69) ou EVITAR"
                " (abaixo de 45).\n"
                "Vem só de dados passados — a decisão é sempre sua."
                " Clique duas vezes numa linha para ver o que somou e o"
                " que tirou pontos."
            )
        # Mesmo padrao de tooltip por coluna do inventario.
        for _col, _tip in {
            self.COL_PRECO: (
                "Preço anunciado agora na Steam. Um '*' indica preço "
                "aproximado, calculado pelo histórico."),
            self.COL_JUSTO: (
                "O preço pelo qual o item costuma ser vendido nos "
                "últimos dias. Serve de referência para saber se está "
                "caro ou barato."),
            self.COL_VEREDITO: (
                "Compara o preço de agora com o preço típico: abaixo "
                "dele é bom para comprar, acima está caro."),
            self.COL_SPREAD: (
                "Diferença entre o que os compradores oferecem e o que "
                "os vendedores pedem.\n"
                "Pequena = fácil de comprar e vender sem perder muito. "
                "Um '~' indica dado aproximado (de outro desgaste do "
                "mesmo skin)."),
            self.COL_BOOK: (
                "Quem está em maior número na fila: gente querendo "
                "comprar ou gente querendo vender. Um '~' indica dado "
                "aproximado."),
            self.COL_TREND: (
                "Se o preço vem subindo, caindo ou parado nos últimos "
                "dias. Passe o mouse na célula para ver o quanto ele se "
                "afastou do normal."),
            self.COL_SD: (
                "Quantos itens são vendidos por dia comparado a quantos "
                "estão à venda. Abaixo de 1 = tem mais gente vendendo do "
                "que comprando.\n"
                "Passe o mouse na célula para ver em quantos dias o "
                "estoque à venda acabaria no ritmo atual."),
            self.COL_RISCO: (
                "Avisa quando o preço subiu rápido demais, perto do "
                "maior valor já registrado e com muito volume — padrão "
                "comum antes de quedas fortes.\n"
                "É só um aviso: não muda a nota."),
            self.COL_CONFIDENCE: (
                "Quanto histórico de preço existe para calcular a nota. "
                "Com pouco histórico, a nota é pouco confiável."),
        }.items():
            _hdr = self._table.horizontalHeaderItem(_col)
            if _hdr is not None:
                _hdr.setToolTip(_tip)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        # Interactive + ajuste manual (_ajustar_colunas): ResizeToContents
        # ignora o padding QSS do cabecalho e truncava o titulo com o piso
        # menor. O ajuste usa o maior entre conteudo e titulo.
        for i in range(1, 13):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnHidden(self.COL_SCORE_OCULTA, True)
        self._ajustar_colunas()
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
                   "Clique duas vezes numa linha para ver de onde veio a nota."],
            # "◎" e' o glifo de "pronto pra agir" (ver docstring do
            # EmptyState) -- precisa de uma CTA de verdade, nao so' os
            # passos em texto. Escaneia a categoria ja' selecionada no
            # combo acima (default = "Todas as categorias").
            cta_label="Escanear agora",
            on_cta=self._on_scan,
        )
        root.addWidget(self._empty_hero, 1)
        # Estado inicial: hero visivel, tabela escondida
        self._table.setVisible(False)

        # Busca sem resultado escondia a tabela inteira sem dizer nada --
        # indistinguivel de "ainda nao escaneei" ou de falha silenciosa
        # (mesmo bug ja corrigido no Inventario, ver _sem_match la).
        self._sem_match = QLabel(
            "Nenhum item escaneado casa com a busca. Limpe o campo pra "
            "ver todos.")
        self._sem_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sem_match.setStyleSheet(t.label_caption())
        self._sem_match.setVisible(False)
        root.addWidget(self._sem_match)

        # Progress/status
        self._status = QLabel("Pronto. Selecione uma categoria e clique em Escanear.")
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};"
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
            f"O mercado pode ter mudado; use a nota com cautela."
        )
        self._regime_banner.setToolTip(ev["summary"])
        self._regime_banner.setVisible(True)

    def _discovery_ligada(self) -> bool:
        """Descoberta e' opt-in (settings.scanner_discovery, default OFF).

        Desligada, o scanner se comporta exatamente como sempre: lista fixa.
        """
        try:
            return bool(
                sv_settings.load_settings().get("scanner_discovery"))
        except Exception:
            return False

    def _on_scan(self) -> None:
        if self._scanning:
            # Mesmo botao vira "Cancelar scan" durante o scan: o clique
            # sinaliza o worker, que para entre itens e reporta.
            self._scan_cancelled = True
            self._scan_btn.setEnabled(False)
            self._scan_btn.setText("Cancelando...")
            self._status.setText("Cancelando scan...")
            return

        cat = self._cat_combo.currentText()
        if cat == "Todas as categorias":
            alvos = list(_SCAN_BY_CATEGORY.items())
        else:
            alvos = [(cat, _SCAN_BY_CATEGORY.get(cat, []))]
        usar_descoberta = self._discovery_ligada()
        # Sem descoberta e sem lista fixa nao ha' o que escanear.
        if not usar_descoberta and not any(fb for _, fb in alvos):
            return

        self._scan_cancelled = False
        self._scanning = True
        self._scan_total_planned = 0
        self._scan_results.clear()
        self._table.setRowCount(0)
        # Mostra a tabela vazia (vai encher progressivamente) e esconde hero
        self._empty_hero.setVisible(False)
        self._table.setVisible(True)
        # O botao primario vira "Cancelar scan" e fica habilitado.
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("Cancelar scan")
        self._scan_btn.setToolTip(
            "Cancela o scan em andamento. Resultados já coletados "
            "permanecem na tabela."
        )
        self._rank_btn.setEnabled(False)
        self._validate_btn.setEnabled(False)
        if usar_descoberta:
            # Total so' se sabe depois da busca por faceta, ja' na worker.
            rotulo = "Descobrindo itens no Mercado..."
        else:
            rotulo = f"Escaneando {sum(len(fb) for _, fb in alvos)} itens..."
        self._status.setText(rotulo)
        self._loading.set_label(rotulo)
        self._loading.setVisible(True)
        self._sync_bar.setVisible(True)

        def _worker():
            # Resolver a lista pode ir a' rede (busca por faceta). Roda AQUI,
            # nunca em _on_scan -- la' e' a thread da UI e a janela travaria.
            #
            # try/except/finally: resolve_scan_items (rede) podia levantar
            # excecao e derrubar a thread ANTES de emitir "FIM"/"CANCELADO"
            # -- sem o sinal, _on_progress nunca reabilitava os botoes e o
            # scanner ficava com "Cancelar scan" preso pra sempre (bug real,
            # achado no diagnostico da Fase 2 de microinteracoes). O except
            # loga e segue pro finally -- mesmo padrao de _scan_item logo
            # abaixo, que ja' nao deixa excecao de item derrubar o scan.
            cancelado = False
            try:
                items: list[str] = []
                vistos = set()
                for nome_cat, fallback in alvos:
                    if self._scan_cancelled:
                        break
                    achados, _origem = discovery.resolve_scan_items(
                        nome_cat, fallback, enabled=usar_descoberta,
                    )
                    for nome in achados:
                        if nome not in vistos:
                            vistos.add(nome)
                            items.append(nome)
                if not items:
                    return
                # Guardado ANTES do loop pra _on_progress distinguir "0
                # itens porque a categoria nao tinha nada" (total=0, nunca
                # chega aqui) de "0 itens porque tudo falhou" (total>0,
                # nenhum _scan_item voltou resultado -- rate limit e' a
                # causa mais provavel, ver _scan_item/steam_api).
                self._scan_total_planned = len(items)
                for i, name in enumerate(items):
                    if self._scan_cancelled:
                        cancelado = True
                        break
                    self._bridge.progress.emit(
                        f"[{i+1}/{len(items)}] {name}"
                    )
                    result = self._scan_item(name)
                    if result:
                        self._bridge.result_ready.emit(result)
                    time.sleep(steam_api.RATE_LIMIT_DELAY_S)
            except Exception as e:
                print(f"WARNING: scan worker falhou: {e}", file=sys.stderr)
            finally:
                self._bridge.progress.emit("CANCELADO" if cancelado else "FIM")

        threading.Thread(target=_worker, daemon=True).start()

    def _scan_item(self, name: str) -> dict | None:
        try:
            overview = steam_api.get_market_overview(name)
            time.sleep(steam_api.RATE_LIMIT_DELAY_S)
            page = steam_api.get_market_page_data(name)
        except Exception as e:
            print(f"WARNING: _scan_item({name}) failed: {e}",
                  file=sys.stderr)
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
        # Metadados oficiais da Steam (tags da description) -- vem na mesma
        # pagina, sem requisicao extra.
        meta = (page.get("meta") or {}) if page else {}
        verdict = steam_api.fair_value_verdict(
            lowest, median,
            spread=ob.get("spread") if ob else None,
            buy_count=ob.get("buy_count") if ob else None,
            sell_count=ob.get("sell_count") if ob else None,
            price_history=page.get("price_history") if page else None,
            tradable_restriction=meta.get("tradable_restriction"),
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
        # A colecao vem da tag ItemSet da Steam: resolve item que o mapa
        # manual _SKIN_TO_CASE nao cobre, sem sobrescrever o que ja' cobre.
        cs = cases.case_status(name, collection=meta.get("collection"))
        is_cont = cases.is_container(name)

        score, breakdown = signals.enhanced_score(
            verdict, volume, supply,
            multi_trend=multi,
            price_history=page.get("price_history") if page else None,
            case_status=cs,
            is_container=is_cont,
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
        # Mesmo formato das outras colunas de dinheiro. "210.00" nao casava
        # com nenhum formato do sort_key_from_text e a coluna ordenava como
        # texto (R$ 9 depois de R$ 100).
        price_str = f"{t.brl(lowest)}{' *' if derived_price else ''}"
        return {
            "name": name,
            "price": lowest,
            "price_str": price_str,
            "median": median,
            "score": score,
            "breakdown": breakdown,
            "data_quality": dq,
            "is_container": is_cont,
            "verdict": verdict.get("label", "—"),
            "verdict_color": t.POSITIVE if verdict.get("diff_pct", 0) <= 0
                             else t.DANGER,
            # Codigo interno ("tight", "buyer_dominant"...) aparecia CRU
            # na celula. Traduz so' pra exibir; a logica segue no codigo.
            "spread": (_SPREAD_TXT.get(verdict.get("spread_verdict", ""),
                                       verdict.get("spread_verdict", "")) +
                       (approx_suffix if verdict.get("spread_verdict") else "")),
            "book": (_BOOK_TXT.get(verdict.get("book_verdict", ""),
                                   verdict.get("book_verdict", "")) +
                     (approx_suffix if verdict.get("book_verdict") else "")),
            "trend": _TREND_TXT.get(verdict.get("trend_verdict", ""),
                                    verdict.get("trend_verdict", "")),
            # Codigo cru pra LOGICA (market_breadth conta "rising"/...).
            # "trend" virou texto de tela em 2026-10-17 e o cartao Mercado
            # passou a mostrar sempre "—" ate' este campo existir.
            "trend_code": verdict.get("trend_verdict", ""),
            "volume": volume,
            "supply": supply,
            "sd_label": signals.supply_demand_ratio(volume, supply).get("label", ""),
            "liquidity_depth": signals.liquidity_depth(
                supply, signals.load_item_volume(name)),
            "zscore": signals.price_zscore(
                page.get("price_history")) if page else {},
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
                "ATENÇÃO" if score >= 45 else "EVITAR"
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
            # Teto de compra: quanto pagar pra, revendendo na mediana,
            # sobrar MARGEM_ALVO_PCT. Verde quando o preco atual cabe.
            teto = None
            if r.get("median"):
                teto = portfolio_mod.max_buy_price(
                    r["median"], self.MARGEM_ALVO_PCT)
            preco_atual = r.get("price")
            if teto is None:
                teto_txt, teto_cor = "—", t.TEXT_MUTED
            else:
                teto_txt = t.brl(teto)
                teto_cor = (t.POSITIVE
                            if preco_atual and preco_atual <= teto
                            else t.TEXT_MUTED)
            cells = [
                (_ln(r["name"]), None),
                (f"{score} · {label}", score_color),
                (r.get("price_str", t.brl(r["price"])), None),
                (t.brl(r["median"]), None),
                (teto_txt, teto_cor),
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
                # auto_cell: chave de ordenacao derivada do texto. Sem ela,
                # Preco/Justo/Spread/Score ordenavam como string.
                item = (SortableItem(str(val), score)
                        if col == self.COL_SCORE else auto_cell(str(val)))
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
                    + "\n\nAvisa quando o preço subiu rápido, perto do "
                    "maior valor já registrado e com muito volume — padrão "
                    "comum antes de quedas fortes.\n"
                    "É só um aviso: não muda a nota."
                )
                self._table.item(i, self.COL_RISCO).setToolTip(risco_tip)
            # Tooltip de profundidade de liquidez (dias de listagens no
            # ritmo atual de negociacao)
            depth = r.get("liquidity_depth")
            if depth:
                cell_sd = self._table.item(i, self.COL_SD)
                if cell_sd is not None:
                    cell_sd.setToolTip(depth["label"])
            # Tooltip de z-score (desvio da media movel de 30d). Testado
            # como fator de score e descartado (drawdown ja' captura o
            # mesmo sinal, sem ganho); segue disponivel como dado bruto,
            # informativo, sem influenciar a nota.
            zs = r.get("zscore")
            if zs:
                cell_trend = self._table.item(i, self.COL_TREND)
                if cell_trend is not None:
                    _desvio = {
                        "extreme_low": "muito abaixo do normal",
                        "low": "abaixo do normal",
                        "neutral": "dentro do normal",
                        "high": "acima do normal",
                        "extreme_high": "muito acima do normal",
                    }.get(zs.get("band"), "perto do normal")
                    media = t.brl(zs.get("mean"))
                    cell_trend.setToolTip(
                        f"Preço {_desvio} para os últimos "
                        f"{zs['window_used']} dias (média {media}).\n"
                        "Não entra na nota — só mostra o quanto o preço "
                        "se afastou do normal."
                    )
            # Tooltip da confidence
            if dq:
                conf_tip = (
                    f"Confiança nos dados: {dq_label}\n"
                    f"Histórico: {dq_n} registros de preço\n"
                    f"Com pouco histórico a nota erra mais:\n"
                    f"use com cautela."
                )
                cell_conf = self._table.item(i, self.COL_CONFIDENCE)
                if cell_conf is not None:
                    cell_conf.setToolTip(conf_tip)
            # Tooltip explicando "~" quando order_book vem de outro wear
            if r.get("order_book_approx"):
                msg = (
                    "A Steam só mostra a fila de ofertas de um desgaste "
                    "do skin; este valor é de outro desgaste do mesmo "
                    "item. Use como aproximação."
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
        right_cols = {self.COL_PRECO, self.COL_JUSTO, self.COL_COMPRAR}
        center_cols = {
            self.COL_SINAL, self.COL_VEREDITO, self.COL_SPREAD,
            self.COL_BOOK, self.COL_TREND, self.COL_SD,
            self.COL_RISCO, self.COL_CONFIDENCE,
        }
        t.align_table_columns(self._table, right=right_cols, center=center_cols)
        self._table.setSortingEnabled(was_sorting)
        self._ajustar_colunas()

        # Aplica filtro de order book approx (so esconde, nunca mostra)
        self._apply_approx_filter()
        # Aplica filtro de baixa confiança (roda por ultimo para nao
        # ser sobrescrito pelo filtro de approx)
        hidden = self._apply_confidence_filter()

        # Stats
        if self._scan_results:
            scores = [r["score"] for r in self._scan_results]
            self._stat_count.set_value(str(len(self._scan_results)),
                                       accent=t.TEXT)
            self._stat_best.set_value(str(max(scores)),
                                      accent=t.POSITIVE)
            # accent explicito: o cartao nasce com "—" (cinza) e sem
            # accent o numero herdava o cinza.
            self._stat_avg.set_value(str(round(sum(scores)/len(scores))),
                                     accent=t.TEXT)
            breadth = signals.market_breadth(
                [r.get("trend_code", "") for r in self._scan_results])
            if breadth:
                breadth_accent = {
                    "up": t.POSITIVE, "down": t.DANGER,
                }.get(breadth["tone"], t.TEXT_MUTED)
                self._stat_breadth.set_value(
                    f"{breadth['pct_up']:.0f}% ↑ / {breadth['pct_down']:.0f}% ↓",
                    accent=breadth_accent)
                self._stat_breadth.setToolTip(
                    f"{self._stat_breadth_tooltip}\n\n{breadth['label']}")
        n = len(self._scan_results)
        self._set_base_status(n, hidden)
        # Busca ativa durante o repopulate: devolve a mensagem de busca.
        self._atualizar_status_busca()

    def _refresh_visibility(self) -> None:
        """Recalcula a visibilidade de TODAS as linhas.

        Antes cada filtro (baixa confiança, approx) rodava sozinho e
        zerava o que o vizinho tinha escondido com setRowHidden(False);
        a ordem no _populate é que segurava a composição. Com a busca
        textual no meio, três filtros só compõem num recalc único: cada
        filtro contribui "esconder", nenhum "mostra" sozinho.
        """
        if not hasattr(self, "_table"):
            return
        alvo = ((self._search_inp.text() or "").strip().lower()
                if hasattr(self, "_search_inp") else "")
        conf = (self._hide_low_conf_cb.isChecked()
                if hasattr(self, "_hide_low_conf_cb") else False)
        approx = (self._hide_approx_cb.isChecked()
                  if hasattr(self, "_hide_approx_cb") else False)
        faixa_alvo = (self._price_filter_cb.currentText()
                      if hasattr(self, "_price_filter_cb") else "Todos os preços")
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            nome = cell.text().lower() if cell else ""
            r = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            # A coluna mostra o nome LOCALIZADO ("Caixa Kilowatt"), mas o
            # usuario que conhece o nome da Steam digita "Kilowatt Case".
            # Casa com os dois: display e raw.
            raw = (r or {}).get("name", "").lower()
            busca = bool(alvo) and alvo not in nome and alvo not in raw
            dq = (r or {}).get("data_quality") or {}
            low = conf and dq.get("level", "none") in ("low", "very_low")
            aprox = approx and bool((r or {}).get("order_book_approx"))
            fora_da_faixa = False
            if faixa_alvo != "Todos os preços":
                banda = signals.price_level_band((r or {}).get("price"))
                fora_da_faixa = banda is None or banda[1] != faixa_alvo
            self._table.setRowHidden(
                row, busca or low or aprox or fora_da_faixa)

    def _apply_search_filter(self, _text: str) -> None:
        self._refresh_visibility()
        self._atualizar_status_busca()

    def _set_base_status(self, n: int, hidden: int = 0) -> None:
        """Mensagem do rodapé sem busca ativa (base pro estado limpo)."""
        base = f"{n} {'item analisado' if n == 1 else 'itens analisados'}"
        self._status_base = (
            f"{base} ({hidden} ocultos por baixa confiança)"
            if hidden else base)
        self._status.setText(self._status_base)

    def _atualizar_status_busca(self) -> None:
        """Rodapé com busca ativa; volta à base quando o campo limpa."""
        alvo = (self._search_inp.text() or "").strip()
        if not alvo:
            self._status.setText(getattr(self, "_status_base", ""))
            self._sem_match.setVisible(False)
            return
        visiveis = sum(1 for row in range(self._table.rowCount())
                       if not self._table.isRowHidden(row))
        self._sem_match.setVisible(
            visiveis == 0 and bool(self._scan_results))
        self._status.setText(
            f"{visiveis} de {len(self._scan_results)} itens • busca “{alvo}”")

    def _focar_busca(self) -> None:
        self._search_inp.setFocus()
        self._search_inp.selectAll()

    def _limpar_busca(self) -> None:
        if self._search_inp.text():
            self._search_inp.clear()  # textChanged cuida do resto
        else:
            self._search_inp.setFocus()

    def _apply_confidence_filter(self) -> int:
        """Aplica/remove esconder baixa confiança. Retorna # ocultas."""
        if not hasattr(self, "_hide_low_conf_cb"):
            return 0
        self._refresh_visibility()
        active = self._hide_low_conf_cb.isChecked()
        hidden = 0
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            r = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if not isinstance(r, dict):
                continue
            dq = r.get("data_quality") or {}
            level = dq.get("level", "none")
            if active and level in ("low", "very_low"):
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
        self._set_base_status(len(self._scan_results), hidden)
        self._atualizar_status_busca()

    def _apply_approx_filter(self) -> int:
        """Aplica esconder order book approx. Retorna # ocultas."""
        if not hasattr(self, "_hide_approx_cb"):
            return 0
        self._refresh_visibility()
        active = self._hide_approx_cb.isChecked()
        hidden = 0
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, self.COL_NAME)
            r = cell.data(Qt.ItemDataRole.UserRole) if cell else None
            if isinstance(r, dict) and active and r.get("order_book_approx"):
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

    def _on_price_filter_change(self, _text: str) -> None:
        from skinvault.settings import (
            load_settings as _ls, save_settings as _ss,
        )
        s = _ls()
        s["scanner_price_filter"] = self._price_filter_cb.currentText()
        _ss(s)
        self._refresh_visibility()
        self._atualizar_status_busca()

    def _on_progress(self, msg: str) -> None:
        if msg in ("FIM", "CANCELADO"):
            self._scanning = False
            self._scan_btn.setText("Escanear categoria")
            self._scan_btn.setToolTip(self._scan_tooltip)
            self._scan_btn.setEnabled(True)
            self._rank_btn.setEnabled(True)
            self._validate_btn.setEnabled(True)
            self._export_btn.setEnabled(True)
            self._loading.setVisible(False)
            self._sync_bar.setVisible(False)
            if msg == "CANCELADO":
                self._status.setText(
                    f"Scan cancelado: {len(self._scan_results)} itens coletados"
                )
            else:
                n = len(self._scan_results)
                total = getattr(self, "_scan_total_planned", 0)
                if n == 0 and total > 0:
                    # Categoria tinha itens (total>0) mas NENHUM voltou --
                    # a causa dominante e' a Steam limitando as consultas
                    # (429 em priceoverview/SSR), nao ausencia de listagem.
                    self._status.setText(
                        f"Scan concluído: 0 de {total} itens — a Steam "
                        "pode estar limitando as consultas agora. Tente "
                        "novamente em alguns minutos."
                    )
                else:
                    self._status.setText(
                        f"Scan concluido: {n} itens"
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
        act_why = menu.addAction("Por que essa nota?")
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
            "Item", "Nota", "Avaliação", "Preço", "Preço típico",
            "Diferença compra/venda", "Fila de ofertas", "Tendência",
            "Procura × Oferta", "Confiança nos dados", "Caixa/coleção",
            "Risco",
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
                        _CONF_CSV.get(dq.get("level", ""),
                                      dq.get("level", "")),
                        case_label,
                        _RISCO_CSV.get(risk, risk),
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
                    except Exception as e:
                        print(f"WARNING: scanner price_history({name}) failed: {e}",
                              file=sys.stderr)
                        price_history = None
                    if price_history:
                        try:
                            samples = backtest.simulate_item(
                                name, price_history,
                            )
                        except Exception as e:
                            print(f"WARNING: scanner simulate({name}) failed: {e}",
                                  file=sys.stderr)
                            samples = []
                        if samples:
                            bridge.samples_ready.emit(samples)
                    # Rate-limit so' em fetch (cache hit nao bate Steam)
                    if not hit:
                        time.sleep(steam_api.RATE_LIMIT_DELAY_S)
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
