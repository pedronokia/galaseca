"""Conta + dado pessoal por usuário (SQLite, ver `db.py`).

`load_user_json`/`save_user_json` guardam a MESMA forma de dado (lista de
dicts) que `portfolio.json`/`trades.json`/`watchlist.json` já usam no app
local -- só troca ONDE mora (uma linha de `user_data`, não um arquivo
global). As funções PURAS de cálculo (`portfolio.evaluate_portfolio` etc.)
continuam as mesmas, chamadas direto com o que isto devolve.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from skinvault.public_site import db


def upsert_user(steamid: str, persona_name: "str | None" = None,
                avatar_url: "str | None" = None,
                path: "Path | str | None" = None) -> None:
    """Cria a conta no primeiro login ou atualiza nome/avatar/último login."""
    now = time.time()
    conn = db.connect(path)
    try:
        conn.execute(
            "INSERT INTO users (steamid, persona_name, avatar_url, "
            "created_ts, last_login_ts) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(steamid) DO UPDATE SET "
            "persona_name=excluded.persona_name, "
            "avatar_url=excluded.avatar_url, "
            "last_login_ts=excluded.last_login_ts",
            (steamid, persona_name, avatar_url, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_user(steamid: str, path: "Path | str | None" = None) -> "dict | None":
    """Dados da conta, ou None se o steamid nunca logou."""
    conn = db.connect(path)
    try:
        row = conn.execute(
            "SELECT steamid, persona_name, avatar_url, created_ts, "
            "last_login_ts FROM users WHERE steamid = ?",
            (steamid,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "steamid": row[0], "persona_name": row[1], "avatar_url": row[2],
        "created_ts": row[3], "last_login_ts": row[4],
    }


def load_user_json(steamid: str, kind: str, default: Any,
                   path: "Path | str | None" = None) -> Any:
    """Dado pessoal do usuário (`kind` = "portfolio" por agora).

    `default` volta sem tocar no banco quando o usuário ainda não tem
    nada salvo desse `kind` -- mesmo espírito do `load_json_record` de
    `_paths.py`, nunca um erro por ausência.
    """
    conn = db.connect(path)
    try:
        row = conn.execute(
            "SELECT payload FROM user_data WHERE steamid = ? AND kind = ?",
            (steamid, kind),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return default
    try:
        return json.loads(row[0])
    except ValueError:
        return default


def save_user_json(steamid: str, kind: str, data: Any,
                   path: "Path | str | None" = None) -> None:
    conn = db.connect(path)
    try:
        conn.execute(
            "INSERT INTO user_data (steamid, kind, payload, updated_ts) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(steamid, kind) DO UPDATE SET "
            "payload=excluded.payload, updated_ts=excluded.updated_ts",
            (steamid, kind, json.dumps(data), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user(steamid: str, path: "Path | str | None" = None) -> None:
    """Apaga a conta e TODO dado pessoal (portfólio/trades/watchlist/
    histórico) desse steamid -- usado por `/conta/excluir`. Irreversível:
    quem chama (a rota) é responsável por confirmar antes."""
    conn = db.connect(path)
    try:
        conn.execute("DELETE FROM users WHERE steamid = ?", (steamid,))
        conn.execute("DELETE FROM user_data WHERE steamid = ?", (steamid,))
        conn.commit()
    finally:
        conn.close()
