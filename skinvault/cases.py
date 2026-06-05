"""Database de cases/colecoes e mapeamento skin -> case.

Status:
- active: caixa ainda dropa no jogo (oferta cresce)
- discontinued: caixa nao dropa mais (oferta congelada)
- rare: caixa rara (oferta cresce lentamente)
- collection: skin de colecao (Cobblestone, Cache, etc -- nao tem caixa)

Cobertura intencionalmente focada nos itens mais populares/liquidos.
Expandir conforme necessario.
"""
from __future__ import annotations

import re

# Status por case
_CASES: dict[str, dict] = {
    # === DISCONTINUED (nao dropam mais) ===
    "CS:GO Weapon Case": {"status": "discontinued", "year": 2013},
    "CS:GO Weapon Case 2": {"status": "discontinued", "year": 2013},
    "CS:GO Weapon Case 3": {"status": "discontinued", "year": 2014},
    "eSports 2013 Case": {"status": "discontinued", "year": 2013},
    "eSports 2013 Winter Case": {"status": "discontinued", "year": 2013},
    "eSports 2014 Summer Case": {"status": "discontinued", "year": 2014},
    "Winter Offensive Weapon Case": {"status": "discontinued", "year": 2013},
    "Operation Bravo Case": {"status": "discontinued", "year": 2013},
    "Operation Phoenix Weapon Case": {"status": "discontinued", "year": 2014},
    "Operation Breakout Weapon Case": {"status": "discontinued", "year": 2014},
    "Operation Vanguard Weapon Case": {"status": "discontinued", "year": 2014},
    "Huntsman Weapon Case": {"status": "discontinued", "year": 2014},
    "Operation Wildfire Case": {"status": "discontinued", "year": 2016},
    "Operation Bloodhound Weapon Case": {"status": "discontinued", "year": 2015},
    "Falchion Case": {"status": "discontinued", "year": 2015},
    "Shadow Case": {"status": "discontinued", "year": 2015},
    "Revolver Case": {"status": "discontinued", "year": 2015},
    "Chroma Case": {"status": "discontinued", "year": 2015},
    "Chroma 2 Case": {"status": "discontinued", "year": 2015},
    "Chroma 3 Case": {"status": "discontinued", "year": 2016},
    "Gamma Case": {"status": "discontinued", "year": 2016},
    "Gamma 2 Case": {"status": "discontinued", "year": 2016},
    "Glove Case": {"status": "discontinued", "year": 2016},
    "Spectrum Case": {"status": "discontinued", "year": 2017},
    "Spectrum 2 Case": {"status": "discontinued", "year": 2017},
    "Operation Hydra Case": {"status": "discontinued", "year": 2017},
    "Operation Shattered Web Case": {"status": "discontinued", "year": 2019},
    "Operation Broken Fang Case": {"status": "discontinued", "year": 2020},
    "Operation Riptide Case": {"status": "discontinued", "year": 2021},
    "Clutch Case": {"status": "discontinued", "year": 2018},
    "Horizon Case": {"status": "discontinued", "year": 2018},
    "Danger Zone Case": {"status": "discontinued", "year": 2018},
    "Prisma Case": {"status": "discontinued", "year": 2019},
    "Prisma 2 Case": {"status": "discontinued", "year": 2020},
    "CS20 Case": {"status": "discontinued", "year": 2019},
    "Shattered Web Case": {"status": "discontinued", "year": 2019},
    "Fracture Case": {"status": "discontinued", "year": 2020},
    "Snakebite Case": {"status": "discontinued", "year": 2021},

    # === ACTIVE (ainda dropam) ===
    "Dreams & Nightmares Case": {"status": "active", "year": 2022},
    "Recoil Case": {"status": "active", "year": 2022},
    "Revolution Case": {"status": "active", "year": 2023},
    "Kilowatt Case": {"status": "active", "year": 2024},
    "Gallery Case": {"status": "active", "year": 2024},
    "Fever Case": {"status": "active", "year": 2025},

    # === COLECOES (sem caixa, drop em mapas/operations) ===
    "The Cobblestone Collection": {"status": "collection", "year": 2014},
    "The Cache Collection": {"status": "collection", "year": 2016},
    "The Overpass Collection": {"status": "collection", "year": 2014},
    "The Dust 2 Collection": {"status": "collection", "year": 2014},
    "The Mirage Collection": {"status": "collection", "year": 2014},
    "The Inferno Collection": {"status": "collection", "year": 2014},
    "The Train Collection": {"status": "collection", "year": 2014},
    "The Nuke Collection": {"status": "collection", "year": 2014},
    "The Anubis Collection": {"status": "collection", "year": 2022},
    "The Ancient Collection": {"status": "collection", "year": 2021},
    "The St. Marc Collection": {"status": "collection", "year": 2023},
}

