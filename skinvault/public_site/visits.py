"""Contador de visitas simples e privado -- só pra saber se alguém usa.

Sem cookie, sem IP, sem nada por visitante (a página de privacidade já
promete isso). É literalmente um número que soma 1 a cada carregamento
do dashboard público. Não é analytics de verdade, é um termômetro.
"""
from __future__ import annotations

import json
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

_DEFAULT_PATH = DATA_DIR / "visitas.json"


def registrar(path: "Path | str | None" = None) -> int:
    """Soma 1 e grava. Devolve o total atualizado.

    `path=None` resolvido aqui dentro (não como default de parâmetro --
    ver AGENTS.md gotcha #17), senão monkeypatch em teste não alcançaria.
    """
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, {"total": 0})
    total = int(data.get("total") or 0) + 1
    try:
        atomic_write_text(p, json.dumps({"total": total}))
    except OSError:
        pass
    return total


def total(path: "Path | str | None" = None) -> int:
    """Total atual, sem incrementar."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    data = load_json_record(p, {"total": 0})
    return int(data.get("total") or 0)
