"""Testes do watcher de arquivos do jogo (gamedata.py)."""
import json

import pytest

from skinvault import gamedata


# ---------------------------------------------------------------------------
# Fixture: items_game.txt minimo com as estruturas relevantes
# ---------------------------------------------------------------------------

ITEMS_FIXTURE = '''
"items_game"
{
	"client_loot_lists"
	{
		"set_timed_drops_achroma_common"
		{
			"[aa_fade]weapon_p250"		"1"
		}
		"set_timed_drops_achroma"
		{
			"set_timed_drops_achroma_common"		"1"
		}
		"set_timed_drops_warm_rare"
		{
			"[cu_thing]weapon_ak47"		"1"
		}
	}
	"items"
	{
		"4001"
		{
			"item_name"		"#CSGO_crate_old_case"
			"name"		"crate_old_case"
			"first_sale_date"		"2019/10/02"
			"prefab"		"weapon_case_base"
		}
		"4002"
		{
			"item_name"		"#CSGO_crate_new_case"
			"name"		"crate_new_case"
			"prefab"		"weapon_case_base"
		}
	}
	"revolving_loot_lists"
	{
		"1"		"crate_old_case_lootlist"
	}
	"revolving_loot_lists"
	{
		"2"		"crate_new_case_lootlist"
	}
	"seasonaloperations"
	{
		"8"
		{
			"quest_reward"
			{
				"item_name"		"crate_historico_ignorado"
			}
		}
	}
	"seasonaloperations"
	{
		"11"
		{
			"redeemable_goods"		"xpshop"
			"operational_point_redeemable"
			{
				"points"		"4"
				"item_name"		"lootlist:set_spy_tech"
			}
			"operational_point_redeemable"
			{
				"points"		"2"
				"item_name"		"crate_community_35"
			}
		}
	}
}
'''

ENGLISH_FIXTURE = '''
"lang"
{
	"Tokens"
	{
		"CSGO_crate_old_case"		"Old Case"
		"CSGO_crate_new_case"		"New Case"
		"CSGO_set_timed_drops_achroma"		"The Achroma Collection"
		"CSGO_set_timed_drops_warm"		"The Radiant Collection"
		"CSGO_set_spy_tech"		"The Spy Tech Collection"
		"CSGO_crate_community_35"		"Fever Case"
	}
}
'''


@pytest.fixture
def state():
    return gamedata.extract_state(ITEMS_FIXTURE)


@pytest.fixture
def loc():
    return gamedata.parse_localization(ENGLISH_FIXTURE)


# ---------------------------------------------------------------------------
# extract_state
# ---------------------------------------------------------------------------

def test_extract_timed_drop_sets_strips_tiers(state):
    assert state["timed_drop_sets"] == [
        "set_timed_drops_achroma", "set_timed_drops_warm",
    ]


def test_extract_xpshop_only_from_xpshop_block(state):
    # bloco historico (operation 8) nao entra; so o bloco com xpshop
    assert state["xpshop_rewards"] == ["crate_community_35", "set_spy_tech"]


def test_extract_crates_with_and_without_date(state):
    assert state["crates"]["crate_old_case"] == "2019/10/02"
    assert state["crates"]["crate_new_case"] == ""


def test_extract_crate_series_merges_blocks(state):
    assert state["crate_series"] == {
        "1": "crate_old_case_lootlist",
        "2": "crate_new_case_lootlist",
    }


# ---------------------------------------------------------------------------
# Localizacao
# ---------------------------------------------------------------------------

def test_parse_localization(loc):
    assert loc["CSGO_crate_old_case"] == "Old Case"


def test_display_name_resolves_crate_and_set(loc):
    assert gamedata.display_name("crate_old_case", loc) == "Old Case"
    assert gamedata.display_name("set_spy_tech", loc) == \
        "The Spy Tech Collection"
    # prefixo set_ implicito (xpshop as vezes lista sem set_)
    assert gamedata.display_name("spy_tech", loc) == "The Spy Tech Collection"


def test_display_name_fallback_internal(loc):
    assert gamedata.display_name("sticker_pack_xyz_lootlist", loc) == \
        "sticker_pack_xyz_lootlist"


