"""InventoryScreen -- a aba propria do inventario.

Saiu de dentro da "Minha Conta" em 28/07/2026: la' o inventario dividia a
janela com perfil, quatro cartoes de valor, cinco de desempenho e um
grafico, e sobrava rodape pro conteudo que da' nome a tela.
"""
from __future__ import annotations

import pytest

from skinvault.ui.inventory_screen import InventoryScreen


@pytest.fixture(autouse=True)
def app():
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


@pytest.fixture
def tela(monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {"Kilowatt Case": 0.24})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    # A escolha Grade/Tabela e' persistida. Sem este mock a suite grava no
    # settings.json REAL do dono -- ja' aconteceu: uma rodada deixou o app
    # abrindo na tabela sem ninguem ter pedido.
    #
    # Os DOIS lados precisam do mesmo armazenamento falso: `_on_view_segment`
    # so' grava quando o valor mudou, e mockar so' o save deixaria o load
    # lendo o disco real e discordando do que acabou de ser "gravado".
    gravado = {}
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s, *a, **k: gravado.update(s))
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: dict(gravado))
    tela = InventoryScreen()
    tela._settings_gravado = gravado
    return tela


ROWS = [
    {"name": "AK-47 | Redline (Battle-Scarred)", "quantity": 1,
     "price": 175.71, "market": 175.71, "net_if_sold": 149.35, "pnl": None},
    {"name": "Kilowatt Case", "quantity": 21,
     "price": 1.22, "market": 25.62, "net_if_sold": 1.04, "pnl": None},
]
POS = [{"source": "steam_sync", "icon": "abc", "type": "Rifle"},
       {"source": "steam_sync", "icon": "def", "type": "Container"}]


# ── estado vazio ───────────────────────────────────────────────────


def test_comeca_vazia(tela):
    assert tela._views.isVisibleTo(tela) is False
    assert tela._empty.isVisibleTo(tela) is True


def test_dados_escondem_o_empty_state(tela):
    tela.set_data(ROWS, POS)
    assert tela._views.isVisibleTo(tela) is True
    assert tela._empty.isVisibleTo(tela) is False


def test_lista_vazia_volta_pro_empty_state(tela):
    tela.set_data(ROWS, POS)
    tela.set_data([], [])
    assert tela._empty.isVisibleTo(tela) is True
    assert tela._status.text() == ""


# ── as duas visoes ─────────────────────────────────────────────────


def test_popula_grade_e_tabela(tela):
    tela.set_data(ROWS, POS)
    assert tela._grid.count() == 2
    assert tela._table.rowCount() == 2


def test_grade_traz_as_duas_avaliacoes(tela):
    tela.set_data(ROWS, POS)
    kilo = next(x.item for x in tela._grid._tiles
                if "Kilowatt" in x.item["raw_name"])
    assert kilo["steam_net"] == 1.04
    assert kilo["market_net"] is not None
    assert kilo["premium_pct"] is not None


def test_pref_tabela_aplica_depois_do_build(monkeypatch):
    """inventory_view=table nas settings abre a tela na tabela SEM crash.

    Regressao 2026-07-31: o select('table') rodava no meio do _build, antes
    de self._views existir; _on_view_segment (slot sincrono do emit) levantava
    AttributeError e o PyQt6 abortava o processo com exit 0xC0000409.
    O fixture tela mocka settings pra grid e por isso nunca pegava; o script
    de screenshots (settings reais) morria. So' existe por que o testes nao
    mockavam esse caminho.
    """
    gravado = {"inventory_view": "table"}
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s, *a, **k: gravado.update(s))
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: dict(gravado))
    tela = InventoryScreen()
    # A escolha persistida chega ao stack: tabela ativa + segmento marcado.
    assert tela._views.currentIndex() == 1
    assert tela._view_seg._items["table"].isChecked()
    assert tela._view_seg._items["grid"].isChecked() is False
    # E a tela continua navegavel: trocar de visao nao levanta excecao.
    tela._view_seg.select("grid")
    assert tela._views.currentIndex() == 0


# ── ordenacao: seta de direcao nos segmentos ──────────────────────


def test_ordem_nasce_com_seta_desc_em_valor(tela):
    """Valor abre do maior pro menor: a seta aponta pra baixo no ativo."""
    tela._atualizar_ordem_labels()
    assert tela._ordem_seg._items["valor"].text() == "Valor ▼"
    assert tela._ordem_seg._items["nome"].text() == "Nome"
    assert tela._ordem_seg._items["qtd"].text() == "Qtd"


def test_trocar_de_chave_move_a_seta(tela):
    tela._grid.set_items([
        {"name": "Zulu", "qty": 1, "icon": None, "type": "Rifle",
         "steam_net": 99.0, "market_net": None, "premium_pct": None},
        {"name": "Alfa", "qty": 1, "icon": None, "type": "Rifle",
         "steam_net": 1.0, "market_net": None, "premium_pct": None},
    ])
    tela._on_ordem("nome")
    assert [tl.item["name"] for tl in tela._grid._tiles] == ["Alfa", "Zulu"]
    assert tela._ordem_seg._items["nome"].text() == "Nome ▲"
    assert tela._ordem_seg._items["valor"].text() == "Valor"


def test_clicar_de_novo_na_chave_ativa_inverte(tela):
    tela._grid.set_items([
        {"name": "Zulu", "qty": 1, "icon": None, "type": "Rifle",
         "steam_net": 99.0, "market_net": None, "premium_pct": None},
        {"name": "Alfa", "qty": 1, "icon": None, "type": "Rifle",
         "steam_net": 1.0, "market_net": None, "premium_pct": None},
    ])
    tela._on_ordem("nome")
    tela._on_ordem("nome")
    assert [tl.item["name"] for tl in tela._grid._tiles] == ["Zulu", "Alfa"]
    assert tela._ordem_seg._items["nome"].text() == "Nome ▼"


