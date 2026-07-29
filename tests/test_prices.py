"""Testes do cache de preco + avaliacao do inventario (rede e cache mockados)."""
from __future__ import annotations

import time

import pytest

from skinvault import prices, steam_api


def test_cache_hit_within_ttl(tmp_path):
    c = prices.PriceCache(path=tmp_path / "p.json", ttl=100)
    c.put("AK-47 | Redline", 200.0, now=1000)
    assert c.get("AK-47 | Redline", now=1050) == 200.0   # dentro do TTL
    assert c.get("AK-47 | Redline", now=1200) is None     # expirou
    assert c.get("Inexistente", now=1050) is None


def test_cache_persists_across_instances(tmp_path):
    p = tmp_path / "p.json"
    prices.PriceCache(path=p).put("Glock | Fade", 50.0, now=1000)
    # nova instancia le' do disco
    assert prices.PriceCache(path=p).get("Glock | Fade", now=1001) == 50.0


def test_value_inventory_uses_cache_no_network(tmp_path, monkeypatch):
    # inventario fake com 2 itens
    monkeypatch.setattr(
        steam_api, "fetch_inventory",
        lambda sid: (steam_api.INV_OK, [
            {"name": "AK-47 | Redline", "quantity": 1, "tradable": True},
            {"name": "Chroma 3 Case", "quantity": 4, "tradable": True},
        ]),
    )
    # se bater na rede, falha o teste (cache deve cobrir tudo)
    def _boom(*a, **k):
        raise AssertionError("nao deveria chamar a rede -- cache deveria cobrir")
    monkeypatch.setattr(steam_api, "get_market_price", _boom)

    c = prices.PriceCache(path=tmp_path / "p.json", ttl=10_000)
    c.put("AK-47 | Redline", 200.0)
    c.put("Chroma 3 Case", 2.5)

    status, rows, total = prices.value_inventory("123", cache=c, throttle=0)
    assert status == steam_api.INV_OK
    assert total == 200.0 + 2.5 * 4
    assert rows[0]["name"] == "AK-47 | Redline"   # ordenado por total desc


def test_value_inventory_propagates_private(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_api, "fetch_inventory",
                        lambda sid: (steam_api.INV_PRIVATE, []))
    status, rows, total = prices.value_inventory(
        "123", cache=prices.PriceCache(path=tmp_path / "p.json"), throttle=0)
    assert status == steam_api.INV_PRIVATE
    assert rows == [] and total == 0.0


def test_cache_neg_ttl_expires_sooner(tmp_path):
    """Entradas None (sem preco) expiram com TTL mais curto."""
    c = prices.PriceCache(path=tmp_path / "p.json", ttl=1000, neg_ttl=10)
    c.put("Unknown Item", None, now=1000)
    assert c.get("Unknown Item", now=1005) is None       # dentro do neg_ttl
    assert c.has("Unknown Item", now=1005) is True
    assert c.get("Unknown Item", now=1015) is None       # expirou o neg_ttl


def test_age_method(tmp_path):
    """age() retorna idade em segundos ou None."""
    c = prices.PriceCache(path=tmp_path / "p.json")
    assert c.age("Inexistente") is None
    c.put("AK", 200.0, now=1000)
    age = c.age("AK", now=1050)
    assert age == 50.0


def test_cache_save_oserror(tmp_path):
    """Engole OSError ao salvar."""
    file_path = tmp_path / "afile"
    file_path.write_text("", encoding="utf-8")
    bad = file_path / "p.json"  # file_path e' arquivo, nao diretorio
    c = prices.PriceCache(path=bad, ttl=100)
    c.put("AK", 200.0, now=1000)
    # nao crashou


def _fake_status(status, price=None, calls=None):
    """Substitui get_market_price_STATUS -- o backoff passa a olhar o status,
    entao mockar o wrapper `get_market_price` nao alcanca mais o caminho."""
    def _fn(n, currency=7):
        if calls is not None:
            calls.append(n)
        return status, price
    return _fn


def test_fetch_with_backoff_success(monkeypatch):
    """Retorna preco na primeira tentativa."""
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_OK, 150.0))
    assert prices._fetch_with_backoff("AK") == 150.0


def test_fetch_with_backoff_rate_limit_esgota_tentativas(monkeypatch):
    """429 e' o unico caso em que esperar pode ajudar -- aí sim insiste."""
    calls = []
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_RATE_LIMITED,
                                     calls=calls))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    status, price = prices.fetch_price_status("AK", retries=3)
    assert (status, price) == (steam_api.PRICE_RATE_LIMITED, None)
    assert len(calls) == 3


