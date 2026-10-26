"""Testes do envio de webhook Discord (skinvault/public_site/discord_notify.py)."""
from __future__ import annotations

from skinvault.public_site import discord_notify


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeClient:
    def __init__(self, status_code=204, levanta=None):
        self._status_code = status_code
        self._levanta = levanta
        self.chamadas = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None):
        self.chamadas.append((url, json))
        if self._levanta:
            raise self._levanta
        return _FakeResponse(self._status_code)


_WEBHOOK_OK = "https://discord.com/api/webhooks/123456789012345678/AbC-dEf_token"


def test_enviar_sem_url_nao_tenta(monkeypatch):
    assert discord_notify.enviar("", "oi") is False


def test_enviar_sucesso(monkeypatch):
    fake = _FakeClient(status_code=204)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar(_WEBHOOK_OK, "alerta") is True
    assert fake.chamadas[0][0] == _WEBHOOK_OK


def test_enviar_falha_http_devolve_false(monkeypatch):
    fake = _FakeClient(status_code=404)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar(_WEBHOOK_OK, "alerta") is False


def test_enviar_excecao_de_rede_devolve_false(monkeypatch):
    fake = _FakeClient(levanta=OSError("sem rede"))
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar(_WEBHOOK_OK, "alerta") is False


def test_enviar_trunca_mensagem_grande(monkeypatch):
    fake = _FakeClient(status_code=204)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    discord_notify.enviar(_WEBHOOK_OK, "x" * 3000)
    assert len(fake.chamadas[0][1]["content"]) == 2000


# ── url_valida / defesa contra SSRF ─────────────────────────────

def test_url_valida_aceita_discord_com():
    assert discord_notify.url_valida(
        "https://discord.com/api/webhooks/123/abcDEF") is True


def test_url_valida_aceita_discordapp_legado():
    assert discord_notify.url_valida(
        "https://discordapp.com/api/webhooks/123/abcDEF") is True


def test_url_valida_rejeita_host_arbitrario():
    # exatamente o caso que motivou a correção: um host interno/de nuvem
    # em vez de um webhook de verdade da Discord.
    assert discord_notify.url_valida("http://169.254.169.254/latest/meta-data/") is False


def test_url_valida_rejeita_http_sem_tls():
    assert discord_notify.url_valida(
        "http://discord.com/api/webhooks/123/abcDEF") is False


def test_url_valida_rejeita_vazio():
    assert discord_notify.url_valida("") is False


def test_url_valida_rejeita_dominio_parecido():
    # "discord.com.evil.example" tem discord.com como SUBSTRING mas não
    # é o host -- regex ancorada no início da URL (^https://domain\.com/)
    # já cobre isso, este teste trava a cobertura.
    assert discord_notify.url_valida(
        "https://discord.com.evil.example/api/webhooks/123/abcDEF") is False


def test_enviar_url_invalida_nao_chama_rede(monkeypatch):
    fake = _FakeClient(status_code=204)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar("http://169.254.169.254/", "oi") is False
    assert fake.chamadas == []
