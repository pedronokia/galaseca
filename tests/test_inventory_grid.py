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


# ── etiqueta do tile: valor e de onde ele vem ──────────────────────
#
# Com a Steam racionada, `steam_net` e' None em tudo e a grade virava uma
# parede de travessoes -- com o valor de fora ja' dentro do dict do item.


def test_etiqueta_prefere_o_saldo_da_steam(app):
    from skinvault.ui.inventory_grid import _valor_do_tile
    assert _valor_do_tile(_item("x", steam=10.0, market=7.0)) == (10.0, "saldo")


def test_etiqueta_cai_pro_valor_de_fora_sem_saldo(app):
    from skinvault.ui.inventory_grid import _valor_do_tile
    assert _valor_do_tile(
        _item("x", steam=None, market=7.0)) == (7.0, "fora")


def test_etiqueta_usa_o_melhor_mercado_quando_ha_lista(app):
    """`mercados` ja' vem ordenado pelo liquido -- o primeiro paga mais."""
    from skinvault.ui.inventory_grid import _valor_do_tile
    it = _item("x", steam=None, market=7.0)
    it["mercados"] = [{"source": "csgotm", "net_brl": 9.5, "fee": 0.05},
                      {"source": "skinport", "net_brl": 8.0, "fee": 0.12}]
    assert _valor_do_tile(it) == (9.5, "fora")


def test_etiqueta_sem_nenhuma_cotacao(app):
    from skinvault.ui.inventory_grid import _valor_do_tile
    assert _valor_do_tile(_item("x", steam=None, market=None)) == (None, "")


def test_origem_viaja_junto_com_o_numero(app):
    """Saldo travado e dinheiro nao sao a mesma moeda -- nao podem sair
    com a mesma etiqueta."""
    from skinvault.ui.inventory_grid import _valor_do_tile
    _, origem_steam = _valor_do_tile(_item("x", steam=10.0))
    _, origem_fora = _valor_do_tile(_item("x", steam=None, market=10.0))
    assert origem_steam != origem_fora


def test_grade_ordena_pelo_valor_exibido_sem_saldo(app):
    """Sem steam_net a chave era None em tudo e a ordem saia arbitraria."""
    g = InventoryGrid()
    g.set_items([
        _item("barata", steam=None, market=1.0, qty=1),
        _item("cara", steam=None, market=30.0, qty=1),
        _item("media", steam=None, market=5.0, qty=1),
    ])
    assert [tl.item["name"] for tl in g._tiles] == ["cara", "media", "barata"]


# ── rotulo do card ─────────────────────────────────────────────────
#
# O card mostra o nome SEMPRE, nao so' quando falta icone: com 96px e so'
# a imagem, saber qual skin era exigia passar o mouse em cada tile.


def test_rotulo_usa_o_acabamento_nao_a_arma(app):
    """Com o icone ao lado, o que identifica e' o acabamento -- e' assim
    que os sites de troca rotulam."""
    tile = InventoryTile(_item("AWP | Asiimov (Testada em Campo)"))
    assert tile._rotulo_curto() == "Asiimov"


def test_rotulo_tira_o_desgaste(app):
    tile = InventoryTile(_item("AK-47 | Redline (Field-Tested)"))
    assert tile._rotulo_curto() == "Redline"


def test_rotulo_de_faca_ignora_a_estrela(app):
    tile = InventoryTile(_item("★ Falchion Knife | Autotronic (FT)"))
    assert tile._rotulo_curto() == "Autotronic"


def test_rotulo_de_container_mantem_o_nome(app):
    """Nome de caixa ja' e' curto e nao tem barra pra cortar."""
    tile = InventoryTile(_item("Caixa Kilowatt"))
    assert tile._rotulo_curto() == "Caixa Kilowatt"


def test_rotulo_aguenta_nome_vazio(app):
    assert InventoryTile(_item(""))._rotulo_curto() == ""


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
    assert "149" in p._steam_recebe.text()
    assert "111" in p._fora.text()


def test_painel_explica_que_saldo_nao_e_dinheiro(app):
    """A distincao e' o ponto da tela -- nao pode sumir."""
    p = ItemDetailPanel()
    p.show_item(_item("X"))
    assert "saldo" in p._steam_recebe.text().lower()
    assert "dinheiro" in p._titulo_fora.text().lower()


