"""Inventario em grade: tiles, selecao e as duas avaliacoes."""
from __future__ import annotations

import pytest

from skinvault.ui.inventory_grid import (
    InventoryGrid,
    InventoryTile,
    ItemDetailPanel,
)


def _item(nome, steam=10.0, market=7.0, prem=30.0, qty=1, icon=None):
    return {"name": nome, "qty": qty, "icon": icon, "type": "Rifle",
            "steam_net": steam, "market_net": market, "premium_pct": prem}


@pytest.fixture(autouse=True)
def app():
    """Mesmo ciclo de vida do test_ui_smoke.

    Criar QApplication de um jeito diferente entre arquivos derruba a suite
    inteira: o outro arquivo chama app.quit() no teardown e estes testes
    reusavam a instancia ja' encerrada.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


# ── tile ───────────────────────────────────────────────────────────


def test_tile_guarda_o_item(app):
    it = _item("AK-47 | Redline")
    tile = InventoryTile(it)
    assert tile.item is it


def test_tile_tooltip_traz_as_duas_avaliacoes(app):
    tile = InventoryTile(_item("AK-47 | Redline", steam=8.5, market=6.2,
                               prem=37.0))
    tip = tile.toolTip()
    assert "AK-47 | Redline" in tip
    assert "Steam" in tip and "Dinheiro real" in tip
    assert "+37" in tip


# ── tooltip multi-plataforma ───────────────────────────────────────
#
# A taxa varia demais entre plataformas (5% na CSGOTM contra 12% no
# Skinport), entao ordenar pelo BRUTO enganaria. Medido na AK-47 Redline
# FT em 2026-07-30: CSGOTM pagava R$ 155,75 liquidos e Skinport R$ 130,62.


def _com_mercados(nome="AK-47 | Redline"):
    it = _item(nome, steam=200.0, market=155.75, prem=28.0)
    it["mercados"] = [
        {"source": "csgotm", "gross_brl": 163.95, "net_brl": 155.75,
         "fee": 0.05, "premium_pct": 28.0},
        {"source": "skinport", "gross_brl": 154.37, "net_brl": 135.85,
         "fee": 0.12, "premium_pct": 36.0},
    ]
    return it


def test_tooltip_lista_todas_as_plataformas(app):
    tip = InventoryTile(_com_mercados()).toolTip()
    assert "CS.MONEY/TM" in tip
    assert "Skinport" in tip
    assert "155,75" in tip and "135,85" in tip


def test_tooltip_mostra_a_taxa_de_cada_uma(app):
    tip = InventoryTile(_com_mercados()).toolTip()
    assert "taxa 5%" in tip
    assert "taxa 12%" in tip


def test_tooltip_marca_quem_paga_mais(app):
    tip = InventoryTile(_com_mercados()).toolTip()
    linhas = [x for x in tip.splitlines() if "paga mais" in x]
    assert len(linhas) == 1
    assert "CS.MONEY/TM" in linhas[0]


def test_tooltip_com_uma_plataforma_nao_marca_vencedor(app):
    """Marcar 'paga mais' com uma opcao so' e' ruido."""
    it = _com_mercados()
    it["mercados"] = it["mercados"][:1]
    assert "paga mais" not in InventoryTile(it).toolTip()


def test_tooltip_separa_saldo_de_dinheiro(app):
    """O ponto do premio de 36%: saldo Steam nao e' dinheiro."""
    tip = InventoryTile(_com_mercados()).toolTip()
    assert "saldo" in tip
    assert "dinheiro" in tip.lower()


def test_tile_mostra_quantidade_no_tooltip(app):
    tip = InventoryTile(_item("Kilowatt Case", qty=21)).toolTip()
    assert "21" in tip


def test_tile_sem_preco_nao_quebra(app):
    tile = InventoryTile({"name": "X", "qty": 1})
    assert tile.item["name"] == "X"
    assert "X" in tile.toolTip()


def test_tile_emite_clique(app):
    """PyQt6 exige QPointF no QMouseEvent (QPoint nao casa a assinatura)."""
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    it = _item("AWP | Asiimov")
    tile = InventoryTile(it)
    recebidos = []
    tile.clicked.connect(recebidos.append)
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress,
                     QPointF(10, 10), QPointF(10, 10),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    tile.mousePressEvent(ev)
    assert recebidos and recebidos[0] is it


def test_tile_botao_direito_nao_seleciona(app):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    tile = InventoryTile(_item("X"))
    recebidos = []
    tile.clicked.connect(recebidos.append)
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress,
                     QPointF(10, 10), QPointF(10, 10),
                     Qt.MouseButton.RightButton, Qt.MouseButton.RightButton,
                     Qt.KeyboardModifier.NoModifier)
    tile.mousePressEvent(ev)
    assert recebidos == []


