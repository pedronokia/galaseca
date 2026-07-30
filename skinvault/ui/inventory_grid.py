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

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
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

TILE = 96
_BADGE_H = 20


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
        self.setFixedSize(TILE, TILE + _BADGE_H)
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
                    TILE - 12, TILE - 12,
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
        corpo = QRect(0, 0, TILE, TILE)

        fundo = t.SURFACE_HOV if (self._hover or self._selected) else t.SURFACE
        p.setBrush(QColor(fundo))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(corpo, t.RADIUS_SM, t.RADIUS_SM)

        if self._selected:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t.TEXT), 2))
            p.drawRoundedRect(corpo.adjusted(1, 1, -1, -1),
                              t.RADIUS_SM, t.RADIUS_SM)

        if self._pix:
            x = (TILE - self._pix.width()) // 2
            y = (TILE - self._pix.height()) // 2
            p.drawPixmap(x, y, self._pix)
        else:
            p.setPen(QColor(t.TEXT_MUTED))
            p.drawText(corpo, Qt.AlignmentFlag.AlignCenter, "?")

        qtd = self.item.get("qty", 1)
        if qtd > 1:
            p.setPen(QColor(t.TEXT))
            p.drawText(corpo.adjusted(0, 4, -6, 0),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                       f"{qtd}")

        # Etiqueta de preco: saldo Steam, que e' o numero que a Steam mostra.
        preco = self.item.get("steam_net")
        p.setPen(QColor(t.TEXT if preco is not None else t.TEXT_MUTED))
        p.drawText(QRect(0, TILE, TILE, _BADGE_H),
                   Qt.AlignmentFlag.AlignCenter,
                   t.brl(preco) if preco is not None else "—")
        p.end()


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
        self._linhas: dict = {}
        for chave, rotulo in (("steam", "Vendendo na Steam"),
                              ("market", "Vendendo fora")):
            cap = QLabel(rotulo)
            cap.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};")
            val = QLabel("—")
            val.setStyleSheet(
                f"color: {t.TEXT}; font-size: {t.FS_STAT}; font-weight: 600;")
            sub = QLabel("")
            sub.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};")
            v.addWidget(cap)
            v.addWidget(val)
            v.addWidget(sub)
            v.addSpacing(t.SPACE_SM)
            self._linhas[chave] = (val, sub)

        self._premio = QLabel("")
        self._premio.setWordWrap(True)
        self._premio.setStyleSheet(f"font-size: {t.FS_MUTED};")
        v.addWidget(self._premio)
        v.addStretch(1)

    def show_item(self, item: dict | None) -> None:
        if not item:
            self._nome.setText("Selecione um item")
            self._tipo.setText("")
            self._icon.clear()
            for val, sub in self._linhas.values():
                val.setText("—")
                sub.setText("")
            self._premio.setText("")
            return

        self._nome.setText(item.get("name", ""))
        qtd = item.get("qty", 1)
        tipo = item.get("type") or ""
        self._tipo.setText(f"{tipo}   ×{qtd}" if qtd > 1 else tipo)

        p = icons.local_path(item.get("icon"))
        if p:
            pm = QPixmap(str(p))
            if not pm.isNull():
                self._icon.setPixmap(pm.scaled(
                    160, 120, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        else:
            self._icon.clear()

        val, sub = self._linhas["steam"]
        sn = item.get("steam_net")
        val.setText(t.brl(sn) if sn is not None else "—")
        sub.setText("saldo, so' compra na Steam")

        val, sub = self._linhas["market"]
        mn = item.get("market_net")
        val.setText(t.brl(mn) if mn is not None else "sem cotação")
        sub.setText("dinheiro de verdade" if mn is not None
                    else "item não listado fora")

        prem = item.get("premium_pct")
        if prem is None:
            self._premio.setText("")
        else:
            cor = t.POSITIVE if prem > 0 else t.DANGER
            texto = ("A Steam paga mais — mas em saldo travado."
                     if prem > 0 else
                     "Fora da Steam paga mais, e em dinheiro.")
            self._premio.setText(
                f"<span style='color:{cor}'><b>{prem:+.0f}%</b></span> "
                f"<span style='color:{t.TEXT_MUTED}'>{texto}</span>")


class InventoryGrid(QWidget):
    """Grade rolavel de tiles + painel de detalhe."""

    item_selected = pyqtSignal(dict)

    def __init__(self, columns: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._columns = max(1, columns)
        self._tiles: list[InventoryTile] = []

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(t.SPACE_LG)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
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

        ordenados = sorted(
            [i for i in (items or []) if isinstance(i, dict)],
            key=lambda i: ((i.get("steam_net") or 0) * (i.get("qty") or 1)),
            reverse=True,
        )
        for idx, item in enumerate(ordenados):
            tile = InventoryTile(item)
            tile.clicked.connect(self._on_tile)
            self._grid.addWidget(tile, idx // self._columns,
                                 idx % self._columns)
            self._tiles.append(tile)
        self._detail.show_item(ordenados[0] if ordenados else None)
        if self._tiles:
            self._tiles[0].set_selected(True)

    def _on_tile(self, item: dict) -> None:
        for tile in self._tiles:
            tile.set_selected(tile.item is item)
        self._detail.show_item(item)
        self.item_selected.emit(item)

    def count(self) -> int:
        return len(self._tiles)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._columns * (TILE + t.SPACE_SM) + 280, 520)
