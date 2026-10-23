"""Testes das rotas de trades pessoais -- Flask test client.

Mesmo padrão de `test_account_routes.py`: `db._DB_PATH` monkeypatchado
(as rotas não recebem `path=` do chamador).
"""
from __future__ import annotations

import re

import pytest

from skinvault.public_site import db
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


def _csrf_token(client):
    html = client.get("/conta/trades").data.decode("utf-8")
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1)


def test_listar_sem_login_redireciona(client):
    resp = client.get("/conta/trades")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_listar_vazio_mostra_empty_state(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/conta/trades")
    assert resp.status_code == 200
    assert "Nenhum trade registrado".encode("utf-8") in resp.data


def test_adicionar_trade(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    resp = client.post("/conta/trades", data={
        "name": "AK-47 | Redline (Field-Tested)", "buy_cost": "50.00",
        "sell_price": "80.00", "quantity": "1", "notes": "teste",
        "csrf_token": token,
    })
    assert resp.status_code == 302
    pagina = client.get("/conta/trades").data.decode("utf-8")
    assert "Testada em Campo" in pagina
    assert "teste" in pagina


def test_adicionar_trade_sem_csrf_falha(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/conta/trades", data={
        "name": "X", "buy_cost": "1", "sell_price": "2",
    })
    assert resp.status_code == 403


def test_adicionar_trade_custo_invalido_nao_grava(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/trades", data={
        "name": "X", "buy_cost": "abc", "sell_price": "2",
        "csrf_token": token,
    })
    pagina = client.get("/conta/trades").data.decode("utf-8")
    assert "Nenhum trade registrado".encode("utf-8") in pagina.encode("utf-8")


def test_remover_trade(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/trades", data={
        "name": "X", "buy_cost": "1", "sell_price": "2",
        "csrf_token": token,
    })
    client.post("/conta/trades/0/remover", data={"csrf_token": token})
    pagina = client.get("/conta/trades").data.decode("utf-8")
    assert "Nenhum trade registrado".encode("utf-8") in pagina.encode("utf-8")


def test_trades_isolados_entre_contas(client, monkeypatch):
    _login(client, monkeypatch, steamid="111")
    token = _csrf_token(client)
    client.post("/conta/trades", data={
        "name": "TradeDoUm", "buy_cost": "1", "sell_price": "2",
        "csrf_token": token,
    })
    client.get("/logout")
    _login(client, monkeypatch, steamid="222")
    pagina = client.get("/conta/trades").data.decode("utf-8")
    assert "TradeDoUm" not in pagina


def test_link_trades_aparece_no_dashboard_logado(client, monkeypatch):
    _login(client, monkeypatch)
    pagina = client.get("/").data.decode("utf-8")
    assert "/conta/trades" in pagina
