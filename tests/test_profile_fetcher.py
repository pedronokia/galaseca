"""Testes do profile_fetcher (F11)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from skinvault.ui import profile_fetcher as pf


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<profile>
  <steamID64>76561198000000001</steamID64>
  <steamID><![CDATA[Pedro]]></steamID>
  <onlineState>online</onlineState>
  <stateMessage>Online</stateMessage>
  <privacyState>public</privacyState>
  <avatarIcon><![CDATA[https://avatars.steamstatic.com/abc.jpg]]></avatarIcon>
  <avatarMedium><![CDATA[https://avatars.steamstatic.com/abc_medium.jpg]]></avatarMedium>
  <avatarFull><![CDATA[https://avatars.steamstatic.com/abc_full.jpg]]></avatarFull>
  <vacBanned>0</vacBanned>
</profile>
"""


class TestParseProfileXml:
    def test_extracts_all_fields(self):
        parsed = pf.parse_profile_xml(SAMPLE_XML)
        assert parsed is not None
        assert parsed["steamid"] == "76561198000000001"
        assert parsed["name"] == "Pedro"
        assert parsed["avatar_url"].endswith("_full.jpg")

    def test_returns_none_for_empty(self):
        assert pf.parse_profile_xml("") is None

    def test_returns_none_for_non_profile(self):
        assert pf.parse_profile_xml("<html></html>") is None

    def test_handles_missing_avatar(self):
        xml = """<?xml version="1.0"?>
<profile>
  <steamID64>76561198000000002</steamID64>
  <steamID>NoAvatar</steamID>
</profile>"""
        parsed = pf.parse_profile_xml(xml)
        assert parsed["steamid"] == "76561198000000002"
        assert parsed["name"] == "NoAvatar"
        assert parsed["avatar_url"] is None

    def test_falls_back_to_steamid_when_no_name(self):
        xml = """<?xml version="1.0"?>
<profile>
  <steamID64>76561198000000003</steamID64>
</profile>"""
        parsed = pf.parse_profile_xml(xml)
        assert parsed["name"] == "76561198000000003"

    def test_no_cdata_works_too(self):
        xml = """<?xml version="1.0"?>
<profile>
  <steamID64>76561198000000004</steamID64>
  <steamID>NoCDATA</steamID>
  <avatarFull>https://example.com/a.jpg</avatarFull>
</profile>"""
        parsed = pf.parse_profile_xml(xml)
        assert parsed["name"] == "NoCDATA"
        assert parsed["avatar_url"] == "https://example.com/a.jpg"


class TestFetchPublicProfile:
    def test_returns_none_for_empty_steamid(self):
        assert pf.fetch_public_profile("") is None

    def test_caches_response(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(pf, "_PROFILES_PATH", tmp_path / "profiles.json")
        monkeypatch.setattr(pf, "_AVATARS_DIR", tmp_path / "avatars")

        call_count = [0]

        def mock_get(url, timeout=10.0):
            call_count[0] += 1
            if "?xml=1" in url:
                return SAMPLE_XML.encode("utf-8")
            return b"\xff\xd8\xff\xe0fake-jpeg"  # avatar bytes

        monkeypatch.setattr(pf, "_http_get", mock_get)

        first = pf.fetch_public_profile("76561198000000001")
        assert first is not None
        assert first["name"] == "Pedro"
        assert first["avatar_path"] is not None
        assert Path(first["avatar_path"]).exists()

        before_calls = call_count[0]
        # Segunda chamada: usa cache (sem novas requests)
        second = pf.fetch_public_profile("76561198000000001")
        assert second == first
        assert call_count[0] == before_calls

    def test_force_bypasses_cache(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(pf, "_PROFILES_PATH", tmp_path / "profiles.json")
        monkeypatch.setattr(pf, "_AVATARS_DIR", tmp_path / "avatars")

        def mock_get(url, timeout=10.0):
            if "?xml=1" in url:
                return SAMPLE_XML.encode("utf-8")
            return b"jpeg"

        monkeypatch.setattr(pf, "_http_get", mock_get)
        pf.fetch_public_profile("76561198000000001")
        # Simula passar do TTL substituindo o cache
        cache = pf._load_cache()
        cache["76561198000000001"]["fetched_at"] = 0
        pf._save_cache(cache)

        result = pf.fetch_public_profile("76561198000000001", force=True)
        assert result is not None
        assert result["fetched_at"] > 0

    def test_falls_back_to_cache_on_network_error(self, monkeypatch,
                                                  tmp_path: Path):
        monkeypatch.setattr(pf, "_PROFILES_PATH", tmp_path / "profiles.json")
        monkeypatch.setattr(pf, "_AVATARS_DIR", tmp_path / "avatars")

        # Pre-popula cache
        cache_data = {
            "76561198000000001": {
                "steamid": "76561198000000001",
                "name": "Cached",
                "avatar_url": None,
                "avatar_path": None,
                "fetched_at": time.time() - _DAY_SECONDS - 100,  # expired
            }
        }
        pf._save_cache(cache_data)

        monkeypatch.setattr(pf, "_http_get", lambda *a, **k: None)
        result = pf.fetch_public_profile("76561198000000001")
        assert result is not None
        assert result["name"] == "Cached"  # serviu cache expirado


_DAY_SECONDS = 86400


class TestCacheHelpers:
    def test_load_cached_profile_missing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(pf, "_PROFILES_PATH", tmp_path / "p.json")
        assert pf.load_cached_profile("unknown") is None

    def test_load_avatar_bytes_missing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(pf, "_AVATARS_DIR", tmp_path / "avatars")
        assert pf.load_avatar_bytes("no") is None

    def test_load_avatar_bytes_present(self, monkeypatch, tmp_path: Path):
        avdir = tmp_path / "avatars"
        avdir.mkdir()
        (avdir / "76561198000000001.jpg").write_bytes(b"jpeg-bytes")
        monkeypatch.setattr(pf, "_AVATARS_DIR", avdir)
        assert pf.load_avatar_bytes("76561198000000001") == b"jpeg-bytes"
