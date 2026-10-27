"""Testes das rotas de watchlist pessoal -- Flask test client.

Mesmo padrão de `test_account_routes.py`: `db._DB_PATH` monkeypatchado.
Preço/volume/oferta/score mockados -- a avaliação de regras em si já é
testada em `tests/test_alerts.py`; aqui só confirmamos que a rota liga
tudo certo.
"""
from __future__ import annotations

import re

import pytest

from skinvault.public_site import db, watchlist_routes
from skinvault.public_site.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_DB_PATH", tmp_path / "public_site.db")

    class _FakeCache:
        def get(self, name, now=None):
            return {"AK-47": 10.0, "M4A4": 100.0}.get(name)

    monkeypatch.setattr(watchlist_routes, "PriceCache", _FakeCache)
    monkeypatch.setattr(
        "skinvault.signals.load_item_volume", lambda name: [])
    monkeypatch.setattr(
        "skinvault.signals.load_item_supply", lambda name: [])
    monkeypatch.setattr(
        "skinvault.scan_store.load_last_scan", lambda: None)

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
    html = client.get("/conta/watchlist").data.decode("utf-8")
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1)


def test_listar_sem_login_redireciona(client):
    resp = client.get("/conta/watchlist")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_listar_vazio_mostra_empty_state(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.get("/conta/watchlist")
    assert resp.status_code == 200
    assert "Nenhum item acompanhado".encode("utf-8") in resp.data


def test_adicionar_item(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    resp = client.post("/conta/watchlist", data={
        "name": "AK-47", "target": "15.00", "csrf_token": token,
    })
    assert resp.status_code == 302
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "AK-47" in pagina


def test_adicionar_sem_csrf_falha(client, monkeypatch):
    _login(client, monkeypatch)
    resp = client.post("/conta/watchlist", data={"name": "AK-47"})
    assert resp.status_code == 403


def test_item_sem_regra_mostra_sem_gatilho(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "AK-47", "target": "0", "csrf_token": token,
    })
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "sem gatilho agora" in pagina
    assert "dispararia agora" not in pagina


def test_price_below_dispara(client, monkeypatch):
    """AK-47 custa 10.0 no cache fake; alvo 15 deve disparar."""
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "AK-47", "target": "15.00", "csrf_token": token,
    })
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "dispararia agora" in pagina


def test_price_below_nao_dispara_quando_preco_acima(client, monkeypatch):
    """M4A4 custa 100.0 no cache fake; alvo 5 nao deve disparar."""
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "M4A4", "target": "5.00", "csrf_token": token,
    })
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "sem gatilho agora" in pagina


def test_editar_regras(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "AK-47", "csrf_token": token,
    })
    client.post("/conta/watchlist/AK-47/regras", data={
        "price_drop_pct": "10", "baseline_price": "20", "csrf_token": token,
    })
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "queda 10%" in pagina


def test_remover_item(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "AK-47", "csrf_token": token,
    })
    client.post("/conta/watchlist/AK-47/remover", data={"csrf_token": token})
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "Nenhum item acompanhado".encode("utf-8") in pagina.encode("utf-8")


def test_itens_isolados_entre_contas(client, monkeypatch):
    _login(client, monkeypatch, steamid="111")
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "AK-47", "csrf_token": token,
    })
    client.get("/logout")
    _login(client, monkeypatch, steamid="222")
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "AK-47" not in pagina


# ── webhook Discord ──────────────────────────────────────────

_WEBHOOK_OK = "https://discord.com/api/webhooks/111/abcDEF"


def test_salvar_webhook(client, monkeypatch):
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist/webhook", data={
        "webhook_url": _WEBHOOK_OK, "csrf_token": token,
    })
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert _WEBHOOK_OK in pagina


def test_salvar_webhook_url_invalida_nao_salva(client, monkeypatch):
    # Caso que motivou a correção (SSRF): uma URL que não é um webhook
    # de verdade da Discord não pode ser persistida.
    _login(client, monkeypatch)
    token = _csrf_token(client)
    resp = client.post("/conta/watchlist/webhook", data={
        "webhook_url": "http://169.254.169.254/latest/meta-data/",
        "csrf_token": token,
    })
    assert resp.status_code == 302
    assert "erro_webhook" in resp.headers["Location"]
    pagina = client.get(resp.headers["Location"]).data.decode("utf-8")
    assert "169.254.169.254" not in pagina
    assert "não parece um webhook" in pagina


def test_webhook_isolado_entre_contas(client, monkeypatch):
    _login(client, monkeypatch, steamid="111")
    token = _csrf_token(client)
    client.post("/conta/watchlist/webhook", data={
        "webhook_url": "https://discord.com/api/webhooks/111/hook-111",
        "csrf_token": token,
    })
    client.get("/logout")
    _login(client, monkeypatch, steamid="222")
    pagina = client.get("/conta/watchlist").data.decode("utf-8")
    assert "hook-111" not in pagina


def test_item_disparado_envia_webhook(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "skinvault.public_site.watchlist_routes.discord_notify.enviar",
        lambda url, texto: chamadas.append((url, texto)) or True)
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist/webhook", data={
        "webhook_url": _WEBHOOK_OK, "csrf_token": token,
    })
    client.post("/conta/watchlist", data={
        "name": "AK-47", "target": "50", "csrf_token": token,
    })
    client.get("/conta/watchlist")
    assert len(chamadas) == 1
    assert chamadas[0][0] == _WEBHOOK_OK


def test_item_nao_disparado_nao_envia_webhook(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "skinvault.public_site.watchlist_routes.discord_notify.enviar",
        lambda url, texto: chamadas.append((url, texto)) or True)
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist/webhook", data={
        "webhook_url": _WEBHOOK_OK, "csrf_token": token,
    })
    # AK-47 preco = 10.0, target bem abaixo -- nao dispara
    client.post("/conta/watchlist", data={
        "name": "AK-47", "target": "1", "csrf_token": token,
    })
    client.get("/conta/watchlist")
    assert chamadas == []


def test_sem_webhook_configurado_nao_tenta_enviar(client, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "skinvault.public_site.watchlist_routes.discord_notify.enviar",
        lambda url, texto: chamadas.append((url, texto)) or True)
    _login(client, monkeypatch)
    token = _csrf_token(client)
    client.post("/conta/watchlist", data={
        "name": "AK-47", "target": "50", "csrf_token": token,
    })
    client.get("/conta/watchlist")
    assert chamadas == []


def test_listar_busca_webhook_url_uma_vez_so(client, monkeypatch):
    """get_webhook_url abre uma conexão SQLite por chamada (db.connect
    via user_store.load_user_json) -- listar() buscava duas vezes na
    mesma requisição (uma pra _notificar_discord, outra pro template).
    Corrigido pra buscar uma vez e reaproveitar."""
    chamadas = []
    original = watchlist_routes.user_webhook.get_webhook_url

    def _contada(steamid, path=None):
        chamadas.append(steamid)
        return original(steamid, path=path)

    monkeypatch.setattr(
        watchlist_routes.user_webhook, "get_webhook_url", _contada)
    _login(client, monkeypatch)
    _csrf_token(client)  # já conta 1 GET -- reseta antes da medição
    chamadas.clear()
    client.get("/conta/watchlist")
    assert len(chamadas) == 1
