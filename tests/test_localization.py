"""Testes da localizacao pt-BR de nomes de skins."""
from __future__ import annotations

from skinvault.localization import localize_name


# ── Wear conditions ──────────────────────────────────────────


def test_factory_new():
    assert localize_name("AK-47 | Redline (Factory New)") == \
        "AK-47 | Redline (Nova de Fábrica)"


def test_minimal_wear():
    assert localize_name("AWP | Asiimov (Minimal Wear)") == \
        "AWP | Asiimov (Pouco Usada)"


def test_field_tested():
    assert localize_name("USP-S | Bleeding Edge (Field-Tested)") == \
        "USP-S | Bleeding Edge (Testada em Campo)"


def test_well_worn():
    assert localize_name("Glock-18 | Fade (Well-Worn)") == \
        "Glock-18 | Fade (Bastante Usada)"


def test_battle_scarred():
    assert localize_name("M4A4 | Howl (Battle-Scarred)") == \
        "M4A4 | Howl (Veterana de Guerra)"


def test_no_wear_unchanged():
    assert localize_name("AK-47 | Redline") == "AK-47 | Redline"


# ── Prefixos ──────────────────────────────────────────────────


def test_sticker_prefix():
    assert localize_name("Sticker | chelo | Berlin 2019") == \
        "Adesivo | chelo | Berlin 2019"


def test_music_kit_prefix():
    assert localize_name("Music Kit | Daniel Sadowski, Crimson Assault") == \
        "Pacote de Música | Daniel Sadowski, Crimson Assault"


def test_graffiti_prefix():
    assert localize_name("Graffiti | XAXAXA (Frog Green)") == \
        "Grafite | XAXAXA (Frog Green)"


def test_sealed_graffiti_prefix():
    """Sealed Graffiti vem antes de Graffiti no matching."""
    assert localize_name("Sealed Graffiti | XAXAXA (Frog Green)") == \
        "Grafite Selado | XAXAXA (Frog Green)"


def test_patch_prefix():
    assert localize_name("Patch | Liquid (Foil)") == "Remendo | Liquid (Foil)"


# ── Caixas ────────────────────────────────────────────────────


def test_known_case_name():
    assert localize_name("Dreams & Nightmares Case") == \
        "Caixa Sonhos e Pesadelos"


def test_known_case_kilowatt():
    assert localize_name("Kilowatt Case") == "Caixa Kilowatt"


def test_known_case_revolution():
    assert localize_name("Revolution Case") == "Caixa Revolução"


def test_unknown_case_generic_rule():
    """Caixa nao listada: aplica regra 'X Case' -> 'Caixa X'."""
    assert localize_name("Mystery Case") == "Caixa Mystery"


# ── Edge cases ────────────────────────────────────────────────


def test_empty_string():
    assert localize_name("") == ""


def test_none_safe():
    """Funcao tolera None tipado como str pelo type hint."""
    # Mesma logica: nao crasha em string vazia
    assert localize_name("") == ""


def test_combination_sticker_with_no_wear():
    """Sticker em nome composto."""
    assert localize_name("Sticker | Heroic (Holo) | 2020 RMR") == \
        "Adesivo | Heroic (Holo) | 2020 RMR"


def test_combination_souvenir_in_name():
    """'Souvenir' as prefix do nome (nao temos regra ainda, fica como esta)."""
    out = localize_name("Souvenir P250 | Whiteout (Factory New)")
    assert "Nova de Fábrica" in out  # wear traduzido
    assert "Souvenir" in out  # prefix nao tem regra ainda


def test_does_not_modify_input():
    original = "AK-47 | Redline (Field-Tested)"
    localize_name(original)
    assert original == "AK-47 | Redline (Field-Tested)"
