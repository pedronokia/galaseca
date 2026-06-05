"""Testes do steam_session -- logica pura (mocks de rede)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from skinvault import steam_session as ss
from skinvault.steam_session import (
    SteamSession,
    extract_steamid_from_cookie,
    load,
    merge_cookies,
    persist,
    validate,
)


SAMPLE_STEAMID = "76561198000000001"
SAMPLE_COOKIES = {
    "sessionid": "abc123",
    "steamLoginSecure": f"{SAMPLE_STEAMID}%7C%7CeyJ0eXAi.payload.sig",
    "steamCountry": "BR%7Cabc",
    "browserid": "12345",
}


class TestExtractSteamIDFromCookie:
    def test_extracts_from_url_encoded_pipes(self):
        assert extract_steamid_from_cookie(SAMPLE_COOKIES) == SAMPLE_STEAMID

    def test_extracts_when_pipes_already_decoded(self):
        cookies = {"steamLoginSecure": f"{SAMPLE_STEAMID}||token.payload.sig"}
        assert extract_steamid_from_cookie(cookies) == SAMPLE_STEAMID

    def test_returns_none_when_cookie_missing(self):
        assert extract_steamid_from_cookie({}) is None

    def test_returns_none_when_cookie_empty(self):
        assert extract_steamid_from_cookie({"steamLoginSecure": ""}) is None

    def test_returns_none_for_malformed_id(self):
        cookies = {"steamLoginSecure": "not-a-number||token"}
        assert extract_steamid_from_cookie(cookies) is None

    def test_returns_none_for_short_id(self):
        cookies = {"steamLoginSecure": "12345||token"}
        assert extract_steamid_from_cookie(cookies) is None


class TestSteamSessionDataclass:
    def test_cookie_header_format(self):
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        header = s.cookie_header()
        assert "sessionid=abc123" in header
        assert "steamLoginSecure=" in header
        assert "; " in header

    def test_cookie_header_skips_empty(self):
        s = SteamSession(steamid="x", cookies={"a": "1", "b": "", "c": "2"})
        assert s.cookie_header() == "a=1; c=2"

    def test_is_complete_true(self):
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        assert s.is_complete()

    def test_is_complete_false_no_steamid(self):
        s = SteamSession(steamid="", cookies=SAMPLE_COOKIES)
        assert not s.is_complete()

    def test_is_complete_false_no_loginsecure(self):
        s = SteamSession(steamid=SAMPLE_STEAMID,
                         cookies={"sessionid": "x"})
        assert not s.is_complete()


class TestPersistAndLoad:
    def test_roundtrip(self, tmp_path: Path):
        target = tmp_path / "session.json"
        original = SteamSession(
            steamid=SAMPLE_STEAMID,
            cookies=SAMPLE_COOKIES,
            captured_at=1234567890.0,
            validated_at=1234567900.0,
        )
        persist(original, target)
        loaded = load(target)
        assert loaded is not None
        assert loaded.steamid == SAMPLE_STEAMID
        assert loaded.cookies == SAMPLE_COOKIES
        assert loaded.captured_at == 1234567890.0
        assert loaded.validated_at == 1234567900.0

    def test_persist_writes_warning(self, tmp_path: Path):
        target = tmp_path / "session.json"
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        persist(s, target)
        raw = json.loads(target.read_text(encoding="utf-8"))
        assert "_warning" in raw
        assert "CREDENCIAIS" in raw["_warning"]

    def test_load_missing_returns_none(self, tmp_path: Path):
        assert load(tmp_path / "nope.json") is None

    def test_load_invalid_json_returns_none(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{", encoding="utf-8")
        assert load(bad) is None

    def test_load_non_dict_returns_none(self, tmp_path: Path):
        bad = tmp_path / "arr.json"
        bad.write_text("[1,2,3]", encoding="utf-8")
        assert load(bad) is None

    def test_clear_removes_file(self, tmp_path: Path):
        target = tmp_path / "session.json"
        persist(SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES), target)
        assert target.exists()
        ss.clear(target)
        assert not target.exists()

    def test_clear_missing_is_noop(self, tmp_path: Path):
        ss.clear(tmp_path / "nada.json")  # nao explode


class TestValidate:
    def test_valid_session_when_redirect_profiles(self, monkeypatch):
        def mock_redirect(url, cookie_header, timeout):
            return f"https://steamcommunity.com/profiles/{SAMPLE_STEAMID}/"

        monkeypatch.setattr(ss, "_follow_redirect", mock_redirect)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        assert validate(s) is True
        assert s.validated_at > 0

    def test_valid_session_when_redirect_vanity(self, monkeypatch):
        def mock_redirect(url, cookie_header, timeout):
            return "https://steamcommunity.com/id/myvanityname/"

        monkeypatch.setattr(ss, "_follow_redirect", mock_redirect)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        assert validate(s) is True

    def test_expired_session_redirect_login(self, monkeypatch):
        def mock_redirect(url, cookie_header, timeout):
            return "https://steamcommunity.com/login/home/?goto=my"

        monkeypatch.setattr(ss, "_follow_redirect", mock_redirect)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        assert validate(s) is False
        assert s.validated_at == 0

    def test_validate_incomplete_session(self, monkeypatch):
        # Nem chega a bater na rede.
        calls = []

        def mock_redirect(url, cookie_header, timeout):
            calls.append(url)
            return "https://steamcommunity.com/profiles/x/"

        monkeypatch.setattr(ss, "_follow_redirect", mock_redirect)
        s = SteamSession(steamid="", cookies={})
        assert validate(s) is False
        assert calls == []

    def test_validate_network_error_returns_false(self, monkeypatch):
        def mock_redirect(url, cookie_header, timeout):
            return None

        monkeypatch.setattr(ss, "_follow_redirect", mock_redirect)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        assert validate(s) is False


class TestMergeCookies:
    def test_keeps_relevant_keys_only(self):
        existing = {"sessionid": "old"}
        new = {"sessionid": "new", "steamLoginSecure": "tok",
               "irrelevant": "x"}
        out = merge_cookies(existing, new)
        assert out["sessionid"] == "new"
        assert out["steamLoginSecure"] == "tok"
        assert "irrelevant" not in out

    def test_drops_empty_values(self):
        existing = {"sessionid": "x"}
        new = {"sessionid": ""}
        out = merge_cookies(existing, new)
        assert out["sessionid"] == "x"

    def test_preserves_other_existing(self):
        existing = {"sessionid": "x", "steamCountry": "BR"}
        new = {"steamLoginSecure": "tok"}
        out = merge_cookies(existing, new)
        assert out == {"sessionid": "x", "steamCountry": "BR",
                       "steamLoginSecure": "tok"}