# ── grade ──────────────────────────────────────────────────────────


def test_grade_povoa_e_conta(app):
    g = InventoryGrid()
    g.set_items([_item(f"item {i}") for i in range(7)])
    assert g.count() == 7


def test_grade_ordena_por_valor_total(app):
    """21 caixas de R$1 valem mais que 1 skin de R$15 -- e vem antes."""
    g = InventoryGrid()
    g.set_items([
        _item("skin cara", steam=15.0, qty=1),
        _item("caixa barata", steam=1.0, qty=21),
        _item("meio", steam=8.0, qty=1),
    ])
    assert g._tiles[0].item["name"] == "caixa barata"   # 21.0
    assert g._tiles[1].item["name"] == "skin cara"      # 15.0
    assert g._tiles[2].item["name"] == "meio"           # 8.0


def test_grade_seleciona_o_primeiro_automaticamente(app):
    g = InventoryGrid()
    g.set_items([_item("a"), _item("b")])
    assert g._tiles[0]._selected is True
    assert g._tiles[1]._selected is False


def test_grade_troca_selecao_no_clique(app):
    g = InventoryGrid()
    g.set_items([_item("a", steam=9.0), _item("b", steam=1.0)])
    g._on_tile(g._tiles[1].item)
    assert g._tiles[0]._selected is False
    assert g._tiles[1]._selected is True


def test_grade_emite_item_selecionado(app):
    g = InventoryGrid()
    g.set_items([_item("a"), _item("b", steam=1.0)])
    vistos = []
    g.item_selected.connect(vistos.append)
    g._on_tile(g._tiles[1].item)
    assert vistos[0]["name"] == "b"


def test_grade_repovoar_limpa_os_antigos(app):
    g = InventoryGrid()
    g.set_items([_item(f"a{i}") for i in range(5)])
    g.set_items([_item("unico")])
    assert g.count() == 1


def test_grade_vazia_e_segura(app):
    g = InventoryGrid()
    g.set_items([])
    assert g.count() == 0
    g.set_items(None)
    assert g.count() == 0


def test_grade_ignora_entrada_invalida(app):
    g = InventoryGrid()
    g.set_items([_item("bom"), "nao e' dict", None])
    assert g.count() == 1


# ── painel de detalhe ──────────────────────────────────────────────


def test_painel_mostra_as_duas_colunas(app):
    p = ItemDetailPanel()
    p.show_item(_item("AK-47 | Redline", steam=149.35, market=111.93,
                      prem=38.0))
    assert "Redline" in p._nome.text()
    assert "149" in p._linhas["steam"][0].text()
    assert "111" in p._linhas["market"][0].text()


def test_painel_explica_que_saldo_nao_e_dinheiro(app):
    """A distincao e' o ponto da tela -- nao pode sumir."""
    p = ItemDetailPanel()
    p.show_item(_item("X"))
    assert "saldo" in p._linhas["steam"][1].text().lower()
    assert "dinheiro" in p._linhas["market"][1].text().lower()


def test_painel_premio_positivo_avisa_do_travamento(app):
    p = ItemDetailPanel()
    p.show_item(_item("X", prem=36.0))
    txt = p._premio.text()
    assert "+36%" in txt
    assert "travado" in txt.lower()


def test_painel_premio_negativo_indica_o_outro_lado(app):
    p = ItemDetailPanel()
    p.show_item(_item("X", prem=-4.0))
    assert "-4%" in p._premio.text()
    assert "fora da steam" in p._premio.text().lower()


def test_painel_sem_cotacao_de_mercado(app):
    p = ItemDetailPanel()
    p.show_item(_item("X", market=None, prem=None))
    assert "sem cotação" in p._linhas["market"][0].text()
    assert p._premio.text() == ""


def test_painel_nao_desenha_borda_nos_rotulos(app):
    """QLabel herda de QFrame: seletor de tipo poria caixa em cada rotulo.

    Regressao visual -- a primeira versao usava `QFrame { border: ... }` e
    todo texto do painel aparecia dentro de um retangulo.
    """
    p = ItemDetailPanel()
    css = p.styleSheet()
    assert p.objectName() == "itemDetailPanel"
    assert "QFrame {" not in css, "seletor de tipo volta a vazar pros filhos"
    assert "#itemDetailPanel" in css
    assert "QLabel" in css and "border: none" in css


def test_painel_limpa_com_none(app):
    p = ItemDetailPanel()
    p.show_item(_item("X"))
    p.show_item(None)
    assert "Selecione" in p._nome.text()
    assert p._linhas["steam"][0].text() == "—"
