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


def test_enviar_sem_url_nao_tenta(monkeypatch):
    assert discord_notify.enviar("", "oi") is False


def test_enviar_sucesso(monkeypatch):
    fake = _FakeClient(status_code=204)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar("https://discord.example/hook", "alerta") is True
    assert fake.chamadas[0][0] == "https://discord.example/hook"


def test_enviar_falha_http_devolve_false(monkeypatch):
    fake = _FakeClient(status_code=404)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar("https://discord.example/hook", "alerta") is False


def test_enviar_excecao_de_rede_devolve_false(monkeypatch):
    fake = _FakeClient(levanta=OSError("sem rede"))
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    assert discord_notify.enviar("https://discord.example/hook", "alerta") is False


def test_enviar_trunca_mensagem_grande(monkeypatch):
    fake = _FakeClient(status_code=204)
    monkeypatch.setattr("httpx.Client", lambda **kw: fake)
    discord_notify.enviar("https://discord.example/hook", "x" * 3000)
    assert len(fake.chamadas[0][1]["content"]) == 2000
