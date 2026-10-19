"""Rotas gerais (misc.py) -- so' o que ganhou cobertura nova: servir
icone de item (/api/icon/<hash>). As demais (/, /api/ping, /api/events)
ja' sao exercitadas indiretamente pelos testes de cada tela.
"""
from __future__ import annotations

import pytest

from skinvault import icons as icons_mod
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_icon_404_quando_sem_cache_e_rede_falha(client, monkeypatch):
    monkeypatch.setattr(icons_mod, "fetch", lambda h, timeout=10.0: None)
    resp = client.get("/api/icon/algum-hash")
    assert resp.status_code == 404


def test_icon_serve_arquivo_do_cache(client, monkeypatch, tmp_path):
    arquivo = tmp_path / "icone.png"
    arquivo.write_bytes(b"\x89PNG\r\n fake-bytes")
    monkeypatch.setattr(icons_mod, "fetch", lambda h, timeout=10.0: arquivo)
    resp = client.get("/api/icon/algum-hash")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == arquivo.read_bytes()


def test_icon_aceita_hash_com_barra(client, monkeypatch, tmp_path):
    # icons.py: o hash as vezes vem com '/' -- a rota precisa aceitar
    # na URL (<path:...>), nao so' o nome de arquivo local sanitizado.
    arquivo = tmp_path / "icone.png"
    arquivo.write_bytes(b"fake")
    recebido = {}

    def fake_fetch(h, timeout=10.0):
        recebido["hash"] = h
        return arquivo

    monkeypatch.setattr(icons_mod, "fetch", fake_fetch)
    resp = client.get("/api/icon/abc/def-123")
    assert resp.status_code == 200
    assert recebido["hash"] == "abc/def-123"
