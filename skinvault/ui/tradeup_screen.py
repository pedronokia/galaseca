"""Tela — Calculadora de Trade-up.

Monta um contrato (10 itens -> raridade seguinte, ou 5 Covert -> faca/luva)
e calcula o valor esperado com a mediana recente do Steam Market, liquida
da taxa de 15%. Toda a regra mora em `skinvault.tradeup`; aqui so' ha'
formulario, tabela e os dois workers.

Duas coisas nao rodam na UI thread:
  - o CATALOGO (download de ~14 MB do dataset quando expirou);
  - a PRECIFICACAO, que pode buscar uma listing page por skin de saida.
    Um contrato de faca tem 20-60 resultados; com RATE_LIMIT_DELAY_S entre
    buscas isso leva minutos na primeira vez e zero com cache quente.

O numero e' descritivo (EV com precos de agora), nunca previsao.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCompleter,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from skinvault import tradeup
from skinvault.ui import theme as t
from skinvault.ui._price_worker import _safe_emit
from skinvault.ui.cards import Card, StatCard
from skinvault.ui.components import (
    FormRow, PageHeader, Toast, num_cell, set_button_loading,
)


# ── workers ──────────────────────────────────────────────────
class CatalogWorker(QObject):
    """Carrega/atualiza o catalogo. Emite (status, catalogo|None)."""

    done = pyqtSignal(str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, force: bool = False) -> None:
        if self._running:
            return
        self._running = True
        sig = self.done

        def worker() -> None:
            status, cat = tradeup.CATALOG_UNAVAILABLE, None
            try:
                status, cat = tradeup.refresh_catalog(force=force)
            except Exception:
                pass
            finally:
                self._running = False
            _safe_emit(sig, status, cat)

        threading.Thread(target=worker, daemon=True).start()


class EvalWorker(QObject):
    """Precifica o plano via SSR cache. progress(feitos, total, buscas)."""

    progress = pyqtSignal(int, int, int)
    done = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, plan: dict) -> None:
        if self._running:
            return
        self._running = True
        prog, sig = self.progress, self.done

        def worker() -> None:
            res = None
            try:
                pricer = tradeup.SsrPricer()
                nomes = tradeup.price_names(plan)
                total = len(nomes)
                _safe_emit(prog, 0, total, pricer.pending(nomes))
                # Pre-aquece na ordem agrupada por skin (vizinhos viram
                # cache hit); evaluate() depois so' le' o memo.
                for i, nome in enumerate(nomes, 1):
                    pricer(nome)
                    _safe_emit(prog, i, total, pricer.fetches)
                res = tradeup.evaluate(plan, pricer)
                if pricer.blocked:
                    res["warnings"].append(
                        "A Steam parou de responder (provavel rate limit): "
                        "parte dos precos ficou de fora. Tente de novo mais "
                        "tarde -- o que ja' veio fica no cache.")
            except Exception as e:  # nunca deixar a UI sem resposta
                res = {"errors": [f"Falha ao precificar: {e}"]}
            finally:
                self._running = False
            _safe_emit(sig, res)

        threading.Thread(target=worker, daemon=True).start()


_INPUT_COLS = (
    ("Item", "market_hash_name exato, com wear."),
    ("Qtd", "Quantas unidades deste item entram no contrato."),
    ("Float", "Float informado. 'meio da faixa' = nao informado: usa o "
              "ponto medio da faixa do wear dentro do range do skin."),
    ("Custo un.", "Custo unitario informado. 'mediana' = usa a mediana de "
                  "7 dias do Steam Market."),
    ("Coleção", "Colecao do skin (define o pool de saida)."),
    ("Raridade", "Todos os itens precisam ter a mesma raridade."),
)

_OUT_COLS = (
    ("Resultado", "Item que pode sair, ja' com o wear calculado pelo float "
                  "de saida."),
    ("Coleção", "Colecao sorteada para este resultado."),
    ("Prob.", "Chance: (inputs da colecao / total) x (1 / itens possiveis "
              "na colecao)."),
    ("Float", "Float de saida: media dos floats normalizados de cada input, "
              "mapeada no range deste skin."),
    ("Preço ref.", "Mediana dos ultimos 7 dias no Steam Market (bruto)."),
    ("Líquido", "Preco de referencia menos a taxa da Steam (15%)."),
    ("vs custo", "Liquido menos o custo total do contrato."),
)


def _header(table: QTableWidget, cols) -> None:
    """Cabecalho com tooltip por coluna. Chamar DEPOIS de configure_table.

    O nome do item (coluna 0) e' o que estica: o resto e' numero curto e
    so' precisa caber.
    """
    table.setColumnCount(len(cols))
    for i, (nome, dica) in enumerate(cols):
        item = QTableWidgetItem(nome)
        item.setToolTip(dica)
        table.setHorizontalHeaderItem(i, item)
    hh = table.horizontalHeader()
    hh.setStretchLastSection(False)
    hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for i in range(1, len(cols)):
        hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    table.setWordWrap(False)


def _pct(v) -> str:
    return "—" if v is None else f"{v * 100:.1f}%".replace(".", ",")


class TradeUpScreen(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog: dict | None = None
        self._entries: list[dict] = []  # {name, qty, float, cost}
        self._catalog_worker = CatalogWorker(self)
        self._catalog_worker.done.connect(self._on_catalog)
        self._eval_worker = EvalWorker(self)
        self._eval_worker.progress.connect(self._on_progress)
        self._eval_worker.done.connect(self._on_result)
        self._build()

    # ── layout ───────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        root.setSpacing(t.SPACE_MD)

        self._catalog_btn = QPushButton("Atualizar catálogo")
        self._catalog_btn.setStyleSheet(t.btn_secondary())
        self._catalog_btn.setToolTip(
            "Baixa de novo o catalogo de colecoes, raridades, ranges de "
            "float e pools de faca/luva (dataset publico ByMykel/CSGO-API). "
            "Atualiza sozinho a cada 7 dias.")
        self._catalog_btn.clicked.connect(
            lambda: self._load_catalog(force=True))
        root.addWidget(PageHeader(
            "Trade-up",
            "Valor esperado de contratos 10→1 e 5 Covert→faca/luva, "
            "com preços do Steam Market",
            actions=[self._catalog_btn]))

        self._catalog_lbl = QLabel("Catálogo ainda não carregado.")
        self._catalog_lbl.setStyleSheet(t.label_caption())
        root.addWidget(self._catalog_lbl)

        root.addWidget(self._build_form())

        self._inputs = QTableWidget(0, len(_INPUT_COLS))
        t.configure_table(self._inputs)
        _header(self._inputs, _INPUT_COLS)
        self._inputs.setSortingEnabled(False)
        self._inputs.setMaximumHeight(200)
        root.addWidget(self._inputs)

        acoes = QHBoxLayout()
        acoes.setContentsMargins(0, 0, 0, 0)
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(t.label_body_muted())
        acoes.addWidget(self._count_lbl, 1)
        self._remove_btn = QPushButton("Remover selecionado")
        self._remove_btn.setStyleSheet(t.btn_ghost())
        self._remove_btn.setToolTip("Remove a linha selecionada do contrato.")
        self._remove_btn.clicked.connect(self._on_remove)
        acoes.addWidget(self._remove_btn)
        self._clear_btn = QPushButton("Limpar")
        self._clear_btn.setStyleSheet(t.btn_ghost())
        self._clear_btn.setToolTip("Remove todos os itens do contrato.")
        self._clear_btn.clicked.connect(self._on_clear)
        acoes.addWidget(self._clear_btn)
        self._calc_btn = QPushButton("Calcular EV")
        self._calc_btn.setStyleSheet(t.btn_primary())
        self._calc_btn.setToolTip(
            "Busca os precos de cada resultado possivel (SSR cache; o que "
            "faltar vem do Steam Market, com pausa entre buscas) e calcula "
            "o valor esperado.")
        self._calc_btn.clicked.connect(self._on_calculate)
        acoes.addWidget(self._calc_btn)
        root.addLayout(acoes)

        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(t.SPACE_MD)
        self._card_cost = StatCard("Custo do contrato")
        self._card_ev = StatCard("EV líquido")
        self._card_profit = StatCard("Resultado esperado")
        self._card_chance = StatCard("Chance de cobrir o custo")
        for c, dica in (
            (self._card_cost, "Soma do custo dos inputs."),
            (self._card_ev, "Soma de probabilidade x valor liquido de cada "
                            "resultado (sem preco conta como zero)."),
            (self._card_profit, "EV liquido menos o custo, e o ROI."),
            (self._card_chance, "Probabilidade somada dos resultados cujo "
                                "liquido cobre o custo total."),
        ):
            c.setToolTip(dica)
            cards.addWidget(c)
        root.addLayout(cards)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"color: {t.WARN_TEXT}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};")
        self._status_lbl.setVisible(False)
        root.addWidget(self._status_lbl)

        self._outputs = QTableWidget(0, len(_OUT_COLS))
        t.configure_table(self._outputs)
        _header(self._outputs, _OUT_COLS)
        root.addWidget(self._outputs, 1)

        nota = QLabel(
            "Descritivo, não previsão: EV calculado com a mediana dos últimos "
            "7 dias do Steam Market, líquida da taxa de 15%. O saldo da Steam "
            "não é sacável, e o item recebido fica 7 dias em Trade Protection.")
        nota.setWordWrap(True)
        nota.setStyleSheet(t.label_caption())
        root.addWidget(nota)

        self._sync_count()

    def _build_form(self) -> Card:
        card = Card(self, padding=t.CARD_PAD_MD, radius=t.RADIUS_MD)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(t.SPACE_SM)

        self._name_inp = QLineEdit()
        self._name_inp.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        self._name_inp.setStyleSheet(t.input_style())
        self._name_inp.returnPressed.connect(self._on_add)
        row.addWidget(FormRow("Item", self._name_inp,
                              tooltip="Nome exato de mercado, com wear. "
                                      "O autocomplete vem do catalogo."), 4)

        self._qty_inp = QSpinBox()
        self._qty_inp.setRange(1, tradeup.STANDARD_INPUTS)
        self._qty_inp.setStyleSheet(t.input_style())
        row.addWidget(FormRow("Qtd", self._qty_inp,
                              tooltip="Unidades deste item."), 1)

        self._float_inp = QLineEdit()
        self._float_inp.setPlaceholderText("opcional")
        self._float_inp.setStyleSheet(t.input_style())
        row.addWidget(FormRow("Float", self._float_inp,
                              tooltip="Float exato do item (ex.: 0,2134). "
                                      "Vazio = meio da faixa do wear."), 1)

        self._cost_inp = QDoubleSpinBox()
        self._cost_inp.setRange(0, 999999)
        self._cost_inp.setDecimals(2)
        self._cost_inp.setPrefix("R$ ")
        self._cost_inp.setStyleSheet(t.input_style())
        row.addWidget(FormRow("Custo un.", self._cost_inp,
                              tooltip="Quanto voce pagou por unidade. "
                                      "R$ 0,00 = usar a mediana do Steam "
                                      "Market."), 1)

        self._add_btn = QPushButton("Adicionar")
        self._add_btn.setStyleSheet(t.btn_secondary())
        self._add_btn.setToolTip("Adiciona o item ao contrato.")
        self._add_btn.clicked.connect(self._on_add)
        row.addWidget(self._add_btn, 0, Qt.AlignmentFlag.AlignBottom)

        card.layout().addLayout(row)
        return card

    # ── catalogo ─────────────────────────────────────────────
    def refresh(self) -> None:
        """Chamado ao navegar pra tela: carrega o catalogo uma vez."""
        if self._catalog is None:
            self._load_catalog(force=False)

    def _load_catalog(self, force: bool) -> None:
        if self._catalog_worker.running:
            return
        set_button_loading(self._catalog_btn, True, "Carregando…")
        self._catalog_lbl.setText("Carregando catálogo…")
        self._catalog_worker.start(force=force)

    def _on_catalog(self, status: str, catalog) -> None:
        set_button_loading(self._catalog_btn, False)
        if catalog:
            self._catalog = catalog
            self._install_completer()
        textos = {
            tradeup.CATALOG_CACHED: "Catálogo carregado do disco",
            tradeup.CATALOG_UPDATED: "Catálogo atualizado agora",
            tradeup.CATALOG_STALE: "Sem rede: usando catálogo salvo",
        }
        if catalog:
            n_col = len(catalog.get("collections") or {})
            n_sk = len(catalog.get("skins") or {})
            self._catalog_lbl.setText(
                f"{textos.get(status, 'Catálogo')} · {n_col} coleções · "
                f"{n_sk} skins · fonte: ByMykel/CSGO-API")
        else:
            self._catalog_lbl.setText(
                "Catálogo indisponível (sem rede e nada salvo). "
                "Tente “Atualizar catálogo”.")
            Toast.show_toast(self, "Não foi possível carregar o catálogo.",
                             "error")

    def _install_completer(self) -> None:
        comp = QCompleter(tradeup.input_suggestions(self._catalog),
                          self._name_inp)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.setMaxVisibleItems(12)
        comp.popup().setStyleSheet(
            f"background: {t.BG_ELEVATED}; color: {t.TEXT};")
        self._name_inp.setCompleter(comp)

    # ── contrato ─────────────────────────────────────────────
    def _total_items(self) -> int:
        return sum(e["qty"] for e in self._entries)

    def _expanded(self) -> list[dict]:
        out = []
        for e in self._entries:
            for _ in range(e["qty"]):
                out.append({"name": e["name"], "float": e["float"],
                            "cost": e["cost"]})
        return out

    def _on_add(self) -> None:
        nome = self._name_inp.text().strip()
        if not nome:
            Toast.show_toast(self, "Informe o item.", "warning")
            return
        texto_f = self._float_inp.text().strip().replace(",", ".")
        f = None
        if texto_f:
            try:
                f = float(texto_f)
            except ValueError:
                Toast.show_toast(self, "Float inválido.", "error")
                return
        custo = self._cost_inp.value() or None
        qtd = self._qty_inp.value()
        if self._total_items() + qtd > tradeup.STANDARD_INPUTS:
            Toast.show_toast(
                self, f"O contrato tem no máximo "
                      f"{tradeup.STANDARD_INPUTS} itens.", "warning")
            return
        self._entries.append({"name": nome, "qty": qtd, "float": f,
                              "cost": custo})
        self._name_inp.clear()
        self._float_inp.clear()
        self._render_inputs()

    def _on_remove(self) -> None:
        row = self._inputs.currentRow()
        if 0 <= row < len(self._entries):
            del self._entries[row]
            self._render_inputs()

    def _on_clear(self) -> None:
        self._entries.clear()
        self._render_inputs()
        self._outputs.setRowCount(0)
        self._show_totals(None)

    def _render_inputs(self) -> None:
        skins = (self._catalog or {}).get("skins") or {}
        self._inputs.setRowCount(len(self._entries))
        for r, e in enumerate(self._entries):
            meta = skins.get(tradeup.parse_market_name(e["name"])["base"]) or {}
            rar = tradeup.RARITY_LABELS.get(meta.get("r"), "—")
            celulas = [
                QTableWidgetItem(e["name"]),
                num_cell(str(e["qty"]), e["qty"]),
                QTableWidgetItem("meio da faixa" if e["float"] is None
                                 else f"{e['float']:.4f}"),
                QTableWidgetItem("mediana" if e["cost"] is None
                                 else t.brl(e["cost"])),
                QTableWidgetItem(meta.get("c") or "—"),
                QTableWidgetItem(rar),
            ]
            if not meta:
                celulas[0].setForeground(_color(t.DANGER))
                celulas[0].setToolTip("Nao encontrado no catalogo.")
            for c, item in enumerate(celulas):
                self._inputs.setItem(r, c, item)
        self._sync_count()

    def _sync_count(self) -> None:
        n = self._total_items()
        modo = ""
        skins = (self._catalog or {}).get("skins") or {}
        if self._entries:
            base = tradeup.parse_market_name(self._entries[0]["name"])["base"]
            if (skins.get(base) or {}).get("r") == "ancient":
                modo = f" · faca/luva: {tradeup.RARE_INPUTS} Covert"
            else:
                modo = f" · normal: {tradeup.STANDARD_INPUTS} itens"
        self._count_lbl.setText(f"{n} item(ns) no contrato{modo}")

    # ── calculo ──────────────────────────────────────────────
    def _on_calculate(self) -> None:
        if self._eval_worker.running:
            return
        if not self._catalog:
            Toast.show_toast(self, "Catálogo ainda não carregado.", "warning")
            return
        plan = tradeup.plan_contract(self._expanded(), self._catalog)
        if plan["errors"]:
            self._show_status(plan["errors"])
            Toast.show_toast(self, plan["errors"][0], "error")
            return
        self._show_status([])
        set_button_loading(self._calc_btn, True, "Precificando…")
        self._eval_worker.start(plan)

    def _on_progress(self, feitos: int, total: int, buscas: int) -> None:
        self._show_status([f"Precificando {feitos}/{total} · "
                           f"{buscas} página(s) da Steam"], warn=False)

    def _on_result(self, res) -> None:
        set_button_loading(self._calc_btn, False)
        res = res or {}
        if res.get("errors"):
            self._show_status(res["errors"])
            return
        self._show_status(res.get("warnings") or [])
        self._show_totals(res)
        self._render_outputs(res)

    def _show_status(self, linhas: list, warn: bool = True) -> None:
        self._status_lbl.setVisible(bool(linhas))
        self._status_lbl.setText("\n".join(linhas))
        cor = t.WARN_TEXT if warn else t.TEXT_MUTED
        self._status_lbl.setStyleSheet(
            f"color: {cor}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};")

    def _show_totals(self, res) -> None:
        res = res or {}
        self._card_cost.set_value(t.brl(res.get("cost")))
        self._card_ev.set_value(t.brl(res.get("ev_net")))
        lucro = res.get("profit")
        if lucro is None:
            self._card_profit.set_value("—")
        else:
            cor = t.POSITIVE if lucro >= 0 else t.DANGER
            roi = res.get("roi")
            sufixo = f" ({_pct(roi)})" if roi is not None else ""
            self._card_profit.set_value(t.brl(lucro) + sufixo, cor)
        self._card_chance.set_value(_pct(res.get("prob_profit")))

    def _render_outputs(self, res: dict) -> None:
        outs = res.get("outcomes") or []
        custo = res.get("cost")
        self._outputs.setSortingEnabled(False)
        self._outputs.setRowCount(len(outs))
        for r, o in enumerate(outs):
            net = o.get("net")
            delta = (net - custo) if (net is not None and custo is not None) \
                else None
            cor = None if delta is None else (
                t.POSITIVE if delta >= 0 else t.DANGER)
            celulas = [
                QTableWidgetItem(o["name"]),
                QTableWidgetItem(o["collection"]),
                num_cell(_pct(o["prob"]), o["prob"]),
                num_cell("—" if o.get("float") is None
                         else f"{o['float']:.4f}", o.get("float")),
                num_cell(t.brl(o.get("price")), o.get("price")),
                num_cell(t.brl(net), net),
                num_cell(t.brl(delta), delta, cor),
            ]
            if o.get("price") is None:
                celulas[4].setToolTip("Sem historico no Steam Market para "
                                      "este nome (ou a busca nao completou).")
            for c, item in enumerate(celulas):
                self._outputs.setItem(r, c, item)
        self._outputs.setSortingEnabled(True)
        # Sem isto vale a ordem herdada do header (coluna 0); o que importa
        # e' ver primeiro o que paga o contrato.
        self._outputs.sortItems(5, Qt.SortOrder.DescendingOrder)


def _color(hex_color: str):
    from PyQt6.QtGui import QBrush, QColor
    return QBrush(QColor(hex_color))
