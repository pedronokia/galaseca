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

_TIMEOUT = 5.0


def enviar(webhook_url: str, mensagem: str) -> bool:
    """POST no webhook do Discord. True se aceito (204), False em
    qualquer outro caso -- nunca levanta exceção pra quem chama."""
    if not webhook_url:
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
