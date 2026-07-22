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

    def test_clear_on_directory_oserror(self, tmp_path: Path):
        """clear em diretorio nao quebra."""
        d = tmp_path / "adir"
        d.mkdir()
        ss.clear(d)  # nao deve levantar

    def test_persist_oserror_ignored(self, tmp_path: Path, monkeypatch):
        """Erro de escrita no persist nao quebra."""
        target = tmp_path / "session.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        # cria um arquivo e transforma em diretorio para forcar erro
        s = SteamSession(steamid="123", cookies={"a": "b"})
        persist(s, target)  # sucesso inicial
        target.unlink()
        target.mkdir()

        def fail(*a, **kw):
            raise OSError("permission")
        monkeypatch.setattr("pathlib.Path.write_text", fail)
        persist(s, target)  # nao crashou

    def test_load_corrupted_session_data(self, tmp_path: Path):
        """load com dados que quebram no construtor SteamSession retorna None."""
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"captured_at": "not-a-float"}), encoding="utf-8")
        assert load(bad) is None


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

    def test_validate_unknown_url_returns_false(self, monkeypatch):
        def mock_redirect(url, cookie_header, timeout):
            return "https://steamcommunity.com/unknown"

        monkeypatch.setattr(ss, "_follow_redirect", mock_redirect)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=SAMPLE_COOKIES)
        assert validate(s) is False


# â”€â”€ _follow_redirect â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def test_follow_redirect_success(monkeypatch):
    class MockResp:
        def __init__(self):
            self._url = "https://steamcommunity.com/profiles/123/"
        def geturl(self):
            return self._url
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: MockResp())
    result = ss._follow_redirect("https://steamcommunity.com/my/", "cookies", 10)
    assert result == "https://steamcommunity.com/profiles/123/"


def test_follow_redirect_network_error_returns_none(monkeypatch):
    def _raise(req, timeout=10):
        raise OSError("connection failed")

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    result = ss._follow_redirect("https://steamcommunity.com/my/", "cookies", 10)
    assert result is None


def test_follow_redirect_http_error_returns_url(monkeypatch):
    """HTTPError retorna exc.url."""
    import io
    def _raise(req, timeout=10):
        from urllib.error import HTTPError
        raise HTTPError("https://steamcommunity.com/login/", 302,
                        "Redirect", {}, io.BytesIO())

    monkeypatch.setattr("urllib.request.urlopen", _raise)
    result = ss._follow_redirect("https://steamcommunity.com/my/", "cookies", 10)
    assert result == "https://steamcommunity.com/login/"

class TestRefreshTokenExtractor:
    def test_extracts_jwt_after_pipes(self):
        cookies = {"steamRefresh_steam": f"{SAMPLE_STEAMID}||eyJ.payload.sig"}
        assert ss._refresh_token_from_cookies(cookies) == "eyJ.payload.sig"

    def test_extracts_when_url_encoded(self):
        cookies = {"steamRefresh_steam": f"{SAMPLE_STEAMID}%7C%7Ctok.p.s"}
        assert ss._refresh_token_from_cookies(cookies) == "tok.p.s"

    def test_returns_none_when_missing(self):
        assert ss._refresh_token_from_cookies({}) is None

    def test_returns_none_when_empty(self):
        assert ss._refresh_token_from_cookies({"steamRefresh_steam": ""}) is None

    def test_no_pipes_returns_whole_value(self):
        # Token sem prefixo steamid â€” usa o valor inteiro
        cookies = {"steamRefresh_steam": "rawjwt"}
        assert ss._refresh_token_from_cookies(cookies) == "rawjwt"


class TestMultipartEncode:
    def test_includes_all_fields(self):
        body, ctype = ss._multipart_encode({"nonce": "abc", "sessionid": "x"})
        assert ctype.startswith("multipart/form-data; boundary=")
        text = body.decode()
        assert 'name="nonce"' in text
        assert "abc" in text
        assert 'name="sessionid"' in text

    def test_boundary_matches_header(self):
        body, ctype = ss._multipart_encode({"a": "1"})
        boundary = ctype.split("boundary=", 1)[1]
        assert f"--{boundary}".encode() in body
        assert f"--{boundary}--".encode() in body


