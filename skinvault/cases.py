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

from skinvault.sticker_data import get_all as _get_stickers

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
    # "Operation Bloodhound Weapon Case" removida em 2026-07-29: nao existe
    # no Market. Verificado pelo <title> da listing page (ver AGENTS.md #12)
    # nas tres grafias plausiveis -- todas devolvem o generico "Market Item".
    # A Operation Bloodhound nao trouxe caixa propria; a caixa dela e' a
    # Falchion Case, que ja' esta' catalogada logo abaixo.
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
    # "Operation Shattered Web Case" removida em 2026-07-29: duplicata
    # invalida de "Shattered Web Case" (mesma operacao, mesmo ano), que
    # esta' logo abaixo e responde com 3130 pontos. Mesmo metodo do <title>.
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


# Cápsulas de Major (sticker capsules)
#
# Status: TODAS sao 'discontinued' por consequencia do update IEM Cologne 2026
# (22/05/2026), que aboliu o sistema de capsulas — stickers de Major agora sao
# vendidas direto via Major Shop com tokens. Cápsulas pré-Cologne 2026 viraram
# supply-fixa permanente. Ver skinvault/valve_events.py (capsule_abolition_2026_05).
#
# Cápsulas pre-2024 ja estavam descontinuadas ha anos (drop cessava ~6-12 meses
# pos-Major). Austin 2025 e Budapest 2025 foram afetadas pelo update Cologne 2026.
_CAPSULES: dict[str, dict] = {
    # 2014 — formato Steam Market: {Sponsor} {Location} {Year} {Tier}
    # (sem "Sticker Capsule" no nome). DreamHack so' teve Legends.
    "EMS Katowice 2014 Legends": {"status": "discontinued", "year": 2014},
    "EMS Katowice 2014 Challengers": {"status": "discontinued", "year": 2014},
    "ESL One Cologne 2014 Legends": {"status": "discontinued", "year": 2014},
    "ESL One Cologne 2014 Challengers": {"status": "discontinued", "year": 2014},
    "DreamHack 2014 Legends (Holo-Foil)": {"status": "discontinued", "year": 2014},

    # 2015 — Katowice usa (Holo-Foil); Cologne so' (Foil); Cluj-Napoca prefix DreamHack
    "ESL One Katowice 2015 Legends (Holo-Foil)": {"status": "discontinued", "year": 2015},
    "ESL One Katowice 2015 Challengers (Holo-Foil)": {"status": "discontinued", "year": 2015},
    "ESL One Cologne 2015 Legends (Foil)": {"status": "discontinued", "year": 2015},
    "ESL One Cologne 2015 Challengers (Foil)": {"status": "discontinued", "year": 2015},
    "DreamHack Cluj-Napoca 2015 Legends (Foil)": {"status": "discontinued", "year": 2015},
    "DreamHack Cluj-Napoca 2015 Challengers (Foil)": {"status": "discontinued", "year": 2015},

    # 2016 — MLG Columbus mantem prefix; Cologne 2016 NAO leva ESL One no Steam
    "MLG Columbus 2016 Legends (Holo-Foil)": {"status": "discontinued", "year": 2016},
    "MLG Columbus 2016 Challengers (Holo-Foil)": {"status": "discontinued", "year": 2016},
    "Cologne 2016 Legends (Holo-Foil)": {"status": "discontinued", "year": 2016},
    "Cologne 2016 Challengers (Holo-Foil)": {"status": "discontinued", "year": 2016},

    # 2017 — Atlanta/Krakow perdem sponsor prefix no Steam Market
    "Atlanta 2017 Legends (Holo-Foil)": {"status": "discontinued", "year": 2017},
    "Atlanta 2017 Challengers (Holo-Foil)": {"status": "discontinued", "year": 2017},
    "Krakow 2017 Legends (Holo-Foil)": {"status": "discontinued", "year": 2017},
    "Krakow 2017 Challengers (Holo-Foil)": {"status": "discontinued", "year": 2017},

    # 2018 — sem sponsor prefix mas com sufixo (Holo-Foil)
    "Boston 2018 Legends (Holo-Foil)": {"status": "discontinued", "year": 2018},
    "Boston 2018 Returning Challengers (Holo-Foil)": {"status": "discontinued", "year": 2018},
    "Boston 2018 Minor Challengers (Holo-Foil)": {"status": "discontinued", "year": 2018},
    "London 2018 Legends (Holo-Foil)": {"status": "discontinued", "year": 2018},
    "London 2018 Returning Challengers (Holo-Foil)": {"status": "discontinued", "year": 2018},
    "London 2018 Minor Challengers (Holo-Foil)": {"status": "discontinued", "year": 2018},

    # 2019 — mesmo padrao do 2018
    "Katowice 2019 Legends (Holo-Foil)": {"status": "discontinued", "year": 2019},
    "Katowice 2019 Returning Challengers (Holo-Foil)": {"status": "discontinued", "year": 2019},
    "Katowice 2019 Minor Challengers (Holo-Foil)": {"status": "discontinued", "year": 2019},
    "Berlin 2019 Legends (Holo-Foil)": {"status": "discontinued", "year": 2019},
    "Berlin 2019 Returning Challengers (Holo-Foil)": {"status": "discontinued", "year": 2019},
    "Berlin 2019 Minor Challengers (Holo-Foil)": {"status": "discontinued", "year": 2019},

    # 2020 (RMR — sem Major presencial pela pandemia)
    "2020 RMR Legends": {"status": "discontinued", "year": 2020},
    "2020 RMR Challengers": {"status": "discontinued", "year": 2020},
    "2020 RMR Contenders": {"status": "discontinued", "year": 2020},

    # 2021+ — passou a usar "Sticker Capsule" no sufixo.
    # Champions Autograph Capsules foram movidas para _AUTOGRAPH_CAPSULES
    # (assinatura de jogadores, mercado diferente).
    "Stockholm 2021 Legends Sticker Capsule": {"status": "discontinued", "year": 2021},
    "Stockholm 2021 Challengers Sticker Capsule": {"status": "discontinued", "year": 2021},
    "Stockholm 2021 Contenders Sticker Capsule": {"status": "discontinued", "year": 2021},

    # 2022
    "Antwerp 2022 Legends Sticker Capsule": {"status": "discontinued", "year": 2022},
    "Antwerp 2022 Challengers Sticker Capsule": {"status": "discontinued", "year": 2022},
    "Antwerp 2022 Contenders Sticker Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Legends Sticker Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Challengers Sticker Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Contenders Sticker Capsule": {"status": "discontinued", "year": 2022},

    # 2023
    "Paris 2023 Legends Sticker Capsule": {"status": "discontinued", "year": 2023},
    "Paris 2023 Challengers Sticker Capsule": {"status": "discontinued", "year": 2023},
    "Paris 2023 Contenders Sticker Capsule": {"status": "discontinued", "year": 2023},

    # 2024
    "Copenhagen 2024 Legends Sticker Capsule": {"status": "discontinued", "year": 2024},
    "Copenhagen 2024 Challengers Sticker Capsule": {"status": "discontinued", "year": 2024},
    "Copenhagen 2024 Contenders Sticker Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Legends Sticker Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Challengers Sticker Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Contenders Sticker Capsule": {"status": "discontinued", "year": 2024},

    # 2025
    "Austin 2025 Legends Sticker Capsule": {"status": "discontinued", "year": 2025},
    "Austin 2025 Challengers Sticker Capsule": {"status": "discontinued", "year": 2025},
    "Austin 2025 Contenders Sticker Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Legends Sticker Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Challengers Sticker Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Contenders Sticker Capsule": {"status": "discontinued", "year": 2025},

    # === COMMUNITY / SPECIAL CAPSULES (nao vinculadas a um Major) ===
    "Sticker Capsule 2": {"status": "discontinued", "year": 2014},
    "CS20 Sticker Capsule": {"status": "discontinued", "year": 2019},
    "Perfect World Sticker Capsule 1": {"status": "discontinued", "year": 2020},
    "Perfect World Sticker Capsule 2": {"status": "discontinued", "year": 2020},
    "Ambush Sticker Capsule": {"status": "discontinued", "year": 2021},
    "Enfu Sticker Capsule": {"status": "discontinued", "year": 2021},
    "Espionage Sticker Capsule": {"status": "discontinued", "year": 2021},
    "10 Year Birthday Sticker Capsule": {"status": "discontinued", "year": 2023},
}

