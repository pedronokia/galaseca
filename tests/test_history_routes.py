"""Testes das rotas de histórico pessoal -- Flask test client.

Mesmo padrão de `test_account_routes.py`. O ponto de histórico é
gravado por `account.py:conta()` -- essa rota precisa de um preço no
cache pra `evaluate_portfolio` fechar um `totals.market` numérico.
"""
from __future__ import annotations

import pytest
from urllib.parse import parse_qs, urlsplit

from galaseca.public_site import db
from galaseca.public_site.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "public_site.db")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _login(client, monkeypatch, steamid="76561198000000000"):
    monkeypatch.setattr(
        "galaseca.public_site.account.steam_openid.verify_callback",
        lambda args: steamid)
    monkeypatch.setattr(
        "galaseca.public_site.account.fetch_public_profile",
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


def test_listar_sem_login_redireciona(client):
    resp = client.get("/conta/historico")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_listar_sem_pontos_mostra_empty_state(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/conta/historico")
    assert resp.status_code == 200
    assert "Nenhum ponto registrado".encode("utf-8") in resp.data


def test_visitar_conta_grava_ponto_de_historico(client, monkeypatch):
    _login(client, monkeypatch)
    client.get("/conta")  # portfolio vazio -> totals.market == 0.0
    pagina = client.get("/conta/historico").data.decode("utf-8")
    assert "Nenhum ponto registrado" not in pagina
    assert "R$" in pagina


def test_visitar_conta_duas_vezes_sem_mudar_nao_duplica(client, monkeypatch):
    _login(client, monkeypatch)
    client.get("/conta")
    client.get("/conta")
    client.get("/conta")
    from galaseca.public_site import user_history
    pontos = user_history.load_history("76561198000000000")
    assert len(pontos) == 1


def test_grafico_aparece_apos_dois_pontos_distintos(client, monkeypatch):
    _login(client, monkeypatch)
    token_html = client.get("/conta").data.decode("utf-8")
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', token_html).group(1)
    client.post("/conta/posicoes", data={
        "name": "AK-47", "cost": "10", "quantity": "1", "csrf_token": token,
    })
    client.get("/conta")  # custo nao afeta market sem preco, mas garante 2a visita
    from galaseca.public_site import user_history
    # Forca dois pontos distintos direto no banco pra testar so' a tela.
    user_history.record_if_changed(
        "76561198000000000", 50.0, now=1.0)
    user_history.record_if_changed(
        "76561198000000000", 80.0, now=2.0)
    pagina = client.get("/conta/historico").data.decode("utf-8")
    assert "<svg" in pagina


def test_historico_isolado_entre_contas(client, monkeypatch):
    _login(client, monkeypatch, steamid="111")
    client.get("/conta")
    client.get("/logout")
    _login(client, monkeypatch, steamid="222")
    pagina = client.get("/conta/historico").data.decode("utf-8")
    assert "Nenhum ponto registrado".encode("utf-8") in pagina.encode("utf-8")
