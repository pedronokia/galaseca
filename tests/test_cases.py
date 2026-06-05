"""Testes do case database."""
from __future__ import annotations

from skinvault import cases


def test_normalize_strips_wear():
    assert cases._normalize_skin_name(
        "AK-47 | Redline (Field-Tested)"
    ) == "AK-47 | Redline"


def test_normalize_strips_stattrak():
    assert cases._normalize_skin_name(
        "StatTrak™ AK-47 | Redline (Field-Tested)"
    ) == "AK-47 | Redline"


def test_normalize_strips_souvenir():
    assert cases._normalize_skin_name(
        "Souvenir AWP | Dragon Lore (Factory New)"
    ) == "AWP | Dragon Lore"


def test_case_status_discontinued():
    r = cases.case_status("AK-47 | Redline (Field-Tested)")
    assert r["case"] == "Operation Phoenix Weapon Case"
    assert r["status"] == "discontinued"
    assert r["is_discontinued"] is True
    assert "descontinuada" in r["label"]


def test_case_status_active():
    r = cases.case_status("AK-47 | Nightwish (Factory New)")
    assert r["case"] == "Dreams & Nightmares Case"
    assert r["status"] == "active"
    assert r["is_discontinued"] is False
    assert "ativa" in r["label"]


def test_case_status_collection():
    r = cases.case_status("AWP | Dragon Lore (Factory New)")
    assert r["case"] == "The Cobblestone Collection"
    assert r["status"] == "collection"
    assert r["is_discontinued"] is False
    assert r["is_rare"] is False


def test_case_status_unknown():
    r = cases.case_status("Glock-18 | Fake Skin (Battle-Scarred)")
    assert r["case"] is None
    assert r["status"] == "unknown"
    assert r["is_discontinued"] is False
    assert r["label"] == ""


def test_case_status_stattrak_normalized():
    r = cases.case_status("StatTrak™ AK-47 | Fuel Injector (Minimal Wear)")
    assert r["case"] == "Operation Wildfire Case"
    assert r["is_discontinued"] is True


def test_case_status_gloves_partial_match():
    r = cases.case_status(
        "★ Sport Gloves | Pandora's Box (Field-Tested)"
    )
    assert r["case"] == "Glove Case"


def test_list_cases_by_status_active():
    active = cases.list_cases_by_status("active")
    assert "Recoil Case" in active
    assert "Dreams & Nightmares Case" in active


def test_list_cases_by_status_discontinued():
    disc = cases.list_cases_by_status("discontinued")
    assert "Operation Bravo Case" in disc
    assert "Clutch Case" in disc


def test_skin_to_case_mappings_reference_existing_cases():
    """Toda case mencionada em _SKIN_TO_CASE deve existir em _CASES."""
    known = set(cases._CASES.keys())
    missing = {v for v in cases._SKIN_TO_CASE.values() if v not in known}
    assert not missing, f"Cases referenciados mas nao definidos: {missing}"


def test_normalize_handles_extra_whitespace():
    assert cases._normalize_skin_name(
        "  AK-47 | Redline (Field-Tested)  "
    ) == "AK-47 | Redline"
