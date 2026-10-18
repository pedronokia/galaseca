"""Lista fixa de itens do Scanner, por categoria.

Extraido de `ui/scanner_screen.py` (Fase 11 da migracao web) pra nao
duplicar ~85 nomes escritos a mao entre a UI Qt e a UI web -- as duas
importam esta mesma lista. Hoje e' o FALLBACK: `discovery.py` resolve
por faceta quando a descoberta esta' ligada (`settings.scanner_discovery`),
caindo aqui em qualquer falha.
"""
from __future__ import annotations

from skinvault import cases

SCAN_BY_CATEGORY = {
    "Rifles": [
        "AK-47 | Redline (Field-Tested)", "AK-47 | Bloodsport (Field-Tested)",
        "AK-47 | Neon Rider (Field-Tested)", "AK-47 | The Empress (Field-Tested)",
        "AK-47 | Phantom Disruptor (Field-Tested)", "AK-47 | Rat Rod (Field-Tested)",
        "AK-47 | Safari Mesh (Battle-Scarred)", "M4A4 | Howl (Field-Tested)",
        "M4A4 | Asiimov (Field-Tested)", "M4A4 | Dragon King (Minimal Wear)",
        "M4A4 | Neo-Noir (Field-Tested)", "M4A4 | Desolate Space (Field-Tested)",
        "M4A1-S | Master Piece (Field-Tested)", "M4A1-S | Mecha Industries (Field-Tested)",
        "M4A1-S | Decimator (Field-Tested)", "M4A1-S | Golden Coil (Field-Tested)",
        "AWP | Asiimov (Field-Tested)", "AWP | Hyper Beast (Field-Tested)",
        "AWP | Mortis (Field-Tested)", "AWP | Wildfire (Field-Tested)",
    ],
    "Pistolas": [
        "Desert Eagle | Blaze (Factory New)", "Desert Eagle | Code Red (Factory New)",
        "Desert Eagle | Printstream (Factory New)", "Desert Eagle | Hand Cannon (Field-Tested)",
        "USP-S | Kill Confirmed (Field-Tested)", "USP-S | Neo-Noir (Factory New)",
        "Glock-18 | Water Elemental (Minimal Wear)", "Glock-18 | Wasteland Rebel (Field-Tested)",
        "Glock-18 | Neo-Noir (Field-Tested)",
    ],
    "Facas": [
        "Bayonet | Doppler (Factory New)", "Bayonet | Marble Fade (Factory New)",
        "Bayonet | Tiger Tooth (Factory New)", "Bayonet | Rust Coat (Battle-Scarred)",
        "Butterfly Knife | Fade (Factory New)", "Butterfly Knife | Slaughter (Minimal Wear)",
        "Karambit | Doppler (Factory New)", "Karambit | Tiger Tooth (Factory New)",
        "Karambit | Fade (Factory New)", "Flip Knife | Doppler (Factory New)",
        "Flip Knife | Marble Fade (Factory New)",
        "M9 Bayonet | Doppler (Factory New)", "M9 Bayonet | Tiger Tooth (Factory New)",
        "M9 Bayonet | Fade (Factory New)", "Talon Knife | Doppler (Factory New)",
        "Stiletto Knife | Doppler (Factory New)",
    ],
    "Luvas": [
        "Hand Wraps | Cobalt Skull (Field-Tested)",
        "Hand Wraps | Leather (Minimal Wear)", "Hand Wraps | Slaughter (Factory New)",
        "Moto Gloves | Spearmint (Field-Tested)",
        "Moto Gloves | Boom! (Field-Tested)",
        "Bloodhound Gloves | Bronzed (Field-Tested)",
        "Bloodhound Gloves | Charred (Battle-Scarred)",
        "Sport Gloves | Pandora's Box (Field-Tested)",
        "Sport Gloves | Big Game (Field-Tested)",
        "Driver Gloves | Lunar Weave (Field-Tested)",
        "Driver Gloves | King Snake (Factory New)",
        "Specialist Gloves | Mogul (Factory New)",
    ],
    "SMGs": [
        "MAC-10 | Neon Rider (Battle-Scarred)", "MP9 | Rose Iron (Factory New)",
        "P90 | Death by Kitty (Minimal Wear)", "PP-Bizon | Osiris (Factory New)",
        "UMP-45 | Minotaur's Labyrinth (Field-Tested)",
        "MP7 | Neon Ply (Factory New)",
    ],
    "Caixas": [
        "CS:GO Weapon Case", "CS:GO Weapon Case 2", "CS:GO Weapon Case 3",
        "Operation Bravo Case", "Winter Offensive Weapon Case",
        "Operation Phoenix Weapon Case",
        "Chroma 2 Case", "Chroma 3 Case",
        "Spectrum Case", "Spectrum 2 Case",
        "Glove Case", "Clutch Case",
        "Prisma Case", "Prisma 2 Case",
        "Fracture Case", "Snakebite Case",
        "Dreams & Nightmares Case", "Recoil Case",
        "Revolution Case", "Kilowatt Case",
        "Gallery Case", "Fever Case",
    ],
    "Cápsulas": cases.list_capsules(),
    "Cápsulas de autógrafo": cases.list_autograph_capsules(),
    "Adesivos de torneio": cases.list_tournament_stickers(),
    "Adesivos de autógrafo": cases.list_autograph_stickers(),
    "Adesivos da comunidade": cases.list_community_stickers(),
    "Adesivos de evento": cases.list_event_stickers(),
}
