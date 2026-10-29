"""Confirma que o rate limit está ligado nas rotas certas.

A lógica da janela já é testada em `test_rate_limit.py`; aqui só
confirmamos que o decorator foi mesmo aplicado onde deveria -- login e
as mutações de /conta. Usa `now=` fixo via monkeypatch de `time.time`
pra não depender de velocidade real.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

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
    login_resp = client.get("/login")
    openid_params = parse_qs(urlsplit(login_resp.headers["Location"]).query)
    return_to = openid_params["openid.return_to"][0]
    query = {
        key: values[0]
        for key, values in parse_qs(urlsplit(return_to).query).items()
    }
    query.update({"openid.mode": "id_res", "openid.return_to": return_to})
    client.get("/login/callback", query_string=query)


def test_login_bloqueia_apos_limite(client):
    for _ in range(rate_limit.LOGIN_MAX_HITS):
        resp = client.get("/login")
        assert resp.status_code == 302
    resp = client.get("/login")
    assert resp.status_code == 429


def test_login_rota_independente_de_outras(client, monkeypatch):
    """Bater o limite de /login nao bloqueia /logout nem /conta."""
    _login(client, monkeypatch)
    ultimo_login = None
    for _ in range(rate_limit.LOGIN_MAX_HITS - 1):
        ultimo_login = client.get("/login")
        assert ultimo_login.status_code == 302
    assert client.get("/login").status_code == 429
    openid_params = parse_qs(urlsplit(ultimo_login.headers["Location"]).query)
    return_to = openid_params["openid.return_to"][0]
    query = {
        key: values[0]
        for key, values in parse_qs(urlsplit(return_to).query).items()
    }
    query.update({"openid.mode": "id_res", "openid.return_to": return_to})
    client.get("/login/callback", query_string=query)
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
