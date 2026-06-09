"""Testes do modulo icons (cache de icones Steam CDN)."""
from __future__ import annotations

import hashlib

import pytest

from skinvault import icons


def test_cache_path_sanitiza_hash_inseguro(tmp_path, monkeypatch):
    """Hash com '/' e ':' nao escapa do ICONS_DIR (SHA-256 trunca)."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    p = icons.cache_path("abc:def/../../malicious")
    assert tmp_path in p.parents
    assert p.suffix == ".png"
    # nome do arquivo é determinístico via sha256
    expected = hashlib.sha256(
        "abc:def/../../malicious".encode("utf-8"),
    ).hexdigest()[:32]
    assert p.name == f"{expected}.png"


def test_local_path_none_quando_arquivo_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    assert icons.local_path("anyhash") is None


def test_local_path_none_quando_hash_vazio_ou_none():
    assert icons.local_path(None) is None
    assert icons.local_path("") is None


def test_local_path_retorna_arquivo_existente(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    icon_hash = "valid_hash"
    p = icons.cache_path(icon_hash)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fake png bytes")
    assert icons.local_path(icon_hash) == p


def test_local_path_none_quando_arquivo_zero_bytes(tmp_path, monkeypatch):
    """Arquivo de 0 bytes (fetch falhou e deixou stub) conta como ausente."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    p = icons.cache_path("zero")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    assert icons.local_path("zero") is None


def test_fetch_none_quando_hash_vazio():
    assert icons.fetch(None) is None
    assert icons.fetch("") is None


def test_fetch_usa_cache_quando_ja_existe(tmp_path, monkeypatch):
    """Se o cache ja' tem o arquivo, fetch nao chama rede e devolve path."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    p = icons.cache_path("cached")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"already cached")

    called = {"flag": False}

    class _FakeHttpx:
        class Client:
            def __init__(self, *a, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def get(self, url):
                called["flag"] = True
                raise AssertionError("nao deveria chamar")

    monkeypatch.setitem(__import__("sys").modules, "httpx", _FakeHttpx)
    result = icons.fetch("cached")
    assert result == p
    assert called["flag"] is False


def test_ensure_cached_dedup_e_ignora_vazios(tmp_path, monkeypatch):
    """ensure_cached ignora hashes None/vazios e nao baixa duplicados."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    p = icons.cache_path("h1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    # h1 ja' cached, h2 ausente, '' ignorado, h1 duplicado ignorado
    out = icons.ensure_cached(["h1", "", None, "h1"])
    assert "h1" in out
    assert "" not in out
    assert None not in out


def test_fetch_retorna_none_quando_httpx_indisponivel(tmp_path, monkeypatch):
    """Sem httpx instalado, fetch falha graciosamente."""
    monkeypatch.setattr(icons, "ICONS_DIR", tmp_path)
    import sys
    # Garante que import vai falhar
    monkeypatch.setitem(sys.modules, "httpx", None)
    assert icons.fetch("any") is None
