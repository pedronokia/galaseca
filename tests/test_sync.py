"""Testes dos leitores do historico de sincronizacao (pos-F10).

sync.py deixou de sincronizar (F10 revertida em 2026-08-07, ver
ROADMAP.md) e virou so' leitura dos arquivos que a sincronizacao antiga
deixou -- steam_market_events.json, active_listings.json,
trade_history.json. Esses dados foram mantidos por decisao do usuario.
"""
from __future__ import annotations

from skinvault import sync


def test_load_market_events_returns_list(tmp_path):
    p = tmp_path / "events.json"
    p.write_text('[{"x": 1}]', encoding="utf-8")
    assert sync.load_market_events(p) == [{"x": 1}]


def test_load_active_listings_returns_list(tmp_path):
    p = tmp_path / "listings.json"
    p.write_text('[{"y": 2}]', encoding="utf-8")
    assert sync.load_active_listings(p) == [{"y": 2}]


def test_load_trade_offers_returns_list(tmp_path):
    p = tmp_path / "trades.json"
    p.write_text('[{"z": 3}]', encoding="utf-8")
    assert sync.load_trade_offers(p) == [{"z": 3}]


def test_loaders_arquivo_ausente_devolve_lista_vazia(tmp_path):
    p = tmp_path / "nao_existe.json"
    assert sync.load_market_events(p) == []
    assert sync.load_active_listings(p) == []
    assert sync.load_trade_offers(p) == []


def test_loaders_json_nao_lista_devolve_lista_vazia(tmp_path):
    p = tmp_path / "dict.json"
    p.write_text('{"nao": "e lista"}', encoding="utf-8")
    assert sync.load_market_events(p) == []


def test_loaders_json_corrompido_devolve_lista_vazia(tmp_path):
    p = tmp_path / "corrompido.json"
    p.write_text("nao e' json", encoding="utf-8")
    assert sync.load_active_listings(p) == []