class TestExtractCookieValue:
    def test_finds_named_cookie(self):
        headers = [
            "sessionid=abc; Path=/",
            "steamLoginSecure=76561%7C%7Cnewtok; Path=/; HttpOnly",
        ]
        assert (ss._extract_cookie_value(headers, "steamLoginSecure")
                == "76561%7C%7Cnewtok")

    def test_returns_none_when_absent(self):
        assert ss._extract_cookie_value(["foo=bar"], "steamLoginSecure") is None


class TestRefresh:
    def _session_with_refresh(self):
        cookies = dict(SAMPLE_COOKIES)
        cookies["steamRefresh_steam"] = f"{SAMPLE_STEAMID}||refresh.jwt.sig"
        return SteamSession(steamid=SAMPLE_STEAMID, cookies=cookies)

    def test_refresh_happy_path(self, monkeypatch):
        calls = []

        def mock_post(url, fields, timeout, extra_headers=None):
            calls.append(url)
            if "finalizelogin" in url:
                payload = json.dumps({
                    "steamID": SAMPLE_STEAMID,
                    "transfer_info": [
                        {"url": "https://steamcommunity.com/login/settoken",
                         "params": {"nonce": "n1", "auth": "a1"}},
                    ],
                }).encode()
                return 200, payload, []
            # transfer endpoint
            return 200, b"{}", [
                f"steamLoginSecure={SAMPLE_STEAMID}%7C%7CNEWTOKEN; Path=/",
            ]

        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        old_secure = s.cookies["steamLoginSecure"]
        assert ss.refresh(s) is True
        assert s.cookies["steamLoginSecure"] != old_secure
        assert "NEWTOKEN" in s.cookies["steamLoginSecure"]
        assert len(s.cookies["sessionid"]) == 24  # token_hex(12)
        assert any("finalizelogin" in c for c in calls)

    def test_refresh_no_token_returns_false(self, monkeypatch):
        called = []
        monkeypatch.setattr(ss, "_post_multipart",
                            lambda *a, **kw: called.append(1))
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.refresh(s) is False
        assert called == []  # nem tenta sem refresh token

    def test_refresh_finalize_fails(self, monkeypatch):
        monkeypatch.setattr(ss, "_post_multipart", lambda *a, **kw: None)
        s = self._session_with_refresh()
        assert ss.refresh(s) is False

    def test_refresh_no_transfer_info(self, monkeypatch):
        def mock_post(url, fields, timeout, extra_headers=None):
            return 200, json.dumps({"transfer_info": []}).encode(), []
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        assert ss.refresh(s) is False

    def test_refresh_skips_non_steam_url(self, monkeypatch):
        def mock_post(url, fields, timeout, extra_headers=None):
            if "finalizelogin" in url:
                payload = json.dumps({"transfer_info": [
                    {"url": "https://evil.example.com/steal",
                     "params": {"nonce": "n"}},
                ]}).encode()
                return 200, payload, []
            raise AssertionError("nao deve postar em dominio nao-Steam")
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        assert ss.refresh(s) is False  # nenhum cookie obtido

    def test_refresh_prefers_community_token(self, monkeypatch):
        """Com transfers de store E community, fica com o token community."""
        def mock_post(url, fields, timeout, extra_headers=None):
            if "finalizelogin" in url:
                payload = json.dumps({"transfer_info": [
                    {"url": "https://store.steampowered.com/login/settoken",
                     "params": {"nonce": "n"}},
                    {"url": "https://steamcommunity.com/login/settoken",
                     "params": {"nonce": "n"}},
                ]}).encode()
                return 200, payload, []
            tok = "STORE" if "store" in url else "COMMUNITY"
            return 200, b"{}", [
                f"steamLoginSecure={SAMPLE_STEAMID}%7C%7C{tok}; Path=/",
            ]
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        assert ss.refresh(s) is True
        assert "COMMUNITY" in s.cookies["steamLoginSecure"]

    def test_refresh_falls_back_to_store_when_community_fails(self, monkeypatch):
        """Se o transfer community falha, usa o token que sobrou (store)."""
        def mock_post(url, fields, timeout, extra_headers=None):
            if "finalizelogin" in url:
                payload = json.dumps({"transfer_info": [
                    {"url": "https://store.steampowered.com/login/settoken",
                     "params": {"nonce": "n"}},
                    {"url": "https://steamcommunity.com/login/settoken",
                     "params": {"nonce": "n"}},
                ]}).encode()
                return 200, payload, []
            if "store" in url:
                return 200, b"{}", [
                    f"steamLoginSecure={SAMPLE_STEAMID}%7C%7CSTORE; Path=/"]
            return None  # community falha (rede)
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        assert ss.refresh(s) is True
        assert "STORE" in s.cookies["steamLoginSecure"]

    def test_refresh_transfer_without_cookie_returns_false(self, monkeypatch):
        def mock_post(url, fields, timeout, extra_headers=None):
            if "finalizelogin" in url:
                payload = json.dumps({"transfer_info": [
                    {"url": "https://store.steampowered.com/login/settoken",
                     "params": {"nonce": "n"}},
                ]}).encode()
                return 200, payload, []
            return 200, b"{}", ["sessionid=x; Path=/"]  # sem steamLoginSecure
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        assert ss.refresh(s) is False