def test_painel_premio_positivo_avisa_do_travamento(app):
    p = ItemDetailPanel()
    p.show_item(_item("X", prem=36.0))
    txt = p._premio.text()
    assert "+36%" in txt
    assert "saldo" in txt.lower()


def test_painel_premio_negativo_indica_o_outro_lado(app):
    p = ItemDetailPanel()
    p.show_item(_item("X", prem=-4.0))
    assert "-4%" in p._premio.text()
    assert "fora da steam" in p._premio.text().lower()


def test_painel_sem_cotacao_de_mercado(app):
    p = ItemDetailPanel()
    p.show_item(_item("X", market=None, prem=None))
    assert "não listado fora" in p._fora.text()
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
    assert p._steam_anuncio.text() == "—"
    assert p._steam_recebe.text() == "—"
    assert p._fora.text() == "—"
    assert p._piso.text() == ""


# ── por quanto vender ──────────────────────────────────────────────
#
# O painel antes mostrava dois liquidos e parava -- nao respondia "por
# quanto anuncio?". A logica esta' em portfolio.sell_guidance, ja'
# testada em test_sell_guidance.py; aqui so' a exibicao.


def _com_guidance(custo=None, preco=229.26, lowest=225.0):
    from skinvault import portfolio
    it = _item("AK-47 | Redline", steam=199.36, market=155.75, prem=28.0)
    it["guidance"] = portfolio.sell_guidance(
        current_price=preco, cost=custo, lowest=lowest)
    it["cost"] = custo
    return it


def test_painel_esconde_o_icone_quando_nao_ha(app):
    """Sem esconder, o minimumHeight de 120px deixava um bloco vazio
    empurrando o nome pra baixo."""
    p = ItemDetailPanel()
    p.show_item(_item("Sem icone", icon=None))
    assert p._icon.isVisibleTo(p) is False


def test_painel_diz_por_quanto_anunciar(app):
    p = ItemDetailPanel()
    p.show_item(_com_guidance())
    assert "229" in p._steam_anuncio.text()


def test_painel_diz_o_que_sobra_do_anuncio(app):
    """229,26 anunciado devolve 199,36 -- a taxa come 13% do anuncio."""
    p = ItemDetailPanel()
    p.show_item(_com_guidance())
    assert "199" in p._steam_recebe.text()
    assert "saldo" in p._steam_recebe.text().lower()


def test_painel_traz_o_cenario_de_venda_rapida(app):
    p = ItemDetailPanel()
    p.show_item(_com_guidance(lowest=225.0))
    assert "224,99" in p._steam_rapido.text()


def test_painel_sem_custo_admite_que_nao_sabe_o_lucro(app):
    """Posicao vinda do sync nao tem custo. Prometer lucro ali seria
    inventar numero."""
    p = ItemDetailPanel()
    p.show_item(_com_guidance(custo=None))
    txt = p._piso.text().lower()
    assert "sem custo" in txt
    assert "lucra" in txt


def test_painel_com_custo_mostra_piso_e_lucro(app):
    p = ItemDetailPanel()
    p.show_item(_com_guidance(custo=100.0))
    txt = p._piso.text()
    assert "115,00" in txt          # piso = custo * 1,15
    assert "lucro" in txt.lower()


def test_painel_com_custo_alto_mostra_prejuizo_e_gap(app):
    """Custo 250, alvo 229,26: o alvo nao cobre, e falta subir."""
    p = ItemDetailPanel()
    p.show_item(_com_guidance(custo=250.0))
    txt = p._piso.text().lower()
    assert "prejuízo" in txt
    assert "precisa subir" in txt


def test_painel_lista_plataformas_ordenadas_pelo_liquido(app):
    it = _com_guidance()
    it["mercados"] = [
        {"source": "csgotm", "gross_brl": 163.95, "net_brl": 155.75,
         "fee": 0.05, "premium_pct": 28.0},
        {"source": "skinport", "gross_brl": 154.37, "net_brl": 135.85,
         "fee": 0.12, "premium_pct": 36.0},
    ]
    p = ItemDetailPanel()
    p.show_item(it)
    txt = p._fora.text()
    assert txt.index("CS.MONEY/TM") < txt.index("Skinport")
    assert "155,75" in txt and "135,85" in txt
    assert "taxa 5%" in txt and "taxa 12%" in txt


