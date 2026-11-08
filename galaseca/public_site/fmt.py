"""Formatação monetária e de data/hora usada pelos templates do site público."""
from __future__ import annotations

import datetime

# Visitantes são do Brasil e o servidor roda em UTC (sem TZ configurado
# no container) -- horário de Brasília é UTC-3 fixo (sem horário de
# verão desde 2019). Qualquer data/hora mostrada pra quem usa o site
# deve usar este fuso, nunca o fuso "local" ambíguo do servidor.
FUSO_BR = datetime.timezone(datetime.timedelta(hours=-3))


def brl(v: "float | None") -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_hora_br(ts: float) -> str:
    """'DD/MM/AAAA HH:MM' no horário de Brasília, a partir de um epoch UTC."""
    return datetime.datetime.fromtimestamp(ts, tz=FUSO_BR).strftime(
        "%d/%m/%Y %H:%M")