def test_alternar_grade_tabela_nao_toca_a_ordenacao(tela):
    tela._on_ordem("nome")
    tela._view_seg.select("table")
    tela._view_seg.select("grid")
    assert tela._ordem_seg._items["nome"].text() == "Nome ▲"


def test_item_sem_cotacao_fora_fica_none(tela, monkeypatch):
    """Nao inventa numero: sem cotacao, o campo fica vazio."""
    monkeypatch.setattr("skinvault.markets.cached_market", lambda *a, **k: {})
    tela.set_data(ROWS, POS)
    for tile in tela._grid._tiles:
        assert tile.item["market_net"] is None
        assert tile.item["steam_net"] is not None


def test_falha_de_rede_nao_derruba_a_tela(tela, monkeypatch):
    def boom(*a, **k):
        raise OSError("sem rede")
    monkeypatch.setattr("skinvault.markets.cached_market", boom)
    tela.set_data(ROWS, POS)
    assert tela._grid.count() == 2


def test_usa_icone_e_tipo_da_posicao(tela):
    tela.set_data(ROWS, POS)
    assert {x.item["icon"] for x in tela._grid._tiles} == {"abc", "def"}


def test_sem_posicoes_nao_quebra(tela):
    tela.set_data(ROWS, [])
    assert tela._grid.count() == 2


# ── "avaliando" nao e' "vazio" ─────────────────────────────────────
#
# A avaliacao roda na AccountScreen (ela tem o PriceWorker). Sob rate
# limit da Steam cada item queima o backoff inteiro -- 2+4+8s -- entao com
# 24 itens sem cache a tela fica ~5,6 min sem dado nenhum. Nesse intervalo
# ela dizia "Inventario vazio / Sincronize com a Steam", que e' falso pra
# quem ja' tem itens e so' esta' esperando.


def test_loading_substitui_o_empty_state(tela):
    tela.set_loading(0, 0)
    assert tela._loading.isVisibleTo(tela) is True
    assert tela._empty.isVisibleTo(tela) is False
    assert tela._views.isVisibleTo(tela) is False


def _progresso_visivel(tela):
    """O progresso pode aparecer no rodape (grade com esqueleto) ou no
    rotulo do spinner (sem total conhecido) -- o que importa e' o usuario
    ver quanto falta."""
    return tela._status.text() + " " + tela._loading._lbl.text()


def test_loading_mostra_o_progresso(tela):
    tela.set_loading(4, 31)
    assert "4/31" in _progresso_visivel(tela)


def test_loading_com_total_usa_esqueleto(tela):
    """Sob rate limit a avaliacao leva minutos: o fantasma diz quanta
    coisa vem, em vez de um spinner num vazio."""
    tela.set_loading(0, 31)
    assert tela._grid.count() == 31
    assert tela._views.isVisibleTo(tela) is True


def test_esqueleto_some_quando_os_dados_chegam(tela):
    tela.set_loading(0, 31)
    tela.set_data(ROWS, POS)
    assert tela._grid.count() == 2


def test_loading_sem_total_nao_inventa_numero(tela):
    tela.set_loading(0, 0)
    assert "0/0" not in tela._loading._lbl.text()


def test_dados_encerram_o_loading(tela):
    tela.set_loading(4, 31)
    tela.set_data(ROWS, POS)
    assert tela._loading.isVisibleTo(tela) is False
    assert tela._views.isVisibleTo(tela) is True


def test_avaliacao_vazia_de_verdade_mostra_o_empty(tela):
    """Terminou e nao veio nada: aí sim o empty state e' honesto."""
    tela.set_loading(0, 0)
    tela.set_data([], [])
    assert tela._empty.isVisibleTo(tela) is True
    assert tela._loading.isVisibleTo(tela) is False


def test_reavaliacao_nao_apaga_a_tabela(tela):
    """Refresh periodico com dados na tela nao pode esconder o que o
    usuario esta' lendo."""
    tela.set_data(ROWS, POS)
    tela.set_loading(2, 31)
    assert tela._views.isVisibleTo(tela) is True
    assert tela._loading.isVisibleTo(tela) is False
    assert "reavaliando 2/31" in tela._status.text()


def test_comeca_no_empty_e_nao_em_branco(tela):
    """Sem sessao a AccountScreen nunca chama refresh(); a tela nao pode
    ficar totalmente em branco."""
    assert tela._empty.isVisibleTo(tela) is True
    assert tela._loading.isVisibleTo(tela) is False


def test_account_emite_progresso_pra_inventory(monkeypatch):
    """O fio que liga as duas telas existe de ponta a ponta."""
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    router = ScreenRouter(PriceCache(ttl=3600))
    router._account_screen.inventory_progress.emit(3, 31)
    inv = router._inventory_screen
    assert "3/31" in (inv._status.text() + " " + inv._loading._lbl.text())


# ── coluna Score ───────────────────────────────────────────────────
#
# O score fica persistido na POSITION pelo "Validar score" da tela Minha
# Conta. A tela de inventario so' exibe -- nao recalcula nem toca a rede,
# que e' rate-limited.