# ── filtro da grade ────────────────────────────────────────────────
#
# O campo de busca ficava desabilitado na grade: uma caixa grande e morta
# no topo da tela, justamente na visao que abre por padrao.


def test_filtro_esconde_o_que_nao_casa(app):
    g = InventoryGrid()
    g.set_items([_item("AK-47 | Redline"), _item("AWP | Asiimov"),
                 _item("Kilowatt Case")])
    assert g.set_filter("awp") == 1
    visiveis = [tl for tl in g._tiles if tl.isVisibleTo(g)]
    assert len(visiveis) == 1
    assert visiveis[0].item["name"] == "AWP | Asiimov"


def test_filtro_e_case_insensitive(app):
    g = InventoryGrid()
    g.set_items([_item("AWP | Asiimov")])
    assert g.set_filter("ASIIMOV") == 1


def test_filtro_vazio_traz_todos_de_volta(app):
    g = InventoryGrid()
    g.set_items([_item("a"), _item("b"), _item("c")])
    g.set_filter("a")
    assert g.set_filter("") == 3
    assert all(tl.isVisibleTo(g) for tl in g._tiles)


def test_filtro_recompacta_a_grade(app):
    """Sem recompactar, o tile escondido levava a celula junto e a grade
    virava um tabuleiro furado."""
    g = InventoryGrid(columns=2)
    g.set_items([_item("zzz1"), _item("alvo A"), _item("zzz2"),
                 _item("alvo B")])
    g.set_filter("alvo")
    posicoes = []
    for tl in g._tiles:
        if not tl.isVisibleTo(g):
            continue
        idx = g._grid.indexOf(tl)
        r, c, _, _ = g._grid.getItemPosition(idx)
        posicoes.append((r, c))
    assert sorted(posicoes) == [(0, 0), (0, 1)]


def test_filtro_sem_match_zera(app):
    g = InventoryGrid()
    g.set_items([_item("AWP | Asiimov")])
    assert g.set_filter("nao existe") == 0


def test_repovoar_reseta_o_filtro(app):
    g = InventoryGrid()
    g.set_items([_item("a"), _item("b")])
    g.set_filter("a")
    g.set_items([_item("x"), _item("y"), _item("z")])
    assert g.visible_count() == 3


# ── procedencia no painel ──────────────────────────────────────────
#
# A metade de baixo do painel estava vazia, e faltava ali o unico dado da
# tela que nao depende da Steam responder: de onde o item vem.


def _texto(label):
    import re
    return re.sub(r"<[^>]+>", "", label.text().replace("<br>", " "))


def test_container_mostra_o_proprio_nome(app):
    p = ItemDetailPanel()
    p.show_item({"name": "Kilowatt Case", "qty": 1})
    txt = _texto(p._origem)
    assert "Kilowatt Case" in txt
    assert "Vem de" not in txt, "o container nao 'vem de' si mesmo"


def test_skin_aponta_a_caixa_de_origem(app):
    p = ItemDetailPanel()
    p.show_item({"name": "AWP | Asiimov (Field-Tested)", "qty": 1})
    txt = _texto(p._origem)
    assert "Vem de" in txt
    assert "Operation Phoenix Weapon Case" in txt


def test_descontinuada_diz_que_nao_cai_mais(app):
    p = ItemDetailPanel()
    p.show_item({"name": "Chroma 2 Case", "qty": 1})
    txt = _texto(p._origem)
    assert "não cai mais em drop" in txt
    assert "2015" in txt


def test_ativa_diz_que_ainda_cai(app):
    p = ItemDetailPanel()
    p.show_item({"name": "Kilowatt Case", "qty": 1})
    assert "ainda cai em drop" in _texto(p._origem)


def test_item_desconhecido_nao_ganha_afirmacao(app):
    """`case_status` NUNCA volta vazio: desconhecido vem com status
    'unknown' e is_discontinued=False. Ler esse False como "ainda cai em
    drop" seria afirmar sobre um item que o app nao conhece."""
    p = ItemDetailPanel()
    for nome in ("Sticker | rallen | Paris 2023",
                 "Sealed Genesis Terminal",
                 "item que nao existe"):
        p.show_item({"name": nome, "qty": 1})
        txt = _texto(p._origem)
        assert "não está mapeado" in txt, nome
        assert "drop" not in txt, nome