class TestPostMultipartNoRedirect:
    def test_captures_set_cookie_from_302(self, monkeypatch):
        """302 com Set-Cookie vira HTTPError e o cookie e' lido dele."""
        import io
        from urllib.error import HTTPError

        class _Hdrs:
            def get_all(self, _name):
                return [f"steamLoginSecure={SAMPLE_STEAMID}%7C%7CTOK; Path=/"]

        def _raise_302(req, timeout=None):
            raise HTTPError(req.full_url, 302, "Found", _Hdrs(),
                            io.BytesIO(b""))

        monkeypatch.setattr(ss._no_redirect_opener, "open", _raise_302)
        res = ss._post_multipart("https://steamcommunity.com/login/settoken",
                                 {"steamID": "x"}, 5.0)
        assert res is not None
        assert ss._extract_cookie_value(res[2], "steamLoginSecure") is not None

    def test_no_redirect_handler_returns_none(self):
        """O handler nao segue redirects (redirect_request -> None)."""
        h = ss._NoRedirect()
        assert h.redirect_request(None, None, 302, "", {}, "http://x") is None


class TestEnsureValid:
    def test_returns_true_when_already_valid(self, monkeypatch):
        monkeypatch.setattr(ss, "validate", lambda s, t=15.0: True)
        monkeypatch.setattr(ss, "refresh",
                            lambda s, t=15.0: pytest.fail("nao deve renovar"))
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid(s) is True

    def test_refreshes_when_expired(self, monkeypatch):
        states = iter([False, True])  # validate: 1o falha, 2o (pos-refresh) ok
        monkeypatch.setattr(ss, "validate", lambda s, t=15.0: next(states))
        refresh_calls = []
        monkeypatch.setattr(ss, "refresh",
                            lambda s, t=15.0: refresh_calls.append(1) or True)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid(s) is True
        assert refresh_calls == [1]

    def test_returns_false_when_refresh_fails(self, monkeypatch):
        monkeypatch.setattr(ss, "validate", lambda s, t=15.0: False)
        monkeypatch.setattr(ss, "refresh", lambda s, t=15.0: False)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid(s) is False


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


class TestValidateEx:
    def test_network_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(ss, "_follow_redirect", lambda u, c, t: None)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.validate_ex(s) is None

    def test_expired_returns_false(self, monkeypatch):
        monkeypatch.setattr(
            ss, "_follow_redirect",
            lambda u, c, t: "https://steamcommunity.com/login/home/")
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.validate_ex(s) is False

    def test_valid_returns_true(self, monkeypatch):
        monkeypatch.setattr(
            ss, "_follow_redirect",
            lambda u, c, t: f"https://steamcommunity.com/profiles/{SAMPLE_STEAMID}/")
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.validate_ex(s) is True

    def test_incomplete_session_returns_false_sem_rede(self, monkeypatch):
        calls = []
        monkeypatch.setattr(ss, "_follow_redirect",
                            lambda u, c, t: calls.append(u))
        s = SteamSession(steamid="", cookies={})
        assert ss.validate_ex(s) is False
        assert calls == []


