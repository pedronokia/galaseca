"""Custo em lote, importacao de custos por CSV e CTA de importacao nas
boas-vindas (bloco 3 da revisao de UI, 2026-10-17)."""
from __future__ import annotations

import pytest

from skinvault import portfolio


# ── portfolio.update_costs_bulk ────────────────────────────────────

def test_update_costs_bulk_grava_uma_vez_e_vira_manual(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("Kilowatt Case", 0.0, 21,
                           source="steam_sync", path=p)
    portfolio.add_position("Fever Case", 0.0, 6, source="steam_sync", path=p)
    portfolio.add_position("AK-47 | Redline (Field-Tested)", 180.0, 1,
                           path=p)
    res = portfolio.update_costs_bulk(
        {"Kilowatt Case": 1.5, "Fever Case": 0.0}, path=p)
    assert sorted(res["atualizados"]) == ["Fever Case", "Kilowatt Case"]
    assert res["nao_encontrados"] == []
    pos = {x["name"]: x for x in portfolio.load_portfolio(p)}
    assert pos["Kilowatt Case"]["cost"] == pytest.approx(1.5)
    # Zero declarado = drop: custo conhecido, nao "nao sei" do sync.
    assert portfolio.has_cost_basis(pos["Fever Case"]) is True
    assert pos["AK-47 | Redline (Field-Tested)"]["cost"] == 180.0


def test_update_costs_bulk_nao_cria_posicao_fantasma(tmp_path):
    p = tmp_path / "pf.json"
    portfolio.add_position("Kilowatt Case", 0.0, 1, path=p)
    res = portfolio.update_costs_bulk({"Nao Existe": 10.0}, path=p)
    assert res == {"atualizados": [], "nao_encontrados": ["Nao Existe"]}
    assert [x["name"] for x in portfolio.load_portfolio(p)] == [
        "Kilowatt Case"]


# ── portfolio.parse_cost_csv ───────────────────────────────────────

def test_parse_cost_csv_le_o_proprio_export():
    """Exportar -> preencher Custo -> importar: o round-trip pretendido."""
    from skinvault import reports
    rows = [{"name": "AK-47 | Redline (Field-Tested)", "quantity": 1,
             "price": 223.5},
            {"name": "★ Karambit | Doppler (Factory New)", "quantity": 1,
             "price": 4380.0}]
    pos = [{"source": "manual", "cost": 180.0},
           {"source": "steam_sync", "cost": 0.0}]
    texto = reports.inventory_csv(rows, pos)
    lido = portfolio.parse_cost_csv(texto)
    # Item sem custo sai vazio no export e e' ignorado em silencio.
    assert lido == {"custos": {"AK-47 | Redline (Field-Tested)": 180.0},
                    "erros": []}


def test_parse_cost_csv_lista_simples_e_formatos_de_numero():
    texto = ("AK-47 | Redline (Field-Tested);R$ 1.234,50\n"
             "# comentario\n"
             "Kilowatt Case;0\n")
    lido = portfolio.parse_cost_csv(texto)
    assert lido["custos"] == {"AK-47 | Redline (Field-Tested)": 1234.5,
                              "Kilowatt Case": 0.0}
    virgula = portfolio.parse_cost_csv("Fever Case,4.53\n")
    assert virgula["custos"] == {"Fever Case": 4.53}


def test_parse_cost_csv_erros_por_linha():
    texto = "Item;Custo\nA;abc\nB;-3\nC\nD;10\n"
    lido = portfolio.parse_cost_csv(texto)
    assert lido["custos"] == {"D": 10.0}
    assert len(lido["erros"]) == 3
    assert lido["erros"][0].startswith("Linha 2")


def test_parse_cost_csv_cabecalho_sem_custo_e_vazio():
    assert portfolio.parse_cost_csv("Item;Quantidade\nA;1\n")["erros"]
    assert portfolio.parse_cost_csv("")["erros"] == ["Arquivo vazio."]


# ── InventoryScreen ────────────────────────────────────────────────

@pytest.fixture
def tela(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    gravado = {}
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s, *a, **k: gravado.update(s))
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: dict(gravado))
    from skinvault.ui.inventory_screen import InventoryScreen
    t = InventoryScreen()
    t._app = app
    return t


ROWS = [
    {"name": "Kilowatt Case", "quantity": 21, "price": 1.22,
     "market": 25.62, "net_if_sold": 1.04, "pnl": None},
    {"name": "AWP | Asiimov (Field-Tested)", "quantity": 1,
     "price": 512.0, "market": 512.0, "net_if_sold": 445.22, "pnl": None},
]
POS = [{"name": "Kilowatt Case", "source": "steam_sync", "cost": 0.0,
        "quantity": 21},
       {"name": "AWP | Asiimov (Field-Tested)", "source": "steam_sync",
        "cost": 0.0, "quantity": 1}]


def _linha_de(tela, nome):
    for r in range(tela._table.rowCount()):
        if tela._nome_da_linha(r) == nome:
            return r
    raise AssertionError(nome)


