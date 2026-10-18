"""Testes da tela de Configuracoes (web) -- Fase 6."""
from __future__ import annotations

from skinvault import backup as backup_mod
from skinvault import trades as trades_mod
from skinvault.settings import DEFAULTS, load_settings, save_settings
from skinvault.webapp.server import create_app

import pytest


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_settings_responde(client):
    resp = client.get("/configuracoes")
    assert resp.status_code == 200


def test_get_settings_devolve_subconjunto(client):
    resp = client.get("/api/settings")
    data = resp.get_json()
    assert set(data.keys()) == {
        "auto_backup", "keep_backups", "start_minimized",
        "minimize_to_tray_on_close", "overlay_mode",
        "cache_ttl_hours", "fee_rate",
    }


def test_update_settings_salva_e_persiste(client):
    resp = client.post("/api/settings", json={"keep_backups": 3, "fee_rate": 0.1})
    assert resp.status_code == 200
    assert resp.get_json()["keep_backups"] == 3
    assert load_settings()["keep_backups"] == 3
    assert load_settings()["fee_rate"] == pytest.approx(0.1)


def test_update_settings_rejeita_chave_desconhecida(client):
    resp = client.post("/api/settings", json={"theme": "light"})
    assert resp.status_code == 400


def test_update_settings_rejeita_fee_rate_fora_do_intervalo(client):
    resp = client.post("/api/settings", json={"fee_rate": 1.5})
    assert resp.status_code == 400


def test_update_settings_rejeita_keep_backups_negativo(client):
    resp = client.post("/api/settings", json={"keep_backups": -1})
    assert resp.status_code == 400


def test_reset_settings_volta_ao_padrao(client):
    client.post("/api/settings", json={"keep_backups": 99})
    resp = client.post("/api/settings/reset")
    assert resp.status_code == 200
    assert resp.get_json()["keep_backups"] == DEFAULTS["keep_backups"]


def test_backups_vazio(client, tmp_path, monkeypatch):
    # `backup._BACKUP_DIR` e' uma constante de modulo (nao aceita path por
    # chamada como trades/portfolio) -- sem isolar aqui, qualquer outro
    # teste da suite que ja tenha feito backup no mesmo DATA_DIR de teste
    # (compartilhado pela sessao inteira, ver conftest.py) faria esta
    # asserção falhar por acumulo, nao por bug.
    monkeypatch.setattr(backup_mod, "_BACKUP_DIR", tmp_path / "backups")
    resp = client.get("/api/settings/backups")
    assert resp.get_json()["backups"] == []


def test_fazer_backup_e_restaurar(client, tmp_path, monkeypatch):
    monkeypatch.setattr(backup_mod, "_BACKUP_DIR", tmp_path / "backups")
    trades_mod.record_trade("Item Backup", 10, 20, 1)

    resp = client.post("/api/settings/backup")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["path"]
    assert len(data["backups"]) == 1

    # Estraga o dado atual e restaura o backup de volta.
    trades_mod.save_trades([])
    assert trades_mod.load_trades() == []

    resp = client.post("/api/settings/restore", json={"path": data["path"]})
    assert resp.status_code == 200
    assert resp.get_json()["count"] > 0
    assert len(trades_mod.load_trades()) == 1
    assert trades_mod.load_trades()[0]["name"] == "Item Backup"


def test_restaurar_backup_inexistente(client):
    resp = client.post("/api/settings/restore", json={"path": "/tmp/nao-existe.zip"})
    assert resp.status_code == 404


def test_fazer_backup_sem_dados_devolve_erro(client, monkeypatch):
    monkeypatch.setattr(backup_mod, "make_backup", lambda *a, **k: None)
    resp = client.post("/api/settings/backup")
    assert resp.status_code == 400