class TestEnsureValidEx:
    def test_valid_direto(self, monkeypatch):
        monkeypatch.setattr(ss, "validate_ex", lambda s, t=15.0: True)
        monkeypatch.setattr(ss, "refresh",
                            lambda s, t=15.0: pytest.fail("nao deve renovar"))
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid_ex(s) == "valid"

    def test_network_error_nao_tenta_refresh(self, monkeypatch):
        monkeypatch.setattr(ss, "validate_ex", lambda s, t=15.0: None)
        monkeypatch.setattr(ss, "refresh",
                            lambda s, t=15.0: pytest.fail("rede fora: nao renovar"))
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid_ex(s) == "network_error"

    def test_refresh_recupera(self, monkeypatch):
        states = iter([False, True])
        monkeypatch.setattr(ss, "validate_ex", lambda s, t=15.0: next(states))
        monkeypatch.setattr(ss, "refresh", lambda s, t=15.0: True)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid_ex(s) == "valid"

    def test_invalid_quando_refresh_falha(self, monkeypatch):
        monkeypatch.setattr(ss, "validate_ex", lambda s, t=15.0: False)
        monkeypatch.setattr(ss, "refresh", lambda s, t=15.0: False)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid_ex(s) == "invalid"

    def test_network_error_pos_refresh(self, monkeypatch):
        states = iter([False, None])  # expirada; pos-refresh a rede caiu
        monkeypatch.setattr(ss, "validate_ex", lambda s, t=15.0: next(states))
        monkeypatch.setattr(ss, "refresh", lambda s, t=15.0: True)
        s = SteamSession(steamid=SAMPLE_STEAMID, cookies=dict(SAMPLE_COOKIES))
        assert ss.ensure_valid_ex(s) == "network_error"


class TestRefreshTokenRotation:
    def _session_with_refresh(self):
        cookies = dict(SAMPLE_COOKIES)
        cookies["steamRefresh_steam"] = f"{SAMPLE_STEAMID}||refresh.jwt.sig"
        return SteamSession(steamid=SAMPLE_STEAMID, cookies=cookies)

    def test_captura_rotacao_no_finalizelogin(self, monkeypatch):
        def mock_post(url, fields, timeout, extra_headers=None):
            if "finalizelogin" in url:
                payload = json.dumps({"transfer_info": [
                    {"url": "https://steamcommunity.com/login/settoken",
                     "params": {"nonce": "n"}},
                ]}).encode()
                return 200, payload, [
                    "steamRefresh_steam=ROTATED.jwt.sig; Path=/; HttpOnly",
                ]
            return 200, b"{}", [
                f"steamLoginSecure={SAMPLE_STEAMID}%7C%7CNEW; Path=/"]
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        assert ss.refresh(s) is True
        assert s.cookies["steamRefresh_steam"] == "ROTATED.jwt.sig"

    def test_sem_rotacao_mantem_token_antigo(self, monkeypatch):
        def mock_post(url, fields, timeout, extra_headers=None):
            if "finalizelogin" in url:
                payload = json.dumps({"transfer_info": [
                    {"url": "https://steamcommunity.com/login/settoken",
                     "params": {"nonce": "n"}},
                ]}).encode()
                return 200, payload, []
            return 200, b"{}", [
                f"steamLoginSecure={SAMPLE_STEAMID}%7C%7CNEW; Path=/"]
        monkeypatch.setattr(ss, "_post_multipart", mock_post)
        s = self._session_with_refresh()
        old = s.cookies["steamRefresh_steam"]
        assert ss.refresh(s) is True
        assert s.cookies["steamRefresh_steam"] == old

