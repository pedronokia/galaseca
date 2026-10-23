"""Ponto de entrada WSGI de produção (gunicorn).

`server.run()` é o dev server do Flask -- ótimo pra testar local
(`scripts/dev_public_site.py`), mas é single-threaded e não é feito pra
tráfego real. Em produção, o processo "web" aponta pra este módulo:

    gunicorn --bind 0.0.0.0:8000 --workers 2 skinvault.public_site.wsgi:app
"""
from __future__ import annotations

from skinvault.public_site.server import create_app

app = create_app()