def test_painel_limpo_zera_a_procedencia(app):
    p = ItemDetailPanel()
    p.show_item({"name": "Kilowatt Case", "qty": 1})
    p.show_item(None)
    assert _texto(p._origem).strip() == "—"


# ── grade responsiva ───────────────────────────────────────────────
#
# 8 colunas fixas deixavam ~700px mortos numa janela larga e forcavam
# rolagem numa estreita.


def _posicoes(g):
    out = []
    for tl in g._visiveis:
        idx = g._grid.indexOf(tl)
        r, c, _, _ = g._grid.getItemPosition(idx)
        out.append((r, c))
    return out


def _com_largura(g, w, h=600):
    """Aplica largura de verdade.

    `resize()` sozinho nao chega no viewport do QScrollArea: sem passe de
    layout ele mantem o tamanho anterior. WA_DontShowOnScreen faz o layout
    rodar sem abrir janela nem roubar foco.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    g.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    g.show()
    g.resize(w, h)
    QApplication.instance().processEvents()
    return g


def test_colunas_acompanham_a_largura(app):
    g = InventoryGrid()
    largo = _com_largura(g, 1400)._colunas_que_cabem()
    estreito = _com_largura(g, 500)._colunas_que_cabem()
    assert largo > estreito >= 1


def test_nunca_zero_colunas(app):
    """Largura minuscula nao pode virar divisao por zero no reposicionar."""
    g = InventoryGrid()
    assert _com_largura(g, 10, 10)._colunas_que_cabem() >= 1


def test_reposicionar_preenche_linha_a_linha(app):
    g = InventoryGrid()
    g.set_items([_item(f"i{n}") for n in range(5)])
    g._columns = 3
    g._reposicionar()
    assert _posicoes(g) == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]


def test_resize_reflui_os_tiles(app):
    g = InventoryGrid()
    g.set_items([_item(f"i{n}") for n in range(12)])
    g._columns = 2
    g._reposicionar()
    antes = max(r for r, _ in _posicoes(g))
    g._columns = 6
    g._reposicionar()
    depois = max(r for r, _ in _posicoes(g))
    assert depois < antes, "mais colunas tem que dar menos linhas"


def test_filtro_e_largura_usam_o_mesmo_calculo(app):
    """Filtrar depois de mudar a largura nao pode voltar pro layout
    antigo -- os dois passam pelo mesmo _reposicionar."""
    g = InventoryGrid()
    g.set_items([_item("alvo 1"), _item("zzz"), _item("alvo 2")])
    g._columns = 5
    g.set_filter("alvo")
    assert _posicoes(g) == [(0, 0), (0, 1)]


# ── colunas: quando ler a largura ──────────────────────────────────


def test_colunas_recalculam_quando_o_viewport_muda(app):
    """Ler a largura no resizeEvent DESTA widget nao funciona: quando ele
    dispara, o layout dos filhos ainda nao rodou e o viewport responde a
    largura anterior -- quase zero no arranque. A grade travava em 2-3
    colunas e nenhum resize novo chegava pra corrigir."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    g = InventoryGrid()
    g.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    g.show()
    g.resize(1500, 700)
    QApplication.instance().processEvents()
    largo = g._columns
    g.resize(560, 700)
    QApplication.instance().processEvents()
    assert largo > g._columns >= 1


# ── navegacao por teclado ──────────────────────────────────────────


def _grade_com(n, cols=3):
    g = InventoryGrid()
    g.set_items([_item(f"i{k}", steam=float(n - k)) for k in range(n)])
    g._columns = cols
    g._reposicionar()
    return g


def test_seta_direita_anda_um(app):
    g = _grade_com(6)
    g.selecionar_por_indice(0)
    g.selecionar_por_indice(g._indice_selecionado() + 1)
    assert g._indice_selecionado() == 1


def test_seta_baixo_anda_uma_linha(app):
    g = _grade_com(9, cols=3)
    g.selecionar_por_indice(0)
    g.selecionar_por_indice(g._indice_selecionado() + g._columns)
    assert g._indice_selecionado() == 3


def test_selecao_nao_sai_da_grade(app):
    """Andar antes do primeiro ou depois do ultimo tem que grudar."""
    g = _grade_com(4)
    g.selecionar_por_indice(-5)
    assert g._indice_selecionado() == 0
    g.selecionar_por_indice(99)
    assert g._indice_selecionado() == 3