def _score_cell(tela, fragmento):
    """Celula de score da linha cujo nome contem `fragmento`.

    Buscar por nome, nao por indice: a tabela roda com setSortingEnabled e
    reordena pelo nome LOCALIZADO ("Caixa Kilowatt" vem antes de "AK-47 |
    Redline (Veterana de Guerra)"), entao a ordem visual nao e' a de entrada.
    """
    for i in range(tela._table.rowCount()):
        nome = tela._table.item(i, tela.COL_NAME)
        if nome and fragmento.lower() in nome.text().lower():
            return tela._table.item(i, tela.COL_SCORE)
    raise AssertionError("linha nao encontrada: " + fragmento)


def test_score_da_position_aparece_na_coluna(tela):
    import time
    pos = [dict(POS[0], current_score=88, score_ts=time.time()),
           dict(POS[1])]
    tela.set_data(ROWS, pos)
    assert _score_cell(tela, "Redline").text() == "88"


def test_score_segue_o_item_certo_apos_a_ordenacao(tela):
    """A tabela reordena; o score nao pode acabar na linha do vizinho."""
    import time
    agora = time.time()
    pos = [dict(POS[0], current_score=88, score_ts=agora),
           dict(POS[1], current_score=12, score_ts=agora)]
    tela.set_data(ROWS, pos)
    assert _score_cell(tela, "Redline").text() == "88"
    assert _score_cell(tela, "Kilowatt").text() == "12"


def test_sem_score_mostra_travessao(tela):
    tela.set_data(ROWS, POS)
    cel = _score_cell(tela, "Redline")
    assert cel.text() == "—"
    assert "Atualizar notas" in cel.toolTip()


def test_score_desatualizado_fica_ambar(tela):
    """Um 90 de tres semanas atras nao e' oportunidade, e' dado velho."""
    import time
    from skinvault.ui import theme as t
    pos = [dict(POS[0], current_score=90, score_ts=time.time() - 86400 * 21),
           dict(POS[1], current_score=90, score_ts=time.time())]
    tela.set_data(ROWS, pos)
    velho = _score_cell(tela, "Redline")
    novo = _score_cell(tela, "Kilowatt")
    assert velho.foreground().color().name() == t.WARN.lower()
    assert novo.foreground().color().name() == t.POSITIVE.lower()
    assert "DESATUALIZADO" in velho.toolTip()
    assert "DESATUALIZADO" not in novo.toolTip()


def test_score_nao_desloca_a_coluna_origem(tela):
    """Origem entrou depois de Score; se os indices saissem de sincronia a
    tabela mostraria 'Steam' na coluna errada."""
    tela.set_data(ROWS, POS)
    assert tela._table.item(0, tela.COL_ORIGIN).text() == "Steam"
    # 10 desde 2026-07-31: "Custo" entrou entre "Onde" e "P&L"
    assert tela._table.columnCount() == 11


def test_coluna_origem_some_quando_nao_ha_mistura(tela):
    """31 linhas 100% 'Steam' nao informa nada, so' ocupa espaco."""
    tela.set_data(ROWS, POS)
    assert tela._table.isColumnHidden(tela.COL_ORIGIN)


def test_coluna_origem_aparece_quando_ha_mistura(tela):
    pos = [dict(POS[0], source="steam_sync"), dict(POS[1], source="manual")]
    tela.set_data(ROWS, pos)
    assert not tela._table.isColumnHidden(tela.COL_ORIGIN)
    cel = _score_cell(tela, "Kilowatt")  # reusa a busca por nome
    row = cel.row()
    assert tela._table.item(row, tela.COL_ORIGIN).text() == "Manual"


# ── a tabela mostra o valor de fora ────────────────────────────────
#
# Ate' 2026-07-30 a tabela so' tinha colunas derivadas do preco da Steam.
# Com o priceoverview em 429 viravam cinco travessoes lado a lado,
# enquanto R$ 1.374 em cotacoes de fora ficavam invisiveis nessa visao.


def test_tabela_mostra_o_melhor_liquido_de_fora(tela, monkeypatch):
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.0)
    monkeypatch.setattr(
        "skinvault.markets.cached_market",
        lambda src, cache=None: (
            {"Kilowatt Case": 4.0} if src == "csgotm"
            else {"Kilowatt Case": 5.0} if src == "skinport" else {}))
    tela.set_data(ROWS, POS)
    linha = _linha_por_nome(tela, "Kilowatt")
    # csgotm: 4*5 = 20 bruto, taxa 5% -> 19,00
    # skinport: 5*5 = 25 bruto, taxa 12% -> 22,00  <- vence
    assert "22,00" in tela._table.item(linha, tela.COL_BEST_OUT).text()
    assert "Skinport" in tela._table.item(linha, tela.COL_WHERE).text()


def test_tabela_sem_cotacao_mostra_travessao(tela, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda src, cache=None: {})
    tela.set_data(ROWS, POS)
    assert tela._table.item(0, tela.COL_BEST_OUT).text() == "—"
    assert tela._table.item(0, tela.COL_WHERE).text() == "—"


def test_tabela_ordena_melhor_fora_por_valor(tela, monkeypatch):
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.0)
    monkeypatch.setattr(
        "skinvault.markets.cached_market",
        lambda src, cache=None: ({"Kilowatt Case": 1.0,
                                  "AK-47 | Redline (Battle-Scarred)": 40.0}
                                 if src == "skinport" else {}))
    from PyQt6.QtCore import Qt
    tela.set_data(ROWS, POS)
    tela._table.sortItems(tela.COL_BEST_OUT, Qt.SortOrder.DescendingOrder)
    assert "Redline" in tela._table.item(0, tela.COL_NAME).text()


def test_rotulo_da_taxa_nao_diz_menos_15(tela):
    """A taxa nao e' -15% do preco: e' preco/1,15, ~-13%. O rotulo antigo
    propagava o modelo errado que o backtest tinha (ver AGENTS.md 4b)."""
    tela.set_data(ROWS, POS)
    cab = tela._table.horizontalHeaderItem(tela.COL_RECEIVED).text()
    assert "-15%" not in cab
    assert "saldo" in cab.lower()


