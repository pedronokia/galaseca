"""Schema SQLite do site público -- a ÚNICA parte do projeto com banco.

Guarda so' conta (steamid publico, via Steam OpenID -- ver steam_openid.py)
e dado pessoal por usuario (`user_data`, uma linha por `kind`: "portfolio"
por agora, "trades"/"watchlist"/etc. nas fases seguintes, reusando a MESMA
tabela). O resto do site (scan_store.json, rankings.json) continua em JSON
global, sem dono -- isso aqui e' so' pro que PRECISA de dono.

`sqlite3` e' stdlib: zero dependencia nova. Um arquivo `public_site.db` em
`DATA_DIR` (mesma pasta do scan_store.json da Fase 1).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from skinvault._paths import DATA_DIR

_DB_PATH = DATA_DIR / "public_site.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    steamid TEXT PRIMARY KEY,
    persona_name TEXT,
    avatar_url TEXT,
    created_ts REAL,
    last_login_ts REAL
);
CREATE TABLE IF NOT EXISTS user_data (
    steamid TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    updated_ts REAL,
    PRIMARY KEY (steamid, kind)
);
"""


def connect(path: "Path | str | None" = None) -> sqlite3.Connection:
    """Abre uma conexao nova, com o schema garantido.

    `path=None` resolve `_DB_PATH` AQUI DENTRO (em tempo de chamada), nao
    como default de parametro, para permitir que testes e chamadores
    escolham um caminho atual. Cada chamador abre e fecha a propria
    conexao; nao ha' conexao global compartilhada entre requests.
    """
    p = Path(path) if path is not None else _DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn
