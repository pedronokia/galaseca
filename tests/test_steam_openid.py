"""Testes de steam_openid.py (login público, não a sessão revertida)."""
from __future__ import annotations

import httpx

from skinvault.public_site import steam_openid


def test_login_redirect_url_contem_params_esperados():
    url = steam_openid.login_redirect_url(
        "http://x.com/login/callback", "http://x.com/")
    assert url.startswith(steam_openid.STEAM_OPENID_URL)
    assert "openid.mode=checkid_setup" in url
    assert "openid.return_to=" in url
    assert "openid.realm=" in url
    assert "identifier_select" in url


def _args_validos():
    return {
        "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000000",
        "openid.identity": "https://steamcommunity.com/openid/id/76561198000000000",
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.sig": "assinatura",
    }


def test_verify_callback_sucesso(monkeypatch):
    class _Resp:
        text = "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _Resp())
    steamid = steam_openid.verify_callback(_args_validos())
    assert steamid == "76561198000000000"


def test_verify_callback_claimed_id_invalido():
    args = {"openid.claimed_id": "https://evil.com/id/123"}
    assert steam_openid.verify_callback(args) is None


def test_verify_callback_sem_claimed_id():
    assert steam_openid.verify_callback({}) is None


def test_verify_callback_steam_rejeita(monkeypatch):
    class _Resp:
        text = "ns:http://specs.openid.net/auth/2.0\nis_valid:false\n"

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _Resp())
    assert steam_openid.verify_callback(_args_validos()) is None


def test_verify_callback_erro_de_rede(monkeypatch):
    def _boom(*a, **kw):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "post", _boom)
    assert steam_openid.verify_callback(_args_validos()) is None


def test_verify_callback_reenvia_mode_check_authentication(monkeypatch):
    recebido = {}

    class _Resp:
        text = "is_valid:true"

    def _fake_post(url, data=None, timeout=None):
        recebido.update(data or {})
        return _Resp()

    monkeypatch.setattr(httpx, "post", _fake_post)
    steam_openid.verify_callback(_args_validos())
    assert recebido["openid.mode"] == "check_authentication"