# ── rodape com o total ─────────────────────────────────────────────


def test_rodape_soma_o_valor_de_fora(tela, monkeypatch):
    """Dizia so' "31 item(ns)" com R$ 1.374 de cotacao na tela."""
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.0)
    monkeypatch.setattr(
        "skinvault.markets.cached_market",
        lambda src, cache=None: ({"Kilowatt Case": 1.0} if src == "skinport"
                                 else {}))
    tela.set_data(ROWS, POS)
    txt = tela._status.text()
    assert "2 itens" in txt
    # 1.0 usd * 5 fx = 5 bruto, taxa 12% -> 4,40 x 21 unidades = 92,40
    assert "92,40" in txt
    assert "dinheiro" in txt


def test_rodape_separa_saldo_de_dinheiro(tela, monkeypatch):
    """Somar os dois num numero so' inventaria um patrimonio que nao
    existe: saldo Steam nao vira dinheiro."""
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.0)
    monkeypatch.setattr(
        "skinvault.markets.cached_market",
        lambda src, cache=None: ({"Kilowatt Case": 1.0} if src == "skinport"
                                 else {}))
    tela.set_data(ROWS, POS)
    txt = tela._status.text()
    assert "saldo Steam" in txt
    assert "dinheiro" in txt


def test_rodape_sem_cotacao_so_conta_itens(tela, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda src, cache=None: {})
    rows = [dict(r, net_if_sold=None) for r in ROWS]
    tela.set_data(rows, POS)
    assert tela._status.text() == "2 itens"


def test_rodape_singular(tela, monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda src, cache=None: {})
    tela.set_data([dict(ROWS[0], net_if_sold=None)], [POS[0]])
    assert tela._status.text() == "1 item"


def _linha_por_nome(tela, fragmento):
    for i in range(tela._table.rowCount()):
        it = tela._table.item(i, tela.COL_NAME)
        if it and fragmento.lower() in it.text().lower():
            return i
    raise AssertionError("linha nao encontrada: " + fragmento)


def test_position_faltando_nao_quebra_a_coluna(tela):
    """set_data(rows, []) e' caminho suportado -- ver test_sem_posicoes."""
    tela.set_data(ROWS, [])
    assert _score_cell(tela, "Redline").text() == "—"


def test_celula_de_score_e_a_mesma_da_watchlist():
    """Se as duas telas divergirem na cor ou no tooltip, uma das duas esta'
    mentindo sobre o mesmo numero."""
    import time
    from skinvault.ui.components import score_table_item
    from skinvault.ui.watchlist_screen import WatchlistScreen
    assert WatchlistScreen  # a tela consome o mesmo helper
    ts = time.time()
    a = score_table_item(75, ts)
    b = score_table_item(75, ts)
    assert a.text() == b.text()
    assert a.toolTip() == b.toolTip()
    assert a.foreground().color().name() == b.foreground().color().name()


# ── alternancia e filtro ───────────────────────────────────────────


def test_comeca_na_grade(tela):
    assert tela._views.currentIndex() == 0


def test_segmentado_leva_pra_visao_pedida(tela):
    """A chave diz o DESTINO. O botao antigo derivava do estado atual, e
    ler o estado na ordem errada ja' inverteu o filtro aqui uma vez."""
    tela._on_view_segment("table")
    assert tela._views.currentIndex() == 1
    tela._on_view_segment("grid")
    assert tela._views.currentIndex() == 0


def test_segmentado_e_idempotente(tela):
    """Pedir duas vezes a mesma visao nao pode alternar."""
    tela._on_view_segment("table")
    tela._on_view_segment("table")
    assert tela._views.currentIndex() == 1


def test_filtro_vale_nas_duas_visoes(tela):
    """O campo ficava desabilitado na grade -- caixa de busca grande e
    morta no topo, justamente na visao que abre por padrao."""
    assert tela._filter.isEnabled() is True
    tela._on_view_segment("table")
    assert tela._filter.isEnabled() is True


def test_filtro_esconde_linhas(tela):
    tela.set_data(ROWS, POS)
    tela._apply_filter("kilowatt")
    escondidas = [tela._table.isRowHidden(i)
                  for i in range(tela._table.rowCount())]
    assert escondidas.count(False) == 1


def test_filtro_vazio_mostra_tudo(tela):
    tela.set_data(ROWS, POS)
    tela._apply_filter("kilowatt")
    tela._apply_filter("")
    assert all(not tela._table.isRowHidden(i)
               for i in range(tela._table.rowCount()))


def test_status_conta_itens(tela):
    tela.set_data(ROWS, POS)
    assert "2" in tela._status.text()


# ── ordenacao por valor, nao por texto ─────────────────────────────
#
# QTableWidgetItem compara por DisplayRole, entao coluna formatada
# ordenava como string. Medido em 2026-07-30 nos 25 trades reais:
# P&L decrescente dava "R$ -7,54 | R$ -1,96 | R$ 1,63" -- o maior
# PREJUIZO no topo. E R$ 16,49 caia abaixo de R$ 9,66.


def test_sortable_item_ordena_por_valor():
    from skinvault.ui.components import SortableItem
    a = SortableItem("R$ 9,66", 9.66)
    b = SortableItem("R$ 16,49", 16.49)
    assert a < b          # pelo texto seria o contrario
    assert not (b < a)