# skin name (sem wear) -> case name
# Foco em itens populares e liquidos.
_SKIN_TO_CASE: dict[str, str] = {
    # CS:GO Weapon Case (2013)
    "AWP | Lightning Strike": "CS:GO Weapon Case",
    "AK-47 | Case Hardened": "CS:GO Weapon Case",
    "Desert Eagle | Hypnotic": "CS:GO Weapon Case",
    "Glock-18 | Dragon Tattoo": "CS:GO Weapon Case",
    "M4A1-S | Dark Water": "CS:GO Weapon Case",

    # Winter Offensive (2013)
    "M4A4 | Asiimov": "Winter Offensive Weapon Case",
    "P90 | Asiimov": "Winter Offensive Weapon Case",

    # Operation Bravo (2013)
    "AK-47 | Fire Serpent": "Operation Bravo Case",
    "Desert Eagle | Golden Koi": "Operation Bravo Case",
    "P90 | Emerald Dragon": "Operation Bravo Case",
    "M4A1-S | Bright Water": "Operation Bravo Case",

    # Operation Phoenix (2014)
    "AK-47 | Redline": "Winter Offensive Weapon Case",
    "AWP | Asiimov": "Operation Phoenix Weapon Case",
    "P90 | Trigon": "Operation Phoenix Weapon Case",

    # Operation Breakout (2014)
    "M4A1-S | Cyrex": "Operation Breakout Weapon Case",
    "Glock-18 | Water Elemental": "Operation Breakout Weapon Case",
    "Butterfly Knife": "Operation Breakout Weapon Case",
    "P250 | Muertos": "Operation Breakout Weapon Case",

    # Operation Vanguard (2014)
    "AK-47 | Wasteland Rebel": "Operation Vanguard Weapon Case",
    "M4A1-S | Basilisk": "Operation Vanguard Weapon Case",
    "AWP | Man-o'-war": "Operation Vanguard Weapon Case",

    # Huntsman (2014)
    "AK-47 | Vulcan": "Huntsman Weapon Case",
    "M4A4 | Desert-Strike": "Huntsman Weapon Case",
    "Huntsman Knife": "Huntsman Weapon Case",

    # Chroma (2015)
    "AK-47 | Cartel": "Chroma Case",
    "M4A4 | Dragon King": "Chroma Case",
    "AWP | Man-o'-war": "Chroma Case",

    # Chroma 2 (2015)
    "AK-47 | Elite Build": "Chroma 2 Case",
    "AWP | Worm God": "Chroma 2 Case",
    "MAC-10 | Neon Rider": "Chroma 2 Case",

    # Chroma 3 (2016)
    "AWP | Phobos": "Chroma 3 Case",
    "M4A1-S | Chantico's Fire": "Chroma 3 Case",

    # Operation Wildfire (2016)
    "AK-47 | Fuel Injector": "Operation Wildfire Case",
    "M4A4 | The Battlestar": "Operation Wildfire Case",

    # Gamma (2016)
    "AK-47 | Neon Revolution": "Gamma Case",
    "Glock-18 | Wasteland Rebel": "Gamma Case",
    "M4A1-S | Mecha Industries": "Gamma Case",

    # Glove Case (2016)
    "AK-47 | Frontside Misty": "Glove Case",
    "M4A4 | Buzz Kill": "Glove Case",
    "Sport Gloves": "Glove Case",
    "Specialist Gloves": "Glove Case",
    "Hand Wraps": "Glove Case",
    "Driver Gloves": "Glove Case",
    "Moto Gloves": "Glove Case",
    "Bloodhound Gloves": "Glove Case",

    # Spectrum (2017)
    "AK-47 | Bloodsport": "Spectrum Case",
    "AWP | Fever Dream": "Spectrum Case",

    # Operation Hydra (2017)
    "AK-47 | Aquamarine Revenge": "Operation Hydra Case",
    "AWP | Oni Taiji": "Operation Hydra Case",

    # Clutch Case (2018)
    "M4A4 | Neo-Noir": "Clutch Case",
    "AK-47 | Orbit Mk01": "Clutch Case",

    # Horizon (2018)
    "AK-47 | Neon Rider": "Horizon Case",
    "Glock-18 | Vogue": "Horizon Case",

    # Danger Zone (2018)
    "AK-47 | Asiimov": "Danger Zone Case",
    "AWP | Neo-Noir": "Danger Zone Case",

    # Prisma (2019)
    "AK-47 | Uncharted": "Prisma Case",
    "AWP | Atheris": "Prisma Case",
    "Galil AR | Akoben": "Prisma Case",

    # Prisma 2 (2020)
    "MAC-10 | Disco Tech": "Prisma 2 Case",
    "AK-47 | Phantom Disruptor": "Prisma 2 Case",

    # CS20 (2019)
    "AWP | Wildfire": "CS20 Case",
    "FAMAS | Decommissioned": "CS20 Case",

    # Shattered Web (2019)
    "AWP | Containment Breach": "Shattered Web Case",
    "AK-47 | Rat Rod": "Shattered Web Case",

    # Fracture (2020)
    "AK-47 | Legion of Anubis": "Fracture Case",
    "Desert Eagle | Printstream": "Fracture Case",
    "M4A4 | Tooth Fairy": "Fracture Case",

    # Operation Broken Fang (2020)
    "M4A1-S | Printstream": "Operation Broken Fang Case",
    "USP-S | Monster Mashup": "Operation Broken Fang Case",
    "Glock-18 | Neo-Noir": "Operation Broken Fang Case",

    # Snakebite (2021)
    "AK-47 | Slate": "Snakebite Case",
    "M4A4 | In Living Color": "Snakebite Case",
    "USP-S | The Traitor": "Snakebite Case",

    # Operation Riptide (2021)
    "AK-47 | Leet Museo": "Operation Riptide Case",
    "M4A1-S | Night Terror": "Operation Riptide Case",

    # === ACTIVE ===
    # Dreams & Nightmares (2022)
    "AK-47 | Nightwish": "Dreams & Nightmares Case",
    "FN57 | Fairy Tale": "Dreams & Nightmares Case",
    "USP-S | Ticket to Hell": "Dreams & Nightmares Case",

    # Recoil (2022)
    "AK-47 | Ice Coaled": "Recoil Case",
    "AWP | Chromatic Aberration": "Recoil Case",
    "M4A4 | Eye of Horus": "Recoil Case",

    # Revolution (2023)
    "AK-47 | Head Shot": "Revolution Case",
    "M4A4 | Temukau": "Revolution Case",
    "AWP | Duality": "Revolution Case",

    # Kilowatt (2024)
    "AK-47 | Inheritance": "Kilowatt Case",
    "M4A1-S | Black Lotus": "Kilowatt Case",
    "Kukri Knife": "Kilowatt Case",

    # Gallery (2024)
    "AWP | The Prince": "Gallery Case",
    "AK-47 | Cartel": "Gallery Case",

    # Fever (2025)
    "AK-47 | Searing Rage": "Fever Case",

    # === COLECOES ===
    "AWP | Dragon Lore": "The Cobblestone Collection",
    "M4A4 | Howl": "The Huntsman Collection",
    "AK-47 | Jet Set": "The Anubis Collection",
}

