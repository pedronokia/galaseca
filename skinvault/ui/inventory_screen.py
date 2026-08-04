"""Tela — Inventário.

Saiu de dentro da "Minha Conta" em 28/07/2026. La' ele dividia a janela
com perfil, quatro cartoes de valor, cinco de desempenho e um grafico --
sobrava rodape pra o conteudo que da' nome a tela. Como aba propria, usa a
janela inteira.

A tela nao avalia nada por conta propria: recebe as linhas ja' avaliadas
pela AccountScreen, que e' quem tem o PriceWorker. Duplicar a avaliacao
seria dobrar o custo de rede num endpoint que ja' e' rate-limited.

Duas visoes, de proposito: a grade serve pra RECONHECER item pelo icone
(como a Steam mostra), a tabela pra conferir numero.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import history, markets, portfolio, reports
from skinvault.ui import theme as t
from skinvault.ui.components import (
    EmptyState,
    FormRow,
    ItemDetailDrawer,
    LoadingState,
    PageHeader,
    SegmentedControl,
    SortableItem,
    Toast,
    ViewModeSwitcher,
    score_table_item,
)
from skinvault.ui._price_worker import IconWorker
from skinvault.ui.exporter import build_export_menu, save_export
from skinvault.ui.inventory_grid import InventoryGrid, InventoryTile


class _CostDialog(QDialog):
    """Dialog para definir o custo (unitario) de uma posicao.

    Custo e' o dado que falta pro P&L existir -- posicao de sync Steam
    grava cost=0.0 pra "nao sei". O dialogo aceita os formatos do
    `_parse_brl` ("199,90", "1.234,50") e mostra o ponto de equilibrio
    da Steam ao vivo, pra nao obrigar o usuario a lembrar dos 15%.
    """

    def __init__(self, name: str, quantity: int = 1,
                 current_cost: float | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Definir custo")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._cost: float | None = None
        self._build(name, quantity, current_cost)

    def _build(self, name: str, quantity: int,
               current_cost: float | None) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        nome = QLabel(name)
        nome.setStyleSheet(t.label_body_muted())
        nome.setWordWrap(True)
        layout.addWidget(nome)

        caption = QLabel(
            f"Preço unitário — {quantity} item(ns) no total.")
        caption.setStyleSheet(t.label_caption())
        caption.setWordWrap(True)
        layout.addWidget(caption)

        self._inp = QLineEdit()
        if current_cost is not None:
            self._inp.setText(f"{current_cost:g}".replace(".", ","))
        self._inp.setPlaceholderText("ex.: 199,90 — zero = drop")
        self._inp.setStyleSheet(t.input_style())
        self._inp.textChanged.connect(self._atualizar_hint)
        layout.addWidget(FormRow("Custo por item (R$):", self._inp))

        # Ponto de equilibrio da Steam ao vivo. A taxa incide sobre o valor
        # do VENDEDOR: listar por cost*1,15 devolve o cost de volta. Sem
        # esse numero o usuario le' o custo no vacuo e decide no chute.
        self._be_label = QLabel("")
        self._be_label.setStyleSheet(t.label_caption())
        self._be_label.setWordWrap(True)
        layout.addWidget(self._be_label)

        self._err_label = QLabel("")
        self._err_label.setStyleSheet(
            f"color: {t.DANGER}; font-size: {t.FS_MUTED};")
        self._err_label.setWordWrap(True)
        self._err_label.setVisible(False)
        layout.addWidget(self._err_label)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.setStyleSheet(t.btn_ghost())
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setToolTip("Fecha sem alterar o custo.")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Salvar custo")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setToolTip("Grava o custo e reavalia o item.")
        ok.clicked.connect(self._on_ok)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        self._atualizar_hint()
        self._inp.setFocus()

    def _parse(self) -> float | None:
        try:
            v = portfolio._parse_brl(self._inp.text())
        except ValueError:
            return None
        if v < 0:
            return None
        return v

    def _atualizar_hint(self) -> None:
        v = self._parse()
        if v is None:
            self._be_label.setText("")
            return
        if v == 0:
            self._be_label.setText(
                "Custo zero (drop): qualquer venda é lucro.")
            return
        be = portfolio.break_even_price(v)
        self._be_label.setText(
            f"Para empatar na Steam, venda por {t.brl(be)} "
            f"({t.brl(be - v)} acima do custo — 15% de taxa).")

    def _on_ok(self) -> None:
        v = self._parse()
        if v is None:
            self._err_label.setText(
                "Custo inválido — use números, ex.: 199,90 (ou 0 para drop).")
            self._err_label.setVisible(True)
            self._inp.setFocus()
            self._inp.selectAll()
            return
        self._cost = round(v, 2)
        self.accept()

    def cost(self) -> float | None:
        return self._cost


class InventoryScreen(QWidget):
    """Grade + tabela do inventario, com filtro."""

    # Reordenada em 2026-07-30. A versao anterior tinha 5 colunas de
    # dinheiro derivadas SO' do preco da Steam -- com o priceoverview em
    # 429 viravam cinco travessoes lado a lado, metade da largura da tela
    # mostrando nada, enquanto as cotacoes de fora (que existem e estao em
    # cache) nao apareciam em lugar nenhum da tabela.
    # "Subtotal" saiu: e' preco x qtd, derivavel, e o total ja' esta' no
    # rodape.
    COL_NAME = 0
    COL_QTY = 1
    COL_PRICE = 2
    COL_RECEIVED = 3
    COL_BEST_OUT = 4
    COL_WHERE = 5
    COL_COST = 6
    COL_PNL = 7
    COL_SCORE = 8
    COL_ORIGIN = 9

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list = []
        self._positions: list = []
        self._mercados: dict = {}
        self._icon_worker = IconWorker(self)
        self._icon_worker.done.connect(self._on_icons_ready)
        self._build()

    # Pedido de reavaliacao depois que o custo muda (o PriceWorker vive na
    # AccountScreen; quem consome e' o ScreenRouter, via refresh()).
    request_reeval = pyqtSignal()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(12)

        root.addWidget(PageHeader(
            "Inventário",
            "Cada item avaliado nos dois mercados: saldo Steam e dinheiro real.",
        ))

        linha = QHBoxLayout()
        linha.setSpacing(t.SPACE_SM)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filtrar por nome do item...")
        self._filter.setClearButtonEnabled(True)
        self._filter.setStyleSheet(t.input_style())
        self._filter.textChanged.connect(self._apply_filter)
        linha.addWidget(self._filter, 1)

        # Alternador de visao em vez de um botao que troca de rotulo: com
        # "Ver em tabela" o usuario le' o nome da visao em que NAO esta', e
        # nada indica quantas opcoes existem. O segmentado mostra as duas e
        # marca a atual. ViewModeSwitcher formaliza o par grid/table que
        # essa tela criava na mao -- Grade ja' nasce marcada.
        self._view_seg = ViewModeSwitcher()
        from skinvault.settings import load_settings as _ls
        self._view_inicial = (
            "table" if _ls().get("inventory_view") == "table" else "grid")
        self._view_seg.setToolTip(
            "Grade de ícones (estilo Steam) ou tabela detalhada.")
        # Ordenacao: a grade era sempre por valor. Quem procura "aquela
        # caixa" quer alfabetica; quem olha lote quer por quantidade.
        self._ordem_seg = SegmentedControl()
        self._ordem_seg.add("valor", "Valor")
        self._ordem_seg.add("nome", "Nome")
        self._ordem_seg.add("qtd", "Qtd")
        self._ordem_seg.setToolTip(
            "Ordem dos cards. “Valor” usa o total do lote, não o preço "
            "unitário:\n21 caixas de R$ 1 pesam mais que uma skin de R$ 15.\n"
            "Clicar na chave já ativa alterna crescente/decrescente.")
        # Lambda, nao `self._grid.set_order`: a grade so' e' construida
        # adiante neste mesmo _build, e ligar o metodo agora explodiria.
        self._ordem_seg.segment_changed.connect(self._on_ordem)
        linha.addWidget(self._ordem_seg, 0)

        self._view_seg.segment_changed.connect(self._on_view_segment)
        linha.addWidget(self._view_seg, 0)

        # Exportar inventário + relatório (CSV/JSON/HTML). Ghost: é
        # leitura/ação auxiliar; o destaque da tela continua o filtro.
        self._export_btn = QPushButton("Exportar")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setStyleSheet(
            t.btn_ghost(padding="8px 14px", fs=t.FS_BODY))
        self._export_btn.setToolTip(
            "Exporta o inventário avaliado: CSV, JSON ou relatório HTML\n"
            "print-friendly com o histórico de valor da carteira.")
        self._export_btn.clicked.connect(self._on_export_menu)
        linha.addWidget(self._export_btn, 0)
        root.addLayout(linha)
        # NAO selecionar aqui: select() emite segment_changed, e o handler
        # _on_view_segment mexe em self._views -- que so' nasce adiante neste
        # _build. O AttributeError dentro do emit aborta o processo em PyQt6
        # (o teste passa porque mocka settings pra grid e nao entra aqui;
        # o script de screenshots usava settings reais e morria).
        # A escolha persistida e' aplicada no fim do _build (ver
        # _apply_view_pref).

        # Ctrl+F e' o gesto que todo mundo ja' tem no dedo pra buscar; sem
        # ele o caminho era achar o campo com o mouse. Esc limpa -- filtro
        # esquecido ligado faz o inventario parecer que perdeu itens.
        # Kwarg `activated=` no construtor nao funciona em toda versao
        # (AGENTS.md #8).
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            self._focar_filtro)
        QShortcut(QKeySequence("Esc"), self).activated.connect(
            self._limpar_filtro)

        self._grid = InventoryGrid(columns=8)
        self._atualizar_ordem_labels()
        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels([
            "Item", "Qtd", "Anúncio Steam", "Recebe (saldo)",
            "Melhor fora", "Onde", "Custo", "P&L", "Score", "Origem",
        ])
        _tips = {
            self.COL_PRICE: (
                "Preço de anúncio na Steam — o que o comprador paga."),
            self.COL_RECEIVED: (
                "O que sobra pra você em SALDO Steam, já descontada a taxa.\n"
                "A taxa incide sobre o valor do vendedor: você anuncia por "
                "R$ 115 e recebe R$ 100."),
            self.COL_BEST_OUT: (
                "Melhor líquido entre as plataformas de fora, em DINHEIRO "
                "de verdade.\n"
                "Já desconta a taxa de cada uma (5% a 12%) — por isso o "
                "maior preço anunciado nem sempre é quem paga mais."),
            self.COL_WHERE: "Plataforma que paga o melhor líquido.",
            self.COL_COST: (
                "Quanto você pagou pelo item (ou zero se foi drop).\n"
                "Duplo clique na coluna para definir.\n"
                "É daqui que o P&L sai: sem custo, não há lucro que se "
                "possa afirmar."),
            self.COL_SCORE: (
                "Score do item (0-100), calculado pelo botão 'Validar score' "
                "na tela Minha Conta.\n"
                "Fica âmbar quando está desatualizado. '—' significa que "
                "ainda não foi calculado."),
            self.COL_ORIGIN: (
                "Se o item veio da sincronização com a Steam ou foi "
                "lançado manualmente.\n"
                "Só aparece quando o inventário mistura as duas origens."),
        }
        for col, tip in _tips.items():
            cab = self._table.horizontalHeaderItem(col)
            if cab is not None:
                cab.setToolTip(tip)
        from skinvault.settings import load_settings as _ls
        t.configure_table(
            self._table, density=_ls().get("table_density", "standard"))
        # Custo se edita na tabela: duplo clique na coluna ou menu de
        # contexto na linha. A grade so' mostra o custo, nao edita -- o
        # reconhecimento por icone nao e' o momento de digitar numero.
        self._table.cellDoubleClicked.connect(self._on_cost_double_click)
        self._table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, self.COL_ORIGIN + 1):
            hh.setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents)

        # Corpo: filtros a' esquerda + visao a' direita, como o Mercado da
        # Comunidade. As categorias saem de `portfolio.classify_item`, as
        # mesmas do cartao de composicao da Conta.
        corpo = QHBoxLayout()
        corpo.setSpacing(t.SPACE_LG)

        self._cat_panel = QWidget()
        self._cat_panel.setFixedWidth(190)
        cat_lay = QVBoxLayout(self._cat_panel)
        cat_lay.setContentsMargins(0, 0, 0, 0)
        cat_lay.setSpacing(2)
        cat_titulo = QLabel("Filtros")
        cat_titulo.setStyleSheet(t.label_section())
        cat_lay.addWidget(cat_titulo)
        self._cat_botoes: dict = {}
        self._cat_lay = cat_lay
        cat_lay.addStretch(1)
        # Escondido ate' haver item: senao a tela vazia mostra o titulo
        # "Filtros" com nada embaixo. `_montar_categorias` reexibe.
        self._cat_panel.setVisible(False)
        corpo.addWidget(self._cat_panel, 0)

        self._views = QStackedWidget()
        self._views.addWidget(self._grid)
        self._views.addWidget(self._table)
        corpo.addWidget(self._views, 1)

        # A Grade ja' tem o proprio painel de detalhe fixo (InventoryTile
        # + ItemDetailPanel). A Tabela nao tinha NENHUMA forma de ver
        # detalhe de um item alem das celulas da propria linha -- o
        # drawer cobre exatamente essa visao.
        self._drawer = ItemDetailDrawer(self)
        self._table.cellClicked.connect(self._on_table_row_clicked)
        corpo.addWidget(self._drawer, 0)

        root.addLayout(corpo, 1)

        # Filtro sem resultado deixava a tela em branco: indistinguivel de
        # inventario vazio ou de falha ao carregar.
        self._sem_match = QLabel(
            "Nenhum item casa com o filtro. Limpe o campo pra ver todos.")
        self._sem_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sem_match.setStyleSheet(t.label_caption())
        self._sem_match.setVisible(False)
        root.addWidget(self._sem_match)

        self._empty = EmptyState(
            icon="◇",
            title="Inventário vazio",
            subtitle=("Sincronize com a Steam na tela Minha Conta\n"
                       "pra puxar seus itens."),
        )
        root.addWidget(self._empty, 1)

        # Enquanto a AccountScreen avalia, nem a grade nem o "vazio" valem:
        # dizer "sincronize com a Steam" pra quem TEM itens e' so' esperar
        # e' mentir sobre a causa. Sob rate limit a avaliacao chega a levar
        # minutos (backoff de 14s por item), entao o estado intermediario e'
        # o que o usuario mais ve'.
        self._loading = LoadingState("Avaliando inventário…")
        root.addWidget(self._loading, 1)

        # Default e' o empty state, nao o loading: sem sessao a AccountScreen
        # nunca chama refresh(), e a tela ficaria em branco pra sempre.
        self._views.setVisible(False)
        self._empty.setVisible(True)
        self._loading.setVisible(False)

        self._status = QLabel("")
        self._status.setStyleSheet(t.label_caption())
        root.addWidget(self._status)

        self._apply_view_pref()

    def _apply_view_pref(self) -> None:
        """Aplica a visao persistida em settings.json.

        Tem que rodar DEPOIS de self._views existir: _on_view_segment le
        currentIndex do stack, e select() emite segment_changed
        sincronamente. Chama-la antes do fim do _build aborta o processo
        (AttributeError num slot PyQt6 vira abort nativo, medido em
        2026-07-31).
        """
        if getattr(self, "_view_inicial", "grid") == "table":
            self._view_seg.select("table")

    # ── dados ─────────────────────────────────────────────

    def set_loading(self, done: int = 0, total: int = 0) -> None:
        """Avaliacao em andamento na AccountScreen.

        Só entra no estado de carregamento quando ainda NAO ha' dados: uma
        reavaliacao com a tabela ja' preenchida nao deve apagar o que o
        usuario esta' lendo.
        """
        if self._rows:
            if total:
                self._status.setText(
                    f"{len(self._rows)} item(ns) • reavaliando {done}/{total}…")
            return
        self._empty.setVisible(False)
        # Esqueleto na grade em vez de um spinner num vazio: sob rate limit
        # a avaliacao leva minutos, e o fantasma ja' diz quanta coisa vem e
        # onde cada parte vai cair -- a tela nao "salta" quando os dados
        # chegam. So' vale se o total for conhecido; sem ele, o spinner
        # continua sendo a leitura honesta.
        if total and self._views.currentIndex() == 0:
            self._grid.set_skeleton(total)
            self._views.setVisible(True)
            self._loading.setVisible(False)
            self._status.setText(f"Avaliando inventário… {done}/{total}")
            return
        self._views.setVisible(False)
        self._loading.setVisible(True)
        self._loading.set_label(
            f"Avaliando inventário… {done}/{total}" if total
            else "Avaliando inventário…"
        )
        self._status.setText("")

    def set_data(self, rows: list, positions: list,
                 rate_limited: bool = False) -> None:
        """Recebe as linhas ja' avaliadas pela AccountScreen.

        `rate_limited` distingue "estes itens nao tem preco" de "a Steam
        recusou as consultas" -- na tabela os dois viram travessao igual.
        """
        self._rows = list(rows or [])
        self._positions = list(positions or [])
        # Cotacoes de fora resolvidas UMA vez e compartilhadas entre a
        # grade e a tabela. Cada dicionario tem ~25 mil entradas; resolver
        # por tela releria os tres duas vezes.
        self._mercados = self._resolver_mercados()
        self._listados = self._carregar_listados()
        tem = bool(self._rows)
        self._loading.setVisible(False)
        self._views.setVisible(tem)
        self._empty.setVisible(not tem)
        if not tem:
            self._status.setText(
                "A Steam limitou as consultas de preço. Tente de novo daqui a "
                "alguns minutos." if rate_limited else ""
            )
            return
        self._populate_grid()
        self._montar_categorias()
        self._populate_table()
        sem_preco = sum(1 for r in self._rows if r.get("price") is None)
        # O rodape dizia so' "31 item(ns)" com R$ 1.374 de cotacao na tela.
        # A soma e' a informacao que o usuario quer -- quanto vale isto.
        total = self._resumo_de_valor()
        if rate_limited:
            self._rodape_base = (
                f"{total} • a Steam limitou as consultas; "
                f"{sem_preco} sem preço agora (volta sozinho)"
            )
        else:
            self._rodape_base = total
        self._status.setText(self._rodape_base)
        self._apply_filter(self._filter.text())
        # Icone e' host separado do preco: vale tentar mesmo sob rate limit.
        self._icon_worker.start(
            [p.get("icon") for p in self._positions] +
            [r.get("icon") for r in self._rows]
        )

    def _resumo_de_valor(self) -> str:
        """"31 itens • R$ 1.374,18 vendendo fora • R$ X em saldo Steam".

        Os dois totais existem separados de proposito: saldo Steam nao vira
        dinheiro (a Steam pede ~36% a mais justamente por isso), entao
        somar os dois num numero so' seria inventar um patrimonio que nao
        existe em lugar nenhum.
        """
        n = len(self._rows)
        partes = [f"{n} {'item' if n == 1 else 'itens'}"]

        fora = 0.0
        tem_fora = False
        from collections import Counter
        por_plataforma: Counter = Counter()
        for r in self._rows:
            mercados = self._mercados.get(r.get("name") or "") or []
            if mercados:
                tem_fora = True
                fora += mercados[0]["net_brl"] * (r.get("quantity") or 1)
                por_plataforma[mercados[0]["source"]] += 1
        if tem_fora:
            partes.append(f"{t.brl(fora)} vendendo fora (dinheiro)")
            # O total de fora e' a soma do MELHOR liquido item a item, e o
            # melhor nem sempre e' a mesma plataforma. Dizer qual lidera
            # evita ler o total como "e' tudo num lugar so'".
            if por_plataforma:
                nome, quantos = por_plataforma.most_common(1)[0]
                rotulo = InventoryTile._NOME_MERCADO.get(nome, nome)
                partes.append(
                    f"{rotulo} paga mais em {quantos} de "
                    f"{sum(por_plataforma.values())}")

        saldo = sum((r.get("net_if_sold") or 0) * 1
                    for r in self._rows if r.get("net_if_sold"))
        if saldo:
            partes.append(f"{t.brl(saldo)} em saldo Steam")
        return " • ".join(partes)

    def _on_export_menu(self) -> None:
        if not self._rows:
            self._status.setText("Nada para exportar — inventário vazio.")
            return
        menu = build_export_menu(
            self._export_btn,
            [("Exportar CSV", lambda: self._do_export("csv")),
             ("Exportar JSON", lambda: self._do_export("json")),
             ("Exportar relatório HTML",
              lambda: self._do_export("html"))],
        )
        menu.exec(self._export_btn.mapToGlobal(
            self._export_btn.rect().bottomLeft()))

    def _do_export(self, kind: str) -> None:
        if kind == "csv":
            conteudo = reports.inventory_csv(
                self._rows, self._positions, self._mercados)
        elif kind == "json":
            conteudo = reports.inventory_json(
                self._rows, self._positions, self._mercados)
        else:
            conteudo = reports.html_report(
                self._rows, history.load_history(), None,
                self._positions, self._mercados)
        path, erro = save_export(self, "inventario", kind, conteudo)
        if erro:
            self._status.setText(f"Erro ao exportar: {erro}")
        elif path:
            self._status.setText(f"Exportado: {path}")

    def _on_icons_ready(self, quantos: int) -> None:
        """Repinta a grade com os icones que acabaram de chegar.

        Só a grade -- a tabela nao usa icone, e repintar ela perderia
        ordenacao e selecao do usuario a' toa.
        """
        if quantos > 0 and self._rows:
            self._populate_grid()

    def _resolver_mercados(self) -> dict:
        """{nome: [mercados ordenados pelo liquido]} pra todas as linhas.

        `cached_market` so' bate na rede em cache miss (TTL 12h), entao o
        caminho normal e' local. Falha de rede deixa tudo vazio e a tela
        mostra "sem cotação" em vez de inventar numero.
        """
        cotacoes: dict = {}
        fx = 0.0
        try:
            fx = markets.usd_brl()
            for fonte in markets.MARKET_FEES:
                cotacoes[fonte] = markets.cached_market(fonte)
        except Exception:
            return {}
        out = {}
        for r in self._rows:
            nome = r.get("name") or ""
            if not nome:
                continue
            out[nome] = self._mercados_do_item(
                nome, r.get("price"), cotacoes, fx)
        return out

    def _carregar_listados(self) -> set:
        """Nomes com pelo menos uma listagem ativa no Mercado da Steam.

        Aproximacao por NOME, nao por asset individual: `sync.py` guarda
        `active_listings.json` sem asset_id (extrai de results_html, ver
        sync._extract_listings_from_response), entao 3 unidades do mesmo
        item com so' 1 anunciada aparecem como "No Mercado" as tres. Mesma
        granularidade que o resto da tela ja usa -- P&L e preco tambem sao
        por nome agrupado, nao por unidade.
        """
        try:
            from skinvault import sync
            listagens = sync.load_active_listings()
        except Exception:
            return set()
        return {lst.get("name") for lst in listagens if lst.get("name")}

    def _populate_grid(self) -> None:
        """Alimenta a grade com a avaliacao em TODAS as plataformas."""
        from skinvault.localization import localize_name as _ln
        itens = []
        for i, r in enumerate(self._rows):
            pos = self._positions[i] if i < len(self._positions) else {}
            nome = r.get("name") or ""
            preco_steam = r.get("price")
            mercados = self._mercados.get(nome) or []
            melhor = mercados[0] if mercados else None
            # Custo so' entra quando e' CONHECIDO. O sync grava cost=0.0
            # pra "nao sei", e tratar isso como "custou zero" faria o
            # painel prometer lucro que nao existe.
            custo = (pos.get("cost")
                     if portfolio.has_cost_basis(pos) else None)
            itens.append({
                "name": _ln(nome) or nome,
                "raw_name": nome,
                "qty": r.get("quantity") or 1,
                "icon": pos.get("icon") or r.get("icon"),
                "type": pos.get("type") or r.get("type") or "",
                "steam_list": preco_steam,
                "cost": custo,
                # `price` vem de `get_market_price`, que devolve a MENOR
                # listagem. Serve de alvo e de referencia pra venda
                # rapida ao mesmo tempo -- a mediana exigiria
                # `get_market_overview`, que e' o endpoint mais racionado.
                # Quando os dois coincidem, "vender hoje" fica um centavo
                # abaixo do alvo, que e' o que a pratica faz mesmo.
                "guidance": portfolio.sell_guidance(
                    current_price=preco_steam, cost=custo,
                    lowest=preco_steam),
                "steam_net": r.get("net_if_sold"),
                # `market_net` fica sendo o do MELHOR mercado: e' o que o
                # usuario receberia de fato escolhendo bem.
                "market_net": melhor["net_brl"] if melhor else None,
                "premium_pct": melhor["premium_pct"] if melhor else None,
                "mercados": mercados,
                # O score ja' vivia na position (gravado pelo "Validar
                # score") e so' aparecia numa coluna da tabela -- quem usa
                # a grade nunca o via.
                "score": pos.get("current_score"),
                "score_ts": pos.get("score_ts"),
                "pnl": r.get("pnl"),
                "listed": nome in self._listados,
            })
        self._grid.set_items(itens)

    @staticmethod
    def _mercados_do_item(nome: str, preco_steam, cotacoes: dict,
                          fx: float) -> list:
        """Igual a `markets.compare_all`, mas com as cotacoes ja' em maos.

        Chamar `compare_all` por item releria os 3 dicionarios de ~25 mil
        entradas 31 vezes; aqui eles sao carregados uma vez pelo chamador.
        """
        if fx <= 0:
            return []
        out = []
        for fonte, precos in cotacoes.items():
            usd = precos.get(nome)
            if not usd or usd <= 0:
                continue
            taxa = markets.MARKET_FEES.get(fonte, 0.12)
            bruto = usd * fx
            out.append({
                "source": fonte,
                "gross_brl": round(bruto, 2),
                "net_brl": round(bruto * (1 - taxa), 2),
                "fee": taxa,
                "premium_pct": (round((preco_steam / bruto - 1) * 100, 1)
                                if preco_steam and preco_steam > 0 else None),
            })
        out.sort(key=lambda x: -x["net_brl"])
        return out

    def _populate_table(self) -> None:
        from skinvault.localization import localize_name as _ln
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for i, r in enumerate(self._rows):
            self._table.insertRow(i)
            pos = self._positions[i] if i < len(self._positions) else {}
            origem = ("Steam" if pos.get("source") == "steam_sync"
                      else "Manual")
            pnl = r.get("pnl")
            # Custo com has_cost_basis: sync grava cost=0.0 pra "nao sei",
            # e exibir "R$ 0,00" mentiria que o item nao custou nada (a
            # regra da grade, linha ~382, e' a mesma).
            tem_custo = portfolio.has_cost_basis(pos)
            custo = pos.get("cost") if tem_custo else None
            # 3o campo = chave de ordenacao (None = ordena pelo texto).
            # Sem ela, moeda ordenava como string: R$ 16,49 caia abaixo de
            # R$ 9,66 -- ver components.SortableItem.
            # A cotacao de fora nao depende da Steam. Com o priceoverview
            # em 429, e' a UNICA coluna de dinheiro com valor de verdade --
            # antes ela nao existia na tabela e a tela virava uma parede de
            # travessoes com R$ 1.374 de cotacao escondidos.
            mercados = self._mercados.get(r.get("name") or "") or []
            melhor = mercados[0] if mercados else None
            onde = (InventoryTile._NOME_MERCADO.get(
                melhor["source"], melhor["source"]) if melhor else "—")
            celulas = [
                (self.COL_NAME, _ln(r.get("name") or "") or "—", None),
                (self.COL_QTY, str(r.get("quantity") or 1),
                 r.get("quantity") or 1),
                (self.COL_PRICE, t.brl(r.get("price")), r.get("price")),
                (self.COL_RECEIVED, t.brl(r.get("net_if_sold")),
                 r.get("net_if_sold")),
                (self.COL_BEST_OUT,
                 t.brl(melhor["net_brl"]) if melhor else "—",
                 melhor["net_brl"] if melhor else None),
                (self.COL_WHERE, onde, None),
                (self.COL_COST,
                 t.brl(custo) if tem_custo else "—",
                 custo if tem_custo else None),
                (self.COL_PNL, t.brl(pnl) if pnl is not None else "—", pnl),
                (self.COL_ORIGIN, origem, None),
            ]
            for col, val, chave in celulas:
                item = (QTableWidgetItem(val) if chave is None
                        else SortableItem(val, chave))
                if col == self.COL_NAME:
                    # Nome cru no UserRole: a tabela e' sortable, entao a
                    # linha visual N raramente e' self._rows[N] depois de
                    # ordenar por qualquer coluna. O drawer (e qualquer
                    # acao futura por linha) tem que casar pelo dado real
                    # da celula, nao pelo indice de insercao.
                    item.setData(Qt.ItemDataRole.UserRole, r.get("name") or "")
                if col == self.COL_PNL and pnl is not None:
                    item.setForeground(QBrush(QColor(
                        t.POSITIVE if pnl >= 0 else t.DANGER)))
                elif col == self.COL_BEST_OUT and melhor:
                    item.setForeground(QBrush(QColor(t.POSITIVE)))
                elif col == self.COL_WHERE and melhor:
                    item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
                elif col == self.COL_COST and tem_custo:
                    item.setForeground(QBrush(QColor(t.TEXT_MUTED)))
                elif col == self.COL_ORIGIN and origem == "Steam":
                    item.setForeground(QBrush(QColor(t.STEAM_BLUE)))
                if col != self.COL_NAME:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(i, col, item)

            # O score vem persistido na position pelo "Validar score" da tela
            # Minha Conta -- nao ha' recalculo nem rede aqui. Uma linha sem
            # score (item novo, ou validacao nunca rodada) mostra travessao.
            score_item = score_table_item(
                pos.get("current_score"), pos.get("score_ts"))
            score_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, self.COL_SCORE, score_item)
        # 31 linhas 100% "Steam" nao informa nada, so' ocupa espaco. So'
        # vale mostrar a coluna quando o inventario de fato mistura origens.
        origens = {
            "Steam" if p.get("source") == "steam_sync" else "Manual"
            for p in self._positions
        }
        self._table.setColumnHidden(self.COL_ORIGIN, len(origens) <= 1)
        self._table.setSortingEnabled(True)

    # ── interacao ─────────────────────────────────────────

    def _montar_categorias(self) -> None:
        """(Re)constroi os botoes de categoria a partir do que ha' na grade.

        Reconstroi em vez de atualizar: as categorias mudam quando o
        inventario muda, e manter um botao de categoria que ficou sem item
        levaria a um filtro que nao devolve nada.
        """
        for b in self._cat_botoes.values():
            b.setParent(None)
            b.deleteLater()
        self._cat_botoes = {}
        cats = self._grid.categorias()
        if not cats:
            self._cat_panel.setVisible(False)
            return
        self._cat_panel.setVisible(True)
        total = sum(n for _, n in cats)
        for chave, rotulo, n in [(None, "Todos", total)] + [
                (c, c, n) for c, n in cats]:
            btn = self._botao_categoria(rotulo, n, chave is None)
            btn.clicked.connect(
                lambda _=False, c=chave: self._on_categoria(c))
            # antes do stretch final, senao os botoes vao pro rodape
            self._cat_lay.insertWidget(self._cat_lay.count() - 1, btn)
            self._cat_botoes[chave] = btn

    @staticmethod
    def _botao_categoria(rotulo: str, n: int, marcado: bool) -> QPushButton:
        """Linha de filtro: rotulo a' esquerda, contagem a' direita.

        Com o texto num `setText` unico, alinhar a contagem exigiria contar
        espacos -- e a coluna saia irregular, porque a fonte nao e'
        monoespacada. Dois QLabels num layout resolvem de verdade.

        Os rotulos ficam transparentes ao mouse: sem isso o clique morre no
        label e o botao nunca dispara.
        """
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
        btn.setChecked(marcado)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setMinimumHeight(30)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" border-radius: {t.RADIUS_SM}px; padding: 0 10px;"
            f" text-align: left; }}"
            f"QPushButton:hover {{ background: {t.SURFACE}; }}"
            f"QPushButton:pressed {{ background: {t.SURFACE_HOV}; }}"
            f"QPushButton:checked {{ background: {t.SURFACE}; }}"
            f"QPushButton:focus {{ background: {t.SURFACE}; }}"
        )
        lay = QHBoxLayout(btn)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(8)
        cor = t.TEXT if marcado else t.TEXT_MUTED
        peso = "600" if marcado else "500"
        lbl = QLabel(rotulo)
        lbl.setStyleSheet(
            f"color: {cor}; font-size: {t.FS_BODY}; font-weight: {peso};"
            f" font-family: {t.FONT_FAMILY}; background: transparent;")
        cnt = QLabel(str(n))
        cnt.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY}; background: transparent;")
        for w in (lbl, cnt):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(lbl)
        lay.addStretch(1)
        lay.addWidget(cnt)
        btn._rotulo, btn._contagem = lbl, cnt
        return btn

    def _on_categoria(self, categoria) -> None:
        self._grid.set_category(categoria)
        self._apply_filter(self._filter.text())
        # O `:checked` do stylesheet pinta o BOTAO, nao os QLabels dentro
        # dele -- sem repintar aqui, a categoria ativa ficava com a mesma
        # cor das outras e nao dava pra saber qual estava valendo.
        for chave, btn in self._cat_botoes.items():
            ativo = chave == categoria
            btn._rotulo.setStyleSheet(
                f"color: {t.TEXT if ativo else t.TEXT_MUTED};"
                f" font-size: {t.FS_BODY};"
                f" font-weight: {'600' if ativo else '500'};"
                f" font-family: {t.FONT_FAMILY}; background: transparent;")

    def _focar_filtro(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()

    def _on_cost_double_click(self, row: int, col: int) -> None:
        if col == self.COL_COST:
            self._editar_custo_linha(row)

    def _on_table_row_clicked(self, row: int, _col: int) -> None:
        """Abre o drawer com o resumo da linha clicada.

        So' clique -- duplo clique na coluna Custo continua abrindo o
        editor (_on_cost_double_click), sinal separado, sem conflito.

        NAO indexa self._rows[row]: a tabela e' sortable (configure_table
        liga setSortingEnabled), entao a linha visual `row` so' bate com
        self._rows na ordem de insercao original -- ordenar por qualquer
        coluna (inclusive o duplo-clique em cabecalho) desalinha os dois e
        o drawer abriria com o item errado (visto na validacao manual: 1a
        linha visivel era "XM1014" e o drawer mostrou "AK-47"). Busca pelo
        nome cru guardado no UserRole da propria celula clicada.
        """
        cell = self._table.item(row, self.COL_NAME)
        if cell is None:
            return
        raw = cell.data(Qt.ItemDataRole.UserRole) or ""
        idx = next((i for i, r in enumerate(self._rows)
                    if (r.get("name") or "") == raw), None)
        if idx is None:
            return
        from skinvault.localization import localize_name as _ln
        r = self._rows[idx]
        pos = self._positions[idx] if idx < len(self._positions) else {}
        mercados = self._mercados.get(raw) or []
        self._drawer.show_item({
            "name": _ln(raw) or raw,
            "raw_name": raw,
            "icon": pos.get("icon") or r.get("icon"),
            "price": r.get("price"),
            "net_if_sold": r.get("net_if_sold"),
            "melhor_fora": mercados[0] if mercados else None,
            "pnl": r.get("pnl"),
            "listed": raw in self._listados,
        })

    def _on_context_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        if row >= len(self._rows):
            return
        menu = QMenu(self._table)
        acao = menu.addAction("Definir custo…")
        acao.setToolTip(
            "Quanto você pagou pelo item (ou zero se foi drop).\n"
            "É daqui que o P&L sai.")
        if menu.exec(self._table.viewport().mapToGlobal(pos)) == acao:
            self._editar_custo_linha(row)

    def _editar_custo_linha(self, row: int) -> None:
        """Abre o dialogo de custo pra linha e reavalia a posicao.

        Reavaliacao e' pedida via sinal em vez de feita aqui: o PriceWorker
        vive na AccountScreen, e duplicar a avaliacao dobraria o custo de
        rede (AGENTS.md: worker na tela que tem os dados).
        """
        if row >= len(self._rows) or row >= len(self._positions):
            return
        r = self._rows[row]
        pos = self._positions[row]
        nome = r.get("name") or pos.get("name") or ""
        qty = r.get("quantity") or pos.get("quantity") or 1
        atual = pos.get("cost") if portfolio.has_cost_basis(pos) else None
        dlg = _CostDialog(nome, qty, atual, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        novo = dlg.cost()
        if novo is None:
            return
        self._salvar_custo(nome, novo)

    def _salvar_custo(self, nome: str, custo: float) -> None:
        res = portfolio.update_position_cost(nome, custo)
        if res is None:
            # Nome fora do portfolio (filtro manual desalinhado): cria a
            # posicao manual e a reavaliacao abaixo traz as linhas novas.
            portfolio.add_position(nome, custo, 1)
        else:
            self._positions = res
        self.request_reeval.emit()
        Toast(self, f"Custo de “{nome}” salvo — reavaliando…",
              "success").show()

    def _limpar_filtro(self) -> None:
        if self._filter.text():
            self._filter.clear()

    # Rotulos dos segmentos de ordenacao com a seta de direcao. A seta so'
    # aparece na chave ATIVA ("Valor ▼"), as demais ficam limpas -- e a
    # troca de direcao e' clicar de novo na mesma chave.
    _ORDEM_ROTULOS = {"valor": "Valor", "nome": "Nome", "qtd": "Qtd"}

    def _atualizar_ordem_labels(self) -> None:
        ativa = self._grid.order()
        seta = "▼" if self._grid.reverse() else "▲"
        for k, rotulo in self._ORDEM_ROTULOS.items():
            self._ordem_seg.set_label(
                k, f"{rotulo} {seta}" if k == ativa else rotulo)

    def _on_ordem(self, key: str) -> None:
        """Delega pra grade (troca de chave ou alterna Asc/Desc quando a
        chave ja' e' a ativa) e re-sincroniza as setas dos segmentos."""
        self._grid.set_order(key)
        self._atualizar_ordem_labels()

    def _on_view_segment(self, key: str) -> None:
        """O segmentado manda o destino, nao um 'inverta'.

        O botao antigo derivava o destino do estado atual, e ler o estado
        na ordem errada ja' inverteu o filtro aqui uma vez. Agora a chave
        diz pra onde ir e nao ha' o que inverter.
        """
        self._views.setCurrentIndex(1 if key == "table" else 0)
        # Quem prefere a tabela reescolhia a cada abertura do app.
        from skinvault.settings import load_settings, save_settings
        s = load_settings()
        if s.get("inventory_view") != key:
            s["inventory_view"] = key
            save_settings(s)

    def _apply_filter(self, texto: str) -> None:
        """Filtra as DUAS visoes.

        O campo ficava desabilitado na grade -- uma caixa de busca grande e
        morta no topo da tela, e a grade e' a visao que abre por padrao.
        """
        alvo = (texto or "").strip().lower()
        for i in range(self._table.rowCount()):
            item = self._table.item(i, self.COL_NAME)
            nome = item.text().lower() if item else ""
            self._table.setRowHidden(i, bool(alvo) and alvo not in nome)
        sobraram = self._grid.set_filter(alvo)

        # Filtro sem resultado deixava a grade em branco, sem uma palavra --
        # indistinguivel de inventario vazio ou de falha de carregamento.
        base = getattr(self, "_rodape_base", "")
        if not alvo:
            self._status.setText(base)
            self._sem_match.setVisible(False)
            return
        total = self._grid.count()
        self._sem_match.setVisible(sobraram == 0 and total > 0)
        if sobraram:
            self._status.setText(
                f"Mostrando {sobraram} de {total} itens • filtro "
                f"“{texto.strip()}”")
        else:
            self._status.setText(
                f"Nenhum dos {total} itens casa com "
                f"“{texto.strip()}”")
