"""Contador de visitas simples e privado -- só pra saber se alguém usa.

Sem cookie, sem IP, sem nada por visitante (a página de privacidade já
promete isso). Total acumulado + série por dia (pro gráfico em /status).
Não é analytics de verdade, é um termômetro.
"""
from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

from lodout._paths import DATA_DIR, atomic_write_text, load_json_record
from lodout.public_site.fmt import FUSO_BR

_DEFAULT_PATH = DATA_DIR / "visitas.json"
_DIAS_MANTIDOS = 60


def dia_local(ts: "float | None" = None) -> str:
    """Chave YYYY-MM-DD do dia no horário de Brasília.

    achado 2026-11-08: a série usava gmtime() (UTC) -- o "dia" virava
    às 21h de Brasília, quase 3h antes da meia-noite real do
    visitante, fazendo o contador "hoje" zerar cedo demais."""
    momento = time.time() if ts is None else ts
    return datetime.datetime.fromtimestamp(
        momento, tz=FUSO_BR).strftime("%Y-%m-%d")


def registrar(path: "Path | str | None" = None,
              now: "float | None" = None) -> int:
    """Soma 1 (total e no dia de hoje) e grava. Devolve o total atualizado.

    `path=None` é resolvido aqui dentro, não como default de parâmetro,
    para que testes possam apontar para um arquivo isolado.
    """
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, {"total": 0, "por_dia": {}})
    total = int(data.get("total") or 0) + 1
    por_dia = data.get("por_dia") or {}
    hoje = dia_local(now)
    por_dia[hoje] = int(por_dia.get(hoje, 0)) + 1
    # Mantém só os últimos N dias -- série de visitas não precisa crescer
    # sem limite (diferente do histórico de ciclos, que já tem cap próprio).
    if len(por_dia) > _DIAS_MANTIDOS:
        for dia_antigo in sorted(por_dia)[:-_DIAS_MANTIDOS]:
            del por_dia[dia_antigo]
    try:
        atomic_write_text(p, json.dumps({"total": total, "por_dia": por_dia}))
    except OSError:
        pass
    return total


def total(path: "Path | str | None" = None) -> int:
    """Total atual, sem incrementar."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, {"total": 0})
    return int(data.get("total") or 0)


def serie_por_dia(path: "Path | str | None" = None) -> list[tuple[str, int]]:
    """[(dia, contagem)] em ordem cronológica, mais antigo primeiro."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, {"por_dia": {}})
    por_dia = data.get("por_dia") or {}
    return sorted(por_dia.items())