# ---------------------------------------------------------------------------
# diff_states
# ---------------------------------------------------------------------------

def test_diff_states_no_changes(state, loc):
    assert gamedata.diff_states(state, state, loc) == []


def test_diff_states_drop_pool_rotation(state, loc):
    new = dict(state)
    new["timed_drop_sets"] = ["set_timed_drops_achroma",
                              "set_timed_drops_cool"]
    events = gamedata.diff_states(state, new, loc)
    types = {(e["type"], e["internal"]) for e in events}
    assert ("drop_pool_added", "set_timed_drops_cool") in types
    assert ("drop_pool_removed", "set_timed_drops_warm") in types
    removed = [e for e in events if e["type"] == "drop_pool_removed"][0]
    assert "The Radiant Collection" in removed["summary"]
    assert "congela" in removed["summary"]


def test_diff_states_xpshop_rotation(state, loc):
    new = dict(state)
    new["xpshop_rewards"] = ["crate_community_35", "set_arabesque"]
    events = gamedata.diff_states(state, new, loc)
    types = {(e["type"], e["internal"]) for e in events}
    assert ("xpshop_added", "set_arabesque") in types
    assert ("xpshop_removed", "set_spy_tech") in types


def test_diff_states_new_container(state, loc):
    new = dict(state)
    new["crates"] = dict(state["crates"])
    new["crates"]["crate_terminal_1"] = "2026/03/11"
    events = gamedata.diff_states(state, new, loc)
    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "new_container"
    assert ev["internal"] == "crate_terminal_1"
    assert "2026/03/11" in ev["summary"]


def test_diff_states_removed_container_is_not_event(state, loc):
    # containers nunca somem dos arquivos; remocao seria ruido de parsing
    new = dict(state)
    new["crates"] = {}
    events = gamedata.diff_states(state, new, loc)
    assert all(e["type"] != "new_container" for e in events)


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def test_state_roundtrip(tmp_path, state):
    p = tmp_path / "state.json"
    gamedata.save_state({"sha": "abc", "state": state}, path=p)
    loaded = gamedata.load_state(path=p)
    assert loaded["sha"] == "abc"
    assert loaded["state"] == state


def test_load_state_missing_file(tmp_path):
    assert gamedata.load_state(path=tmp_path / "nope.json") is None


def test_log_events_appends_and_caps(tmp_path):
    p = tmp_path / "events.json"
    gamedata.log_events([{"type": "x", "n": i} for i in range(3)], path=p)
    assert len(gamedata.load_events_log(path=p)) == 3
    gamedata.log_events(
        [{"type": "y", "n": i} for i in range(gamedata._LOG_CAP)], path=p)
    log = gamedata.load_events_log(path=p)
    assert len(log) == gamedata._LOG_CAP
    assert log[-1]["type"] == "y"


def test_log_events_empty_noop(tmp_path):
    p = tmp_path / "events.json"
    gamedata.log_events([], path=p)
    assert not p.exists()


# ---------------------------------------------------------------------------
# check_for_updates (HTTP mockado)
# ---------------------------------------------------------------------------

def _mock_github(monkeypatch, sha, items_text):
    commits_body = json.dumps([{
        "sha": sha,
        "commit": {"committer": {"date": "2026-07-19T12:00:00Z"},
                   "message": f"update {sha}"},
    }])

    def fake_get(url, timeout=60.0):
        if "api.github.com" in url:
            return 200, commits_body
        if "items_game.txt" in url:
            return 200, items_text
        if "csgo_english.txt" in url:
            return 200, ENGLISH_FIXTURE
        return 404, None

    monkeypatch.setattr(gamedata, "_http_get", fake_get)


def test_check_first_run_saves_baseline_without_events(tmp_path, monkeypatch):
    _mock_github(monkeypatch, "sha1", ITEMS_FIXTURE)
    sp, lp = tmp_path / "s.json", tmp_path / "l.json"
    result = gamedata.check_for_updates(state_path=sp, log_path=lp)
    assert result["changed"] is True
    assert result["events"] == []
    assert result["error"] is None
    assert gamedata.load_state(path=sp)["sha"] == "sha1"
    assert not lp.exists()


