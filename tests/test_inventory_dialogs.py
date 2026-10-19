"""Dialogos do Inventario: importar da Steam e adicionar item."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog

from skinvault import portfolio, steam_api

ID = "76561198023414915"


@pytest.fixture(autouse=True)
def _qapp():
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication.instance() or QApplication([])
    yield app


class _InlineThread:
    def __init__(self, target=None, daemon=None, **kw):
        self._target = target

    def start(self):
        if self._target is not None:
            self._target()


@pytest.fixture
def carteira(tmp_path, monkeypatch):
    """merge_steam_inventory grava num arquivo temporario."""
    arq = tmp_path / "portfolio.json"
    original = portfolio.merge_steam_inventory

    def _merge(items, remove_missing=True, path=None):
        return original(items, remove_missing=remove_missing, path=arq)

    monkeypatch.setattr(portfolio, "merge_steam_inventory", _merge)
    monkeypatch.setattr("threading.Thread", _InlineThread)
    return arq


def _dialogo(monkeypatch, resolve=None, fetch=None):
    if resolve is not None:
        monkeypatch.setattr(steam_api, "resolve_steam_id", resolve)
    if fetch is not None:
        monkeypatch.setattr(steam_api, "fetch_inventory", fetch)
    from skinvault.ui.inventory_dialogs import ImportarSteamDialog
    return ImportarSteamDialog()


# ── importar ─────────────────────────────────────────────────
def test_link_invalido_nao_busca_nada(monkeypatch, carteira):
    dlg = _dialogo(monkeypatch,
                   resolve=lambda t: pytest.fail("nao devia resolver"))
    dlg._link.setText("https://example.com/xyz")
    dlg._on_importar()
    assert "não parece um perfil" in dlg._status.text()
    assert dlg._importar.isEnabled() and not dlg.importou()


def test_inventario_privado_explica_como_abrir(monkeypatch, carteira):
    dlg = _dialogo(
        monkeypatch,
        resolve=lambda t: (steam_api.RESOLVE_OK, ID),
        fetch=lambda sid: (steam_api.INV_PRIVATE, []))
    dlg._link.setText(ID)
    dlg._on_importar()
    assert "privado" in dlg._status.text()
    assert "Público" in dlg._status.text()
    assert dlg._importar.isEnabled() and not dlg.importou()


def test_buscar_inventario_tenta_de_novo_apos_bloqueio_passageiro(monkeypatch):
    chamadas = []

    def fake_fetch(sid):
        chamadas.append(sid)
        if len(chamadas) < 3:
            return steam_api.INV_RATE_LIMITED, []
        return steam_api.INV_OK, [{"name": "AK-47 | Alfa (FT)", "quantity": 1}]

    monkeypatch.setattr(steam_api, "resolve_steam_id",
                         lambda t: (steam_api.RESOLVE_OK, ID))
    monkeypatch.setattr(steam_api, "fetch_inventory", fake_fetch)
    from skinvault.ui.inventory_dialogs import buscar_inventario
    status, itens = buscar_inventario(ID)
    assert status == steam_api.INV_OK
    assert len(chamadas) == 3
    assert len(itens) == 1


def test_perfil_nao_encontrado(monkeypatch, carteira):
    dlg = _dialogo(monkeypatch,
                   resolve=lambda t: (steam_api.RESOLVE_NOT_FOUND, None))
    dlg._link.setText("apelido-que-nao-existe")
    dlg._on_importar()
    assert "Não achamos esse perfil" in dlg._status.text()


def test_importacao_ok_mescla_resume_e_lembra_o_perfil(monkeypatch, carteira):
    from skinvault import settings
    itens = [{"name": "AK-47 | Alfa (FT)", "quantity": 2, "icon": "h",
              "type": "Rifle"}]
    dlg = _dialogo(
        monkeypatch,
        resolve=lambda t: (steam_api.RESOLVE_OK, ID),
        fetch=lambda sid: (steam_api.INV_OK, itens))
    link = f"https://steamcommunity.com/profiles/{ID}"
    dlg._link.setText(link)
    dlg._on_importar()
    assert dlg.importou()
    assert dlg.resumo()["adicionados"] == 1
    assert "1 novo(s) na carteira" in dlg._status.text()
    assert "defina o custo" in dlg._status.text()
    assert not dlg._importar.isVisibleTo(dlg)
    assert dlg._cancelar.text() == "Fechar"
    assert settings.load_settings()["steam_profile"] == link
    pos = portfolio.load_portfolio(carteira)
    assert pos[0]["name"] == "AK-47 | Alfa (FT)" and pos[0]["quantity"] == 2


def test_opcao_remover_vai_pra_mescla(monkeypatch, carteira):
    recebido = {}

    def _merge(items, remove_missing=True, path=None):
        recebido["remove"] = remove_missing
        return {"adicionados": 0, "atualizados": 0, "removidos": 0,
                "manuais_mantidos": 0, "itens_no_inventario": 0}

    monkeypatch.setattr(portfolio, "merge_steam_inventory", _merge)
    dlg = _dialogo(monkeypatch,
                   resolve=lambda t: (steam_api.RESOLVE_OK, ID),
                   fetch=lambda sid: (steam_api.INV_OK, []))
    dlg._link.setText(ID)
    dlg._remover.setChecked(False)
    dlg._on_importar()
    assert recebido["remove"] is False


def test_resumo_em_linguagem_comum():
    from skinvault.ui.inventory_dialogs import resumo_importacao
    txt = resumo_importacao({"adicionados": 3, "atualizados": 2,
                             "removidos": 1, "manuais_mantidos": 1,
                             "itens_no_inventario": 6})
    assert "6 item(ns) encontrados" in txt
    assert "3 novo(s)" in txt and "2 já estavam" in txt
    assert "1 não estavam mais no inventário" in txt
    assert "você já acompanhava à mão" in txt


# ── adicionar item ───────────────────────────────────────────
def _add_dialogo():
    from skinvault.ui.inventory_dialogs import AdicionarItemDialog
    return AdicionarItemDialog()


def test_adicionar_exige_nome():
    dlg = _add_dialogo()
    dlg._on_ok()
    assert dlg.valores() is None and "nome" in dlg._erro.text()


@pytest.mark.parametrize("texto,esperado", [
    ("", None), ("199,90", 199.9), ("1.234,50", 1234.5), ("0", 0.0),
])
def test_adicionar_custo_opcional(texto, esperado):
    dlg = _add_dialogo()
    dlg._nome.setText("Kilowatt Case")
    dlg._qtd.setValue(4)
    dlg._custo.setText(texto)
    dlg._on_ok()
    assert dlg.valores() == {"name": "Kilowatt Case", "quantity": 4,
                             "cost": esperado}


@pytest.mark.parametrize("texto", ["abc", "-5"])
def test_adicionar_custo_invalido(texto):
    dlg = _add_dialogo()
    dlg._nome.setText("X")
    dlg._custo.setText(texto)
    dlg._on_ok()
    assert dlg.valores() is None and "Custo inválido" in dlg._erro.text()


# ── ligacao com a tela ───────────────────────────────────────
def test_tela_adiciona_item_e_pede_reavaliacao(monkeypatch):
    from skinvault.ui import inventory_dialogs
    from skinvault.ui.inventory_screen import InventoryScreen

    class _Falso:
        def __init__(self, parent=None): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def valores(self):
            return {"name": "Fever Case", "quantity": 2, "cost": None}

    gravado = []
    monkeypatch.setattr(inventory_dialogs, "AdicionarItemDialog", _Falso)
    monkeypatch.setattr(portfolio, "add_position",
                        lambda n, c, q: gravado.append((n, c, q)))
    tela = InventoryScreen()
    sinais = []
    tela.request_reeval.connect(lambda: sinais.append(1))
    tela._on_adicionar_item()
    assert gravado == [("Fever Case", None, 2)] and sinais == [1]


def test_tela_vazia_oferece_importar():
    from skinvault.ui.inventory_screen import InventoryScreen
    tela = InventoryScreen()
    tela.set_data([], [], False)
    assert "Importe pelo link" in tela._empty._sub.text()
    assert tela._import_btn.text() == "Importar da Steam"
