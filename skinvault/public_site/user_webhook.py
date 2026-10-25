"""Configuração + dedup do webhook Discord pessoal da watchlist.

Reaproveita user_store (kind="webhook" pra URL, kind="webhook_enviado"
pro controle de "já mandei esse alerta recentemente") -- mesmo padrão
genérico por steamid/kind de portfolio/trades/watchlist.
"""
from __future__ import annotations

import time
from pathlib import Path

from skinvault.public_site import user_store

_REENVIO_MIN_S = 3600.0  # não repete o mesmo alerta antes de 1h


def get_webhook_url(steamid: str, path: "Path | str | None" = None) -> str:
    data = user_store.load_user_json(steamid, "webhook", {}, path=path)
    return data.get("url", "") if isinstance(data, dict) else ""


def set_webhook_url(steamid: str, url: str,
                    path: "Path | str | None" = None) -> None:
    user_store.save_user_json(steamid, "webhook", {"url": url.strip()}, path=path)


def deve_notificar(steamid: str, item_name: str,
                   path: "Path | str | None" = None,
                   now: "float | None" = None) -> bool:
    """True se esse item não foi notificado nos últimos `_REENVIO_MIN_S`
    segundos pra esse usuário -- evita reenviar o mesmo alerta toda vez
    que a página /conta/watchlist é recarregada."""
    agora = time.time() if now is None else now
    enviados = user_store.load_user_json(steamid, "webhook_enviado", {}, path=path)
    ultimo = enviados.get(item_name) if isinstance(enviados, dict) else None
    return ultimo is None or (agora - ultimo) >= _REENVIO_MIN_S


def marcar_notificado(steamid: str, item_name: str,
                      path: "Path | str | None" = None,
                      now: "float | None" = None) -> None:
    enviados = user_store.load_user_json(steamid, "webhook_enviado", {}, path=path)
    if not isinstance(enviados, dict):
        enviados = {}
    enviados[item_name] = time.time() if now is None else now
    user_store.save_user_json(steamid, "webhook_enviado", enviados, path=path)