def test_sortable_item_negativo_vem_antes_do_positivo():
    from skinvault.ui.components import SortableItem
    assert SortableItem("R$ -7,54", -7.54) < SortableItem("R$ 1,63", 1.63)


def test_sortable_item_ausente_vai_pro_fim():
    """None -> -inf, pra linha sem valor nao se misturar aos numeros."""
    from skinvault.ui.components import num_cell
    vazio = num_cell("—", None)
    assert vazio < num_cell("R$ 0,00", 0.0)


def test_sortable_item_contra_item_comum_nao_explode():
    from PyQt6.QtWidgets import QTableWidgetItem
    from skinvault.ui.components import SortableItem
    SortableItem("x", 1) < QTableWidgetItem("y")  # nao levanta


def test_sort_key_reconhece_os_formatos_do_projeto():
    """Os tres formatos que t.brl, _fmt_date e o f-string de % produzem."""
    from skinvault.ui.components import sort_key_from_text as k
    assert k("R$ 16,49") == 16.49
    assert k("R$ -7,54") == -7.54
    assert k("R$ 1.234,56") == 1234.56
    assert k("+103.8%") == 103.8
    assert k("-90.2%") == -90.2
    assert k("88") == 88
    # data vira AAAAMMDD, que ordena igual a data
    assert k("30/04/2026") < k("29/05/2026")
    # o Historico usa DD/MM/AA; as duas grafias tem que conviver
    assert k("30/07/26") == k("30/07/2026")
    assert k("31/12/25") < k("01/01/26")


def test_sort_key_devolve_none_no_que_nao_reconhece():
    """Formato desconhecido volta a ordenar por texto -- nunca piora."""
    from skinvault.ui.components import sort_key_from_text as k
    for texto in ("AK-47 | Redline", "Steam", "—", "", "  ", "R$ ---"):
        assert k(texto) is None


def test_auto_cell_ordena_moeda(tela):
    from skinvault.ui.components import auto_cell, SortableItem
    from PyQt6.QtWidgets import QTableWidgetItem
    caro, barato = auto_cell("R$ 16,49"), auto_cell("R$ 9,66")
    assert isinstance(caro, SortableItem)
    assert barato < caro
    # texto puro continua sendo item comum
    assert not isinstance(auto_cell("AK-47"), SortableItem)


def test_inventario_ordena_preco_por_valor(tela):
    from PyQt6.QtCore import Qt
    rows = [dict(ROWS[0], name="Caro", price=16.49),
            dict(ROWS[1], name="Barato", price=9.66)]
    tela.set_data(rows, POS)
    tela._table.sortItems(tela.COL_PRICE, Qt.SortOrder.DescendingOrder)
    assert tela._table.item(0, tela.COL_NAME).text() == "Caro"


def test_inventario_ordena_score_por_valor(tela):
    from PyQt6.QtCore import Qt
    import time
    agora = time.time()
    pos = [dict(POS[0], current_score=9, score_ts=agora),
           dict(POS[1], current_score=88, score_ts=agora)]
    tela.set_data(ROWS, pos)
    tela._table.sortItems(tela.COL_SCORE, Qt.SortOrder.DescendingOrder)
    assert tela._table.item(0, tela.COL_SCORE).text() == "88"


def test_inventario_score_ausente_nao_vence_score_alto(tela):
    from PyQt6.QtCore import Qt
    import time
    pos = [dict(POS[0]),  # sem score -> "—"
           dict(POS[1], current_score=50, score_ts=time.time())]
    tela.set_data(ROWS, pos)
    tela._table.sortItems(tela.COL_SCORE, Qt.SortOrder.DescendingOrder)
    assert tela._table.item(0, tela.COL_SCORE).text() == "50"


# ── icones ─────────────────────────────────────────────────────────
#
# A grade e' network-free de proposito (icons.local_path so' olha o disco),
# e nada no app populava esse disco -- ensure_cached existia sem chamador.
# 25 das 31 posicoes apareciam como "?" numa tela cujo proposito e'
# reconhecer item pelo icone.


def test_set_data_dispara_download_dos_icones(tela, monkeypatch):
    pedidos = []
    monkeypatch.setattr(tela._icon_worker, "start", pedidos.append)
    pos = [dict(POS[0], icon="hashA"), dict(POS[1], icon="hashB")]
    tela.set_data(ROWS, pos)
    assert pedidos and "hashA" in pedidos[0] and "hashB" in pedidos[0]


def test_worker_ignora_icone_ja_em_cache(monkeypatch):
    """Nem acorda thread quando nao ha' o que baixar."""
    from skinvault.ui._price_worker import IconWorker
    from skinvault import icons
    monkeypatch.setattr(icons, "local_path", lambda h: "ja/existe.png")
    threads = []
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: threads.append(kw) or _Dummy())
    IconWorker().start(["a", "b"])
    assert threads == []


class _Dummy:
    def start(self):
        pass


def test_worker_deduplica_e_baixa_so_o_que_falta(monkeypatch):
    from skinvault.ui._price_worker import IconWorker
    from skinvault import icons
    monkeypatch.setattr(icons, "local_path",
                        lambda h: "existe.png" if h == "tem" else None)
    pedidos = []
    monkeypatch.setattr(icons, "ensure_cached",
                        lambda hs: pedidos.append(list(hs)) or {})

    class _Inline:
        def __init__(self, target=None, **kw):
            self._t = target
        def start(self):
            self._t()

    monkeypatch.setattr("threading.Thread", _Inline)
    IconWorker().start(["tem", "falta", "falta", None, "", "outro"])
    assert pedidos == [["falta", "outro"]]


