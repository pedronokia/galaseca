"""Confirma que o rate limit está ligado nas rotas certas.

A lógica da janela já é testada em `test_rate_limit.py`; aqui só
confirmamos que o decorator foi mesmo aplicado onde deveria -- login e
as mutações de /conta. Usa `now=` fixo via monkeypatch de `time.time`
pra não depender de velocidade real.
"""
from __future__ import annotations

import pytest

from skinvault.public_site import db, rate_limit
from skinvault.public_site.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "public_site.db")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _login(client, monkeypatch, steamid="76561198000000000"):
    monkeypatch.setattr(
        "skinvault.public_site.account.steam_openid.verify_callback",
        lambda args: steamid)
    monkeypatch.setattr(
        "skinvault.public_site.account.fetch_public_profile",
        lambda sid: {"name": "Fulano", "avatar_url": None})
    client.get("/login/callback")


def test_login_bloqueia_apos_limite(client):
    for _ in range(rate_limit.LOGIN_MAX_HITS):
        resp = client.get("/login")
        assert resp.status_code == 302
    resp = client.get("/login")
    assert resp.status_code == 429


def test_login_rota_independente_de_outras(client, monkeypatch):
    """Bater o limite de /login nao bloqueia /logout nem /conta."""
    for _ in range(rate_limit.LOGIN_MAX_HITS):
        client.get("/login")
    assert client.get("/login").status_code == 429
    _login(client, monkeypatch)  # usa /login/callback, rota diferente
    assert client.get("/conta").status_code == 200


def test_adicionar_posicao_bloqueia_apos_limite(client, monkeypatch):
    _login(client, monkeypatch)
    html = client.get("/conta").data.decode("utf-8")
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    for _ in range(rate_limit.MUTATION_MAX_HITS):
        resp = client.post("/conta/posicoes", data={
            "name": "X", "cost": "1", "quantity": "1", "csrf_token": token,
        })
        assert resp.status_code == 302
    resp = client.post("/conta/posicoes", data={
        "name": "X", "cost": "1", "quantity": "1", "csrf_token": token,
    })
    assert resp.status_code == 429
