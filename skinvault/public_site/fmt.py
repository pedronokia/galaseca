"""Formatação compartilhada entre as telas do site público.

Cópia mínima de `ui/theme.py:brl` -- este pacote não importa PyQt6 de
propósito (ver AGENTS.md/plano da Fase 1).
"""
from __future__ import annotations


def brl(v: "float | None") -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
