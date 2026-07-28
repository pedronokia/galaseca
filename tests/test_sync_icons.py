"""sync_inventory salva icone/tipo e faz backfill em posicao antiga."""
from __future__ import annotations

import json

from skinvault import sync


class _Sessao:
    steamid = "76561198000000042"


def _mock_inv(monkeypatch, items):
    monkeypatch.setattr(
        "skinvault.steam_api.fetch_inventory_authed",
        lambda s: ("ok", items))
    monkeypatch.setattr("skinvault.steam_api.INV_OK", "ok")


def _ler(p):
    return json.loads(p.read_text(encoding="utf-8"))


def test_posicao_nova_guarda_icone_e_tipo(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.json"
    _mock_inv(monkeypatch, [
        {"name": "Kilowatt Case", "quantity": 21, "icon": "hash1",
         "type": "Base Grade Container"},
    ])
    r = sync.sync_inventory(_Sessao(), path=p)
    assert r["added"] == 1
    pos = _ler(p)[0]
    assert pos["icon"] == "hash1"
    assert pos["type"] == "Base Grade Container"


def test_backfill_em_posicao_ja_existente(tmp_path, monkeypatch):
    """O caso real: quem sincronizou antes do campo existir.

    O laco antigo pulava nome ja' conhecido, entao a grade ficaria sem
    icone pra sempre nessas posicoes.
    """
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps([
        {"name": "Kilowatt Case", "cost": 0.0, "quantity": 21,
         "source": "steam_sync"},
    ]), encoding="utf-8")

    _mock_inv(monkeypatch, [
        {"name": "Kilowatt Case", "quantity": 21, "icon": "hash1",
         "type": "Base Grade Container"},
    ])
    r = sync.sync_inventory(_Sessao(), path=p)
    assert r["added"] == 0
    assert r["enriched"] == 1
    pos = _ler(p)[0]
    assert pos["icon"] == "hash1"
    assert pos["quantity"] == 21, "backfill nao pode mexer no resto"


def test_backfill_nao_sobrescreve_valor_existente(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps([
        {"name": "X", "cost": 5.0, "quantity": 1, "icon": "antigo"},
    ]), encoding="utf-8")
    _mock_inv(monkeypatch, [{"name": "X", "quantity": 1, "icon": "novo"}])
    r = sync.sync_inventory(_Sessao(), path=p)
    assert r["enriched"] == 0
    assert _ler(p)[0]["icon"] == "antigo"


def test_backfill_preserva_custo_manual(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps([
        {"name": "X", "cost": 42.0, "quantity": 1, "source": "manual"},
    ]), encoding="utf-8")
    _mock_inv(monkeypatch, [{"name": "X", "quantity": 9, "icon": "h"}])
    sync.sync_inventory(_Sessao(), path=p)
    pos = _ler(p)[0]
    assert pos["cost"] == 42.0
    assert pos["source"] == "manual"
    assert pos["icon"] == "h"


def test_item_sem_icone_nao_cria_campo_lixo(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps([{"name": "X", "cost": 0.0, "quantity": 1}]),
                 encoding="utf-8")
    _mock_inv(monkeypatch, [{"name": "X", "quantity": 1}])
    r = sync.sync_inventory(_Sessao(), path=p)
    assert r["enriched"] == 0
    assert "icon" not in _ler(p)[0]


def test_falha_de_inventario_nao_mexe_no_portfolio(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps([{"name": "X", "cost": 1.0, "quantity": 1}]),
                 encoding="utf-8")
    monkeypatch.setattr("skinvault.steam_api.fetch_inventory_authed",
                        lambda s: ("rate_limited", []))
    r = sync.sync_inventory(_Sessao(), path=p)
    assert r["added"] == 0
    assert _ler(p) == [{"name": "X", "cost": 1.0, "quantity": 1}]
