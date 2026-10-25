"""Latência média por rota, em memória.

Aproximado de propósito -- mesmo espírito do `rate_limit.py`: cada
worker do gunicorn tem sua própria memória, então isto é "por worker",
não agregado globalmente entre processos. Suficiente pra notar uma
rota lenta no `/admin` sem trazer infraestrutura de métrica nova
(Prometheus etc.) pra um site de visitante único por request.
"""
from __future__ import annotations

from collections import defaultdict, deque

_JANELA = 200  # últimas N amostras por rota
_amostras: "dict[str, deque]" = defaultdict(lambda: deque(maxlen=_JANELA))


def registrar(endpoint: str, duracao_ms: float) -> None:
    if not endpoint:
        return
    _amostras[endpoint].append(duracao_ms)


def resumo() -> list[dict]:
    """[{endpoint, media_ms, contagem}], ordenado por média desc."""
    out = []
    for endpoint, valores in _amostras.items():
        if not valores:
            continue
        out.append({
            "endpoint": endpoint,
            "media_ms": round(sum(valores) / len(valores), 1),
            "contagem": len(valores),
        })
    out.sort(key=lambda d: -d["media_ms"])
    return out


def reset() -> None:
    """Limpa o estado -- o dict é de módulo e sobrevive entre testes na
    mesma sessão do pytest (mesmo padrão do disjuntor de rate limit)."""
    _amostras.clear()
