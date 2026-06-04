"""Testes do cache de preco + avaliacao do inventario (rede e cache mockados)."""
from __future__ import annotations

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
