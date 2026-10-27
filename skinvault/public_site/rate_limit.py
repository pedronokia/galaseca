"""Limite de tentativas por IP -- janela deslizante em memória.

Hand-rolled, mesmo espírito do disjuntor de rate limit da Steam em
`steam_api.py` (dict de módulo, sem dependência nova) em vez de trazer
Flask-Limiter pra isto. Não é rigoroso sob múltiplos processos/workers
-- cada worker do gunicorn tem sua própria memória, então o limite real
é "por worker", não "por IP globalmente". É uma primeira camada contra
o caso óbvio (um script martelando `/login` ou os formulários de
`/conta`), não a palavra final: tráfego de produção de verdade quer um
backend compartilhado (Redis, por exemplo).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, request

_hits: "dict[str, deque]" = defaultdict(deque)

# Presets usados pelas rotas de /login e /conta/* -- um lugar só pra
# ajustar o número sem procurar em cada arquivo de rota.
LOGIN_MAX_HITS, LOGIN_WINDOW_S = 10, 60.0
MUTATION_MAX_HITS, MUTATION_WINDOW_S = 30, 60.0

# `/api/recommendations` é pública de propósito (pensada pra consumo
# programático -- ver api_docs.html) e mais generosa que os presets de
# formulário. `/api/csp-report` é posta só pelo próprio navegador do
# visitante (nunca por um humano clicando), então um volume normal é
# baixo -- o limite aqui é contra abuso, não contra uso real.
API_MAX_HITS, API_WINDOW_S = 60, 60.0
CSP_REPORT_MAX_HITS, CSP_REPORT_WINDOW_S = 20, 60.0

# `/icone/<hash>.jpg` (icon_cache.py) é pública, sem login, e um cache
# miss dispara requisição de rede pro CDN da Steam + grava um arquivo
# novo em disco -- sem limite nenhum, um hash diferente a cada chamada
# vira disco cheio (sem eviction no cache de ícone) e tráfego de saída
# sem fim, achado 2026-10-27 junto da sanitização do hash em
# icon_cache.obter(). Generoso o bastante pra uma página carregar
# dezenas de ícones distintos de uma vez sem barrar uso normal.
ICON_MAX_HITS, ICON_WINDOW_S = 120, 60.0


def allow(key: str, max_hits: int, window_seconds: float,
         now: "float | None" = None) -> bool:
    """True se `key` ainda tem orçamento na janela; já registra o hit.

    Janela deslizante: descarta hits mais velhos que `window_seconds`
    antes de contar.
    """
    ts = now if now is not None else time.time()
    hits = _hits[key]
    corte = ts - window_seconds
    while hits and hits[0] < corte:
        hits.popleft()
    if len(hits) >= max_hits:
        return False
    hits.append(ts)
    return True


def reset() -> None:
    """Limpa todo o estado -- o dict é de módulo e sobrevive entre
    testes na mesma sessão do pytest, mesmo padrão do disjuntor da
    Steam (`steam_api._rate_limit_state`)."""
    _hits.clear()


def rate_limited(max_hits: int, window_seconds: float):
    """Decorator de rota: `max_hits` por `window_seconds`, por IP+rota.

    Fica ANTES de `login_required`/`csrf_protect` na pilha de
    decorators (mais barato, roda primeiro) -- ver `account.py`/
    `trades_routes.py`/`watchlist_routes.py`.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr or "desconhecido"
            # `request.endpoint` distingue rota (ex.: "account.login" vs
            # "account.adicionar_posicao") -- um IP barrado numa rota
            # não fica barrado nas outras.
            key = f"{request.endpoint}:{ip}"
            if not allow(key, max_hits, window_seconds):
                abort(429)
            return view(*args, **kwargs)
        return wrapped
    return decorator
