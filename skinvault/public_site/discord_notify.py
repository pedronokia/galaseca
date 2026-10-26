"""Envia alerta da watchlist pro Discord do próprio usuário (webhook que
ele mesmo configura e controla -- nunca escolhemos o canal por ele).

Única chamada de rede que sai do processo `web`: documentado à parte do
resto do site (que `NUNCA fala com a Steam`, ver server.py) porque
Discord não é a Steam -- a regra de "zero rede por visitante" é sobre
não martelar um endpoint agressivamente limitado, não sobre rede em
geral. Mesmo assim, timeout curto e falha sempre silenciosa: isso nunca
pode travar nem quebrar o carregamento de `/conta/watchlist`.
"""
from __future__ import annotations

import re

_TIMEOUT = 5.0

# Formato oficial de webhook do Discord (discord.com ou o domínio legado
# discordapp.com, ambos ainda aceitos pela própria Discord). Validar
# contra isso ANTES de deixar o servidor fazer o POST é a defesa contra
# SSRF: sem isso, um usuário logado podia colar qualquer URL (endpoint
# de metadata da nuvem, serviço interno do Docker) em `webhook_url` e o
# próprio servidor faria a requisição toda vez que ele abrisse
# `/conta/watchlist` com um alerta disparado -- achado em auditoria,
# 2026-10-26.
_WEBHOOK_RE = re.compile(
    r"^https://(discord|discordapp)\.com/api/webhooks/\d+/[\w.-]+/?$")


def url_valida(url: str) -> bool:
    """True só pro formato oficial de webhook do Discord."""
    return bool(url) and bool(_WEBHOOK_RE.match(url))


def enviar(webhook_url: str, mensagem: str) -> bool:
    """POST no webhook do Discord. True se aceito (204), False em
    qualquer outro caso -- nunca levanta exceção pra quem chama.

    Revalida o formato aqui dentro (não só na rota que salva a URL):
    é a ÚLTIMA linha de defesa antes da requisição de rede sair, caso
    uma URL inválida chegue até aqui por outro caminho."""
    if not url_valida(webhook_url):
        return False
    try:
        import httpx
    except ImportError:
        return False
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(webhook_url, json={"content": mensagem[:2000]})
            return resp.status_code in (200, 204)
    except Exception:
        return False
