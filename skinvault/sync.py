"""Leitores dos dados historicos deixados pela sincronizacao de conta (F10).

A Fase 10 sincronizava inventario, historico de mercado, listagens ativas
e trade offers usando cookies de sessao Steam. Removida em 2026-08-07 por
decisao do usuario apos pesquisa da politica da Valve: o Steam Subscriber
Agreement proibe "scripts, bots, macros ou sistemas nao-controlados-por-
humano" interagindo com servicos da Steam, com terminacao de conta sem
aviso previo -- categoria de risco real e distinta do scan publico anonimo
(que nunca usa cookie nenhum). Ver ROADMAP.md.

Os dados JA sincronizados (steam_market_events.json, active_listings.json,
trade_history.json) foram mantidos por decisao do usuario -- sao registro
historico local, sem risco. So' a CAPACIDADE de sincronizar de novo saiu
(exigiria SteamSession, que nao existe mais). Este modulo agora so' le'
esses arquivos; nada aqui bate na rede.
"""
from __future__ import annotations

from pathlib import Path

from skinvault._paths import DATA_DIR, load_json_record

_EVENTS_PATH = DATA_DIR / "steam_market_events.json"
_LISTINGS_PATH = DATA_DIR / "active_listings.json"
_TRADES_PATH = DATA_DIR / "trade_history.json"


def _load_json_list(path: Path) -> list[dict]:
    data = load_json_record(path, [])
    return data if isinstance(data, list) else []


def load_market_events(path: Path | str = _EVENTS_PATH) -> list[dict]:
    return _load_json_list(Path(path))


def load_active_listings(path: Path | str = _LISTINGS_PATH) -> list[dict]:
    return _load_json_list(Path(path))


def load_trade_offers(path: Path | str = _TRADES_PATH) -> list[dict]:
    return _load_json_list(Path(path))