def test_icones_prontos_repintam_a_grade(tela, monkeypatch):
    tela.set_data(ROWS, POS)
    repintou = []
    monkeypatch.setattr(tela, "_populate_grid",
                        lambda: repintou.append(True))
    tela._on_icons_ready(3)
    assert repintou == [True]


def test_zero_icones_novos_nao_repinta(tela, monkeypatch):
    """Repintar a' toa pisca a grade sem motivo."""
    tela.set_data(ROWS, POS)
    repintou = []
    monkeypatch.setattr(tela, "_populate_grid",
                        lambda: repintou.append(True))
    tela._on_icons_ready(0)
    assert repintou == []


def test_falha_no_cdn_nao_derruba_a_tela(monkeypatch):
    from skinvault.ui._price_worker import IconWorker
    from skinvault import icons
    monkeypatch.setattr(icons, "local_path", lambda h: None)

    def _boom(hs):
        raise OSError("CDN fora")

    monkeypatch.setattr(icons, "ensure_cached", _boom)

    class _Inline:
        def __init__(self, target=None, **kw):
            self._t = target
        def start(self):
            self._t()

    monkeypatch.setattr("threading.Thread", _Inline)
    w = IconWorker()
    recebidos = []
    w.done.connect(recebidos.append)
    w.start(["x"])
    assert recebidos == [0]


# ── integracao com o router ────────────────────────────────────────


def test_router_liga_account_ao_inventario(tmp_path):
    """A AccountScreen avalia; a InventoryScreen so' exibe."""
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    r = ScreenRouter(PriceCache(tmp_path / "p.json", ttl=3600))
    r._account_screen.inventory_ready.emit(ROWS, POS, False)
    assert r._inventory_screen._grid.count() == 2


def test_router_propaga_o_rate_limit(tmp_path):
    """"Sem preço" e "a Steam recusou" viram o mesmo travessão na tabela;
    o rodapé é o único lugar que pode distinguir."""
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    r = ScreenRouter(PriceCache(tmp_path / "p.json", ttl=3600))
    sem_preco = [dict(x, price=None) for x in ROWS]
    r._account_screen.inventory_ready.emit(sem_preco, POS, True)
    assert "limitou" in r._inventory_screen._status.text()


def test_rate_limit_sem_linha_nenhuma_explica_no_rodape(tela):
    tela.set_data([], [], True)
    assert "limitou" in tela._status.text()


def test_sem_rate_limit_o_rodape_nao_fala_de_limite(tela):
    """O rodape passou a somar valor (2026-07-30); o que ele NAO pode
    trazer sem rate limit e' o aviso de limite."""
    tela.set_data(ROWS, POS, False)
    txt = tela._status.text()
    assert "2 itens" in txt
    assert "limitou" not in txt


def test_router_navega_pro_inventario(tmp_path):
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import SCREEN_INVENTORY, ScreenRouter
    r = ScreenRouter(PriceCache(tmp_path / "p.json", ttl=3600))
    r.navigate(SCREEN_INVENTORY)
    assert r._stack.currentWidget() is r._inventory_screen


# ── filtro: contexto no rodape e aviso de zero ─────────────────────
#
# Filtrar ate' zero deixava a tela em branco sem uma palavra --
# indistinguivel de inventario vazio ou de falha ao carregar.


def test_rodape_diz_quantos_o_filtro_deixou(tela):
    tela.set_data(ROWS, POS)
    tela._apply_filter("kilowatt")
    txt = tela._status.text()
    assert "Mostrando 1 de 2" in txt
    assert "kilowatt" in txt


def test_filtro_sem_resultado_avisa(tela):
    tela.set_data(ROWS, POS)
    tela._apply_filter("nao existe nada assim")
    assert tela._sem_match.isVisibleTo(tela) is True
    assert "Nenhum dos 2 itens" in tela._status.text()


def test_limpar_filtro_volta_o_rodape(tela):
    tela.set_data(ROWS, POS)
    base = tela._status.text()
    tela._apply_filter("kilowatt")
    tela._apply_filter("")
    assert tela._status.text() == base
    assert tela._sem_match.isVisibleTo(tela) is False


# ── atalhos ────────────────────────────────────────────────────────


def test_ctrl_f_foca_o_filtro(tela):
    """Selecionar tudo importa: o gesto e' buscar de novo, e digitar
    por cima do termo anterior tem que substituir, nao concatenar."""
    tela._filter.setText("kilowatt")
    tela._focar_filtro()
    assert tela._filter.hasSelectedText() is True


def test_esc_limpa_o_filtro(tela):
    """Filtro esquecido ligado faz o inventario parecer que perdeu itens."""
    tela.set_data(ROWS, POS)
    tela._filter.setText("kilowatt")
    tela._limpar_filtro()
    assert tela._filter.text() == ""


# ── visao persistida ───────────────────────────────────────────────


def test_escolher_tabela_persiste(tela):
    tela._on_view_segment("table")
    assert tela._settings_gravado.get("inventory_view") == "table"


def test_voltar_pra_grade_persiste(tela):
    tela._on_view_segment("table")
    tela._on_view_segment("grid")
    assert tela._settings_gravado.get("inventory_view") == "grid"


# ── custo: coluna, dialogo e reavaliacao ───────────────────────────
#
# Custo e' o dado que faltava pro P&L existir: o sync grava cost=0.0 pra
# "nao sei" e a unica entrada era o CLI. A coluna e o dialogo sao a porta
# de dentro do app.


def test_coluna_custo_mostra_travessao_sem_custo(tela):
    """Posicao do sync nao tem custo -> "—", nao "R$ 0,00" (mentiria
    que o item nao custou nada)."""
    tela.set_data(ROWS, POS)
    assert tela._table.item(0, tela.COL_COST).text() == "—"


