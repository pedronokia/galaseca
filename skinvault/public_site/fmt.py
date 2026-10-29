"""Formatação monetária usada pelos templates do site público."""
from __future__ import annotations


def brl(v: "float | None") -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