def test_fetch_sem_mercado_desiste_na_primeira(monkeypatch):
    """Item sem preco nao muda de opiniao em 14s de backoff. Era o custo
    que fazia a avaliacao do portfolio levar minutos."""
    calls = []
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_NO_PRICE, calls=calls))
    dormidas = []
    monkeypatch.setattr(time, "sleep", lambda s: dormidas.append(s))
    status, price = prices.fetch_price_status("AK", retries=3)
    assert (status, price) == (steam_api.PRICE_NO_PRICE, None)
    assert len(calls) == 1
    assert dormidas == []


def test_fetch_erro_de_rede_desiste_na_primeira(monkeypatch):
    calls = []
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_ERROR, calls=calls))
    dormidas = []
    monkeypatch.setattr(time, "sleep", lambda s: dormidas.append(s))
    assert prices.fetch_price_status("AK", retries=3)[0] == steam_api.PRICE_ERROR
    assert len(calls) == 1
    assert dormidas == []


def test_rate_limit_nao_envenena_o_cache(monkeypatch, tmp_path):
    """O 429 nao diz NADA sobre o item. Cachear como "sem preco" (TTL 1h)
    sumia com o portfolio inteiro por uma hora depois de a Steam liberar."""
    c = prices.PriceCache(path=tmp_path / "p.json")
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_RATE_LIMITED))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    status, preco = prices.cached_price_status("AK", cache=c)
    assert status == steam_api.PRICE_RATE_LIMITED
    assert preco is None
    assert c.has("AK") is False  # nada gravado

    # Steam liberou: a proxima consulta acha o preco de verdade.
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_OK, 150.0))
    assert prices.cached_price("AK", cache=c) == 150.0


def test_erro_de_rede_tambem_nao_envenena(monkeypatch, tmp_path):
    c = prices.PriceCache(path=tmp_path / "p.json")
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_ERROR))
    prices.cached_price("AK", cache=c)
    assert c.has("AK") is False


def test_sem_mercado_continua_sendo_cacheado(monkeypatch, tmp_path):
    """Este SIM e' fato sobre o item -- cachear evita re-fetch a cada
    startup, que era o motivo do TTL negativo existir."""
    c = prices.PriceCache(path=tmp_path / "p.json")
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_NO_PRICE))
    assert prices.cached_price("AK", cache=c) is None
    assert c.has("AK") is True
    assert c.get("AK") is None


def test_cached_price_hit(monkeypatch, tmp_path):
    """cached_price com cache hit nao chama a rede."""
    c = prices.PriceCache(path=tmp_path / "p.json")
    c.put("AK", 200.0)
    def _boom(*a):
        raise AssertionError("nao deveria chamar a rede")
    monkeypatch.setattr(steam_api, "get_market_price", _boom)
    assert prices.cached_price("AK", cache=c) == 200.0


def test_cached_price_miss(monkeypatch, tmp_path):
    """cached_price com cache miss busca na rede e armazena."""
    c = prices.PriceCache(path=tmp_path / "p.json")
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_OK, 150.0))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    assert prices.cached_price("AK", cache=c) == 150.0
    assert c.get("AK") == 150.0


def test_value_inventory_miss_fetches(monkeypatch, tmp_path):
    """value_inventory busca itens fora do cache."""
    monkeypatch.setattr(
        steam_api, "fetch_inventory",
        lambda sid: (steam_api.INV_OK, [
            {"name": "AK", "quantity": 1, "tradable": True},
        ]),
    )
    monkeypatch.setattr(steam_api, "get_market_price_status",
                        _fake_status(steam_api.PRICE_OK, 200.0))
    monkeypatch.setattr(time, "sleep", lambda _: None)

    c = prices.PriceCache(path=tmp_path / "p.json", ttl=100)
    # Nao preenche o cache — forca miss
    status, rows, total = prices.value_inventory("123", cache=c, throttle=0)
    assert len(rows) == 1
    assert rows[0]["total"] == 200.0


def test_value_inventory_progress(monkeypatch, tmp_path):
    """value_inventory chama callback de progresso."""
    monkeypatch.setattr(
        steam_api, "fetch_inventory",
        lambda sid: (steam_api.INV_OK, [
            {"name": "AK", "quantity": 1, "tradable": True},
            {"name": "AWP", "quantity": 1, "tradable": True},
        ]),
    )
    monkeypatch.setattr(steam_api, "get_market_price", lambda n: 100.0)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    c = prices.PriceCache(path=tmp_path / "p.json", ttl=100)
    progress_log = []
    def prog(i, n, name):
        progress_log.append((i, n, name))
    prices.value_inventory("123", cache=c, throttle=0, progress=prog)
    assert len(progress_log) == 2
    assert progress_log[0] == (1, 2, "AK")
    assert progress_log[1] == (2, 2, "AWP")
