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


# === Container input direto (caixa ou capsula) ===

def test_case_status_direct_case_name():
    r = cases.case_status("Chroma 2 Case")
    assert r["case"] == "Chroma 2 Case"
    assert r["status"] == "discontinued"
    assert r["is_discontinued"] is True
    assert r["year"] == 2015


def test_case_status_direct_active_case():
    r = cases.case_status("Fever Case")
    assert r["case"] == "Fever Case"
    assert r["status"] == "active"
    assert r["is_discontinued"] is False


def test_case_status_capsule_legends():
    r = cases.case_status("Stockholm 2021 Legends Sticker Capsule")
    assert r["case"] == "Stockholm 2021 Legends Sticker Capsule"
    assert r["status"] == "discontinued"
    assert r["is_discontinued"] is True
    assert r["year"] == 2021
    assert "descontinuada" in r["label"]


def test_case_status_capsule_katowice_2014():
    # Pre-2020 sao "EMS Katowice 2014 Legends" no Steam Market (sem
    # "Sticker Capsule" no nome).
    r = cases.case_status("EMS Katowice 2014 Legends")
    assert r["status"] == "discontinued"
    assert r["year"] == 2014


def test_case_status_capsule_unknown_returns_unknown():
    r = cases.case_status("Fake 9999 Legends Sticker Capsule")
    assert r["case"] is None
    assert r["status"] == "unknown"


def test_all_capsules_are_discontinued_after_cologne_2026():
    """Apos IEM Cologne 2026 (22/05/2026), TODAS as capsulas viraram supply-fixa."""
    non_disc = [
        name for name, meta in cases._CAPSULES.items()
        if meta.get("status") != "discontinued"
    ]
    assert not non_disc, f"Capsulas nao descontinuadas: {non_disc}"


def test_capsules_have_year():
    no_year = [
        name for name, meta in cases._CAPSULES.items()
        if "year" not in meta
    ]
    assert not no_year, f"Capsulas sem year: {no_year}"


def test_is_container_recognizes_capsules():
    # Modernas (terminam com "Sticker Capsule")
    assert cases.is_container("Stockholm 2021 Legends Sticker Capsule")
    # Vintage (nao terminam com "Capsule" — lookup direto em _CAPSULES)
    assert cases.is_container("EMS Katowice 2014 Legends")
    assert cases.is_container("DreamHack 2014 Legends (Holo-Foil)")
    assert cases.is_container("Boston 2018 Legends (Holo-Foil)")


def test_capsules_and_cases_dont_collide():
    """Nenhum nome deve aparecer em ambos _CASES e _CAPSULES."""
    collisions = set(cases._CASES) & set(cases._CAPSULES)
    assert not collisions, f"Nomes colidem: {collisions}"


def test_capsule_count_minimum():
    """Catalogo deve cobrir >= 50 capsulas (todos os Majors documentados)."""
    assert len(cases._CAPSULES) >= 50


def test_list_capsules_returns_all():
    result = cases.list_capsules()
    assert len(result) == len(cases._CAPSULES)
    assert "Stockholm 2021 Legends Sticker Capsule" in result


def test_list_capsules_returns_list_not_view():
    """Mutar o retorno nao deve afetar _CAPSULES."""
    result = cases.list_capsules()
    result.append("FAKE")
    assert "FAKE" not in cases._CAPSULES