# === AUTOGRAPH CAPSULES (assinatura de jogadores, nao logos de times)
#
# Autograph Capsules contem stickers de assinatura de jogadores em vez de logos
# de times. Compartilham a tese de escassez estrutural (todas discontinued pos-
# Cologne 2026), mas o driver de demanda e' diferente (performance do player /
# nostalgia vs sticker de time).
#
# Cobertura: Krakow 2017+ (naming consistente moderno).
# Krakow 2017, Katowice 2019 e Berlin 2019 usam o formato moderno
# "{Event} {Tier} Autograph Capsule" — mesmo padrao pos-2021.
#
# Pre-2017 excluido: naming heterogeneo (~3 formatos diferentes),
# drivers atrelados a performance individual, muitos itens com liquidez baixa.
#
# Naming: "{Event} {Tier} Autograph Capsule" (mesmo padrao das Sticker Capsules)
_AUTOGRAPH_CAPSULES: dict[str, dict] = {
    # 2017 — Krakow teve 2 tiers (Challengers + Legends)
    "Krakow 2017 Challengers Autograph Capsule": {"status": "discontinued", "year": 2017},
    "Krakow 2017 Legends Autograph Capsule": {"status": "discontinued", "year": 2017},

    # 2019 — Katowice e Berlin so' tiveram Legends
    "Katowice 2019 Legends Autograph Capsule": {"status": "discontinued", "year": 2019},
    "Berlin 2019 Legends Autograph Capsule": {"status": "discontinued", "year": 2019},

    # 2021 — Stockholm teve 2 tiers (Champions + Finalists)
    "Stockholm 2021 Champions Autograph Capsule": {"status": "discontinued", "year": 2021},
    "Stockholm 2021 Finalists Autograph Capsule": {"status": "discontinued", "year": 2021},

    # 2022
    "Antwerp 2022 Champions Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Antwerp 2022 Legends Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Antwerp 2022 Challengers Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Antwerp 2022 Contenders Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Champions Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Legends Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Challengers Autograph Capsule": {"status": "discontinued", "year": 2022},
    "Rio 2022 Contenders Autograph Capsule": {"status": "discontinued", "year": 2022},

    # 2023
    "Paris 2023 Champions Autograph Capsule": {"status": "discontinued", "year": 2023},
    "Paris 2023 Legends Autograph Capsule": {"status": "discontinued", "year": 2023},
    "Paris 2023 Challengers Autograph Capsule": {"status": "discontinued", "year": 2023},
    "Paris 2023 Contenders Autograph Capsule": {"status": "discontinued", "year": 2023},

    # 2024
    "Copenhagen 2024 Champions Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Copenhagen 2024 Legends Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Copenhagen 2024 Challengers Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Copenhagen 2024 Contenders Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Champions Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Legends Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Challengers Autograph Capsule": {"status": "discontinued", "year": 2024},
    "Shanghai 2024 Contenders Autograph Capsule": {"status": "discontinued", "year": 2024},

    # 2025
    "Austin 2025 Champions Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Austin 2025 Legends Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Austin 2025 Challengers Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Austin 2025 Contenders Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Champions Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Legends Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Challengers Autograph Capsule": {"status": "discontinued", "year": 2025},
    "Budapest 2025 Contenders Autograph Capsule": {"status": "discontinued", "year": 2025},
}

