"""Testes de configuração/dedup do webhook Discord pessoal."""
from __future__ import annotations

from skinvault.public_site import user_webhook


def test_set_e_get_webhook_url(tmp_path):
    p = tmp_path / "x.db"
    user_webhook.set_webhook_url("1", "https://discord.example/hook", path=p)
    assert user_webhook.get_webhook_url("1", path=p) == "https://discord.example/hook"


def test_get_webhook_url_vazio_por_padrao(tmp_path):
    p = tmp_path / "x.db"
    assert user_webhook.get_webhook_url("1", path=p) == ""


def test_deve_notificar_primeira_vez(tmp_path):
    p = tmp_path / "x.db"
    assert user_webhook.deve_notificar("1", "Item X", path=p) is True


def test_deve_notificar_false_logo_apos_marcar(tmp_path):
    p = tmp_path / "x.db"
    user_webhook.marcar_notificado("1", "Item X", path=p, now=1000.0)
    assert user_webhook.deve_notificar("1", "Item X", path=p, now=1030.0) is False


def test_deve_notificar_true_apos_1h(tmp_path):
    p = tmp_path / "x.db"
    user_webhook.marcar_notificado("1", "Item X", path=p, now=1000.0)
    assert user_webhook.deve_notificar("1", "Item X", path=p, now=1000.0 + 3601) is True


def test_dedup_isolado_por_item(tmp_path):
    p = tmp_path / "x.db"
    user_webhook.marcar_notificado("1", "Item X", path=p, now=1000.0)
    assert user_webhook.deve_notificar("1", "Item Y", path=p, now=1000.0) is True
