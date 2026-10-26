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


def test_skins_in_case_conta_mapeadas():
    assert cases.skins_in_case("Operation Phoenix Weapon Case") >= 1


def test_skins_in_case_sem_nome():
    assert cases.skins_in_case(None) == 0


def test_skins_in_case_nome_desconhecido():
    assert cases.skins_in_case("Caixa Que Nao Existe") == 0


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
    """Catalogo deve cobrir >= 66 capsulas (Majors + comunidade)."""
    assert len(cases._CAPSULES) >= 66


def test_list_capsules_returns_all():
    result = cases.list_capsules()
    assert len(result) == len(cases._CAPSULES)
    assert "Stockholm 2021 Legends Sticker Capsule" in result


def test_list_capsules_returns_list_not_view():
    """Mutar o retorno nao deve afetar _CAPSULES."""
    result = cases.list_capsules()
    result.append("FAKE")
    assert "FAKE" not in cases._CAPSULES


# === Autograph Capsules ===

def test_case_status_autograph_capsule():
    r = cases.case_status("Antwerp 2022 Champions Autograph Capsule")
    assert r["case"] == "Antwerp 2022 Champions Autograph Capsule"
    assert r["status"] == "discontinued"
    assert r["is_discontinued"] is True
    assert r["year"] == 2022
    assert "descontinuada" in r["label"]


def test_case_status_autograph_stockholm():
    r = cases.case_status("Stockholm 2021 Champions Autograph Capsule")
    assert r["status"] == "discontinued"
    assert r["year"] == 2021


def test_case_status_autograph_budapest():
    r = cases.case_status("Budapest 2025 Contenders Autograph Capsule")
    assert r["status"] == "discontinued"
    assert r["year"] == 2025


def test_case_status_autograph_unknown():
    r = cases.case_status("Fake 9999 Autograph Capsule")
    assert r["case"] is None
    assert r["status"] == "unknown"


def test_is_container_autograph():
    assert cases.is_container("Antwerp 2022 Champions Autograph Capsule")
    assert cases.is_container("Paris 2023 Legends Autograph Capsule")


def test_list_autograph_capsules_returns_all():
    result = cases.list_autograph_capsules()
    assert len(result) == len(cases._AUTOGRAPH_CAPSULES)
    assert "Stockholm 2021 Champions Autograph Capsule" in result


def test_list_autograph_capsules_returns_list_not_view():
    result = cases.list_autograph_capsules()
    result.append("FAKE")
    assert "FAKE" not in cases._AUTOGRAPH_CAPSULES


def test_autograph_capsules_have_year():
    no_year = [
        name for name, meta in cases._AUTOGRAPH_CAPSULES.items()
        if "year" not in meta
    ]
    assert not no_year, f"Autograph capsules sem year: {no_year}"


def test_autograph_capsules_all_discontinued():
    non_disc = [
        name for name, meta in cases._AUTOGRAPH_CAPSULES.items()
        if meta.get("status") != "discontinued"
    ]
    assert not non_disc, f"Autograph capsules nao descontinuadas: {non_disc}"


def test_autograph_capsules_dont_collide_with_cases():
    collisions = set(cases._AUTOGRAPH_CAPSULES) & set(cases._CASES)
    assert not collisions, f"Colisao _AUTOGRAPH_CAPSULES x _CASES: {collisions}"


def test_autograph_capsules_dont_collide_with_sticker_capsules():
    collisions = set(cases._AUTOGRAPH_CAPSULES) & set(cases._CAPSULES)
    assert not collisions, f"Colisao _AUTOGRAPH_CAPSULES x _CAPSULES: {collisions}"


def test_autograph_count_minimum():
    assert len(cases._AUTOGRAPH_CAPSULES) >= 32


# --- Premium Stickers ---

def test_premium_stickers_count():
    """~386 stickers de todos os Majors 2014-2024 (Holo/Glitter)."""
    n = len(cases._PREMIUM_STICKERS)
    assert 380 <= n <= 400, f"Expected ~386, got {n}"


def test_premium_stickers_have_year():
    no_year = [
        name for name, meta in cases._PREMIUM_STICKERS.items()
        if "year" not in meta
    ]
    assert not no_year, f"Premium stickers sem year: {no_year}"


def test_premium_stickers_have_source():
    no_src = [
        name for name, meta in cases._PREMIUM_STICKERS.items()
        if "source" not in meta
    ]
    assert not no_src, f"Premium stickers sem source: {no_src}"


