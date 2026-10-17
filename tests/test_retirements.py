"""Registro de aposentadoria de caixas (skinvault/retirements.py)."""
from __future__ import annotations

import calendar
import json

import pytest

from skinvault import cases, retirements


@pytest.fixture(autouse=True)
def _registro_isolado(tmp_path, monkeypatch):
    """Nunca le' nem grava o case_retirements.json real."""
    monkeypatch.setattr(retirements, "_PATH", tmp_path / "case_retirements.json")
    retirements._cache["key"] = None
    yield
    retirements._cache["key"] = None


def _ts(dia: str) -> float:
    a, m, d = (int(x) for x in dia.split("-"))
    return float(calendar.timegm((a, m, d, 12, 0, 0)))


def _ev(tipo="xpshop_removed", interno="crate_community_35",
        nome="Fever Case", commit_date="2026-09-04T17:02:11Z"):
    return {"type": tipo, "internal": interno, "name": nome,
            "commit_date": commit_date, "commit_sha": "abcdef1234567"}


# ── registro ─────────────────────────────────────────────────
def test_seed_tem_gallery_com_fonte():
    reg = retirements.get("Gallery Case")
    assert reg["date"] == "2025-10-01"
    assert reg["channel"] == retirements.CHANNEL_ARMORY
    assert "Valve" in reg["source"]


def test_record_mantem_a_data_mais_antiga():
    assert retirements.record("Fever Case", "2026-11-04", "armory", "x")
    assert not retirements.record("Fever Case", "2026-12-01", "armory", "y")
    assert retirements.get("Fever Case")["date"] == "2026-11-04"
    assert retirements.record("Fever Case", "2026-10-30", "armory", "z")
    assert retirements.get("Fever Case")["date"] == "2026-10-30"
    # Seed nao e' sobrescrito por data posterior
    assert not retirements.record("Gallery Case", "2026-01-01", "armory", "x")


def test_record_rejeita_data_invalida():
    assert not retirements.record("X Case", "ontem", "armory", "x")
    assert not retirements.record("", "2026-01-01", "armory", "x")


def test_arquivo_corrompido_cai_no_seed(tmp_path):
    retirements._PATH.write_text("{nao e json", encoding="utf-8")
    retirements._cache["key"] = None
    assert retirements.get("Gallery Case")["date"] == "2025-10-01"


def test_record_from_events_so_container_saindo_do_armory():
    eventos = [
        _ev(),                                             # grava
        _ev(tipo="xpshop_added"),                          # entrada: ignora
        _ev(interno="set_train_2025", nome="Train 2025"),  # colecao: ignora
        _ev(tipo="drop_pool_removed", interno="set_x", nome="X"),
        _ev(interno="crate_community_99", nome="crate_community_99"),  # sem loc
    ]
    assert retirements.record_from_events(eventos) == ["Fever Case"]
    reg = retirements.get("Fever Case")
    assert reg["date"] == "2026-09-04"
    assert "abcdef12" in reg["source"]
    disco = json.loads(retirements._PATH.read_text(encoding="utf-8"))
    assert list(disco) == ["Fever Case"]


def test_years_since():
    reg = {"date": "2025-10-01"}
    assert retirements.years_since(reg, now=_ts("2026-10-01")) == \
        pytest.approx(365 / 365.25)
    assert retirements.years_since(None) is None


# ── integracao com cases.case_status ─────────────────────────
def test_gallery_deixa_de_ser_ativa():
    cs = cases.case_status("Gallery Case")
    assert cs["status"] == "discontinued" and cs["is_discontinued"]
    assert cs["retired_at"] == "2025-10-01"
    assert cs["label"] == "Gallery Case (aposentada em 01/10/2025)"


def test_as_of_antes_da_aposentadoria_ve_caixa_ativa():
    """Sem isso o backtest enxergava o status de hoje no passado."""
    cs = cases.case_status("Gallery Case", as_of=_ts("2025-06-01"))
    assert cs["status"] == "active" and not cs["is_discontinued"]
    cs = cases.case_status("Gallery Case", as_of=_ts("2025-10-01"))
    assert cs["is_discontinued"]


def test_caixa_sem_registro_nao_muda():
    cs = cases.case_status("Chroma 2 Case")
    assert cs["status"] == "discontinued" and cs["retired_at"] is None
    assert cs["label"] == "Chroma 2 Case (descontinuada, 2015)"
    assert cases.case_status("Fever Case")["status"] == "active"


def test_registro_do_watcher_reflete_no_status():
    retirements.record_from_events([_ev()])
    cs = cases.case_status("Fever Case")
    assert cs["is_discontinued"] and cs["retired_at"] == "2026-09-04"


def test_skin_da_colecao_herda_a_aposentadoria():
    cs = cases.case_status("AWP | Exemplo (Field-Tested)",
                           collection="The Gallery Collection")
    assert cs["case"] == "Gallery Case" and cs["is_discontinued"]


# ── gamedata chama o registro ────────────────────────────────
def test_check_for_updates_grava_aposentadoria(tmp_path, monkeypatch):
    from skinvault import gamedata
    head = {"sha": "abcdef1234567", "date": "2026-09-04T17:02:11Z",
            "message": "x"}
    monkeypatch.setattr(gamedata, "fetch_recent_commits", lambda n=1: [head])
    monkeypatch.setattr(gamedata, "fetch_items_game", lambda ref: "texto")
    monkeypatch.setattr(gamedata, "fetch_localization",
                        lambda ref: {"CSGO_crate_community_35": "Fever Case"})
    antigo = {"timed_drop_sets": [], "crates": {},
              "xpshop_rewards": ["crate_community_35"], "crate_series": {}}
    novo = dict(antigo, xpshop_rewards=[])
    monkeypatch.setattr(gamedata, "extract_state", lambda text: novo)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"sha": "old", "state": antigo}),
                     encoding="utf-8")
    r = gamedata.check_for_updates(state_path=state,
                                   log_path=tmp_path / "log.json")
    assert [e["type"] for e in r["events"]] == ["xpshop_removed"]
    assert retirements.get("Fever Case")["date"] == "2026-09-04"
