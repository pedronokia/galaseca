"""Contador de visitas simples e privado -- só pra saber se alguém usa.

Sem cookie, sem IP, sem nada por visitante (a página de privacidade já
promete isso). Total acumulado + série por dia (pro gráfico em /status).
Não é analytics de verdade, é um termômetro.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

_DEFAULT_PATH = DATA_DIR / "visitas.json"
_DIAS_MANTIDOS = 60


def registrar(path: "Path | str | None" = None,
              now: "float | None" = None) -> int:
    """Soma 1 (total e no dia de hoje) e grava. Devolve o total atualizado.

    `path=None` resolvido aqui dentro (não como default de parâmetro --
    ver AGENTS.md gotcha #17), senão monkeypatch em teste não alcançaria.
    """
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, {"total": 0, "por_dia": {}})
    total = int(data.get("total") or 0) + 1
    por_dia = data.get("por_dia") or {}
    hoje = time.strftime("%Y-%m-%d", time.gmtime(
        time.time() if now is None else now))
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
