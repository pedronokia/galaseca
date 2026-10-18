"""Testes da Calculadora de Trade-up (web) -- Fase 5.

`tradeup.py` ja' e' logica pura e bem coberta por tests/test_tradeup.py;
aqui testa-se so' o encaixe web (tradeup_data.py + rotas), com rede
sempre bloqueada pela fixture autouse de conftest.py.
"""
from __future__ import annotations

import time

import pytest

from skinvault import tradeup as tradeup_mod
from skinvault.webapp import tradeup_data
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _catalogo_teste() -> dict:
    return {
        "version": tradeup_mod.CATALOG_VERSION,
        "ts": time.time(),
        "source": "test",
        "skins": {
            "Test Weapon | Alpha": {
                "c": "Test Collection", "r": "common",
                "min": 0.0, "max": 1.0, "st": False, "glove": False,
            },
            "Test Weapon | Beta": {
                "c": "Test Collection", "r": "uncommon",
                "min": 0.0, "max": 1.0, "st": False, "glove": False,
            },
        },
        "collections": {
            "Test Collection": {
                "tiers": {
                    "common": ["Test Weapon | Alpha"],
                    "uncommon": ["Test Weapon | Beta"],
                },
                "rare": [], "rare_st": [],
            },
        },
    }


def test_parse_lines():
    raw = (
        "AK-47 | Redline (Field-Tested)\n"
        "  \n"
        "AK-47 | Redline (Field-Tested);0.22\n"
        "AK-47 | Redline (Field-Tested);0,22;45,50\n"
    )
    out = tradeup_data.parse_lines(raw)
    assert len(out) == 3
    assert out[0] == {"name": "AK-47 | Redline (Field-Tested)"}
    assert out[1]["float"] == pytest.approx(0.22)
    assert out[2]["float"] == pytest.approx(0.22)
    assert out[2]["cost"] == pytest.approx(45.50)


def test_catalog_status_sem_catalogo():
    status = tradeup_data.catalog_status()
    assert status["status"] == "missing"


def test_quick_plan_sem_catalogo():
    res = tradeup_data.quick_plan("qualquer coisa")
    assert res["errors"]


def test_quick_plan_com_catalogo_de_teste():
    tradeup_mod.save_catalog(_catalogo_teste())
    linhas = "\n".join(["Test Weapon | Alpha (Field-Tested)"] * 10)
    res = tradeup_data.quick_plan(linhas)
    assert res["errors"] == []
    assert len(res["outcomes"]) == 1
    assert res["outcomes"][0]["base"] == "Test Weapon | Beta"
    assert res["outcomes"][0]["prob"] == pytest.approx(1.0)
    # sem nada no ssr_cache, cobertura fica zero -- nunca bate na rede
    assert res["coverage"] == 0.0


def test_quick_plan_quantidade_errada_vira_erro():
    tradeup_mod.save_catalog(_catalogo_teste())
    res = tradeup_data.quick_plan("Test Weapon | Alpha (Field-Tested)")
    assert any("10 itens" in e for e in res["errors"])


def test_rota_catalog_status(client):
    resp = client.get("/api/tradeup/catalog")
    assert resp.status_code == 200
    assert "status" in resp.get_json()


def test_rota_plan(client):
    tradeup_mod.save_catalog(_catalogo_teste())
    linhas = "\n".join(["Test Weapon | Alpha (Field-Tested)"] * 10)
    resp = client.post("/api/tradeup/plan", json={"lines": linhas})
    assert resp.status_code == 200
    assert resp.get_json()["errors"] == []


def test_rota_catalog_refresh_dispara_e_termina(client):
    resp = client.post("/api/tradeup/catalog/refresh")
    assert resp.status_code == 200
    assert resp.get_json()["started"] is True
    for _ in range(100):
        if not tradeup_data.is_refreshing_catalog():
            break
        time.sleep(0.02)
    assert not tradeup_data.is_refreshing_catalog()


def test_rota_catalog_refresh_recusa_concorrente(client, monkeypatch):
    monkeypatch.setattr(tradeup_data, "_refreshing_catalog", True)
    resp = client.post("/api/tradeup/catalog/refresh")
    assert resp.status_code == 409


def test_rota_evaluate_dispara_e_termina(client):
    tradeup_mod.save_catalog(_catalogo_teste())
    linhas = "\n".join(["Test Weapon | Alpha (Field-Tested)"] * 10)
    resp = client.post("/api/tradeup/evaluate", json={"lines": linhas})
    assert resp.status_code == 200
    assert resp.get_json()["started"] is True
    for _ in range(200):
        if not tradeup_data.is_evaluating():
            break
        time.sleep(0.02)
    assert not tradeup_data.is_evaluating()


def test_rota_evaluate_recusa_concorrente(client, monkeypatch):
    monkeypatch.setattr(tradeup_data, "_evaluating", True)
    resp = client.post("/api/tradeup/evaluate", json={"lines": "x"})
    assert resp.status_code == 409


def test_pagina_tradeup_responde(client):
    resp = client.get("/trade-up")
    assert resp.status_code == 200