def test_editar_custo_usa_nome_da_linha_com_tabela_ordenada(tela,
                                                            monkeypatch):
    """Ordenada por nome, a linha 0 visual e' a AWP; self._rows[0] e' a
    caixa. O editor indexava self._rows[row] e gravava no item errado."""
    from PyQt6.QtCore import Qt
    tela.set_data(ROWS, POS, False)
    tela._table.sortItems(tela.COL_NAME, Qt.SortOrder.AscendingOrder)
    row_awp = _linha_de(tela, "AWP | Asiimov (Field-Tested)")
    assert tela._rows[row_awp]["name"] != "AWP | Asiimov (Field-Tested)"

    vistos = []

    class _Dlg:
        def __init__(self, nome, *a, **k):
            vistos.append(nome)

        def exec(self):
            from PyQt6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted

        def cost(self):
            return 400.0

    salvos = []
    monkeypatch.setattr("skinvault.ui.inventory_screen._CostDialog", _Dlg)
    monkeypatch.setattr(tela, "_salvar_custo",
                        lambda n, c: salvos.append((n, c)))
    tela._editar_custo_linha(row_awp)
    assert vistos == ["AWP | Asiimov (Field-Tested)"]
    assert salvos == [("AWP | Asiimov (Field-Tested)", 400.0)]


def test_custo_em_lote_aplica_a_todos_os_selecionados(tela, monkeypatch):
    tela.set_data(ROWS, POS, False)
    tela._table.selectAll()
    assert sorted(tela._nomes_selecionados()) == sorted(
        r["name"] for r in ROWS)

    class _Dlg:
        def __init__(self, *a, **k):
            pass

        def exec(self):
            from PyQt6.QtWidgets import QDialog
            return QDialog.DialogCode.Accepted

        def cost(self):
            return 0.0

    gravado = []
    monkeypatch.setattr("skinvault.ui.inventory_screen._CostDialog", _Dlg)
    monkeypatch.setattr("skinvault.portfolio.update_costs_bulk",
                        lambda c, *a, **k: gravado.append(c) or
                        {"atualizados": list(c), "nao_encontrados": []})
    reeval = []
    tela.request_reeval.connect(lambda: reeval.append(True))
    tela._definir_custo_em_lote(tela._nomes_selecionados())
    assert gravado == [{r["name"]: 0.0 for r in ROWS}]
    assert reeval == [True]


def test_importar_custos_csv_cp1252_e_resumo(tela, monkeypatch, tmp_path):
    """Excel salva CSV em ANSI: acento/★ nao pode derrubar a leitura."""
    arq = tmp_path / "custos.csv"
    arq.write_bytes("Item;Custo\nKilowatt Case;1,50\nCaixa Fantasma;3\n"
                    "AWP | Asiimov (Field-Tested);é\n".encode("cp1252"))
    monkeypatch.setattr(
        "skinvault.ui.inventory_screen.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(arq), ""))
    gravado = []
    monkeypatch.setattr(
        "skinvault.portfolio.update_costs_bulk",
        lambda c, *a, **k: gravado.append(c) or
        {"atualizados": [n for n in c if n != "Caixa Fantasma"],
         "nao_encontrados": [n for n in c if n == "Caixa Fantasma"]})
    avisos = []
    monkeypatch.setattr(
        "skinvault.ui.inventory_screen.QMessageBox.information",
        lambda *a, **k: avisos.append(a[2]))
    reeval = []
    tela.request_reeval.connect(lambda: reeval.append(True))
    tela._on_importar_custos_csv()
    assert gravado == [{"Kilowatt Case": 1.5, "Caixa Fantasma": 3.0}]
    assert reeval == [True]
    assert "1 item(ns)" in tela._status.text()
    assert len(avisos) == 1
    assert "Caixa Fantasma" in avisos[0] and "Linha 4" in avisos[0]


def test_importar_custos_csv_cancelado_nao_faz_nada(tela, monkeypatch):
    monkeypatch.setattr(
        "skinvault.ui.inventory_screen.QFileDialog.getOpenFileName",
        lambda *a, **k: ("", ""))
    chamado = []
    monkeypatch.setattr("skinvault.portfolio.update_costs_bulk",
                        lambda *a, **k: chamado.append(1))
    tela._on_importar_custos_csv()
    assert chamado == []


# ── boas-vindas ────────────────────────────────────────────────────

def test_welcome_botao_importar_marca_escolha():
    from PyQt6.QtWidgets import QApplication, QPushButton
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from skinvault.ui.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog()
    assert dlg.quer_importar is False
    botao = next(b for b in dlg.findChildren(QPushButton)
                 if "Importar" in b.text())
    assert botao.toolTip()
    botao.click()
    assert dlg.quer_importar is True


def test_router_abre_importacao_quando_welcome_pede(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import SCREEN_INVENTORY, ScreenRouter
    import skinvault.settings as _settings

    class _FakeWelcome:
        def __init__(self, parent=None):
            self.quer_importar = True

        def exec(self):
            return 1

    monkeypatch.setattr("skinvault.ui.welcome_dialog.WelcomeDialog",
                        _FakeWelcome)
    monkeypatch.setattr(_settings, "load_settings",
                        lambda: {"welcome_seen": False})
    monkeypatch.setattr(_settings, "save_settings", lambda s: None)
    router = ScreenRouter(PriceCache(ttl=3600))
    aberto = []
    monkeypatch.setattr(router._inventory_screen, "_on_importar_steam",
                        lambda: aberto.append(True))
    navegou = []
    monkeypatch.setattr(router, "navigate", navegou.append)
    router._maybe_show_welcome()
    app.processEvents()
    assert navegou == [SCREEN_INVENTORY]
    assert aberto == [True]