def test_check_same_sha_no_change(tmp_path, monkeypatch):
    _mock_github(monkeypatch, "sha1", ITEMS_FIXTURE)
    sp, lp = tmp_path / "s.json", tmp_path / "l.json"
    gamedata.check_for_updates(state_path=sp, log_path=lp)
    result = gamedata.check_for_updates(state_path=sp, log_path=lp)
    assert result["changed"] is False
    assert result["events"] == []


def test_check_new_sha_generates_and_logs_events(tmp_path, monkeypatch):
    sp, lp = tmp_path / "s.json", tmp_path / "l.json"
    _mock_github(monkeypatch, "sha1", ITEMS_FIXTURE)
    gamedata.check_for_updates(state_path=sp, log_path=lp)

    updated = ITEMS_FIXTURE.replace(
        '"set_timed_drops_warm_rare"',
        '"set_timed_drops_cool_rare"',
    )
    _mock_github(monkeypatch, "sha2", updated)
    result = gamedata.check_for_updates(state_path=sp, log_path=lp)
    assert result["changed"] is True
    types = {(e["type"], e["internal"]) for e in result["events"]}
    assert ("drop_pool_added", "set_timed_drops_cool") in types
    assert ("drop_pool_removed", "set_timed_drops_warm") in types
    for ev in result["events"]:
        assert ev["commit_sha"] == "sha2"
        assert "ts" in ev
    assert gamedata.load_state(path=sp)["sha"] == "sha2"
    logged = gamedata.load_events_log(path=lp)
    assert len(logged) == len(result["events"])


def test_check_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr(gamedata, "_http_get", lambda url, timeout=60.0: (0, None))
    result = gamedata.check_for_updates(
        state_path=tmp_path / "s.json", log_path=tmp_path / "l.json")
    assert result["changed"] is False
    assert result["error"] == "network"


def test_fetch_recent_commits_parses(monkeypatch):
    body = json.dumps([{
        "sha": "abc123",
        "commit": {"committer": {"date": "2026-01-21T22:58:42Z"},
                   "message": "2000700 | 10 files | ...\nsegunda linha"},
    }])
    monkeypatch.setattr(gamedata, "_http_get",
                        lambda url, timeout=60.0: (200, body))
    commits = gamedata.fetch_recent_commits(n=1)
    assert commits == [{"sha": "abc123", "date": "2026-01-21T22:58:42Z",
                        "message": "2000700 | 10 files | ..."}]


def test_fetch_recent_commits_rate_limited(monkeypatch):
    monkeypatch.setattr(gamedata, "_http_get",
                        lambda url, timeout=60.0: (403, None))
    assert gamedata.fetch_recent_commits() == []


# ---------------------------------------------------------------------------
# Integracao com o log de alertas
# ---------------------------------------------------------------------------

def test_record_events_as_alerts(tmp_path):
    from skinvault import alerts
    log = tmp_path / "alerts_log.json"
    events = [
        {"type": "drop_pool_removed", "internal": "set_timed_drops_warm",
         "name": "The Radiant Collection",
         "summary": "Colecao 'The Radiant Collection' saiu do weekly drop."},
        {"type": "new_container", "internal": "crate_terminal_1",
         "name": "crate_terminal_1",
         "summary": "Container novo 'crate_terminal_1' nos arquivos."},
    ]
    recorded = gamedata.record_events_as_alerts(events, path=log)
    assert len(recorded) == 2
    logged = alerts.load_alerts_log(path=log)
    assert len(logged) == 2
    assert all(e["rule"] == "game_update" for e in logged)
    by_name = {e["name"]: e for e in logged}
    # remocao do drop pool = escassez estrutural -> opportunity
    assert by_name["The Radiant Collection"]["severity"] == "opportunity"
    assert by_name["crate_terminal_1"]["severity"] == "info"
    assert "saiu do weekly drop" in by_name["The Radiant Collection"]["label"]


def test_record_events_as_alerts_empty(tmp_path):
    log = tmp_path / "alerts_log.json"
    assert gamedata.record_events_as_alerts([], path=log) == []
    assert not log.exists()