_WEAR_RE = re.compile(r"\s*\([^)]+\)\s*$")
_STATTRAK_RE = re.compile(r"^StatTrak™\s*", re.IGNORECASE)
_SOUVENIR_RE = re.compile(r"^Souvenir\s*", re.IGNORECASE)


def _normalize_skin_name(name: str) -> str:
    """Remove StatTrak/Souvenir prefix, wear suffix, e espacos extras."""
    s = name.strip()
    s = _STATTRAK_RE.sub("", s)
    s = _SOUVENIR_RE.sub("", s)
    s = _WEAR_RE.sub("", s)
    return s.strip()


def case_status(name: str) -> dict:
    """Retorna informacoes de caixa/colecao para o item.

    Output:
    {
      "case": str | None,           # nome da caixa/colecao
      "status": str,                # active | discontinued | rare | collection | unknown
      "is_discontinued": bool,
      "is_rare": bool,
      "year": int | None,
      "label": str,                 # texto curto pra UI
    }
    """
    skin = _normalize_skin_name(name)

    # Match exato primeiro
    case_name = _SKIN_TO_CASE.get(skin)

    # Match parcial: skin name pode ser substring (gloves variants etc)
    if not case_name:
        for key, val in _SKIN_TO_CASE.items():
            if key.lower() in skin.lower():
                case_name = val
                break

    if not case_name:
        return {
            "case": None,
            "status": "unknown",
            "is_discontinued": False,
            "is_rare": False,
            "year": None,
            "label": "",
        }

    meta = _CASES.get(case_name, {})
    status = meta.get("status", "unknown")
    year = meta.get("year")

    is_disc = status == "discontinued"
    is_rare = status == "rare"

    if status == "discontinued":
        label = f"{case_name} (descontinuada"
        if year:
            label += f", {year}"
        label += ")"
    elif status == "active":
        label = f"{case_name} (ativa)"
    elif status == "collection":
        label = f"{case_name}"
    elif status == "rare":
        label = f"{case_name} (rara)"
    else:
        label = case_name

    return {
        "case": case_name,
        "status": status,
        "is_discontinued": is_disc,
        "is_rare": is_rare,
        "year": year,
        "label": label,
    }


def list_cases_by_status(status: str) -> list[str]:
    """Lista nomes de cases por status."""
    return [name for name, meta in _CASES.items() if meta.get("status") == status]