def test_premium_stickers_katowice_2014_titan():
    r = cases.case_status("Sticker | Titan (Holo) | Katowice 2014")
    # Stickers individuais nao tem container mapping -> unknown
    assert r["status"] == "unknown"
    assert r["case"] is None


def test_premium_stickers_cologne_2014_cloud9():
    r = cases.case_status("Sticker | Cloud9 (Holo) | Cologne 2014")
    assert r["status"] == "unknown"


def test_premium_stickers_all_start_with_sticker():
    bad = [
        n for n in cases._PREMIUM_STICKERS
        if not n.startswith("Sticker | ")
    ]
    assert not bad, f"Nomes sem prefixo 'Sticker | ': {bad}"


def test_premium_stickers_no_colon_fallback():
    """Certifies that sticker names with (Holo) in middle position
    are NOT handled by worn/colon fallback case_status mapping.
    The variant (Holo) is NOT at the end, so it's not stripped
    by _normalize_skin_name."""
    r = cases.case_status("Sticker | iBUYPOWER (Holo) | Katowice 2014")
    assert r["status"] == "unknown"
    assert r["case"] is None


def test_premium_stickers_all_have_premium_prefix():
    """All premium stickers must have "Sticker | " prefix (market standard)."""
    for name in cases._PREMIUM_STICKERS:
        assert name.startswith("Sticker | "), f"Bad prefix: {name}"


def test_premium_stickers_katowice_2014_has_16():
    """16 Katowice 2014 stickers (8 Legends + 8 Challengers)."""
    kato_2014 = [
        n for n in cases._PREMIUM_STICKERS
        if "Katowice 2014" in n
    ]
    assert len(kato_2014) == 16, f"Expected 16, got {len(kato_2014)}"


def test_premium_stickers_cologne_2014_has_16():
    cologne_2014 = [
        n for n in cases._PREMIUM_STICKERS
        if "Cologne 2014" in n
    ]
    assert len(cologne_2014) == 16


def test_premium_stickers_dreamhack_2014_has_6():
    dh = [
        n for n in cases._PREMIUM_STICKERS
        if "DreamHack 2014" in n
    ]
    assert len(dh) == 6


def test_premium_stickers_katowice_2015_has_16():
    kato_2015 = [
        n for n in cases._PREMIUM_STICKERS
        if "Katowice 2015" in n
    ]
    assert len(kato_2015) == 16


def test_premium_stickers_all_have_year_2014_to_2024():
    bad = [
        n for n, meta in cases._PREMIUM_STICKERS.items()
        if not (2014 <= meta.get("year", 0) <= 2024)
    ]
    assert not bad, f"Stickers com year fora 2014-2024: {bad}"


def test_premium_stickers_all_year_in_name():
    """Verifica que o ano no nome do sticker bate com o meta year."""
    bad = []
    for name, meta in cases._PREMIUM_STICKERS.items():
        if str(meta["year"]) not in name:
            bad.append(name)
    assert not bad, f"Ano do nome diferente do meta year: {bad}"


def test_premium_stickers_no_collision_with_cases():
    cols = set(cases._PREMIUM_STICKERS) & set(cases._CASES)
    assert not cols, f"Colisao _PREMIUM_STICKERS x _CASES: {cols}"


def test_premium_stickers_no_collision_with_capsules():
    cols = set(cases._PREMIUM_STICKERS) & set(cases._CAPSULES)
    assert not cols, f"Colisao _PREMIUM_STICKERS x _CAPSULES: {cols}"


def test_premium_stickers_no_collision_with_autograph():
    cols = set(cases._PREMIUM_STICKERS) & set(cases._AUTOGRAPH_CAPSULES)
    assert not cols, f"Colisao _PREMIUM_STICKERS x _AUTOGRAPH_CAPSULES: {cols}"


def test_premium_stickers_not_containers():
    """Stickers individuais nao sao containers."""
    name = "Sticker | Titan (Holo) | Katowice 2014"
    assert not cases.is_container(name)


def test_list_premium_stickers_returns_all():
    result = cases.list_premium_stickers()
    assert len(result) == len(cases._PREMIUM_STICKERS)
    assert "Sticker | Titan (Holo) | Katowice 2014" in result


def test_list_premium_stickers_returns_copy():
    result = cases.list_premium_stickers()
    result.append("FAKE")
    assert "FAKE" not in cases._PREMIUM_STICKERS


# --- ALL Stickers (expanded universe) ---

def test_list_all_stickers_has_premium():
    all_s = cases.list_all_stickers()
    premium = cases.list_premium_stickers()
    overlap = [n for n in premium if n in all_s]
    assert len(overlap) >= 234, f"Only {len(overlap)} premium stickers in all_stickers"