# === PREMIUM STICKERS (tournament Holo/Glitter de todos os Majors 2014-2024)
#
# Stickers individuais de todos os 20 Majors. Diferente de capsulas (que sao
# containers), stickers sao items individuais no Steam Market. A tese de
# escassez estrutural se aplica: oferta fixa (capsulas foram descontinuadas),
# demanda organica por nostalgia e colecao.
#
# Perigo: stickers sao alvo de pump groups (M4A1 Nightmare pattern). A coluna
# Risco visual + pump_risk() ajudam a mitigar.
#
# Cobre Legends + Challengers + Contenders de cada Major (~386 stickers).
# Naming: "Sticker | {Team} ({Variant}) | {Event}"
# Variante Holo (2014-2019, 2024+) e Glitter (2021-2023).
# Gerado via _s() helper + for loop para consistencia.

def _s(team: str, variant: str, event: str, year: int, source: str) -> tuple[str, dict]:
    return (f"Sticker | {team} ({variant}) | {event}", {"year": year, "source": source})

_PREMIUM_STICKERS: dict[str, dict] = {}
for _k, _v in [
    # ===== 2014 MAJORS =====
    # --- EMS Katowice 2014 Legends (8 teams, Holo) ---
    _s("Titan", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("Natus Vincere", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("Fnatic", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("Ninjas in Pyjamas", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("compLexity Gaming", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("LGB eSports", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("Team Dignitas", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),
    _s("Team LDLC.com", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Legends"),

    # --- EMS Katowice 2014 Challengers (8 teams, Holo) ---
    _s("iBUYPOWER", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("Reason Gaming", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("HellRaisers", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("Virtus.Pro", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("3DMAX", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("Clan-Mystik", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("mousesports", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),
    _s("Vox Eminor", "Holo", "Katowice 2014", 2014, "EMS Katowice 2014 Challengers"),

    # --- ESL One Cologne 2014 Legends (8 teams, Holo) ---
    _s("Team Dignitas", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("Natus Vincere", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("Fnatic", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("Ninjas in Pyjamas", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("Cloud9", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("HellRaisers", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("Team LDLC.com", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),
    _s("Virtus.Pro", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Legends"),

    # --- ESL One Cologne 2014 Challengers (8 teams, Holo) ---
    _s("iBUYPOWER", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("Titan", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("compLexity Gaming", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("mousesports", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("London Conspiracy", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("Na`Vi", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("Epsilon eSports", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),
    _s("PENTA Sports", "Holo", "Cologne 2014", 2014, "ESL One Cologne 2014 Challengers"),

    # --- DreamHack 2014 Legends (6 teams, Holo-Foil, only 1 capsule) ---
    _s("Cloud9", "Holo", "DreamHack 2014", 2014, "DreamHack 2014 Legends (Holo-Foil)"),
    _s("Fnatic", "Holo", "DreamHack 2014", 2014, "DreamHack 2014 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "DreamHack 2014", 2014, "DreamHack 2014 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "DreamHack 2014", 2014, "DreamHack 2014 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "DreamHack 2014", 2014, "DreamHack 2014 Legends (Holo-Foil)"),
    _s("Team Dignitas", "Holo", "DreamHack 2014", 2014, "DreamHack 2014 Legends (Holo-Foil)"),

    # ===== 2015 MAJORS =====
    # --- ESL One Katowice 2015 Legends (8 teams, Holo-Foil) ---
    _s("Fnatic", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("Titan", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("Team Dignitas", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("HellRaisers", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),
    _s("LDLC.com", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Legends (Holo-Foil)"),

    # --- ESL One Katowice 2015 Challengers (8 teams, Holo-Foil) ---
    _s("Vox Eminor", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("Cloud9", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("Keyd Stars", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("PENTA Sports", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("Team SoloMid", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("Counter Logic Gaming", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),
    _s("3DMAX", "Holo", "Katowice 2015", 2015, "ESL One Katowice 2015 Challengers (Holo-Foil)"),

    # --- ESL One Cologne 2015 Legends (8 teams, Holo-Foil) ---
    _s("Fnatic", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("Team SoloMid", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("EnVyUs", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("Team Dignitas", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),
    _s("HellRaisers", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Legends (Holo-Foil)"),

    # --- ESL One Cologne 2015 Challengers (8 teams, Holo-Foil) ---
    _s("Cloud9", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("Luminosity Gaming", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("Titan", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("mousesports", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("Counter Logic Gaming", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("eBettle", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),
    _s("Renegades", "Holo", "Cologne 2015", 2015, "ESL One Cologne 2015 Challengers (Holo-Foil)"),

    # --- DreamHack Cluj-Napoca 2015 Legends (8 teams, Holo-Foil) ---
    _s("Fnatic", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("EnVyUs", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("Team SoloMid", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),
    _s("Cloud9", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Legends (Holo-Foil)"),

    # --- DreamHack Cluj-Napoca 2015 Challengers (8 teams, Holo-Foil) ---
    _s("Luminosity Gaming", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("Titan", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("mousesports", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("Dignitas", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("Counter Logic Gaming", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("Vexed Gaming", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),
    _s("Team YP", "Holo", "Cluj-Napoca 2015", 2015, "DreamHack Cluj-Napoca 2015 Challengers (Holo-Foil)"),

    # ===== 2016 MAJORS =====
    # --- MLG Columbus 2016 Legends (8 teams, Holo-Foil) ---
    _s("Fnatic", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("Luminosity Gaming", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("Astralis", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("EnVyUs", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Legends (Holo-Foil)"),

    # --- MLG Columbus 2016 Challengers (8 teams, Holo-Foil) ---
    _s("Cloud9", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("mousesports", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("Splyce", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),
    _s("Renegades", "Holo", "Columbus 2016", 2016, "MLG Columbus 2016 Challengers (Holo-Foil)"),

    # --- ESL One Cologne 2016 Legends (8 teams, Holo-Foil) ---
    _s("SK Gaming", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("Fnatic", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("Astralis", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Legends (Holo-Foil)"),

    # --- ESL One Cologne 2016 Challengers (8 teams, Holo-Foil) ---
    _s("mousesports", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("Cloud9", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("Team Dignitas", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("OpTic Gaming", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),
    _s("EnVyUs", "Holo", "Cologne 2016", 2016, "ESL One Cologne 2016 Challengers (Holo-Foil)"),

    # ===== 2017 MAJORS =====
    # --- ELEAGUE Atlanta 2017 Legends (8 teams, Holo-Foil) ---
    _s("Astralis", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("SK Gaming", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("Fnatic", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("EnVyUs", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Legends (Holo-Foil)"),

    # --- ELEAGUE Atlanta 2017 Challengers (8 teams, Holo-Foil) ---
    _s("FaZe Clan", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("Cloud9", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("OpTic Gaming", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("mousesports", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("HellRaisers", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Atlanta 2017", 2017, "ELEAGUE Atlanta 2017 Challengers (Holo-Foil)"),

    # --- PGL Krakow 2017 Legends (8 teams, Holo-Foil) ---
    _s("Gambit Gaming", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("Astralis", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("SK Gaming", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("Fnatic", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Legends (Holo-Foil)"),

    # --- PGL Krakow 2017 Challengers (8 teams, Holo-Foil) ---
    _s("Immortals", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("mousesports", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("Cloud9", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("PENTA Sports", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),
    _s("BIG", "Holo", "Krakow 2017", 2017, "PGL Krakow 2017 Challengers (Holo-Foil)"),

    # ===== 2018 MAJORS =====
    # --- ELEAGUE Boston 2018 Legends (8 teams, Holo-Foil) ---
    _s("Cloud9", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("SK Gaming", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("Astralis", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),
    _s("mousesports", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Legends (Holo-Foil)"),

    # --- ELEAGUE Boston 2018 Challengers (8 teams, Holo-Foil) ---
    _s("Team Liquid", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("Fnatic", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("Vega Squadron", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("BIG", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("Space Soldiers", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),
    _s("AVANGAR", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Challengers (Holo-Foil)"),

    # --- ELEAGUE Boston 2018 Contenders (8 teams, Holo-Foil) ---
    _s("Virtus.Pro", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("Cloud9", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("Renegades", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("EnVyUs", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("HellRaisers", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("FlipSid3 Tactics", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),
    _s("Sprout", "Holo", "Boston 2018", 2018, "ELEAGUE Boston 2018 Contenders (Holo-Foil)"),

    # --- FACEIT London 2018 Legends (8 teams, Holo-Foil) ---
    _s("Astralis", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("Team Liquid", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("mousesports", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("HellRaisers", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),
    _s("Fnatic", "Holo", "London 2018", 2018, "FACEIT London 2018 Legends (Holo-Foil)"),

    # --- FACEIT London 2018 Challengers (8 teams, Holo-Foil) ---
    _s("G2 Esports", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("Cloud9", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("BIG", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("Vega Squadron", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("Renegades", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),
    _s("TyLoo", "Holo", "London 2018", 2018, "FACEIT London 2018 Challengers (Holo-Foil)"),

    # --- FACEIT London 2018 Contenders (8 teams, Holo-Foil) ---
    _s("Space Soldiers", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("OpTic Gaming", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("compLexity Gaming", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("NRG Esports", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("Winstrike Team", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("AVANGAR", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("Rogue", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),
    _s("Team Spirit", "Holo", "London 2018", 2018, "FACEIT London 2018 Contenders (Holo-Foil)"),

    # ===== 2019 MAJORS =====
    # --- IEM Katowice 2019 Legends (8 teams, Holo-Foil) ---
    _s("Astralis", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("mousesports", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("HellRaisers", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),
    _s("BIG", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Legends (Holo-Foil)"),

    # --- IEM Katowice 2019 Challengers (8 teams, Holo-Foil) ---
    _s("Cloud9", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("ENCE", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("Renegades", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("Fnatic", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("Gambit Gaming", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("compLexity Gaming", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),
    _s("Vega Squadron", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Challengers (Holo-Foil)"),

    # --- IEM Katowice 2019 Contenders (8 teams, Holo-Foil) ---
    _s("AVANGAR", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("OpTic Gaming", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("Team Vitality", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("Tyloo", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("NRG Esports", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("Winstrike Team", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),
    _s("Grayhound Gaming", "Holo", "Katowice 2019", 2019, "IEM Katowice 2019 Contenders (Holo-Foil)"),

    # --- StarLadder Berlin 2019 Legends (8 teams, Holo-Foil) ---
    _s("Astralis", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("Team Vitality", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("ENCE", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("NRG Esports", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),
    _s("mousesports", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Legends (Holo-Foil)"),

    # --- StarLadder Berlin 2019 Challengers (8 teams, Holo-Foil) ---
    _s("G2 Esports", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("AVANGAR", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("HellRaisers", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("CR4ZY", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("Fnatic", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("Vitality", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),
    _s("Renegades", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Challengers (Holo-Foil)"),

    # --- StarLadder Berlin 2019 Contenders (8 teams, Holo-Foil) ---
    _s("BIG", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("North", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("compLexity Gaming", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("DreamEaters", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("TyLoo", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("Grayhound Gaming", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("Syman Gaming", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),
    _s("forZe", "Holo", "Berlin 2019", 2019, "StarLadder Berlin 2019 Contenders (Holo-Foil)"),

    # ===== 2021 MAJOR (Glitter era) =====
    # --- PGL Stockholm 2021 Legends (8 teams, Glitter) ---
    _s("Natus Vincere", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("G2 Esports", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("Gambit Gaming", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("Astralis", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),
    _s("Team Vitality", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Legends (Holo-Foil)"),

    # --- PGL Stockholm 2021 Challengers (8 teams, Glitter) ---
    _s("mousesports", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("Team Liquid", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("NIP", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("Fnatic", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("Copenhagen Flames", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("Heroic", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("BIG", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),
    _s("ENCE", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Challengers (Holo-Foil)"),

    # --- PGL Stockholm 2021 Contenders (8 teams, Glitter) ---
    _s("Entropiq", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("Evil Geniuses", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("Team Spirit", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("Renegades", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("paiN Gaming", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("Sharks Esports", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("Tyloo", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),
    _s("Godsent", "Glitter", "Stockholm 2021", 2021, "PGL Stockholm 2021 Contenders (Holo-Foil)"),

    # ===== 2022 MAJORS (Glitter era) =====
    # --- PGL Antwerp 2022 Legends (8 teams, Glitter) ---
    _s("FaZe Clan", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("Team Spirit", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("ENCE", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("G2 Esports", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("Heroic", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Legends (Holo-Foil)"),

    # --- PGL Antwerp 2022 Challengers (8 teams, Glitter) ---
    _s("Copenhagen Flames", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("Team Liquid", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("Fnatic", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("Astralis", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("BIG", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("Imperial Esports", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("Evil Geniuses", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),
    _s("Cloud9", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Challengers (Holo-Foil)"),

    # --- PGL Antwerp 2022 Contenders (8 teams, Glitter) ---
    _s("G2 Esports", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("Sangal Esports", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("Renegades", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("forZe", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("Eternal Fire", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("9z", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("TeamOne", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),
    _s("IHC Esports", "Glitter", "Antwerp 2022", 2022, "PGL Antwerp 2022 Contenders (Holo-Foil)"),

    # --- IEM Rio 2022 Legends (8 teams, Glitter) ---
    _s("FaZe Clan", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("Virtus.Pro", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("Cloud9", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("Heroic", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("Team Liquid", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("ENCE", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Legends (Holo-Foil)"),

    # --- IEM Rio 2022 Challengers (8 teams, Glitter) ---
    _s("Sprout", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("Fnatic", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("BIG", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("MOUZ", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("GamerLegion", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("9z", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("Evil Geniuses", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),
    _s("Grayhound Gaming", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Challengers (Holo-Foil)"),

    # --- IEM Rio 2022 Contenders (8 teams, Glitter) ---
    _s("Team Spirit", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("Imperial Esports", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("FURIA", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("00NATION", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("Bad News Eagles", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("G2 Esports", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("IHC Esports", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),
    _s("paiN Gaming", "Glitter", "Rio 2022", 2022, "IEM Rio 2022 Contenders (Holo-Foil)"),

    # ===== 2023 MAJOR (Glitter era) =====
    # --- BLAST Paris 2023 Legends (8 teams, Glitter) ---
    _s("Team Vitality", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("GamerLegion", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("Heroic", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("Monte", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("Team Liquid", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("Apeks", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("Ninjas in Pyjamas", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Legends (Holo-Foil)"),

    # --- BLAST Paris 2023 Challengers (8 teams, Glitter) ---
    _s("G2 Esports", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("Fnatic", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("Natus Vincere", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("Into the Breach", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("BIG", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("MOUZ", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("ENCE", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),
    _s("Grayhound Gaming", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Challengers (Holo-Foil)"),

    # --- BLAST Paris 2023 Contenders (8 teams, Glitter) ---
    _s("Cloud9", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("9z", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("FURIA", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("Fluxo", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("paiN Gaming", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("TheMongolZ", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("Complexity Gaming", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),
    _s("Team Spirit", "Glitter", "Paris 2023", 2023, "BLAST Paris 2023 Contenders (Holo-Foil)"),

    # ===== 2024 MAJORS (CS2, Holo era de volta) =====
    # --- PGL Copenhagen 2024 Legends (8 teams, Holo) ---
    _s("Natus Vincere", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("Team Vitality", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("Astralis", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("MOUZ", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("Spirit", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),
    _s("Cloud9", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Legends (Holo-Foil)"),

    # --- PGL Copenhagen 2024 Challengers (8 teams, Holo) ---
    _s("Heroic", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("Eternal Fire", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("Virtus.Pro", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("Complexity Gaming", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("FURIA", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("Imperial Esports", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("TheMongolZ", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),
    _s("ECSTATIC", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Challengers (Holo-Foil)"),

    # --- PGL Copenhagen 2024 Contenders (8 teams, Holo) ---
    _s("AMKAL ESPORTS", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("paiN Gaming", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("Sangal Esports", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("Lynn Vision", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("9z", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("SAW", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("Legacy", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),
    _s("Guild Eagles", "Holo", "Copenhagen 2024", 2024, "PGL Copenhagen 2024 Contenders (Holo-Foil)"),

    # --- Perfect World Shanghai 2024 Legends (8 teams, Holo) ---
    _s("Team Spirit", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("FaZe Clan", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("G2 Esports", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("Natus Vincere", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("Team Vitality", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("MOUZ", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("Heroic", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),
    _s("Team Liquid", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Legends (Holo-Foil)"),

    # --- Perfect World Shanghai 2024 Challengers (8 teams, Holo) ---
    _s("Virtus.Pro", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("Cloud9", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("3DMAX", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("FURIA", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("TheMongolZ", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("paiN Gaming", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("Complexity Gaming", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),
    _s("BIG", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Challengers (Holo-Foil)"),

    # --- Perfect World Shanghai 2024 Contenders (8 teams, Holo) ---
    _s("FlyQuest", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("GamerLegion", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("Imperial Esports", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("Rare Atom", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("MIBR", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("Alter Ego", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("Passion UA", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
    _s("Team Falcons", "Holo", "Shanghai 2024", 2024, "Perfect World Shanghai 2024 Contenders (Holo-Foil)"),
]:
    _PREMIUM_STICKERS[_k] = _v

_ALL_STICKERS: dict[str, dict] = dict(_get_stickers())
# Merge premium stickers not in API data (naming differences between events)
for _k, _v in _PREMIUM_STICKERS.items():
    if _k not in _ALL_STICKERS:
        _ALL_STICKERS[_k] = _v


def list_all_stickers() -> list[str]:
    """Retorna TODOS os stickers individuais conhecidos (9892).

    Fonte primaria: ByMykel/CSGO-API (dados oficiais do schema do jogo).
    Inclui tournament (Team), autograph, community e event stickers.
    + Premium stickers com nomes nao encontrados na API.
    """
    return list(_ALL_STICKERS.keys())


def list_stickers_by_category(category: str) -> list[str]:
    """Retorna stickers de uma categoria especifica.

    Categorias: 'Team' (1743), 'Autograph' (7075), 'Community' (850), 'Event' (72).
    Premium extras sao tratados como 'Team' (origem mais comum).
    """
    return sorted(
        k for k, v in _ALL_STICKERS.items()
        if v.get("category", "Team") == category
    )


def list_tournament_stickers() -> list[str]:
    """Stickers de time/torneio (Team). 1743 itens."""
    return list_stickers_by_category("Team")


def list_autograph_stickers() -> list[str]:
    """Stickers de autografo de jogador (Autograph). 7075 itens."""
    return list_stickers_by_category("Autograph")


def list_community_stickers() -> list[str]:
    """Stickers tematicos/comunitarios/operacao (Community). 850 itens."""
    return list_stickers_by_category("Community")


def list_event_stickers() -> list[str]:
    """Stickers de logo de evento (Event). 72 itens."""
    return list_stickers_by_category("Event")


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
    "AK-47 | Redline": "Operation Phoenix Weapon Case",
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

    # Fever (2025)
    "AK-47 | Searing Rage": "Fever Case",

    # === COLECOES ===
    "AWP | Dragon Lore": "The Cobblestone Collection",
    "M4A4 | Howl": "Huntsman Weapon Case",
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


# Colecao (tag ItemSet da Steam) -> caixa que a contem.
#
# Inverte o custo de manutencao: _SKIN_TO_CASE cresce a cada skin lancada
# (centenas), enquanto colecao->caixa cresce so' quando sai caixa nova
# (dezenas). A colecao vem de graca na description da listing page, entao
# nao custa requisicao.
#
# As entradas abaixo sao por correspondencia direta de nome. O modo de
# falha e' benigno: nome que nao bate simplesmente nao acha, e o item cai
# em status="collection" com o nome da colecao -- que ainda e' melhor que
# "unknown". NAO invente entrada sem confirmar o nome exato da colecao.
_COLLECTION_TO_CASE: dict[str, str] = {
    "The Arms Deal Collection": "CS:GO Weapon Case",
    "The Arms Deal 2 Collection": "CS:GO Weapon Case 2",
    "The Arms Deal 3 Collection": "CS:GO Weapon Case 3",
    "The Bravo Collection": "Operation Bravo Case",
    "The Phoenix Collection": "Operation Phoenix Weapon Case",
    "The Winter Offensive Collection": "Winter Offensive Weapon Case",
    "The Breakout Collection": "Operation Breakout Weapon Case",
    "The Huntsman Collection": "Huntsman Weapon Case",
    "The Vanguard Collection": "Operation Vanguard Weapon Case",
    "The Chroma Collection": "Chroma Case",
    "The Chroma 2 Collection": "Chroma 2 Case",
    "The Chroma 3 Collection": "Chroma 3 Case",
    "The Falchion Collection": "Falchion Case",
    "The Shadow Collection": "Shadow Case",
    "The Revolver Case Collection": "Revolver Case",
    "The Wildfire Collection": "Operation Wildfire Case",
    "The Gamma Collection": "Gamma Case",
    "The Gamma 2 Collection": "Gamma 2 Case",
    "The Glove Collection": "Glove Case",
    "The Spectrum Collection": "Spectrum Case",
    "The Spectrum 2 Collection": "Spectrum 2 Case",
    "The Hydra Collection": "Operation Hydra Case",
    "The Clutch Collection": "Clutch Case",
    "The Horizon Collection": "Horizon Case",
    "The Danger Zone Collection": "Danger Zone Case",
    "The Prisma Collection": "Prisma Case",
    "The CS20 Collection": "CS20 Case",
    "The Shattered Web Collection": "Shattered Web Case",
    "The Prisma 2 Collection": "Prisma 2 Case",
    "The Fracture Collection": "Fracture Case",
    "The Broken Fang Collection": "Operation Broken Fang Case",
    "The Snakebite Collection": "Snakebite Case",
    "The Operation Riptide Collection": "Operation Riptide Case",
    "The Dreams & Nightmares Collection": "Dreams & Nightmares Case",
    "The Recoil Collection": "Recoil Case",
    "The Revolution Collection": "Revolution Case",
    "The Kilowatt Collection": "Kilowatt Case",
    "The Gallery Collection": "Gallery Case",
    "The Fever Collection": "Fever Case",
}


def case_from_collection(collection: str | None) -> str | None:
    """Caixa que contem a colecao, ou None. Aceita nome ja' normalizado."""
    if not collection:
        return None
    return _COLLECTION_TO_CASE.get(collection.strip())


def case_status(name: str, collection: str | None = None) -> dict:
    """Retorna informacoes de caixa/colecao/capsula para o item.

    Output:
    {
      "case": str | None,           # nome da caixa/colecao/capsula
      "status": str,                # active | discontinued | rare | collection | unknown
      "is_discontinued": bool,
      "is_rare": bool,
      "year": int | None,
      "label": str,                 # texto curto pra UI
    }

    Aceita 4 tipos de input:
    1. Nome de skin (ex: "AK-47 | Redline (Field-Tested)") -> mapeia via _SKIN_TO_CASE
    2. Nome direto de caixa (ex: "Chroma 2 Case") -> lookup em _CASES
    3. Nome direto de sticker capsula (ex: "Stockholm 2021 Legends Sticker Capsule")
       -> lookup em _CAPSULES
    4. Nome direto de autograph capsula (ex: "Antwerp 2022 Champions Autograph Capsule")
       -> lookup em _AUTOGRAPH_CAPSULES
    """
    skin = _normalize_skin_name(name)

    # (2) Match direto em _CASES (input e' o nome de uma caixa)
    if skin in _CASES:
        return _container_status_dict(skin, _CASES[skin])

    # (3) Match direto em _CAPSULES (input e' o nome de uma sticker capsula)
    if skin in _CAPSULES:
        return _container_status_dict(skin, _CAPSULES[skin])

    # (4) Match direto em _AUTOGRAPH_CAPSULES (input e' o nome de uma autograph capsula)
    if skin in _AUTOGRAPH_CAPSULES:
        return _container_status_dict(skin, _AUTOGRAPH_CAPSULES[skin])

    # (1) Match skin -> case via _SKIN_TO_CASE
    case_name = _SKIN_TO_CASE.get(skin)

    # Match parcial: skin name pode ser substring (gloves variants etc)
    if not case_name:
        for key, val in _SKIN_TO_CASE.items():
            if key.lower() in skin.lower():
                case_name = val
                break

    # (5) Colecao vinda da Steam (tag ItemSet). Entra DEPOIS do mapa manual
    # pra nao mudar resultado de item ja' mapeado -- e' fonte adicional,
    # nao substituta.
    if not case_name:
        case_name = case_from_collection(collection)

    if not case_name:
        # Sem caixa, mas com colecao conhecida: melhor que "unknown", e e'
        # o que a Steam de fato afirma sobre o item.
        if collection:
            return {
                "case": collection.strip(),
                "status": "collection",
                "is_discontinued": False,
                "is_rare": False,
                "year": None,
                "label": collection.strip(),
            }
        return {
            "case": None,
            "status": "unknown",
            "is_discontinued": False,
            "is_rare": False,
            "year": None,
            "label": "",
        }

    meta = _CASES.get(case_name, {})
    return _container_status_dict(case_name, meta)


def _container_status_dict(container_name: str, meta: dict) -> dict:
    """Constroi o dict de retorno de case_status a partir do meta do container."""
    status = meta.get("status", "unknown")
    year = meta.get("year")

    is_disc = status == "discontinued"
    is_rare = status == "rare"

    if status == "discontinued":
        label = f"{container_name} (descontinuada"
        if year:
            label += f", {year}"
        label += ")"
    elif status == "active":
        label = f"{container_name} (ativa)"
    else:
        label = f"{container_name}"

    return {
        "case": container_name,
        "status": status,
        "is_discontinued": is_disc,
        "is_rare": is_rare,
        "year": year,
        "label": label,
    }


def list_cases_by_status(status: str) -> list[str]:
    """Lista nomes de cases por status."""
    return [name for name, meta in _CASES.items() if meta.get("status") == status]


def list_capsules() -> list[str]:
    """Lista todas as capsulas catalogadas.

    Apos IEM Cologne 2026 (22/05/2026), todas as capsulas legacy viraram
    supply-fixa permanente. Usada como categoria 'Cápsulas' no Scanner.
    """
    return list(_CAPSULES.keys())


def list_autograph_capsules() -> list[str]:
    """Lista todas as Autograph Capsules catalogadas (2021+).

    Assinaturas de jogadores em vez de logos de times. Mesma tese de
    escassez estrutural das Sticker Capsules pos-Cologne 2026.
    """
    return list(_AUTOGRAPH_CAPSULES.keys())


def list_premium_stickers() -> list[str]:
    """Lista stickers premium curados (Holo/Glitter de Majors 2014-2024).

    Stickers individuais sao items de score puramente baseado em price_history
    e signals (nao tem case_status como containers). A coluna Risco visual
    ajuda a mitigar pump groups.

    ~386 stickers de todos os 20 Majors 2014-2024:
    - Variante Holo para 2014-2019 e 2024+
    - Variante Glitter para 2021-2023 (Valorant-style)
    - Legends + Challengers + Contenders por Major
    """
    return list(_PREMIUM_STICKERS.keys())


_CONTAINER_SUFFIXES = (
    " Case", " Capsule", " Package", " Pin", " Music Kit",
    " Sticker Capsule", " Patch Pack",
)


def is_container(name: str) -> bool:
    """Retorna True se o item e' um container (caixa, capsula, package).

    Cases respondem a sinais diferentes de skins (oferta finita vs
    geracao continua de drops). Usar essa flag pra ajustar score.

    Reconhece: nome em _CASES, nome em _CAPSULES (capsulas vintage
    pre-2020 nao terminam com 'Capsule' — terminam com 'Legends',
    'Challengers', '(Holo-Foil)' etc), nome em _AUTOGRAPH_CAPSULES,
    ou sufixos conhecidos.
    """
    if not name:
        return False
    if name in _CASES:
        return True
    if name in _CAPSULES:
        return True
    if name in _AUTOGRAPH_CAPSULES:
        return True
    return name.endswith(_CONTAINER_SUFFIXES)
