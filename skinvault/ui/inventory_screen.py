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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import markets, portfolio
from skinvault.ui import theme as t
from skinvault.ui.components import (
    EmptyState,
    LoadingState,
    PageHeader,
    SegmentedControl,
    SortableItem,
    score_table_item,
)
from skinvault.ui._price_worker import IconWorker
from skinvault.ui.inventory_grid import InventoryGrid, InventoryTile


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
    COL_PNL = 6
    COL_SCORE = 7
    COL_ORIGIN = 8

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list = []
        self._positions: list = []
        self._mercados: dict = {}
        self._icon_worker = IconWorker(self)
        self._icon_worker.done.connect(self._on_icons_ready)
        self._build()

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
        # marca a atual.
        self._view_seg = SegmentedControl()
        self._view_seg.add("grid", "Grade")   # o primeiro ja' nasce marcado
        self._view_seg.add("table", "Tabela")
        from skinvault.settings import load_settings as _ls
        self._view_inicial = (
            "table" if _ls().get("inventory_view") == "table" else "grid")
        self._view_seg.setToolTip(
            "Grade de ícones (estilo Steam) ou tabela detalhada.")
        self._view_seg.segment_changed.connect(self._on_view_segment)
        linha.addWidget(self._view_seg, 0)
        root.addLayout(linha)
        if self._view_inicial == "table":
            self._view_seg.select("table")

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
        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels([
            "Item", "Qtd", "Anúncio Steam", "Recebe (saldo)",
            "Melhor fora", "Onde", "P&L", "Score", "Origem",
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
            self.COL_SCORE: (
                "Score do item (0-100), calculado pelo botão 'Validar score' "
                "na tela Minha Conta.\n"
                "Fica âmbar quando está desatualizado. '—' significa que "
                "ainda não foi calculado."),
        }
        for col, tip in _tips.items():
            cab = self._table.horizontalHeaderItem(col)
            if cab is not None:
                cab.setToolTip(tip)
        t.configure_table(self._table)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        for i in range(1, self.COL_ORIGIN + 1):
            hh.setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents)

        self._views = QStackedWidget()
        self._views.addWidget(self._grid)
        self._views.addWidget(self._table)
        root.addWidget(self._views, 1)

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
        self._views.setVisible(False)
        self._empty.setVisible(False)
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
        for r in self._rows:
            mercados = self._mercados.get(r.get("name") or "") or []
            if mercados:
                tem_fora = True
                fora += mercados[0]["net_brl"] * (r.get("quantity") or 1)
        if tem_fora:
            partes.append(f"{t.brl(fora)} vendendo fora (dinheiro)")

        saldo = sum((r.get("net_if_sold") or 0) * 1
                    for r in self._rows if r.get("net_if_sold"))
        if saldo:
            partes.append(f"{t.brl(saldo)} em saldo Steam")
        return " • ".join(partes)

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
                (self.COL_PNL, t.brl(pnl) if pnl is not None else "—", pnl),
                (self.COL_ORIGIN, origem, None),
            ]
            for col, val, chave in celulas:
                item = (QTableWidgetItem(val) if chave is None
                        else SortableItem(val, chave))
                if col == self.COL_PNL and pnl is not None:
                    item.setForeground(QBrush(QColor(
                        t.POSITIVE if pnl >= 0 else t.DANGER)))
                elif col == self.COL_BEST_OUT and melhor:
                    item.setForeground(QBrush(QColor(t.POSITIVE)))
                elif col == self.COL_WHERE and melhor:
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
        self._table.setSortingEnabled(True)

    # ── interacao ─────────────────────────────────────────

    def _focar_filtro(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()

    def _limpar_filtro(self) -> None:
        if self._filter.text():
            self._filter.clear()

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
