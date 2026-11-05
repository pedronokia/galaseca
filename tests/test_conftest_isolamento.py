"""Prova que o bloqueio de rede autouse de conftest.py (`_sem_rede`) de
fato cobre toda a superfície usada pelo projeto -- não só `httpx.get`.

Sem isto, um teste futuro que esquecesse de mockar `httpx.post`/
`httpx.Client` faria uma chamada de rede real em silêncio (achado da
auditoria da skill python-testing-patterns, 2026-11-05): o conftest só
bloqueava `httpx.get`, mas `steam_openid.py` usa `httpx.post` e
`discord_notify.py` usa `httpx.Client()`.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import httpx
import pytest


# Mensagem exata que `_sem_rede` usa -- travar nela (e não só no tipo da
# exceção) importa de verdade aqui: neste ambiente de execução, uma
# chamada de rede de verdade pra um host inválido já falha por conta
# própria (DNS), então um teste que só checasse o tipo passaria mesmo
# sem o mock estar ativo -- confirmado revertendo o fix e rodando este
# arquivo: 4 dos 5 testes "passavam" por acidente, só `httpx.Client`
# de fato denunciava a lacuna.
_MSG = "rede bloqueada na suite de testes"


def test_urlopen_bloqueado():
    with pytest.raises(urllib.error.URLError, match=_MSG):
        urllib.request.urlopen("http://exemplo.invalido")


def test_httpx_get_bloqueado():
    with pytest.raises(httpx.ConnectError, match=_MSG):
        httpx.get("http://exemplo.invalido")


def test_httpx_post_bloqueado():
    with pytest.raises(httpx.ConnectError, match=_MSG):
        httpx.post("http://exemplo.invalido")


def test_httpx_request_bloqueado():
    with pytest.raises(httpx.ConnectError, match=_MSG):
        httpx.request("GET", "http://exemplo.invalido")


def test_httpx_client_bloqueado():
    with pytest.raises(httpx.ConnectError, match=_MSG):
        httpx.Client()
