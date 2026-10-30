"""Testes de steam_openid.py (login público, não a sessão revertida)."""
from __future__ import annotations

import httpx
import pytest

from galaseca.public_site import steam_openid


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
        "openid.mode": "id_res",
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.op_endpoint": steam_openid.STEAM_OPENID_URL,
        "openid.return_to": "https://example.com/login/callback?state=abc",
        "openid.response_nonce": "2026-10-29T17:00:00Zabc",
        "openid.assoc_handle": "handle",
        "openid.signed": (
            "op_endpoint,return_to,response_nonce,assoc_handle,"
            "claimed_id,identity"
        ),
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


@pytest.mark.parametrize("campo", [
    "op_endpoint",
    "return_to",
    "response_nonce",
    "assoc_handle",
    "claimed_id",
    "identity",
])
def test_verify_callback_exige_campos_obrigatorios_assinados(
        monkeypatch, campo):
    chamadas = []

    class _Resp:
        text = "is_valid:true"

    monkeypatch.setattr(
        httpx, "post", lambda *a, **kw: chamadas.append(a) or _Resp())
    args = _args_validos()
    campos_assinados = args["openid.signed"].split(",")
    campos_assinados.remove(campo)
    args["openid.signed"] = ",".join(campos_assinados)

    assert steam_openid.verify_callback(args) is None
    assert chamadas == []


@pytest.mark.parametrize(("campo", "valor"), [
    ("openid.mode", "cancel"),
    ("openid.ns", "http://specs.openid.net/auth/1.1"),
    ("openid.op_endpoint", "https://evil.example/openid"),
    ("openid.identity",
     "https://steamcommunity.com/openid/id/76561198000000001"),
])
def test_verify_callback_rejeita_assertion_incompativel(
        monkeypatch, campo, valor):
    chamadas = []

    class _Resp:
        text = "is_valid:true"

    monkeypatch.setattr(
        httpx, "post", lambda *a, **kw: chamadas.append(a) or _Resp())
    args = _args_validos()
    args[campo] = valor

    assert steam_openid.verify_callback(args) is None
    assert chamadas == []


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
