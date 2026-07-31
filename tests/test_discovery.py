"""Testes do discovery -- descoberta aditiva com fallback garantido."""
from __future__ import annotations

from skinvault import discovery


FALLBACK = ["AK-47 | Redline (Field-Tested)", "AWP | Asiimov (Field-Tested)"]


def _cache(tmp_path, ttl=3600):
    return discovery.DiscoveryCache(path=tmp_path / "d.json", ttl=ttl)


def _fake_search(monkeypatch, status, results, total=0):
    chamadas = []

    def fake(**kw):
        chamadas.append(kw)
        return status, results, total

    monkeypatch.setattr("skinvault.steam_api.search_market_all", fake)
    return chamadas


def _row(nome, preco, anuncios=10):
    return {"name": nome, "hash_name": nome, "price": preco,
            "listings": anuncios}


# ── cache ──────────────────────────────────────────────────────────


def test_cache_guarda_e_le(tmp_path):
    c = _cache(tmp_path)
    c.put("k", ["a", "b"])
    assert c.get("k") == ["a", "b"]


def test_cache_expira(tmp_path):
    c = _cache(tmp_path, ttl=0.001)
    c.put("k", ["a"])
    import time
    time.sleep(0.01)
    assert c.get("k") is None


def test_cache_ignora_vazio(tmp_path):
    c = _cache(tmp_path)
    c.put("k", [])
    c.put("k2", "nao e' lista")
    assert c.get("k") is None
    assert c.get("k2") is None


def test_cache_persiste(tmp_path):
    _cache(tmp_path).put("k", ["a"])
    assert discovery.DiscoveryCache(
        path=tmp_path / "d.json", ttl=3600).get("k") == ["a"]


def test_cache_key_muda_com_filtro():
    assert discovery.cache_key("Rifles", 60, 1.0) != \
        discovery.cache_key("Rifles", 60, 5.0)
    assert discovery.cache_key("Rifles", 60, 1.0) != \
        discovery.cache_key("Facas", 60, 1.0)


# ── discover_category ──────────────────────────────────────────────


def test_categoria_sem_faceta_nao_chama_rede(tmp_path, monkeypatch):
    chamadas = _fake_search(monkeypatch, "ok", [_row("X", 10.0)])
    nomes, origem = discovery.discover_category(
        "Stickers (Community)", cache=_cache(tmp_path))
    assert nomes is None
    assert origem == discovery.SOURCE_FALLBACK
    assert chamadas == [], "nao devia tocar a rede sem faceta mapeada"


def test_descobre_e_filtra_por_preco(tmp_path, monkeypatch):
    _fake_search(monkeypatch, "ok", [
        _row("Barato 1", 0.03),
        _row("Bom", 12.50),
        _row("Barato 2", 0.99),
        _row("Outro Bom", 3.00),
    ])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    nomes, origem = discovery.discover_category(
        "Rifles", cache=_cache(tmp_path))
    assert nomes == ["Bom", "Outro Bom"]
    assert origem == discovery.SOURCE_DISCOVERY


def test_respeita_max_items(tmp_path, monkeypatch):
    _fake_search(monkeypatch, "ok",
                 [_row(f"i{i}", 10.0) for i in range(50)])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    nomes, _ = discovery.discover_category(
        "Rifles", max_items=5, cache=_cache(tmp_path))
    assert len(nomes) == 5


def test_rate_limit_devolve_none(tmp_path, monkeypatch):
    _fake_search(monkeypatch, "rate_limited", [])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    nomes, origem = discovery.discover_category(
        "Rifles", cache=_cache(tmp_path))
    assert nomes is None
    assert origem == discovery.SOURCE_FALLBACK


def test_tudo_abaixo_do_piso_devolve_none(tmp_path, monkeypatch):
    _fake_search(monkeypatch, "ok", [_row("a", 0.03), _row("b", 0.10)])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    nomes, origem = discovery.discover_category(
        "Rifles", cache=_cache(tmp_path))
    assert nomes is None
    assert origem == discovery.SOURCE_FALLBACK


def test_segunda_chamada_usa_cache(tmp_path, monkeypatch):
    chamadas = _fake_search(monkeypatch, "ok", [_row("Bom", 10.0)])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    c = _cache(tmp_path)
    discovery.discover_category("Rifles", cache=c)
    nomes, origem = discovery.discover_category("Rifles", cache=c)
    assert nomes == ["Bom"]
    assert origem == discovery.SOURCE_CACHE
    assert len(chamadas) == 1, "cache nao evitou a segunda requisicao"


# ── resolve_scan_items: a garantia de nunca piorar ─────────────────


def test_resolve_usa_descoberta_quando_da_certo(tmp_path, monkeypatch):
    _fake_search(monkeypatch, "ok", [_row("Descoberto", 20.0)])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    items, origem = discovery.resolve_scan_items(
        "Rifles", FALLBACK, cache=_cache(tmp_path))
    assert items == ["Descoberto"]
    assert origem == discovery.SOURCE_DISCOVERY


def test_resolve_cai_no_fallback_em_rate_limit(tmp_path, monkeypatch):
    _fake_search(monkeypatch, "rate_limited", [])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    items, origem = discovery.resolve_scan_items(
        "Rifles", FALLBACK, cache=_cache(tmp_path))
    assert items == FALLBACK
    assert origem == discovery.SOURCE_FALLBACK


def test_resolve_cai_no_fallback_se_a_busca_explodir(tmp_path, monkeypatch):
    """Descoberta e' opcional: excecao nao pode derrubar o scan."""
    def boom(**kw):
        raise RuntimeError("rede caiu")

    monkeypatch.setattr("skinvault.steam_api.search_market_all", boom)
    items, origem = discovery.resolve_scan_items(
        "Rifles", FALLBACK, cache=_cache(tmp_path))
    assert items == FALLBACK
    assert origem == discovery.SOURCE_FALLBACK


def test_resolve_desligado_nao_toca_a_rede(tmp_path, monkeypatch):
    chamadas = _fake_search(monkeypatch, "ok", [_row("X", 10.0)])
    items, origem = discovery.resolve_scan_items(
        "Rifles", FALLBACK, cache=_cache(tmp_path), enabled=False)
    assert items == FALLBACK
    assert origem == discovery.SOURCE_FALLBACK
    assert chamadas == []


def test_resolve_nao_devolve_a_mesma_lista_do_fallback(tmp_path, monkeypatch):
    """Retorna copia: mutar o resultado nao pode corromper _SCAN_BY_CATEGORY."""
    _fake_search(monkeypatch, "rate_limited", [])
    monkeypatch.setattr("skinvault.steam_api.SEARCH_OK", "ok")
    items, _ = discovery.resolve_scan_items(
        "Rifles", FALLBACK, cache=_cache(tmp_path))
    items.append("sujeira")
    assert "sujeira" not in FALLBACK
