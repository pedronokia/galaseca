"""Alerta no Discord do DONO (não do usuário -- isso é `user_webhook.py`,
por conta/watchlist) quando o worker passa N horas sem completar um
ciclo com itens > 0.

Motivo: o bloqueio real de 429 de 2026-10-25 durou mais de 5 horas sem
ninguém notar até abrir o `/admin` manualmente. Webhook fica em
`GALASECA_ADMIN_DISCORD_WEBHOOK` (env var, nunca hardcoded -- só o dono
tem o link do canal dele). Dedup por `_DEDUP_HORAS`: sem isso, cada
ciclo de 6h sem sucesso mandaria outro alerta pro mesmo incidente.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from galaseca._paths import DATA_DIR, atomic_write_text, load_json_record
from galaseca.public_site import discord_notify
from galaseca._ambiente import ambiente

_ESTADO_PATH = DATA_DIR / "worker_alert_state.json"
_HORAS_LIMITE_DEFAULT = 3.0
_DEDUP_HORAS = 6.0

_ESTADO_DISCO_PATH = DATA_DIR / "disk_alert_state.json"
_DISCO_LIVRE_PCT_LIMITE = 10.0
_DEDUP_DISCO_HORAS = 24.0


def verificar_e_alertar(historico_ciclos: list[dict],
                        now: "float | None" = None,
                        path: "Path | str | None" = None) -> bool:
    """Manda o alerta se: webhook configurado + último ciclo com itens>0
    foi há mais de `GALASECA_WORKER_ALERT_HORAS` (default 3h) + não
    mandou outro alerta nas últimas `_DEDUP_HORAS`. True se mandou."""
    webhook = ambiente("ADMIN_DISCORD_WEBHOOK", "")
    if not webhook or not historico_ciclos:
        return False
    agora = time.time() if now is None else now
    limite_horas = float(ambiente("WORKER_ALERT_HORAS", _HORAS_LIMITE_DEFAULT))
    ultimo_sucesso = next(
        (c for c in reversed(historico_ciclos) if c.get("itens", 0) > 0), None)
    referencia_ts = (ultimo_sucesso or historico_ciclos[0])["ts"]
    horas_sem_sucesso = (agora - referencia_ts) / 3600
    if horas_sem_sucesso < limite_horas:
        return False

    p = Path(path) if path is not None else _ESTADO_PATH
    estado = load_json_record(p, {})
    if not isinstance(estado, dict):
        estado = {}
    if agora - estado.get("ultimo_alerta_ts", 0) < _DEDUP_HORAS * 3600:
        return False

    enviado = discord_notify.enviar(
        webhook,
        f"⚠️ GalaSeca: o worker está há {horas_sem_sucesso:.1f}h sem "
        "trazer nenhum item (provável bloqueio da Steam). Ver /status ou "
        "/admin pro histórico de ciclos.")
    if enviado:
        try:
            atomic_write_text(p, json.dumps({"ultimo_alerta_ts": agora}))
        except OSError:
            pass
    return enviado


def verificar_disco_e_alertar(now: "float | None" = None,
                              path: "Path | str | None" = None) -> bool:
    """Alerta se o disco da partição de `DATA_DIR` tiver menos de
    `_DISCO_LIVRE_PCT_LIMITE`% livre -- numa VM pequena, backups/cache
    acumulando podem encher o disco sem avisar antes do app começar a
    falhar gravação. Dedup separado do alerta de worker atrasado (outro
    tipo de problema, mesmo princípio de não repetir o alerta a cada
    ciclo)."""
    webhook = ambiente("ADMIN_DISCORD_WEBHOOK", "")
    if not webhook:
        return False
    try:
        uso = shutil.disk_usage(DATA_DIR)
    except OSError:
        return False
    if not uso.total:
        return False
    livre_pct = 100 * uso.free / uso.total
    if livre_pct >= _DISCO_LIVRE_PCT_LIMITE:
        return False

    agora = time.time() if now is None else now
    p = Path(path) if path is not None else _ESTADO_DISCO_PATH
    estado = load_json_record(p, {})
    if not isinstance(estado, dict):
        estado = {}
    if agora - estado.get("ultimo_alerta_ts", 0) < _DEDUP_DISCO_HORAS * 3600:
        return False

    enviado = discord_notify.enviar(
        webhook,
        f"⚠️ GalaSeca: disco com só {livre_pct:.1f}% livre na VM. "
        "Ver /admin pro tamanho do banco/backups.")
    if enviado:
        try:
            atomic_write_text(p, json.dumps({"ultimo_alerta_ts": agora}))
        except OSError:
            pass
    return enviado
