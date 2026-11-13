"""Localizacao de nomes de skins/itens do CS2 para pt-BR.

Steam Community Market API sempre retorna `market_hash_name` em ingles
(contrato fixo da API). Pra exibir bonito no UI, aplicamos
transformacoes rule-based aqui — sem mexer nos dados persistidos
ou no que e enviado pra Steam.

Regras:
- Wear conditions (Field-Tested -> Testada em Campo etc.)
- Prefixos de tipo (Sticker | -> Adesivo |, Music Kit | -> ...)
- Sufixo de caixa ("X Case" -> "Caixa X")
- Caixas populares tem traducao curada em _CASE_NAMES

Nomes proprios (armas: AK-47, AWP; skins: Redline, Asiimov;
eventos: Berlin 2019; jogadores: chelo) nao sao traduzidos.
"""
from __future__ import annotations

import re


# ── Wear conditions (vem no final do nome) ────────────────────
_WEARS = [
    ("(Factory New)", "(Nova de Fábrica)"),
    ("(Minimal Wear)", "(Pouco Usada)"),
    ("(Field-Tested)", "(Testada em Campo)"),
    ("(Well-Worn)", "(Bastante Usada)"),
    ("(Battle-Scarred)", "(Veterana de Guerra)"),
]


# ── Prefixos de tipo ──────────────────────────────────────────
# Ordem importa: prefixos mais especificos primeiro.
_PREFIXES = [
    ("Sealed Graffiti | ", "Grafite Selado | "),
    ("Sticker | ", "Adesivo | "),
    ("Music Kit | ", "Pacote de Música | "),
    ("Graffiti | ", "Grafite | "),
    ("Patch | ", "Remendo | "),
]


# ── Caixas com traducao oficial Steam BR ──────────────────────
_CASE_NAMES = {
    "Dreams & Nightmares Case": "Caixa Sonhos e Pesadelos",
    "Fracture Case": "Caixa Fratura",
    "Kilowatt Case": "Caixa Kilowatt",
    "Revolution Case": "Caixa Revolução",
    "Snakebite Case": "Caixa Picada de Cobra",
    "Recoil Case": "Caixa Recuo",
    "Prisma Case": "Caixa Prisma",
    "Prisma 2 Case": "Caixa Prisma 2",
    "Danger Zone Case": "Caixa Zona de Perigo",
    "Horizon Case": "Caixa Horizonte",
    "Spectrum Case": "Caixa Espectro",
    "Spectrum 2 Case": "Caixa Espectro 2",
    "Glove Case": "Caixa de Luvas",
    "Gamma Case": "Caixa Gama",
    "Gamma 2 Case": "Caixa Gama 2",
    "Chroma Case": "Caixa Croma",
    "Chroma 2 Case": "Caixa Croma 2",
    "Chroma 3 Case": "Caixa Croma 3",
    "Shadow Case": "Caixa Sombra",
    "Falchion Case": "Caixa Cimitarra",
    "Shattered Web Case": "Caixa Teia Despedaçada",
    "CS20 Case": "Caixa CS20",
    "Clutch Case": "Caixa Decisiva",
    "Hydra Case": "Caixa Hidra",
    "Phoenix Weapon Case": "Caixa Fênix",
    "Operation Bravo Case": "Caixa da Operação Bravo",
    "Operation Phoenix Weapon Case": "Caixa Fênix da Operação",
    "Operation Vanguard Weapon Case": "Caixa Vanguarda da Operação",
    "Operation Wildfire Case": "Caixa Operação Fogo Selvagem",
    "Operation Hydra Case": "Caixa Operação Hidra",
    "Operation Broken Fang Case": "Caixa Operação Presa Quebrada",
    "Operation Riptide Case": "Caixa Operação Maré Vermelha",
    "Sealed Dead Hand Terminal": "Pacote Lacrado Terminal da Mão Morta",
    "Yellow Is": "Sim Amarelo",  # graffiti
}


_CASE_SUFFIX_RE = re.compile(r" Case$")


def _localize_wear(s: str) -> str:
    for en, pt in _WEARS:
        if s.endswith(en):
            return s[: -len(en)].rstrip() + " " + pt
    return s


def _localize_prefix(s: str) -> str:
    for en, pt in _PREFIXES:
        if s.startswith(en):
            return pt + s[len(en):]
    return s


def localize_name(name: str) -> str:
    """Aplica localizacao pt-BR ao market_hash_name pra exibicao.

    Nao muda o nome original; apenas retorna uma string nova para o UI.
    """
    if not name:
        return ""

    # Caixa com nome curado tem precedencia (match exato)
    if name in _CASE_NAMES:
        return _CASE_NAMES[name]

    s = _localize_wear(name)
    s = _localize_prefix(s)

    # Caixa generica: "X Case" -> "Caixa X" (so se nao casou wear nem prefix)
    if s == name and _CASE_SUFFIX_RE.search(s):
        s = "Caixa " + _CASE_SUFFIX_RE.sub("", s)

    return s