def test_teclado_em_grade_vazia_nao_quebra(app):
    g = InventoryGrid()
    g.selecionar_por_indice(0)
    assert g._indice_selecionado() == -1


def test_navegacao_respeita_o_filtro(app):
    """Andar tem que percorrer o que esta' VISIVEL, nao o inventario todo."""
    g = InventoryGrid()
    g.set_items([_item("alvo A"), _item("zzz"), _item("alvo B")])
    g.set_filter("alvo")
    g.selecionar_por_indice(1)
    assert g._visiveis[g._indice_selecionado()].item["name"] == "alvo B"


# ── total do lote no painel ────────────────────────────────────────


def test_painel_mostra_o_total_do_lote(app):
    """21 caixas de R$ 0,99 sao R$ 20,79 -- o unitario nao decide nada."""
    p = ItemDetailPanel()
    p.show_item({"name": "Kilowatt Case", "qty": 21, "steam_net": 0.99,
                 "type": "Container"})
    assert "×21" in p._tipo.text()
    assert "20,79" in p._tipo.text()


def test_item_unico_nao_ganha_total(app):
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1, "steam_net": 5.0, "type": "Rifle"})
    assert "total" not in p._tipo.text()


def test_lote_sem_cotacao_nao_inventa_total(app):
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 7, "steam_net": None,
                 "market_net": None, "type": "Rifle"})
    assert "×7" in p._tipo.text()
    assert "total" not in p._tipo.text()


# ── ordenacao ──────────────────────────────────────────────────────


def test_ordem_padrao_e_por_valor_do_lote(app):
    """21 caixas de R$ 1 pesam mais que uma skin de R$ 15."""
    g = InventoryGrid()
    g.set_items([_item("skin", steam=15.0), _item("lote", steam=1.0, qty=21)])
    assert g._tiles[0].item["name"] == "lote"


def test_ordem_por_nome(app):
    g = InventoryGrid()
    g.set_items([_item("Zulu", steam=99.0), _item("Alfa", steam=1.0)])
    g.set_order("nome")
    assert [tl.item["name"] for tl in g._tiles] == ["Alfa", "Zulu"]


def test_ordem_por_quantidade(app):
    g = InventoryGrid()
    g.set_items([_item("um", qty=1), _item("muitos", qty=21),
                 _item("alguns", qty=5)])
    g.set_order("qtd")
    assert [tl.item["name"] for tl in g._tiles] == ["muitos", "alguns", "um"]


def test_reordenar_nao_recria_os_tiles(app):
    """Recriar perderia a selecao e o icone ja' carregado."""
    g = InventoryGrid()
    g.set_items([_item("a", steam=1.0), _item("b", steam=2.0)])
    antes = set(id(tl) for tl in g._tiles)
    g.set_order("nome")
    assert set(id(tl) for tl in g._tiles) == antes


def test_ordem_desconhecida_e_ignorada(app):
    g = InventoryGrid()
    g.set_items([_item("a")])
    g.set_order("inexistente")
    assert g._ordem == "valor"


# ── teto de compra ─────────────────────────────────────────────────


def test_painel_diz_ate_quanto_pagar(app):
    """A tela sabia dizer por quanto VENDER e nao por quanto COMPRAR."""
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1,
                 "guidance": {"target_list": 100.0}})
    txt = _texto(p._compra)
    assert "empatar" in txt and "R$" in txt
    assert "20%" in txt


def test_teto_de_compra_fica_abaixo_do_alvo(app):
    """Pagar o proprio preco de venda ja' nasce no prejuizo: ha' taxa."""
    from skinvault import portfolio
    assert portfolio.max_buy_price(100.0) < 100.0
    assert portfolio.max_buy_price(100.0, margin_pct=20.0) < \
        portfolio.max_buy_price(100.0)


def test_sem_referencia_nao_inventa_teto(app):
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1})
    assert "referência" in _texto(p._compra)


# ── score no painel ────────────────────────────────────────────────
#
# O score ja' vivia na position (gravado pelo "Validar score") e so'
# aparecia numa coluna da tabela -- quem usa a grade nunca o via.


def test_painel_mostra_o_score(app):
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1, "score": 78})
    assert "78" in _texto(p._score)


