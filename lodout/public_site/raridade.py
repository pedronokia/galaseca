"""Raridade da skin (cor da borda no ícone) + ícone/URL a partir de um
candidato bruto do scan.

Fatorado de server.py em 2026-11-07 pra uso também fora das rotas
principais (watchlist, trades) -- `_candidatos_filtrados` já calcula
isso pra home/ranking/comparar/item, mas watchlist/trades não passam
por ali (item persistido por usuário, não candidato do scan), então
cruzam pelo nome com o scan atual usando `icone_raridade`.
"""
from __future__ import annotations

from flask import url_for

# Cor de raridade da skin (linguagem visual nativa do CS2) -- achado
# 2026-11-06: a Steam já entrega `name_color` (hex) e `rarity_id` (enum
# estável). O CSP do site (`style-src 'self'`, sem inline) impede usar a
# cor direto no HTML, então mapeia pra classes fixas em style.css.
#
# CORREÇÃO 2026-11-07: a suposição original de que `name_color` dava
# dourado em facas/luvas/contraband era errada -- checado com uma
# requisição real (lodout.steam_api.get_market_page_data) numa Karambit
# e numas Sport Gloves de verdade: as duas vêm com name_color "eb4b4b" e
# rarity_id "Rarity_Ancient_Weapon"/"Rarity_Ancient" -- EXATAMENTE os
# mesmos valores de uma skin Covert comum. O dourado real do jogo vem da
# `quality_id` ("unusual", o prefixo ★), um campo separado que não tinha
# chegado até aqui -- sem a correção abaixo, toda faca/luva do site saía
# com borda vermelha (Covert) em vez de dourada. Contraband (ex. Howl)
# continua mapeado por via das dúvidas, mas não foi possível confirmar
# com um item real (a listing testada não trazia esse sinal).
_RARIDADE_POR_COR = {
    "b0c3d9": "consumer",
    "5e98d9": "industrial",
    "4b69ff": "milspec",
    "8847ff": "restricted",
    "d32ce6": "classified",
    "eb4b4b": "covert",
    "e4ae39": "dourado",
    "caad74": "dourado",
}
_RARIDADE_POR_ID = {
    "Rarity_Common_Weapon": "consumer",
    "Rarity_Uncommon_Weapon": "industrial",
    "Rarity_Rare_Weapon": "milspec",
    "Rarity_Mythical_Weapon": "restricted",
    "Rarity_Legendary_Weapon": "classified",
    "Rarity_Ancient_Weapon": "covert",
    "Rarity_Contraband": "dourado",
}

# Rótulo da borda de raridade pro atributo `title` (achado 2026-11-07: a
# borda colorida não tinha nenhuma explicação na tela -- quem não manja
# das cores oficiais do CS2 via só uma borda sem significado. O termo em
# inglês é o mesmo usado no jogo e no glossário do site (ver #termo-
# raridade em glossario.html); a cor em português do lado ajuda sem
# precisar decorar o nome em inglês.
_RARIDADE_LABELS = {
    "consumer": "Consumer Grade (cinza)",
    "industrial": "Industrial Grade (azul claro)",
    "milspec": "Mil-Spec (azul)",
    "restricted": "Restricted (roxo)",
    "classified": "Classified (rosa)",
    "covert": "Covert (vermelho)",
    "dourado": "Item especial -- faca, luva ou contrabando (dourado)",
}


def raridade_suffix(item: dict) -> str:
    # Checa ANTES do mapa de cor/raridade comum -- facas e luvas têm
    # name_color/rarity_id iguais aos de uma skin Covert, só a
    # quality_id ("unusual") distingue (ver comentário acima do mapa).
    if item.get("quality_id") == "unusual":
        return "dourado"
    nome_cor = (item.get("name_color") or "").strip().lower()
    if nome_cor in _RARIDADE_POR_COR:
        return _RARIDADE_POR_COR[nome_cor]
    rid = item.get("rarity_id")
    if rid in _RARIDADE_POR_ID:
        return _RARIDADE_POR_ID[rid]
    return ""


def raridade_classe(item: dict) -> str:
    suf = raridade_suffix(item)
    return "raridade-" + suf if suf else ""


def raridade_titulo(item: dict) -> str:
    suf = raridade_suffix(item)
    return "Raridade: " + _RARIDADE_LABELS[suf] if suf else ""


def legenda_raridade() -> list:
    """As 7 raridades, na ordem (cinza -> dourado), pro popover de legenda
    perto da tabela -- lê de `_RARIDADE_LABELS` em vez de duplicar a
    lista à mão num template, pra nunca dessincronizar do mapeamento
    real usado nos ícones."""
    return [{"classe": "raridade-" + suf, "titulo": label}
            for suf, label in _RARIDADE_LABELS.items()]


def icone_raridade(raw: "dict | None") -> dict:
    """icon_url (2x incluso) + classe/título de raridade a partir de um
    candidato bruto do scan (campos `icon`/`name_color`/`rarity_id`).

    `raw=None` (item fora do scan atual, ou ainda não há scan) cai no
    mesmo "sem imagem"/sem borda que index.html já trata -- não quebra
    a página de quem chama.
    """
    raw = raw or {}
    icon = raw.get("icon")
    icon_url = url_for("icone_cache", hash_icone=icon, v=2) if icon else None
    # 384px (2x de 192) pro srcset "2x" -- mesma correção de server.py
    # _candidatos_filtrados (2026-11-08): icon_url_2x não pode ser cópia
    # do icon_url de 192px, senão o srcset nunca entrega imagem mais nítida.
    icon_url_2x = (
        url_for("icone_cache", hash_icone=icon, v=2, tam=384)
        if icon else None)
    return {
        "icon_url": icon_url,
        "icon_url_2x": icon_url_2x,
        "raridade_classe": raridade_classe(raw),
        "raridade_titulo": raridade_titulo(raw),
    }