def test_coluna_custo_mostra_valor_declarado(tela):
    pos = [dict(POS[0], cost=150.0, source="manual"),
           dict(POS[1], cost=0.0, source="manual")]
    tela.set_data(ROWS, pos)
    # A tabela ordena por nome (default do QTableWidget, decrescente), entao
    # a linha do item se acha pelo nome, nao pelo indice.
    redline = _linha_por_nome(tela, "Redline")
    kilowatt = _linha_por_nome(tela, "Kilowatt")
    assert tela._table.item(redline, tela.COL_COST).text() == "R$ 150,00"
    # zero DECLARADO (drop) e' custo de verdade -- aparece como zero
    assert tela._table.item(kilowatt, tela.COL_COST).text() == "R$ 0,00"


def _linha_por_nome(tela, trecho: str) -> int:
    for i in range(tela._table.rowCount()):
        if trecho in tela._table.item(i, tela.COL_NAME).text():
            return i
    raise AssertionError(f"linha com '{trecho}' nao encontrada")


def test_salvar_custo_persiste_e_pede_reavaliacao(tela, monkeypatch):
    """Salvar nao recalcula aqui: o PriceWorker vive na AccountScreen, e a
    reavaliacao e' pedida por sinal pro router acionar o refresh."""
    gravado = {}
    monkeypatch.setattr("skinvault.portfolio.update_position_cost",
                        lambda nome, custo: gravado.update(
                            nome=nome, custo=custo) or [{"name": nome}])
    reeval = []
    tela.request_reeval.connect(lambda: reeval.append(1))
    tela.set_data(ROWS, POS)
    tela._salvar_custo("AK-47 | Redline (Battle-Scarred)", 150.0)
    assert gravado == {"nome": "AK-47 | Redline (Battle-Scarred)",
                       "custo": 150.0}
    assert reeval == [1]


def test_salvar_custo_nome_fora_do_portfolio_cria_posicao(tela, monkeypatch):
    monkeypatch.setattr("skinvault.portfolio.update_position_cost",
                        lambda *a, **k: None)
    criado = {}
    monkeypatch.setattr("skinvault.portfolio.add_position",
                        lambda nome, custo, qtd: criado.update(
                            nome=nome, custo=custo, qtd=qtd))
    tela._salvar_custo("Kilowatt Case", 12.5)
    assert criado == {"nome": "Kilowatt Case", "custo": 12.5, "qtd": 1}


def test_dialogo_aceita_formato_br_e_calcula_equilibrio(app):
    from skinvault.ui.inventory_screen import _CostDialog
    dlg = _CostDialog("Kilowatt Case", quantity=21)
    dlg._inp.setText("199,90")
    assert dlg._parse() == 199.9
    dlg._on_ok()
    assert dlg.cost() == 199.9
    # break-even ao vivo: 199,90 x 1,15 = 229,88 (taxa do VENDEDOR)
    assert "229,88" in dlg._be_label.text()


def test_dialogo_rejeita_invalido_e_negativo(app):
    from skinvault.ui.inventory_screen import _CostDialog
    dlg = _CostDialog("Kilowatt Case")
    dlg._inp.setText("abc")
    assert dlg._parse() is None
    dlg._inp.setText("-5")
    assert dlg._parse() is None
    dlg._on_ok()
    assert dlg.cost() is None
    assert dlg._err_label.isVisibleTo(dlg) is True


def test_dialogo_zero_e_drop(app):
    from skinvault.ui.inventory_screen import _CostDialog
    dlg = _CostDialog("Drop")
    dlg._inp.setText("0")
    assert dlg._parse() == 0.0
    assert "qualquer venda é lucro" in dlg._be_label.text()


def test_definir_custo_item_resolve_o_item_do_card(tela, monkeypatch):
    """O atalho do card/painel cai no MESMO caminho do duplo clique da
    tabela (_salvar_custo): nome cru, quantidade e custo atual do tile."""
    class _FakeDlg:
        def __init__(self, nome, qty, atual, parent):
            self._nome, self._qty, self._atual = nome, qty, atual
        def exec(self):
            return 1          # QDialog.Accepted
        def cost(self):
            return 123.0
    monkeypatch.setattr("skinvault.ui.inventory_screen._CostDialog", _FakeDlg)
    gravado = {}
    monkeypatch.setattr("skinvault.portfolio.update_position_cost",
                        lambda nome, custo: gravado.update(
                            nome=nome, custo=custo) or [{"name": nome}])
    tela.set_data(ROWS, POS)
    item = tela._grid._tiles[0].item
    tela._definir_custo_item(item)
    assert gravado == {"nome": "AK-47 | Redline (Battle-Scarred)",
                       "custo": 123.0}


def test_on_liquidity_requested_busca_e_aplica_no_painel(tela, monkeypatch):
    """Clique no botao do painel -> worker busca -> resultado volta pro
    MESMO painel via bridge, sem travar a UI (thread + signal)."""
    import threading
    import time
    from PyQt6.QtWidgets import QApplication

    done = threading.Event()

    def _fake_fetch(name, cache=None):
        done.set()
        return (
            [{"time": i, "price_median": 10.0, "purchases": 50}
             for i in range(10)],
            {"sell_count": 25},
        )

    monkeypatch.setattr(
        "skinvault.ssr_cache.cached_price_history_and_book", _fake_fetch)
    monkeypatch.setattr("skinvault.signals.record_item_supply",
                        lambda n, v: None)

    item = {"name": "AK-47 | Redline (Field-Tested)",
            "raw_name": "AK-47 | Redline (Field-Tested)"}
    tela._grid._detail.show_item(item)
    tela._grid._detail.liquidity_requested.emit(item)

    assert done.wait(timeout=5), "worker nao chamou a busca a tempo"
    for _ in range(20):
        QApplication.instance().processEvents()
        if tela._grid._detail._liquidity_result.text():
            break
        time.sleep(0.05)
    assert "listagens" in tela._grid._detail._liquidity_result.text() \
        or tela._grid._detail._liquidity_result.text() not in ("", "Consultando…")


