"""Testes das rotas de conta (login/logout/portfólio) -- Flask test client.

`db._DB_PATH` é monkeypatchado (não `path=` explícito): as rotas de
`account.py` não recebem `path` do chamador, então o isolamento por teste
depende do módulo reler `_DB_PATH` em tempo de chamada -- exatamente o
que `db.connect` foi desenhado pra fazer (ver gotcha #17 do AGENTS.md:
isto só funciona porque `db.connect` resolve o default DENTRO da função,
não como valor de parâmetro congelado na definição).
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from skinvault.public_site import db
from skinvault.public_site.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "public_site.db")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _login(client, monkeypatch, steamid="76561198000000000",
          nome="Fulano", avatar="http://x/a.jpg"):
    monkeypatch.setattr(
        "skinvault.public_site.account.steam_openid.verify_callback",
        lambda args: steamid)
    monkeypatch.setattr(
        "skinvault.public_site.account.fetch_public_profile",
        lambda sid: {"name": nome, "avatar_url": avatar})
    return client.get(
        "/login/callback", query_string=_callback_query(_start_login(client)))


def _start_login(client):
    login_resp = client.get("/login")
    openid_params = parse_qs(urlsplit(login_resp.headers["Location"]).query)
    return openid_params["openid.return_to"][0]


def _callback_query(return_to):
    query = {
        key: values[0]
        for key, values in parse_qs(urlsplit(return_to).query).items()
    }
    query.update({"openid.mode": "id_res", "openid.return_to": return_to})
    return query


# ── login/logout ─────────────────────────────────────────────

def test_login_redireciona_pra_steam(client):
    resp = client.get("/login")
    assert resp.status_code == 302
    assert "steamcommunity.com/openid/login" in resp.headers["Location"]


def test_login_callback_invalido_volta_pro_dashboard(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.account.steam_openid.verify_callback",
        lambda args: None)
    resp = client.get(
        "/login/callback", query_string=_callback_query(_start_login(client)))
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")


def test_login_callback_sem_fluxo_iniciado_nao_autentica(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "skinvault.public_site.account.steam_openid.verify_callback",
        lambda args: chamadas.append(args) or "76561198000000000")

    resp = client.get("/login/callback?openid.mode=id_res")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    assert chamadas == []
    with client.session_transaction() as sess:
        assert "steamid" not in sess


def test_login_callback_exige_return_to_da_sessao(client, monkeypatch):
    return_to = _start_login(client)
    chamadas = []
    monkeypatch.setattr(
        "skinvault.public_site.account.steam_openid.verify_callback",
        lambda args: chamadas.append(args) or "76561198000000000")

    query = _callback_query(return_to)
    query["state"] = "estado-de-outra-sessao"
    resp = client.get("/login/callback", query_string=query)

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    assert chamadas == []


def test_login_callback_so_aceita_o_return_to_uma_vez(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "skinvault.public_site.account.steam_openid.verify_callback",
        lambda args: chamadas.append(args) or "76561198000000000")
    return_to = _start_login(client)
    query = _callback_query(return_to)

    primeiro = client.get("/login/callback", query_string=query)
    replay = client.get("/login/callback", query_string=query)

    assert primeiro.headers["Location"].endswith("/conta")
    assert replay.headers["Location"].endswith("/")
    assert len(chamadas) == 1


def test_login_callback_sucesso_cria_sessao_e_redireciona_pra_conta(
        client, monkeypatch):
    resp = _login(client, monkeypatch)
    assert resp.status_code == 302
    assert "/conta" in resp.headers["Location"]


def test_login_callback_cria_usuario_no_banco(client, monkeypatch):
    _login(client, monkeypatch, steamid="123", nome="Fulano")
    from skinvault.public_site import user_store
    assert user_store.get_user("123")["persona_name"] == "Fulano"


def test_logout_limpa_sessao(client, monkeypatch):
    _login(client, monkeypatch)
    client.get("/logout")
    resp = client.get("/conta")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


# ── /conta exige login ───────────────────────────────────────

def test_conta_sem_login_redireciona(client):
    resp = client.get("/conta")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_conta_logado_mostra_pagina(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/conta")
    assert resp.status_code == 200
    assert "Fulano".encode() in resp.data


def test_conta_busca_usuario_uma_vez_so(client, monkeypatch):
    """`conta()` passava `usuario=user_store.get_user(steamid)` pro
    template, mas o context processor `_inject_usuario` (server.py) já
    busca o MESMO usuário pra todo template com sessão ativa -- dobrava
    a leitura SQLite (duas conexões abertas/fechadas) sem mudar nenhum
    valor. Corrigido pra deixar só o context processor buscar."""
    from skinvault.public_site import user_store
    _login(client, monkeypatch)
    chamadas = []
    original = user_store.get_user

    def _contada(steamid, path=None):
        chamadas.append(steamid)
        return original(steamid, path=path)

    monkeypatch.setattr(user_store, "get_user", _contada)
    resp = client.get("/conta")
    assert resp.status_code == 200
    assert "Fulano".encode() in resp.data
    assert len(chamadas) == 1


def test_conta_vazia_mostra_empty_state(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/conta")
    assert "Nenhum item ainda".encode("utf-8") in resp.data


# ── CRUD de posicoes ─────────────────────────────────────────

def _csrf_token(client):
    html = client.get("/conta").data.decode("utf-8")
    import re
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1)


def test_adicionar_posicao(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    resp = client.post("/conta/posicoes", data={
        "name": "AK-47 | Redline (Field-Tested)", "cost": "50.00",
        "quantity": "1", "csrf_token": token,
    })
    assert resp.status_code == 302
    pagina = client.get("/conta").data.decode("utf-8")
    assert "Testada em Campo" in pagina  # localize_name


def test_adicionar_posicao_sem_csrf_falha(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/conta/posicoes", data={
        "name": "X", "cost": "1", "quantity": "1",
    })
    assert resp.status_code == 403


def test_adicionar_posicao_sem_login_redireciona(client):
    resp = client.post("/conta/posicoes", data={"name": "X"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_adicionar_posicao_rejeita_custo_nao_numerico(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    resp = client.post("/conta/posicoes", data={
        "name": "X", "cost": "abc", "quantity": "1",
        "csrf_token": token,
    })
    assert resp.status_code == 302
    pagina = client.get(resp.headers["Location"]).data.decode("utf-8")
    assert "O custo precisa ser um número válido e igual ou maior que zero" in pagina
    assert "Nenhum item ainda" in pagina


def test_adicionar_posicao_rejeita_quantidade_zero(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    resp = client.post("/conta/posicoes", data={
        "name": "X", "cost": "10", "quantity": "0",
        "csrf_token": token,
    })
    assert resp.status_code == 302
    pagina = client.get(resp.headers["Location"]).data.decode("utf-8")
    assert "A quantidade precisa ser um número inteiro maior que zero" in pagina
    assert "Nenhum item ainda" in pagina


def test_editar_custo(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "X", "cost": "10", "quantity": "1", "csrf_token": token,
    })
    client.post("/conta/posicoes/X/custo", data={
        "cost": "99.90", "csrf_token": token,
    })
    pagina = client.get("/conta").data.decode("utf-8")
    assert "99,90" in pagina


def test_editar_custo_invalido_preserva_custo_atual(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "X", "cost": "10", "quantity": "1", "csrf_token": token,
    })
    resp = client.post("/conta/posicoes/X/custo", data={
        "cost": "-1", "csrf_token": token,
    })
    assert resp.status_code == 302
    pagina = client.get(resp.headers["Location"]).data.decode("utf-8")
    assert "O custo precisa ser um número válido e igual ou maior que zero" in pagina
    assert "10,00" in pagina


def test_remover_posicao(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "X", "cost": "10", "quantity": "1", "csrf_token": token,
    })
    client.post("/conta/posicoes/X/remover", data={"csrf_token": token})
    pagina = client.get("/conta").data.decode("utf-8")
    assert "Nenhum item ainda".encode("utf-8") in pagina.encode("utf-8")


def test_posicoes_isoladas_entre_contas(client, monkeypatch):
    _login(client, monkeypatch, steamid="111")
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "ItemDoUm", "cost": "1", "quantity": "1",
        "csrf_token": token,
    })
    client.get("/logout")
    _login(client, monkeypatch, steamid="222")
    pagina = client.get("/conta").data.decode("utf-8")
    assert "ItemDoUm" not in pagina


# ── excluir conta ────────────────────────────────────────────

def test_excluir_confirmar_sem_login_redireciona(client):
    resp = client.get("/conta/excluir")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_excluir_confirmar_mostra_pagina(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/conta/excluir")
    assert resp.status_code == 200
    assert "irreversível".encode("utf-8") in resp.data.lower()


def test_excluir_sem_csrf_falha(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/conta/excluir", data={})
    assert resp.status_code == 403


def test_excluir_apaga_conta_e_desloga(client, monkeypatch):
    _login(client, monkeypatch, steamid="76561198000000000")
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "X", "cost": "1", "quantity": "1", "csrf_token": token,
    })
    resp = client.post("/conta/excluir", data={"csrf_token": token})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/")
    # sessao foi limpa -- /conta volta a exigir login
    assert client.get("/conta").status_code == 302

    from skinvault.public_site import user_store
    assert user_store.get_user("76561198000000000") is None


def test_excluir_nao_afeta_outra_conta(client, monkeypatch):
    _login(client, monkeypatch, steamid="111")
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "ItemDoUm", "cost": "1", "quantity": "1",
        "csrf_token": token,
    })
    client.get("/logout")

    _login(client, monkeypatch, steamid="222")
    token2 = _csrf_token(client)
    client.post("/conta/excluir", data={"csrf_token": token2})

    from skinvault.public_site import user_portfolio
    assert [p["name"] for p in user_portfolio.load_positions("111")] == (
        ["ItemDoUm"])


# ── pagina de privacidade ────────────────────────────────────

def test_privacidade_acessivel_sem_login(client):
    resp = client.get("/privacidade")
    assert resp.status_code == 200
    assert "SteamID64".encode("utf-8") in resp.data


def test_privacidade_linkada_no_rodape(client):
    pagina = client.get("/").data.decode("utf-8")
    assert "/privacidade" in pagina


# ── Lote 10: exportar dados (LGPD) + limpeza de avatar na exclusão ──

def test_exportar_dados_sem_login_redireciona(client):
    resp = client.get("/conta/exportar")
    assert resp.status_code == 302


def test_exportar_dados_com_login_devolve_json(client, monkeypatch):
    _login(client, monkeypatch, steamid="76561198000000001")
    token = _csrf_token(client)
    client.post("/conta/posicoes", data={
        "name": "AK-47 | Redline", "cost": "100", "quantity": "2",
        "csrf_token": token,
    })
    resp = client.get("/conta/exportar")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["usuario"]["steamid"] == "76561198000000001"
    assert len(data["portfolio"]) == 1
    assert data["portfolio"][0]["name"] == "AK-47 | Redline"
    assert "attachment" in resp.headers.get("Content-Disposition", "")


def test_excluir_apaga_avatar_em_cache(client, monkeypatch, tmp_path):
    from skinvault.ui import profile_fetcher
    monkeypatch.setattr(profile_fetcher, "_PROFILES_PATH", tmp_path / "perfis.json")
    monkeypatch.setattr(profile_fetcher, "_AVATARS_DIR", tmp_path / "avatars")
    steamid = "76561198000000002"
    profile_fetcher._AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    avatar_path = profile_fetcher._AVATARS_DIR / f"{steamid}.jpg"
    avatar_path.write_bytes(b"fake-jpeg")
    profile_fetcher._save_cache({steamid: {"name": "Fulano"}})

    _login(client, monkeypatch, steamid=steamid)
    token = _csrf_token(client)
    client.post("/conta/excluir", data={"csrf_token": token})

    assert not avatar_path.exists()
    assert steamid not in profile_fetcher._load_cache()