def test_list_all_stickers_starts_with_sticker():
    bad = [n for n in cases.list_all_stickers() if not n.startswith("Sticker | ")]
    assert not bad


def test_list_all_stickers_has_new_events():
    all_s = cases.list_all_stickers()
    austin = [n for n in all_s if "Austin 2025" in n]
    budapest = [n for n in all_s if "Budapest 2025" in n]
    cologne = [n for n in all_s if "Cologne 2026" in n]
    assert len(austin) >= 48, f"Austin 2025: {len(austin)}"
    assert len(budapest) >= 48, f"Budapest 2025: {len(budapest)}"
    assert len(cologne) >= 48, f"Cologne 2026: {len(cologne)}"


def test_list_all_stickers_has_paper_variants():
    all_s = cases.list_all_stickers()
    premium = cases.list_premium_stickers()
    # Paper = in all but NOT premium nor variant-suffixed
    paper = [n for n in all_s if n not in premium
             and "(Holo)" not in n and "(Glitter)" not in n
             and "(Foil)" not in n and "(Gold)" not in n]
    assert len(paper) >= 100


def test_list_all_stickers_has_gold_variants():
    all_s = cases.list_all_stickers()
    gold = [n for n in all_s if "(Gold)" in n]
    assert len(gold) >= 100


def test_list_all_stickers_count():
    """Deve ter >= 9700 stickers com todas as categorias."""
    n = len(cases.list_all_stickers())
    assert 9700 <= n <= 12000, f"Expected ~9892, got {n}"


def test_list_all_stickers_has_autograph():
    all_s = cases.list_all_stickers()
    autograph = [n for n in all_s if "Foil" in n and "Cologne 2015" in n]
    assert len(autograph) >= 1


def test_list_all_stickers_has_community():
    all_s = cases.list_all_stickers()
    community = [n for n in all_s if n == "Sticker | 10 Year Birthday Sticker Capsule"
                 or "Chicken" in n and "(" not in n
                 and "Holo" not in n and "Foil" not in n]
    # Should have community stickers
    chicken = [n for n in all_s if "Chicken" in n]
    assert len(chicken) >= 3


def test_list_all_stickers_has_autograph_category():
    all_s = cases.list_all_stickers()
    # s1mple autographs across events
    simple = [n for n in all_s if "s1mple" in n]
    assert len(simple) >= 5


def test_sticker_data_importable():
    from skinvault.sticker_data import get_all
    assert len(get_all()) >= 9700


def test_list_stickers_by_category_team():
    team = cases.list_tournament_stickers()
    assert len(team) >= 1700
    assert all("Sticker | " in n for n in team[:100])
    assert any("Titan" in n for n in team)
    assert any("Natus Vincere" in n for n in team) or any("NaVi" in n for n in team)


def test_list_stickers_by_category_autograph():
    auto = cases.list_autograph_stickers()
    assert 7000 <= len(auto) <= 7200
    assert any("s1mple" in n for n in auto)
    assert any("Foil" in n or "Gold" in n or "Glitter" in n for n in auto)


def test_list_stickers_by_category_community():
    comm = cases.list_community_stickers()
    assert 800 <= len(comm) <= 900
    assert any("Chicken" in n for n in comm)
    assert any("Birthday" in n for n in comm) or any("Bomb" in n for n in comm)


def test_list_stickers_by_category_event():
    ev = cases.list_event_stickers()
    assert 60 <= len(ev) <= 80
    assert any("BLAST" in n or "IEM" in n or "ESL" in n for n in ev)


def test_list_stickers_by_category_sum_matches_all():
    total = len(cases.list_all_stickers())
    team = len(cases.list_tournament_stickers())
    auto = len(cases.list_autograph_stickers())
    comm = len(cases.list_community_stickers())
    ev = len(cases.list_event_stickers())
    # Sum must be >= total (some premium extras may overlap categories)
    assert team + auto + comm + ev >= total


def test_sticker_categories_no_duplicates():
    """Cada sticker aparece exatamente em uma categoria."""
    team = set(cases.list_tournament_stickers())
    auto = set(cases.list_autograph_stickers())
    comm = set(cases.list_community_stickers())
    ev = set(cases.list_event_stickers())
    # No overlap between categories
    assert team.isdisjoint(auto)
    assert team.isdisjoint(comm)
    assert team.isdisjoint(ev)
    assert auto.isdisjoint(comm)
    assert auto.isdisjoint(ev)
    assert comm.isdisjoint(ev)
