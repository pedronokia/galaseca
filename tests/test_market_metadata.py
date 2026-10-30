"""Metadados oficiais da Steam: tags, commodity, bloqueio de 7 dias."""
from __future__ import annotations

from galaseca import cases, steam_api


# Payload real, colhido da listing page da AK-47 | Redline (Field-Tested)
# em 2026-07-28.
DESC_REDLINE = {
    "type": "Classified Rifle",
    "commodity": False,
    "name_color": "d32ce6",
    "market_tradable_restriction": 7,
    "market_marketable_restriction": 7,
    "tags": [
        {"category": "Type", "internal_name": "CSGO_Type_Rifle",
         "localized_tag_name": "Rifle"},
        {"category": "Weapon", "internal_name": "weapon_ak47",
         "localized_tag_name": "AK-47"},
        {"category": "ItemSet", "internal_name": "set_community_2",
         "localized_tag_name": "The Phoenix Collection"},
        {"category": "Quality", "internal_name": "normal",
         "localized_tag_name": "Normal"},
        {"category": "Rarity", "internal_name": "Rarity_Legendary_Weapon",
         "localized_tag_name": "Classified"},
        {"category": "Exterior", "internal_name": "WearCategory2",
         "localized_tag_name": "Field-Tested"},
    ],
}


# ── _parse_item_meta ───────────────────────────────────────────────


def test_parse_item_meta_extrai_tags():
    m = steam_api._parse_item_meta(DESC_REDLINE)
    assert m["collection"] == "The Phoenix Collection"
    assert m["collection_id"] == "set_community_2"
    assert m["rarity"] == "Classified"
    assert m["rarity_id"] == "Rarity_Legendary_Weapon"
    assert m["exterior"] == "Field-Tested"
    assert m["weapon"] == "AK-47"
    assert m["item_type"] == "Rifle"


def test_parse_item_meta_type_label_nao_colide_com_tag_type():
    """`type` da description e a tag Type sao coisas diferentes."""
    m = steam_api._parse_item_meta(DESC_REDLINE)
    assert m["type_label"] == "Classified Rifle"
    assert m["item_type"] == "Rifle"


def test_parse_item_meta_commodity_e_bloqueio():
    m = steam_api._parse_item_meta(DESC_REDLINE)
    assert m["commodity"] is False           # skin: cada anuncio e' unico
    assert m["tradable_restriction"] == 7
    assert m["marketable_restriction"] == 7


def test_parse_item_meta_container_e_commodity():
    """Verificado em 2026-07-28: Kilowatt Case vem commodity=true."""
    m = steam_api._parse_item_meta(
        {"type": "Base Grade Container", "commodity": True,
         "market_tradable_restriction": 7, "tags": []})
    assert m["commodity"] is True


def test_parse_item_meta_tolera_lixo():
    assert steam_api._parse_item_meta(None) == {}
    assert steam_api._parse_item_meta("x") == {}
    m = steam_api._parse_item_meta({"tags": [None, "x", {"category": "Zzz"}]})
    assert m["commodity"] is False
    assert "collection" not in m


def test_parse_item_meta_restricao_invalida_vira_none():
    m = steam_api._parse_item_meta({"market_tradable_restriction": "sete"})
    assert m["tradable_restriction"] is None


def test_collect_item_meta_indexa_por_nome():
    queries = [
        {"queryKey": ["market", "description", 730, "AK-47 | Redline (FT)"],
         "state": {"data": DESC_REDLINE}},
        {"queryKey": ["market", "pricehistory", 730, "AK-47 | Redline (FT)"],
         "state": {"data": {"prices": [1]}}},
        {"queryKey": ["market", "description"], "state": {"data": {}}},
    ]
    meta = steam_api._collect_item_meta(queries)
    assert list(meta) == ["AK-47 | Redline (FT)"]
    assert meta["AK-47 | Redline (FT)"]["rarity"] == "Classified"


# ── bloqueio de 7 dias no veredito ─────────────────────────────────


def test_verdict_sem_restricao_nao_muda():
    v = steam_api.fair_value_verdict(90.0, 100.0)
    assert "hold_days" not in v
    assert "bloqueio" not in v["message"]


def test_verdict_reporta_hold_days():
    v = steam_api.fair_value_verdict(90.0, 100.0, tradable_restriction=7)
    assert v["hold_days"] == 7
    assert "7 dias" in v["message"]


def test_verdict_hold_nao_altera_o_veredito():
    """E' fato reportado, nao ajuste de score -- o veredito e' o mesmo."""
    base = steam_api.fair_value_verdict(90.0, 100.0)
    com = steam_api.fair_value_verdict(90.0, 100.0, tradable_restriction=7)
    assert base["verdict"] == com["verdict"]
    assert base["diff_pct"] == com["diff_pct"]


def test_verdict_restricao_zero_ou_invalida_e_ignorada():
    for valor in (0, None, "abc"):
        v = steam_api.fair_value_verdict(90.0, 100.0,
                                         tradable_restriction=valor)
        assert "hold_days" not in v


# ── colecao -> caixa ───────────────────────────────────────────────


def test_case_from_collection():
    assert cases.case_from_collection("The Phoenix Collection") == \
        "Operation Phoenix Weapon Case"
    assert cases.case_from_collection("  The Kilowatt Collection  ") == \
        "Kilowatt Case"
    assert cases.case_from_collection("Colecao Inexistente") is None
    assert cases.case_from_collection(None) is None


def test_case_status_usa_colecao_quando_o_mapa_manual_falha():
    desconhecida = "Arma Inventada | Pintura Falsa (Factory New)"
    sem = cases.case_status(desconhecida)
    assert sem["status"] == "unknown"

    com = cases.case_status(desconhecida,
                            collection="The Kilowatt Collection")
    assert com["case"] == "Kilowatt Case"
    assert com["status"] != "unknown"


def test_case_status_colecao_sem_caixa_vira_status_collection():
    """Colecao conhecida pela Steam mas sem caixa mapeada ainda informa."""
    r = cases.case_status("Arma Inventada | X (Factory New)",
                          collection="The Colecao Nova Collection")
    assert r["status"] == "collection"
    assert r["case"] == "The Colecao Nova Collection"
    assert r["label"] == "The Colecao Nova Collection"


def test_case_status_mapa_manual_tem_precedencia():
    """Colecao e' fonte ADICIONAL: nao pode mudar item ja' mapeado."""
    nome = "AK-47 | Redline (Field-Tested)"
    sem = cases.case_status(nome)
    com = cases.case_status(nome, collection="The Kilowatt Collection")
    assert com["case"] == sem["case"], "colecao sobrescreveu o mapa manual"


def test_colecoes_apontam_para_caixas_reais():
    """Toda entrada de _COLLECTION_TO_CASE tem que existir em _CASES."""
    faltando = [
        (col, caixa) for col, caixa in cases._COLLECTION_TO_CASE.items()
        if caixa not in cases._CASES
    ]
    assert not faltando, f"caixas inexistentes: {faltando}"
