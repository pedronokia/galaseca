"""Inventario em grade, no visual da Steam: tiles + painel de detalhe.

A tabela do AccountScreen serve pra conferir numero; ela nao serve pra
RECONHECER item. Quem mexe em inventario reconhece pelo icone, e e' assim
que a Steam mostra. Esta tela existe pra isso.

O que ela acrescenta ao que a Steam mostra: as DUAS avaliacoes lado a
lado. Vendendo na Steam voce recebe saldo travado; vendendo fora recebe
dinheiro. Medido em 2026-07-28 sobre 734 itens, a Steam pede 36% a mais
justamente porque o saldo dela nao sai. Sem as duas colunas juntas, essa
diferenca fica invisivel -- e e' a informacao que decide a operacao.

Sem rede: recebe os dados prontos e le' icone so' do cache local.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from skinvault import icons
from skinvault.ui import theme as t

# Card no formato dos sites de troca (tradeit/CS.MONEY): imagem grande em
# cima, nome e preco embaixo. O tile antigo tinha 96px e so' cabia o icone
# -- pra saber QUAL skin era, so' passando o mouse.
TILE_W = 152
TILE_ICON_H = 96
# Duas linhas de texto: nome, e o valor com a ORIGEM. Com uma linha so' o
# tile teria que escolher entre mentir (numero de fora exibido como saldo
# Steam) e nao dizer nada (a parede de travessoes sob rate limit).
TILE_TEXT_H = 44
TILE_H = TILE_ICON_H + TILE_TEXT_H

# Mantido: `TILE` era a medida do tile quadrado antigo e ainda serve de
# passo horizontal em quem calcula quantas colunas cabem.
TILE = TILE_W


def _valor_do_tile(item: dict) -> tuple:
    """(valor, origem) do que a etiqueta deve mostrar.

    Prefere o saldo da Steam, que e' o numero que a Steam exibe. Quando ele
    falta -- 429, item nao listado -- cai pro melhor liquido de fora, que
    ja' vem calculado no dict. Sao moedas diferentes (saldo travado contra
    dinheiro), entao a origem viaja junto com o numero.
    """
    saldo = item.get("steam_net")
    if saldo is not None:
        return saldo, "saldo"
    mercados = item.get("mercados") or []
    if mercados:
        return mercados[0].get("net_brl"), "fora"
    fora = item.get("market_net")
    if fora is not None:
        return fora, "fora"
    return None, ""


class InventoryTile(QFrame):
    """Um item: icone + etiqueta de preco, no formato da Steam.

    Pintado com QPainter (convencao do projeto). Guarda o dict do item pra
    o painel de detalhe nao precisar procurar de novo.
    """

    clicked = pyqtSignal(dict)

    def __init__(self, item: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self._selected = False
        self._hover = False
        self._pix: QPixmap | None = None
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._load_icon()
        self.setToolTip(self._tooltip())

    def _load_icon(self) -> None:
        p = icons.local_path(self.item.get("icon"))
        if p:
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._pix = pm.scaled(
                    TILE_W - 16, TILE_ICON_H - 12,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)

    _NOME_MERCADO = {
        "skinport": "Skinport",
        "buff163": "Buff163",
        "csgotm": "CS.MONEY/TM",
    }

    def _tooltip(self) -> str:
        """Passar o mouse mostra o item em TODAS as plataformas.

        Ordenado pelo LIQUIDO, nao pelo bruto: a taxa varia demais entre
        elas (5% na CSGOTM contra 12% no Skinport), entao o maior preco
        anunciado nao e' necessariamente quem paga mais.
        """
        it = self.item
        linhas = [it.get("name", "")]
        if it.get("qty", 1) > 1:
            linhas.append(f"Quantidade: {it['qty']}")

        if it.get("steam_net") is not None:
            linhas.append("")
            linhas.append(f"Steam:  {t.brl(it['steam_net'])}  (saldo)")

        mercados = it.get("mercados") or []
        if mercados:
            linhas.append("")
            linhas.append("Vendendo fora (dinheiro):")
            for i, m in enumerate(mercados):
                nome = self._NOME_MERCADO.get(m["source"], m["source"])
                marca = "  ← paga mais" if i == 0 and len(mercados) > 1 else ""
                linhas.append(
                    "  {:<12} {:>9}  (taxa {:.0f}%){}".format(
                        nome, t.brl(m["net_brl"]), m["fee"] * 100, marca))
        elif it.get("market_net") is not None:
            linhas.append("")
            linhas.append(f"Dinheiro real: {t.brl(it['market_net'])}")

        if it.get("premium_pct") is not None:
            linhas.append("")
            linhas.append(
                f"A Steam pede {it['premium_pct']:+.0f}% a mais — mas o que"
                " sai de lá é saldo, não dinheiro.")
        return "\n".join(linhas)

    def set_selected(self, on: bool) -> None:
        if self._selected != on:
            self._selected = on
            self.update()

    def enterEvent(self, e) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(e)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        corpo = QRect(0, 0, TILE_W, TILE_H)
        area_icone = QRect(0, 0, TILE_W, TILE_ICON_H)

        fundo = t.SURFACE_HOV if (self._hover or self._selected) else t.SURFACE
        p.setBrush(QColor(fundo))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(corpo, t.RADIUS_MD, t.RADIUS_MD)

        if self._selected:
            # Anel mais grosso quando a grade tem o foco do teclado: andar
            # de seta em seta sem saber onde se esta' e' pior que nao ter
            # seta nenhuma.
            pai = self.parent()
            com_foco = False
            while pai is not None:
                if isinstance(pai, InventoryGrid):
                    com_foco = pai.hasFocus()
                    break
                pai = pai.parent()
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.TEXT), 3 if com_foco else 2))
            p.drawRoundedRect(corpo.adjusted(2, 2, -2, -2),
                              t.RADIUS_MD, t.RADIUS_MD)

        if self._pix:
            x = (TILE_W - self._pix.width()) // 2
            y = (TILE_ICON_H - self._pix.height()) // 2
            p.drawPixmap(x, y, self._pix)

        qtd = self.item.get("qty", 1)
        if qtd > 1:
            p.setPen(QColor(t.TEXT_MUTED))
            fonte = p.font()
            fonte.setPointSize(8)
            p.setFont(fonte)
            p.drawText(area_icone.adjusted(0, 6, -8, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                       f"x{qtd}")

        # Nome: o tile antigo so' tinha o icone, e saber QUAL skin era
        # exigia passar o mouse. Elidido -- "Asiimov" cabe, o nome inteiro
        # com arma e desgaste nao.
        fonte = p.font()
        fonte.setPointSize(8)
        p.setFont(fonte)
        p.setPen(QColor(t.TEXT_MUTED))
        nome = p.fontMetrics().elidedText(
            self._rotulo_curto(), Qt.TextElideMode.ElideRight, TILE_W - 12)
        p.drawText(QRect(6, TILE_ICON_H, TILE_W - 12, 16),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   nome)

        # Valor e de ONDE ele vem, na mesma linha.
        preco, origem = _valor_do_tile(self.item)
        fonte.setPointSize(10)
        fonte.setBold(True)
        p.setFont(fonte)
        p.setPen(QColor(t.TEXT if preco is not None else t.TEXT_MUTED))
        texto = t.brl(preco) if preco is not None else "—"
        largura_preco = p.fontMetrics().horizontalAdvance(texto)
        fonte.setBold(False)
        fonte.setPointSize(7)
        largura_origem = 0
        if origem:
            p.setFont(fonte)
            largura_origem = p.fontMetrics().horizontalAdvance(" " + origem)
        inicio = max(4, (TILE_W - largura_preco - largura_origem) // 2)

        fonte.setPointSize(10)
        fonte.setBold(True)
        p.setFont(fonte)
        p.drawText(QRect(inicio, TILE_ICON_H + 16, largura_preco, 22),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   texto)
        if origem:
            fonte.setPointSize(7)
            fonte.setBold(False)
            p.setFont(fonte)
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(
                QRect(inicio + largura_preco, TILE_ICON_H + 16,
                      largura_origem + 4, 22),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                " " + origem)
        p.end()

    def _rotulo_curto(self) -> str:
        """Nome que cabe no card.

        "AWP | Asiimov (Testada em Campo)" -> "Asiimov". Com o icone ao
        lado, o que identifica e' o acabamento, nao a arma -- e' assim que
        os sites de troca rotulam. Container mantem o nome inteiro, que ja'
        e' curto.
        """
        nome = (self.item.get("name") or "").strip()
        if not nome:
            return ""
        if "|" in nome:
            nome = nome.split("|")[1].strip()
        if "(" in nome:
            nome = nome.split("(")[0].strip()
        return nome


class ItemDetailPanel(QFrame):
    """Painel lateral: as duas avaliacoes do item selecionado."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Seletor por objectName, NAO por "QFrame": QLabel herda de QFrame,
        # entao um seletor de tipo desenharia borda em todo rotulo filho.
        self.setObjectName("itemDetailPanel")
        self.setStyleSheet(
            f"#itemDetailPanel {{ background: {t.BG_ELEVATED};"
            f" border: 1px solid {t.BORDER};"
            f" border-radius: {t.RADIUS_MD}px; }}"
            f" #itemDetailPanel QLabel {{ background: transparent;"
            " border: none; }")
        self.setMinimumWidth(260)
        v = QVBoxLayout(self)
        v.setContentsMargins(t.SPACE_LG, t.SPACE_LG, t.SPACE_LG, t.SPACE_LG)
        v.setSpacing(t.SPACE_SM)

        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setMinimumHeight(120)
        v.addWidget(self._icon)

        self._nome = QLabel("Selecione um item")
        self._nome.setWordWrap(True)
        # Nome de skin quebra em 2-3 linhas. QLabel com wordWrap calcula
        # altura antes de saber a largura, e a ultima linha saia cortada.
        self._nome.setMinimumHeight(
            self._nome.fontMetrics().height() * 3)
        self._nome.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._nome.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;")
        v.addWidget(self._nome)

        self._tipo = QLabel("")
        self._tipo.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};")
        v.addWidget(self._tipo)

        v.addSpacing(t.SPACE_MD)

        # ── POR QUANTO VENDER ─────────────────────────────
        # O painel antes mostrava dois numeros liquidos e parava. Nao
        # respondia a pergunta que o dono faz: "por quanto anuncio?".
        # Agora traz o PRECO DE ANUNCIO e o que sobra dele, nos dois
        # caminhos -- sem escolher por ele, porque saldo Steam e dinheiro
        # nao sao a mesma coisa (a Steam pede ~36% a mais justamente
        # porque o saldo nao sai de la').
        self._titulo_steam = self._secao(v, "Vendendo na Steam")
        self._steam_anuncio = self._linha(v, "anuncie por", destaque=True)
        self._steam_recebe = self._linha(v, "você recebe")
        self._steam_rapido = self._linha(v, "pra vender hoje")

        v.addSpacing(t.SPACE_MD)
        self._titulo_fora = self._secao(v, "Vendendo fora (dinheiro)")
        self._fora = QLabel("—")
        self._fora.setWordWrap(True)
        self._fora.setTextFormat(Qt.TextFormat.RichText)
        self._fora.setStyleSheet(f"font-size: {t.FS_BODY};")
        v.addWidget(self._fora)

        v.addSpacing(t.SPACE_MD)
        self._piso = QLabel("")
        self._piso.setWordWrap(True)
        self._piso.setTextFormat(Qt.TextFormat.RichText)
        self._piso.setStyleSheet(f"font-size: {t.FS_MUTED};")
        v.addWidget(self._piso)

        self._premio = QLabel("")
        self._premio.setWordWrap(True)
        self._premio.setTextFormat(Qt.TextFormat.RichText)
        self._premio.setStyleSheet(f"font-size: {t.FS_MUTED};")
        v.addWidget(self._premio)

        # ── DE ONDE VEM ───────────────────────────────────
        # Metade de baixo do painel estava vazia, e faltava justamente o
        # unico dado desta tela que nao depende da Steam responder: a
        # procedencia. Container aposentado nao cai mais em drop -- e' fato
        # sobre a oferta, nao previsao de preco.
        # ── COMPRAR MAIS ──────────────────────────────────
        # A tela sabia dizer por quanto VENDER e nao por quanto COMPRAR --
        # metade da decisao de quem revende. `max_buy_price` ja' existia,
        # usada so' pelo Scanner.
        v.addSpacing(t.SPACE_MD)
        self._titulo_compra = self._secao(v, "Comprar mais")
        self._compra = QLabel("—")
        self._compra.setWordWrap(True)
        self._compra.setTextFormat(Qt.TextFormat.RichText)
        self._compra.setStyleSheet(f"font-size: {t.FS_MUTED};")
        v.addWidget(self._compra)

        v.addSpacing(t.SPACE_MD)
        self._titulo_origem = self._secao(v, "De onde vem")
        self._origem = QLabel("—")
        self._origem.setWordWrap(True)
        self._origem.setTextFormat(Qt.TextFormat.RichText)
        self._origem.setStyleSheet(f"font-size: {t.FS_MUTED};")
        v.addWidget(self._origem)
        v.addStretch(1)

    def _secao(self, layout, texto: str) -> QLabel:
        lbl = QLabel(texto.upper())
        lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            " font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(lbl)
        return lbl

    def _linha(self, layout, rotulo: str, destaque: bool = False) -> QLabel:
        """Uma linha rotulo→valor. Devolve so' o valor, que e' o que muda."""
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)
        cap = QLabel(rotulo)
        cap.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};")
        val = QLabel("—")
        val.setAlignment(Qt.AlignmentFlag.AlignRight
                         | Qt.AlignmentFlag.AlignVCenter)
        val.setStyleSheet(
            f"color: {t.TEXT};"
            f" font-size: {t.FS_STAT if destaque else t.FS_BODY};"
            f" font-weight: {'600' if destaque else '500'};")
        linha.addWidget(cap)
        linha.addStretch(1)
        linha.addWidget(val)
        layout.addLayout(linha)
        return val

    def show_item(self, item: dict | None) -> None:
        if not item:
            self._nome.setText("Selecione um item")
            self._tipo.setText("")
            self._icon.clear()
            for lbl in (self._steam_anuncio, self._steam_recebe,
                        self._steam_rapido):
                lbl.setText("—")
            self._fora.setText("—")
            self._piso.setText("")
            self._premio.setText("")
            self._compra.setText("—")
            self._origem.setText("—")
            return

        self._nome.setText(item.get("name", ""))
        qtd = item.get("qty", 1)
        tipo = item.get("type") or ""
        # Num lote, o preco unitario nao e' o numero que decide nada: 21
        # caixas de R$ 0,99 sao R$ 20,79, e era esse total que faltava.
        if qtd > 1:
            unit, _ = _valor_do_tile(item)
            if unit is not None:
                self._tipo.setText(
                    f"{tipo}   ×{qtd}  ·  {t.brl(unit * qtd)} no total"
                    if tipo else f"×{qtd}  ·  {t.brl(unit * qtd)} no total")
            else:
                self._tipo.setText(f"{tipo}   ×{qtd}" if tipo else f"×{qtd}")
        else:
            self._tipo.setText(tipo)

        # Sem icone o QLabel mantinha os 120px de minimumHeight e sobrava um
        # bloco vazio empurrando o nome pra baixo. Esconder colapsa o espaco.
        p = icons.local_path(item.get("icon"))
        pm = QPixmap(str(p)) if p else None
        if pm is not None and not pm.isNull():
            self._icon.setPixmap(pm.scaled(
                160, 120, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            self._icon.setVisible(True)
        else:
            self._icon.clear()
            self._icon.setVisible(False)

        self._preencher_steam(item)
        self._preencher_fora(item)
        self._preencher_piso(item)
        self._preencher_compra(item)
        self._preencher_origem(item)

        prem = item.get("premium_pct")
        if prem is None:
            self._premio.setText("")
        else:
            cor = t.POSITIVE if prem > 0 else t.DANGER
            texto = ("A Steam pede mais — mas o que sai de lá é saldo, "
                     "que só compra na Steam."
                     if prem > 0 else
                     "Fora da Steam paga mais, e em dinheiro.")
            self._premio.setText(
                f"<span style='color:{cor}'><b>{prem:+.0f}%</b></span> "
                f"<span style='color:{t.TEXT_MUTED}'>{texto}</span>")

    def _preencher_steam(self, item: dict) -> None:
        g = item.get("guidance") or {}
        alvo = g.get("target_list")
        self._steam_anuncio.setText(t.brl(alvo) if alvo else "—")

        recebe = g.get("net_at_target")
        if recebe is None:
            recebe = item.get("steam_net")
        self._steam_recebe.setText(
            f"{t.brl(recebe)} em saldo" if recebe is not None else "—")

        rapido = g.get("fast_list")
        self._steam_rapido.setText(t.brl(rapido) if rapido else "—")

    def _preencher_fora(self, item: dict) -> None:
        """Uma linha por plataforma, ordenadas pelo LIQUIDO.

        A taxa varia de 5% a 12% entre elas, entao o maior preco anunciado
        nao e' quem paga mais -- ordenar por bruto mandaria o usuario pro
        lugar errado.
        """
        mercados = item.get("mercados") or []
        if not mercados:
            mn = item.get("market_net")
            self._fora.setText(
                f"<span style='color:{t.TEXT}'>{t.brl(mn)}</span>"
                if mn is not None
                else f"<span style='color:{t.TEXT_MUTED}'>"
                     "item não listado fora</span>")
            return
        partes = []
        for i, m in enumerate(mercados):
            nome = InventoryTile._NOME_MERCADO.get(m["source"], m["source"])
            cor = t.POSITIVE if i == 0 else t.TEXT
            peso = "600" if i == 0 else "400"
            partes.append(
                f"<div style='margin-bottom:2px'>"
                f"<span style='color:{t.TEXT_MUTED}'>{nome}</span> "
                f"<span style='color:{cor};font-weight:{peso}'>"
                f"{t.brl(m['net_brl'])}</span> "
                f"<span style='color:{t.TEXT_MUTED}'>"
                f"(taxa {m['fee'] * 100:.0f}%)</span></div>")
        self._fora.setText("".join(partes))

    def _preencher_compra(self, item: dict) -> None:
        """Teto de compra pra este item, na Steam.

        Nao e' recomendacao: e' o preco de indiferenca dada a taxa. Pagar
        acima disso ja' nasce no prejuizo mesmo que a venda saia no preco
        de referencia.
        """
        from skinvault import portfolio

        g = item.get("guidance") or {}
        alvo = g.get("target_list") or item.get("steam_price")
        if alvo is None:
            self._compra.setText(
                f"<span style='color:{t.TEXT_MUTED}'>Sem preço de "
                "referência agora.</span>")
            return
        empate = portfolio.max_buy_price(alvo)
        margem20 = portfolio.max_buy_price(alvo, margin_pct=20.0)
        self._compra.setText(
            f"<span style='color:{t.TEXT_MUTED}'>Pra empatar, pague até</span> "
            f"<b>{t.brl(empate)}</b>"
            f"<br><span style='color:{t.TEXT_MUTED}'>Pra 20% de margem, "
            f"até</span> <b>{t.brl(margem20)}</b>")

    def _preencher_origem(self, item: dict) -> None:
        """Procedencia do item: a caixa de onde ele sai, e se ela ainda cai.

        Descritivo, nao preditivo. "Descontinuada" e' um fato sobre a
        oferta (o container parou de entrar em drop); o que isso faz com o
        preco e' leitura do dono, nao afirmacao desta tela.
        """
        from skinvault import cases

        nome = item.get("name") or ""
        info = cases.case_status(nome) or {}
        caixa = info.get("case")
        # `case_status` NUNCA devolve vazio: item desconhecido volta com
        # status "unknown" e `is_discontinued: False`. Ler esse False como
        # "ainda cai em drop" seria afirmar sobre um item que o app nao
        # conhece -- o gate e' o nome da caixa, nao a verdade do dict.
        if not caixa or info.get("status") == "unknown":
            self._origem.setText(
                f"<span style='color:{t.TEXT_MUTED}'>Este item não está "
                "mapeado numa caixa.</span>")
            return

        ano = info.get("year")
        proprio = caixa == nome        # o item E' o container
        if info.get("is_discontinued"):
            estado = "não cai mais em drop"
            cor = t.TEXT
        else:
            estado = "ainda cai em drop"
            cor = t.TEXT_MUTED

        if proprio:
            cabeca = f"<b>{caixa}</b>"
        else:
            cabeca = (f"<span style='color:{t.TEXT_MUTED}'>Vem de</span> "
                      f"<b>{caixa}</b>")
        linha = cabeca + f"<br><span style='color:{cor}'>{estado}</span>"
        if ano:
            linha += (f" <span style='color:{t.TEXT_MUTED}'>· "
                      f"{ano}</span>")
        if info.get("is_rare"):
            linha += (f"<br><span style='color:{t.TEXT_MUTED}'>"
                      "marcada como rara</span>")
        self._origem.setText(linha)

    def _preencher_piso(self, item: dict) -> None:
        """O piso so' existe com custo conhecido.

        Posicao vinda do sync nao tem custo -- a Steam nao diz quanto voce
        pagou. Dizer "lucro" ali seria inventar numero (ver
        portfolio.has_cost_basis).
        """
        g = item.get("guidance") or {}
        piso = g.get("break_even_list")
        if piso is None:
            self._piso.setText(
                f"<span style='color:{t.TEXT_MUTED}'>Sem custo registrado — "
                "dá pra ver quanto entra, não quanto lucra.</span>")
            return
        lucro = g.get("profit_at_target")
        cobre = g.get("clears")
        cor = t.POSITIVE if cobre else t.DANGER
        linha = (f"<span style='color:{t.TEXT_MUTED}'>Pra empatar, anuncie "
                 f"por</span> <b>{t.brl(piso)}</b>")
        if lucro is not None:
            sinal = "lucro" if lucro >= 0 else "prejuízo"
            linha += (f"<br><span style='color:{cor}'>{t.brl(abs(lucro))} de "
                      f"{sinal}</span> "
                      f"<span style='color:{t.TEXT_MUTED}'>no alvo</span>")
        gap = g.get("gap_pct")
        if gap is not None and gap > 0:
            linha += (f"<br><span style='color:{t.TEXT_MUTED}'>precisa subir "
                      f"{gap:.1f}% pra empatar</span>")
        self._piso.setText(linha)


class InventoryGrid(QWidget):
    """Grade rolavel de tiles + painel de detalhe."""

    item_selected = pyqtSignal(dict)

    def __init__(self, columns: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = max(1, columns)
        self._tiles: list[InventoryTile] = []
        self._visiveis: list[InventoryTile] = []
        self._itens: list[dict] = []
        self._ordem = "valor"
        # Sem foco a grade nao recebe tecla nenhuma.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(t.SPACE_LG)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.viewport().installEventFilter(self)
        # QScrollArea pinta o viewport com a cor Base da paleta do sistema
        # -- branco no Windows. Sem isto a grade vira um retangulo claro no
        # meio do tema escuro.
        #
        # OPACO, nao transparente: a grade divide um QStackedWidget com a
        # tabela, e com fundo transparente a tabela de tras aparecia por
        # baixo dos tiles -- nomes de item flutuando sobre a grade.
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {t.BG_ELEVATED}; border: none; }}")
        self._scroll.viewport().setStyleSheet(
            f"background: {t.BG_ELEVATED};")
        self._holder = QWidget()
        self._holder.setStyleSheet(f"background: {t.BG_ELEVATED};")
        self._grid = QGridLayout(self._holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(t.SPACE_SM)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop
                                | Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._holder)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        raiz.addWidget(self._scroll, 1)

        self._detail = ItemDetailPanel()
        raiz.addWidget(self._detail, 0)

    def set_items(self, items: list) -> None:
        """Repovoa a grade. Ordena por valor: o que importa aparece antes."""
        for tile in self._tiles:
            tile.setParent(None)
            tile.deleteLater()
        self._tiles = []

        self._itens = [i for i in (items or []) if isinstance(i, dict)]
        ordenados = self._ordenar(self._itens)
        for item in ordenados:
            tile = InventoryTile(item)
            tile.clicked.connect(self._on_tile)
            self._tiles.append(tile)
        self._visiveis = list(self._tiles)
        self._reposicionar()
        self._detail.show_item(ordenados[0] if ordenados else None)
        if self._tiles:
            self._tiles[0].set_selected(True)

    # Chaves de ordenacao. "valor" e' o total do lote, nao o unitario: 21
    # caixas de R$ 1 pesam mais na carteira que uma skin de R$ 15.
    _ORDENS = ("valor", "nome", "qtd")

    def _ordenar(self, itens: list) -> list:
        if self._ordem == "nome":
            return sorted(itens, key=lambda i: (i.get("name") or "").lower())
        if self._ordem == "qtd":
            return sorted(itens, key=lambda i: (i.get("qty") or 1),
                          reverse=True)
        return sorted(
            itens,
            key=lambda i: ((_valor_do_tile(i)[0] or 0) * (i.get("qty") or 1)),
            reverse=True,
        )

    def set_order(self, ordem: str) -> None:
        """Reordena sem refazer os tiles (recriar perde a selecao)."""
        if ordem not in self._ORDENS or ordem == self._ordem:
            return
        self._ordem = ordem
        chave = {id(t.item): t for t in self._tiles}
        self._tiles = [chave[id(i)] for i in self._ordenar(self._itens)
                       if id(i) in chave]
        self._visiveis = [t for t in self._tiles if t.isVisibleTo(self)]
        self._reposicionar()

    def set_filter(self, texto: str) -> int:
        """Esconde os tiles que nao casam, recompacta e devolve quantos ficaram.

        Sem recompactar, esconder deixaria buracos: o QGridLayout guarda a
        posicao de cada tile, entao o item escondido levaria a celula dele
        junto e a grade viraria um tabuleiro furado.
        """
        alvo = (texto or "").strip().lower()
        visiveis = []
        for tile in self._tiles:
            casa = not alvo or alvo in (tile.item.get("name") or "").lower()
            tile.setVisible(casa)
            if casa:
                visiveis.append(tile)
        self._visiveis = visiveis
        self._reposicionar()
        return len(visiveis)

    def _reposicionar(self) -> None:
        """(Re)coloca os tiles visiveis em linha, na largura atual.

        Ponto unico de posicionamento: povoar, filtrar e redimensionar
        chamam daqui. Antes cada um tinha sua copia do calculo de linha e
        coluna, e o filtro esquecia de recompactar.
        """
        for pos, tile in enumerate(self._visiveis):
            self._grid.addWidget(tile, pos // self._columns,
                                 pos % self._columns)

    def _colunas_que_cabem(self) -> int:
        """Quantos tiles cabem na largura util do scroll."""
        largura = self._scroll.viewport().width()
        passo = TILE + self._grid.spacing()
        return max(1, (largura + self._grid.spacing()) // passo)

    def eventFilter(self, obj, evt):  # noqa: N802
        """Recalcula as colunas quando o VIEWPORT muda de tamanho.

        Fazer isso no resizeEvent desta widget nao funciona: quando ele
        dispara, o layout dos filhos ainda nao rodou e
        `viewport().width()` responde a largura ANTERIOR. No arranque a
        anterior e' quase zero, entao a grade travava em 2-3 colunas e
        nunca mais recalculava -- nenhum resize novo chegava pra
        corrigir. O viewport, esse, e' redimensionado exatamente quando a
        largura util muda.
        """
        if obj is self._scroll.viewport() and evt.type() == QEvent.Type.Resize:
            self._ajustar_colunas()
        return super().eventFilter(obj, evt)

    def _ajustar_colunas(self) -> None:
        cabem = self._colunas_que_cabem()
        if cabem != self._columns:
            self._columns = cabem
            self._reposicionar()

    def visible_count(self) -> int:
        return len(getattr(self, "_visiveis", self._tiles))

    def _on_tile(self, item: dict) -> None:
        for tile in self._tiles:
            tile.set_selected(tile.item is item)
        self._detail.show_item(item)
        self.item_selected.emit(item)

    # ── navegacao por teclado ─────────────────────────────
    def _indice_selecionado(self) -> int:
        for i, tile in enumerate(self._visiveis):
            if tile._selected:
                return i
        return -1

    def selecionar_por_indice(self, idx: int) -> None:
        if not self._visiveis:
            return
        idx = max(0, min(idx, len(self._visiveis) - 1))
        alvo = self._visiveis[idx]
        # `_on_tile` recebe o DICT do item, nao o tile -- a selecao compara
        # `tile.item is item`, e passar o widget deixava tudo desmarcado.
        self._on_tile(alvo.item)
        self._scroll.ensureWidgetVisible(alvo)

    def keyPressEvent(self, evt) -> None:  # noqa: N802
        """Setas andam na grade; Home/End vao aos extremos.

        A grade so' respondia a mouse. Com 31 cards e o painel de detalhe
        do lado, conferir item a item exigia um clique em cada um.
        """
        atual = self._indice_selecionado()
        passos = {
            Qt.Key.Key_Right: 1,
            Qt.Key.Key_Left: -1,
            Qt.Key.Key_Down: self._columns,
            Qt.Key.Key_Up: -self._columns,
        }
        tecla = evt.key()
        if tecla in passos:
            self.selecionar_por_indice(
                (atual if atual >= 0 else 0) + passos[tecla])
            evt.accept()
            return
        if tecla == Qt.Key.Key_Home:
            self.selecionar_por_indice(0)
            evt.accept()
            return
        if tecla == Qt.Key.Key_End:
            self.selecionar_por_indice(len(self._visiveis) - 1)
            evt.accept()
            return
        super().keyPressEvent(evt)

    def count(self) -> int:
        return len(self._tiles)

    # Largura nominal do sizeHint. NAO pode sair de `_columns`: `_columns`
    # passou a vir da largura, e um sizeHint que dependesse dele fecharia o
    # ciclo -- o layout encolhia o widget, o widget pedia menos colunas, e
    # a grade estabilizava em 3 colunas com meia tela vazia ao lado.
    _COLUNAS_NOMINAIS = 8

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(
            self._COLUNAS_NOMINAIS * (TILE_W + t.SPACE_SM) + 280, 520)
