"""Testes da tela de Limpeza (web) -- Fase 9.

PERIGO: `cleanup.py` apaga arquivo de verdade a partir de env vars
(TEMP/SystemRoot/LOCALAPPDATA) resolvidas NA HORA da chamada. Uma env
var esquecida nao da' erro -- o alvo cai no caminho REAL da maquina. Ja
aconteceu durante o desenvolvimento deste modulo (ver tests/test_cleanup.py:
22 arquivos reais apagados por um teste que so' patchou TEMP/TMP e
esqueceu SystemRoot). `isolate_env` aqui e' autouse por isso: protege
TODO teste deste arquivo, inclusive um que alguem adicione depois sem
lembrar de isolar.
"""
from __future__ import annotations

import pytest

from skinvault import cleanup as cleanup_mod
from skinvault.webapp.server import create_app


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    sandbox = tmp_path / "_env"
    sandbox.mkdir(exist_ok=True)
    for var in ("TEMP", "TMP", "SystemRoot", "windir", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(sandbox / var))
    monkeypatch.setattr(cleanup_mod, "_protected_paths", lambda: [])
    monkeypatch.setattr(cleanup_mod, "recycle_bin_query", lambda: (0, 0))
    monkeypatch.setattr(cleanup_mod, "recycle_bin_empty", lambda: True)
    yield sandbox


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    winroot = tmp_path / "Windows"
    local = tmp_path / "Local"
    for p in (temp, winroot / "Prefetch",
              winroot / "SoftwareDistribution" / "Download",
              local / "Microsoft" / "Windows" / "Explorer"):
        p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))
    monkeypatch.setenv("SystemRoot", str(winroot))
    monkeypatch.setenv("windir", str(winroot))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    return {"temp": temp, "win": winroot, "local": local}


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_pagina_cleanup_responde(client):
    resp = client.get("/limpeza")
    assert resp.status_code == 200


def test_status_lista_todos_os_alvos(client, fake_env):
    resp = client.get("/api/cleanup/status")
    data = resp.get_json()
    keys = {t["key"] for t in data["targets"]}
    assert keys == set(cleanup_mod.TARGET_KEYS)


def test_status_mede_arquivos_de_verdade(client, fake_env):
    (fake_env["temp"] / "a.tmp").write_bytes(b"x" * 100)
    (fake_env["temp"] / "b.tmp").write_bytes(b"y" * 50)
    resp = client.get("/api/cleanup/status")
    data = resp.get_json()
    temp_target = next(t for t in data["targets"]
                        if t["key"] == cleanup_mod.TEMP_FILES)
    assert temp_target["files"] == 2
    assert temp_target["bytes"] == 150


def test_status_lixeira_nunca_vem_selecionada(client, fake_env):
    from skinvault.settings import load_settings, save_settings
    s = load_settings()
    s["cleanup_selected"] = [cleanup_mod.RECYCLE_BIN, cleanup_mod.TEMP_FILES]
    save_settings(s)
    resp = client.get("/api/cleanup/status")
    data = resp.get_json()
    by_key = {t["key"]: t for t in data["targets"]}
    assert by_key[cleanup_mod.RECYCLE_BIN]["selected"] is False
    assert by_key[cleanup_mod.TEMP_FILES]["selected"] is True


def test_salvar_selecao(client, fake_env):
    resp = client.post("/api/cleanup/selection", json={
        "keys": [cleanup_mod.TEMP_FILES, "chave-invalida"],
    })
    assert resp.status_code == 200
    from skinvault.settings import load_settings
    assert load_settings()["cleanup_selected"] == [cleanup_mod.TEMP_FILES]


def test_salvar_selecao_rejeita_formato_errado(client):
    resp = client.post("/api/cleanup/selection", json={"keys": "nao-e-lista"})
    assert resp.status_code == 400


def test_clean_remove_arquivos_isolados(client, fake_env):
    (fake_env["temp"] / "a.tmp").write_bytes(b"x" * 100)
    resp = client.post("/api/cleanup/clean", json={
        "keys": [cleanup_mod.TEMP_FILES],
    })
    assert resp.status_code == 200
    result = resp.get_json()["results"][cleanup_mod.TEMP_FILES]
    assert result["removed"] == 1
    assert result["freed"] == 100
    assert not (fake_env["temp"] / "a.tmp").exists()
    # A raiz do alvo nunca e' apagada, so' o conteudo.
    assert fake_env["temp"].is_dir()


def test_clean_rejeita_lista_vazia(client):
    resp = client.post("/api/cleanup/clean", json={"keys": []})
    assert resp.status_code == 400


def test_clean_rejeita_chave_desconhecida(client):
    resp = client.post("/api/cleanup/clean", json={"keys": ["chave-invalida"]})
    assert resp.status_code == 400


def test_clean_lixeira_usa_mock_nao_a_maquina_real(client, fake_env):
    """Garante que a rota de limpeza NUNCA chega no shell32 de verdade
    durante o teste -- `isolate_env` ja mocka as duas funcoes de lixeira."""
    resp = client.post("/api/cleanup/clean", json={
        "keys": [cleanup_mod.RECYCLE_BIN],
    })
    assert resp.status_code == 200
    assert resp.get_json()["results"][cleanup_mod.RECYCLE_BIN]["removed"] == 0