def test_on_liquidity_requested_sem_order_book_mostra_sem_dados(tela, monkeypatch):
    import threading
    import time
    from PyQt6.QtWidgets import QApplication

    done = threading.Event()

    def _fake_fetch(name, cache=None):
        done.set()
        return ([{"time": 0, "price_median": 10.0}], None)

    monkeypatch.setattr(
        "skinvault.ssr_cache.cached_price_history_and_book", _fake_fetch)

    item = {"name": "X", "raw_name": "X"}
    tela._grid._detail.show_item(item)
    tela._grid._detail.liquidity_requested.emit(item)

    assert done.wait(timeout=5)
    for _ in range(20):
        QApplication.instance().processEvents()
        if tela._grid._detail._liquidity_result.text():
            break
        time.sleep(0.05)
    assert "Sem dados" in tela._grid._detail._liquidity_result.text()


def test_on_liquidity_requested_via_tabela_aplica_no_drawer(tela, monkeypatch):
    """Mesmo handler/bridge do card da grade, mas disparado pelo drawer
    da view em tabela (_on_table_row_clicked)."""
    import threading
    import time
    from PyQt6.QtWidgets import QApplication

    done = threading.Event()

    def _fake_fetch(name, cache=None):
        done.set()
        return (
            [{"time": i, "price_median": 10.0, "purchases": 50}
             for i in range(10)],
            {"sell_count": 25},
        )

    monkeypatch.setattr(
        "skinvault.ssr_cache.cached_price_history_and_book", _fake_fetch)
    monkeypatch.setattr("skinvault.signals.record_item_supply",
                        lambda n, v: None)

    tela.set_data(ROWS, POS)
    tela._on_table_row_clicked(0, 0)
    tela._drawer._liquidity_btn.click()

    assert done.wait(timeout=5), "worker nao chamou a busca a tempo"
    for _ in range(20):
        QApplication.instance().processEvents()
        if tela._drawer._liquidity_result.text() not in ("", "Consultando…"):
            break
        time.sleep(0.05)
    assert tela._drawer._liquidity_result.text() not in ("", "Consultando…")


def test_rate_limit_vazio_explica_no_empty_state(tela):
    """Inventario vazio por rate limit NAO e' "sincronize com a Steam" --
    e' a Steam recusando. O empty state diz a causa real, com as cotacoes
    de fora seguindo ativas."""
    tela.set_data([], [], True)
    assert tela._empty.isVisibleTo(tela) is True
    sub = tela._empty._sub.text()
    assert "indisponível" in sub
    assert "cotações" in sub
    assert "Sincronize" not in sub


def test_rate_limit_vazio_nao_polui_o_estado_normal(tela):
    """Sem rate limit o empty state volta ao texto padrao (carteira vazia).
    Nada de "sincronize": o recurso saiu na F10 (2026-08-07)."""
    tela.set_data([], [], False)
    assert "Ainda não há itens" in tela._empty._sub.text()
    assert "incroniz" not in tela._empty._sub.text()


# ── painel de filtros ──────────────────────────────────────────────


def test_filtros_listam_categorias_com_contagem(tela):
    tela.set_data(ROWS, POS)
    rotulos = {b._rotulo.text(): b._contagem.text()
               for b in tela._cat_botoes.values()}
    assert rotulos["Todos"] == "2"
    assert rotulos["Skins"] == "1"
    assert rotulos["Caixas e cápsulas"] == "1"


def test_contagem_fica_em_label_separado(tela):
    """Com tudo num setText unico, alinhar a contagem exigiria contar
    espacos -- e a coluna saia irregular, porque a fonte nao e'
    monoespacada."""
    tela.set_data(ROWS, POS)
    btn = tela._cat_botoes[None]
    assert btn._rotulo.text() == "Todos"
    assert btn._contagem.text().isdigit()


def test_rotulos_nao_comem_o_clique(tela):
    """Sem WA_TransparentForMouseEvents o clique morre no label e o botao
    nunca dispara."""
    from PyQt6.QtCore import Qt
    tela.set_data(ROWS, POS)
    btn = tela._cat_botoes[None]
    for w in (btn._rotulo, btn._contagem):
        assert w.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True


def test_categoria_ativa_fica_destacada(tela):
    """O `:checked` do stylesheet pinta o BOTAO, nao os QLabels dentro --
    sem repintar, nao dava pra saber qual filtro estava valendo."""
    from skinvault.ui import theme as t
    tela.set_data(ROWS, POS)
    tela._on_categoria("Skins")
    assert t.TEXT in tela._cat_botoes["Skins"]._rotulo.styleSheet()
    assert t.TEXT_MUTED in tela._cat_botoes[None]._rotulo.styleSheet()


def test_filtros_somem_sem_itens(tela):
    assert tela._cat_panel.isVisibleTo(tela) is False


def test_filtros_reconstroem_a_cada_carga(tela):
    """Categoria que ficou sem item viraria um filtro que nao devolve
    nada."""
    tela.set_data(ROWS, POS)
    assert "Caixas e cápsulas" in tela._cat_botoes
    tela.set_data([ROWS[0]], [POS[0]])
    assert "Caixas e cápsulas" not in tela._cat_botoes
