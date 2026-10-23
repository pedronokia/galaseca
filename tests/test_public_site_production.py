"""Testes do endurecimento de produção (Fase 3): wsgi.py + config de cookie."""
from __future__ import annotations

from flask import Flask

from skinvault.public_site import server
from skinvault.public_site.wsgi import app as wsgi_app


def test_wsgi_app_e_flask_app():
    assert isinstance(wsgi_app, Flask)


def test_secure_cookie_desligado_por_padrao(monkeypatch):
    monkeypatch.delenv("SKINVAULT_PUBLIC_SITE_SECURE_COOKIES", raising=False)
    app = server.create_app()
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_secure_cookie_ligado_via_env(monkeypatch):
    monkeypatch.setenv("SKINVAULT_PUBLIC_SITE_SECURE_COOKIES", "1")
    app = server.create_app()
    assert app.config["SESSION_COOKIE_SECURE"] is True


def test_cookie_httponly_e_samesite_sempre_ligados():
    app = server.create_app()
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_proxy_fix_aplicado():
    from werkzeug.middleware.proxy_fix import ProxyFix
    app = server.create_app()
    assert isinstance(app.wsgi_app, ProxyFix)
