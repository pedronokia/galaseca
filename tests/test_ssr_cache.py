"""Testes do cache local de price_history."""
from __future__ import annotations

import json

import pytest

from skinvault import ssr_cache


def _mk_history(n: int = 3) -> list[dict]:
    return [{"time": i, "price_median": 10.0 + i, "purchases": 5}
            for i in range(n)]


def test_put_get_hit(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    c.put("AK-47", _mk_history())
    got = c.get("AK-47")
    assert got is not None
    assert len(got) == 3
    assert got[0]["price_median"] == 10.0


def test_get_miss_retorna_none(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    assert c.get("Inexistente") is None


def test_has_reflete_estado(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    assert c.has("X") is False
    c.put("X", _mk_history())
    assert c.has("X") is True


def test_ttl_expirado_retorna_none(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=0.001)
    c.put("X", _mk_history())
    import time
    time.sleep(0.01)
    assert c.get("X") is None
    assert c.has("X") is False


def test_persiste_cross_instance(tmp_path):
    p = tmp_path / "c.json"
    c1 = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    c1.put("Item", _mk_history(5))
    # Nova instância lê do disco
    c2 = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    assert c2.has("Item")
    assert len(c2.get("Item")) == 5


def test_clear_apaga_tudo(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    c.put("A", _mk_history())
    c.put("B", _mk_history())
    assert c.size() == 2
    c.clear()
    assert c.size() == 0
    assert c.get("A") is None


def test_clear_persiste(tmp_path):
    p = tmp_path / "c.json"
    c1 = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    c1.put("A", _mk_history())
    c1.clear()
    c2 = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    assert c2.size() == 0


def test_put_nao_aceita_nao_lista(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    c.put("X", "not a list")  # type: ignore[arg-type]
    assert c.size() == 0


def test_arquivo_corrompido_inicia_vazio(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("not json", encoding="utf-8")
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    assert c.size() == 0


def test_size_conta_corretamente(tmp_path):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    assert c.size() == 0
    c.put("A", _mk_history())
    c.put("B", _mk_history())
    c.put("C", _mk_history())
    assert c.size() == 3


def test_cached_price_history_hit_nao_chama_steam(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    c.put("X", _mk_history(4))
    calls = []

    def _fake_steam(name):
        calls.append(name)
        return {"price_history": _mk_history(99)}

    monkeypatch.setattr("skinvault.steam_api.get_market_page_data",
                        _fake_steam)
    out = ssr_cache.cached_price_history("X", cache=c)
    assert len(out) == 4  # veio do cache, nao do steam
    assert calls == []  # steam nao foi chamado


def test_cached_price_history_miss_chama_steam(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    calls = []

    def _fake_steam(name):
        calls.append(name)
        return {"price_history": _mk_history(7)}

    monkeypatch.setattr("skinvault.steam_api.get_market_page_data",
                        _fake_steam)
    out = ssr_cache.cached_price_history("X", cache=c)
    assert len(out) == 7
    assert calls == ["X"]
    # Apos miss + fetch, cache hit no proximo acesso
    out2 = ssr_cache.cached_price_history("X", cache=c)
    assert len(out2) == 7
    assert calls == ["X"]  # nao chamou de novo


def test_cached_price_history_steam_none(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    monkeypatch.setattr("skinvault.steam_api.get_market_page_data",
                        lambda n: None)
    out = ssr_cache.cached_price_history("X", cache=c)
    assert out is None
    assert c.size() == 0


def test_cached_price_history_sem_price_history(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    c = ssr_cache.PriceHistoryCache(path=p, ttl=3600)
    monkeypatch.setattr("skinvault.steam_api.get_market_page_data",
                        lambda n: {"order_book": {}})
    out = ssr_cache.cached_price_history("X", cache=c)
    assert out is None
    assert c.size() == 0
