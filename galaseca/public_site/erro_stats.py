"""Agrega linhas de `errors.log` por tipo de exceção e por dia.

Sem isto, o `/admin` só mostrava a lista crua das últimas linhas (ver
`server.py`), que não dá noção de "qual erro é mais comum" nem "hoje
teve mais erro que ontem" de cara -- só dava pra saber lendo tudo.
"""
from __future__ import annotations

import re

_TIPO_RE = re.compile(r": (\w+(?:Error|Exception|Warning))\(")


def agregar_por_tipo(linhas: list[str]) -> list[tuple[str, int]]:
    """[(tipo, contagem)], desc. "CSP violation" (não é exceção Python,
    é o `/api/csp-report` logando como erro) e "Outro" (linha sem tipo
    reconhecível) entram como categorias próprias."""
    contagem: dict[str, int] = {}
    for linha in linhas:
        if "CSP violation" in linha:
            tipo = "CSP violation"
        else:
            m = _TIPO_RE.search(linha)
            tipo = m.group(1) if m else "Outro"
        contagem[tipo] = contagem.get(tipo, 0) + 1
    return sorted(contagem.items(), key=lambda kv: -kv[1])


def serie_por_dia(linhas: list[str], dias: int = 14) -> list[tuple[str, int]]:
    """[(AAAA-MM-DD, contagem)] só dos dias com erro, até `dias` mais
    recentes. O formato do log (`RotatingFileHandler` com
    `%(asctime)s ...`) sempre começa com "AAAA-MM-DD HH:MM:SS,mmm"."""
    contagem: dict[str, int] = {}
    for linha in linhas:
        dia = linha[:10]
        if len(dia) == 10 and dia[4] == "-" and dia[7] == "-":
            contagem[dia] = contagem.get(dia, 0) + 1
    dias_ordenados = sorted(contagem)[-dias:]
    return [(d, contagem[d]) for d in dias_ordenados]
