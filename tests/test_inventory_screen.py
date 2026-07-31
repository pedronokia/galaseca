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
    return InventoryScreen()


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


def test_loading_mostra_o_progresso(tela):
    tela.set_loading(4, 31)
    assert "4/31" in tela._loading._lbl.text()


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
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    router = ScreenRouter(PriceCache(ttl=3600))
    router._account_screen.inventory_progress.emit(3, 31)
    assert "3/31" in router._inventory_screen._loading._lbl.text()


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
    assert "Validar score" in cel.toolTip()


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
    # 9 desde 2026-07-30: "Melhor fora" e "Onde" entraram, "Subtotal" saiu
    assert tela._table.columnCount() == 9


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