def test_score_diz_a_idade(app):
    """Score e' sinal de 60-90d mas foi calculado num preco de algum
    momento: sem a data, numero velho passa por leitura de agora."""
    import time
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1, "score": 78,
                 "score_ts": time.time() - 3 * 86400})
    assert "3 dias" in _texto(p._score)


def test_score_de_hoje(app):
    import time
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1, "score": 90, "score_ts": time.time()})
    assert "hoje" in _texto(p._score)


def test_sem_score_a_linha_some(app):
    """Linha vazia ocupando espaco e' pior que linha nenhuma."""
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1})
    assert p._score.text() == ""


def test_score_sem_data_nao_inventa_idade(app):
    p = ItemDetailPanel()
    p.show_item({"name": "X", "qty": 1, "score": 55})
    txt = _texto(p._score)
    assert "55" in txt
    assert "dias" not in txt and "hoje" not in txt


# ── esqueleto de carregamento ──────────────────────────────────────
#
# Sob rate limit a avaliacao leva minutos (backoff por item) e a tela
# ficava com um spinner centralizado num vazio.


def test_esqueleto_cria_a_quantidade_pedida(app):
    g = InventoryGrid()
    g.set_skeleton(31)
    assert g.count() == 31


def test_esqueleto_tem_teto(app):
    """Inventario gigante nao pode virar centenas de widgets so' pra
    dizer 'carregando'."""
    g = InventoryGrid()
    g.set_skeleton(5000)
    assert g.count() <= 60


def test_dados_substituem_o_esqueleto(app):
    g = InventoryGrid()
    g.set_skeleton(20)
    g.set_items([_item("a"), _item("b")])
    assert g.count() == 2
    assert all(getattr(tl, "item", None) is not None for tl in g._tiles)


def test_filtrar_durante_o_carregamento_nao_quebra(app):
    """Fantasma nao tem `.item`; filtrar nao pode explodir nem escondê-los."""
    g = InventoryGrid()
    g.set_skeleton(10)
    assert g.set_filter("qualquer coisa") == 10


def test_ordenar_durante_o_carregamento_nao_quebra(app):
    g = InventoryGrid()
    g.set_skeleton(10)
    g.set_order("nome")
    assert g.count() == 10


def test_esqueleto_zera_a_selecao(app):
    g = InventoryGrid()
    g.set_items([_item("a")])
    g.set_skeleton(5)
    assert g._indice_selecionado() == -1


# ── filtro por categoria (layout do Mercado da Comunidade) ─────────


def _cat(nome, **kw):
    it = _item(nome, **kw)
    it["raw_name"] = nome
    return it


def test_categorias_saem_dos_itens(app):
    g = InventoryGrid()
    g.set_items([_cat("Kilowatt Case"), _cat("Revolution Case"),
                 _cat("AK-47 | Redline (Field-Tested)")])
    assert dict(g.categorias()) == {"Caixas e cápsulas": 2, "Skins": 1}


def test_filtrar_por_categoria(app):
    g = InventoryGrid()
    g.set_items([_cat("Kilowatt Case"),
                 _cat("AK-47 | Redline (Field-Tested)")])
    assert g.set_category("Caixas e cápsulas") == 1
    assert g._visiveis[0].item["name"] == "Kilowatt Case"


def test_categoria_none_traz_todos(app):
    g = InventoryGrid()
    g.set_items([_cat("Kilowatt Case"),
                 _cat("AK-47 | Redline (Field-Tested)")])
    g.set_category("Skins")
    assert g.set_category(None) == 2


def test_categoria_compoe_com_o_texto(app):
    """Escolher "Caixas" e digitar "kilo" tem que sobrar so' as caixas
    cujo nome casa -- um filtro nao substitui o outro."""
    g = InventoryGrid()
    g.set_items([_cat("Kilowatt Case"), _cat("Revolution Case"),
                 _cat("AK-47 | Redline (Field-Tested)")])
    g.set_category("Caixas e cápsulas")
    assert g.set_filter("kilo") == 1


def test_limpar_texto_mantem_a_categoria(app):
    g = InventoryGrid()
    g.set_items([_cat("Kilowatt Case"),
                 _cat("AK-47 | Redline (Field-Tested)")])
    g.set_category("Caixas e cápsulas")
    g.set_filter("kilo")
    assert g.set_filter("") == 1, "limpar o texto nao pode limpar a categoria"


def test_categorias_vazias_sem_itens(app):
    assert InventoryGrid().categorias() == []
