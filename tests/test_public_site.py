"""Testes do site público (Fase 1) -- servidor (Flask test client) + worker.

Sem rede: `server.py` só lê `scan_store`, nunca fala com a Steam. Os
testes de `worker.py` mockam `scan_engine.run_full_scan`.
"""
from __future__ import annotations

import time

import pytest
from werkzeug.security import generate_password_hash

from skinvault import ranking, scan_store
from skinvault.public_site import (
    charts, erro_stats, fmt, icon_cache, latencia, rate_limit, scan_progress,
    worker, worker_alert,
)
from skinvault.public_site.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _salva_scan(tmp_path, monkeypatch, resultados, category="Facas"):
    # Captura a funcao ORIGINAL antes do monkeypatch -- referenciar
    # `scan_store.load_last_scan` de dentro do lambda, depois de
    # patcheado, chamaria o proprio lambda (auto-referencia infinita).
    original_load = scan_store.load_last_scan
    p = tmp_path / "scanner_last.json"
    scan_store.save_last_scan(category, resultados, path=p)
    monkeypatch.setattr(
        scan_store, "load_last_scan", lambda: original_load(path=p))


# ── server: / ────────────────────────────────────────────────

def test_index_sem_scan_mostra_vazio(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Ainda não há nenhum scan".encode("utf-8") in resp.data


def test_index_com_scan_lista_candidato(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço baixo (+20)"}]},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Testada em Campo" in body  # localize_name traduziu
    assert "R$" in body
    assert "85" in body


def test_index_nunca_chama_rede(client, monkeypatch, tmp_path):
    """Garantia estrutural: nenhuma rota de server.py importa steam_api."""
    import skinvault.public_site.server as srv
    assert not hasattr(srv, "steam_api")


# ── server: /api/recommendations ────────────────────────────

def test_api_recommendations_sem_scan(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/api/recommendations")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["candidatos"] == []
    assert data["ultimo_scan"]["categoria"] is None


def test_api_recommendations_com_scan(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 90, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item Y", "score": 40, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "high"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados, category="Caixas")
    resp = client.get("/api/recommendations")
    data = resp.get_json()
    assert data["ultimo_scan"]["categoria"] == "Caixas"
    nomes = [c["name"] for c in data["candidatos"]]
    # Item Y tem pump_risk "high" -- filtrado por buy_candidates (default
    # max_pump_risk="medium")
    assert nomes == ["Item X"]


def test_api_recommendations_filtra_owned_vazio_sempre(client, monkeypatch,
                                                        tmp_path):
    """Site publico nao tem login: owned_names e' sempre vazio (ninguem
    'possui' nada), entao nenhum item e' descartado por posse."""
    resultados = [{"name": "Item Z", "score": 60, "price": 1.0,
                  "case_label": "", "pump_risk": {"level": "low"},
                  "breakdown": []}]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/api/recommendations")
    data = resp.get_json()
    assert [c["name"] for c in data["candidatos"]] == ["Item Z"]


# ── server: /healthz ─────────────────────────────────────────

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


# ── server: filtros/busca/ordenar/compacto ──────────────────

def test_index_busca_por_nome(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "AWP | Asiimov (Field-Tested)", "score": 70, "price": 100.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?q=redline")
    body = resp.data.decode("utf-8")
    assert "Redline" in body
    assert "Asiimov" not in body


def test_index_ordenar_por_preco(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caro", "score": 90, "price": 100.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Barato", "score": 50, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?ordenar=preco")
    body = resp.data.decode("utf-8")
    assert body.index("Barato") < body.index("Caro")


def test_index_nota_min_filtra(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Nota alta", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Nota baixa", "score": 30, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?nota_min=50")
    body = resp.data.decode("utf-8")
    assert "Nota alta" in body
    assert "Nota baixa" not in body


def test_index_preco_max_filtra(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caro", "score": 80, "price": 500.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Barato", "score": 50, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/?preco_max=10")
    body = resp.data.decode("utf-8")
    assert "Barato" in body
    assert "Caro" not in body


def test_index_pagina_2(client, monkeypatch, tmp_path):
    resultados = [
        {"name": f"Item {i}", "score": 100 - i, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(25)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    pagina1 = client.get("/").data.decode("utf-8")
    pagina2 = client.get("/?pagina=2").data.decode("utf-8")
    assert "Item 0" in pagina1
    assert "Item 0" not in pagina2
    assert "Item 20" in pagina2


def test_index_descontinuada_ganha_selo(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caixa Velha", "score": 80, "price": 1.0,
         "case_label": "Alguma Caixa (descontinuada, 2018)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "selo-descontinuada" in body


def test_index_modo_compacto_aplica_classe(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [])
    body = client.get("/?compacto=1").data.decode("utf-8")
    assert "modo-compacto" in body


def test_index_mostra_contagem_por_categoria(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "A", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Facas"},
        {"name": "B", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Facas"},
        {"name": "C", "score": 60, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Luvas"},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "Facas (2)" in body
    assert "Luvas (1)" in body


def test_index_mostra_badge_proximo_scan(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "A", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "badge-cooldown" in body
    assert "Próxima atualização" in body


# ── server: robots/sitemap/404/cache ─────────────────────────

def test_static_app_js_tem_atalho_e_notas_locais(client):
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "keydown" in body
    assert "skinvault_notas" in body


def test_robots_txt(client):
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    assert b"Sitemap:" in resp.data
    assert b"Allow: /" in resp.data


def test_sitemap_xml(client):
    resp = client.get("/sitemap.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/xml"
    assert b"<urlset" in resp.data
    assert b"/privacidade" in resp.data


def test_pagina_404_customizada(client):
    resp = client.get("/isso-nao-existe")
    assert resp.status_code == 404
    assert "não existe".encode("utf-8") in resp.data


def test_static_tem_cache_control(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "max-age" in resp.headers.get("Cache-Control", "")


# ── server: polimentos (copiar/agrupar/breakdown/changelog/api) ──

def test_index_tem_botao_copiar_e_atalho_js(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "botao-copiar" in body
    assert 'data-copiar="AK-47 | Redline (Field-Tested)"' in body
    assert "campo-busca" in body
    assert "static/app.js" in body  # atalho "/" mora no JS externo (CSP)


def test_index_detalhe_motivo_mostra_breakdown_completo(client, monkeypatch,
                                                         tmp_path):
    resultados = [
        {"name": "X", "score": 60, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [
             {"factor": "mediana", "delta": 10, "label": "Preço baixo (+10)"},
             {"factor": "momentum", "delta": -5, "label": "Subiu rápido (-5)"},
         ]},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "lista-breakdown" in body
    assert "Preço baixo (+10)" in body
    assert "Subiu rápido (-5)" in body
    assert "delta-positivo" in body
    assert "delta-negativo" in body


def test_index_agrupar_por_categoria(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Faca A", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Facas"},
        {"name": "Luva B", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [], "category": "Luvas"},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/?agrupar=1").data.decode("utf-8")
    assert "grupo-categoria" in body
    assert "Facas (1)" in body
    assert "Luvas (1)" in body
    assert "Faca A" in body
    assert "Luva B" in body


def test_changelog_page(client):
    resp = client.get("/changelog")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "2026-10-25" in body


def test_api_docs_page(client):
    resp = client.get("/api")
    assert resp.status_code == 200
    assert b"/api/recommendations" in resp.data


def test_rodape_tem_link_feedback_changelog_api(client):
    body = client.get("/").data.decode("utf-8")
    assert "github.com/pedronokia/skinvault/issues/new" in body
    assert "/changelog" in body
    assert "/api" in body


# ── server: rodada final (tendência/ranking/método/health/etc) ──

def test_index_mostra_tendencia_alta(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "skinvault.public_site.server.signals.load_item_history",
        lambda name: [{"ts": 1, "price": 10.0}, {"ts": 2, "price": 20.0}])
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "tendencia-alta" in body


def test_index_sem_historico_nao_mostra_tendencia(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "skinvault.public_site.server.signals.load_item_history",
        lambda name: [])
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "icone-tendencia" not in body


def test_index_busca_com_or(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "AWP | Asiimov (Field-Tested)", "score": 70, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Glock-18 | Fade (Factory New)", "score": 60, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/?q=redline+OR+asiimov").data.decode("utf-8")
    assert "Redline" in body
    assert "Asiimov" in body
    assert "Glock" not in body


def test_index_tem_steamdb_link_e_json_ld(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "steamdb.info/search" in body
    assert "application/ld+json" in body


def test_index_minimalista_esconde_selo_top(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    normal = client.get("/").data.decode("utf-8")
    minimalista = client.get("/?minimalista=1").data.decode("utf-8")
    assert "selo-top" in normal
    assert "selo-top" not in minimalista


def test_index_apresentacao_aplica_classe_e_refresh(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [])
    body = client.get("/?apresentacao=1").data.decode("utf-8")
    assert "modo-apresentacao" in body
    assert "http-equiv=\"refresh\"" in body


def test_index_tem_input_tag_local(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "input-tag-local" in body
    assert "static/app.js" in body  # localStorage mora no JS externo (CSP)


def test_index_registra_termo_buscado(client, monkeypatch, tmp_path):
    chamados = []
    monkeypatch.setattr(
        "skinvault.public_site.server.buscas.registrar",
        lambda termo: chamados.append(termo))
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    client.get("/?q=redline")
    assert chamados == ["redline"]


def test_index_sem_busca_nao_registra_termo(client, monkeypatch):
    chamados = []
    monkeypatch.setattr(
        "skinvault.public_site.server.buscas.registrar",
        lambda termo: chamados.append(termo))
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    client.get("/")
    assert chamados == []


def test_changelog_feed_xml(client):
    resp = client.get("/changelog.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/rss+xml"
    assert b"<rss" in resp.data


def test_metodo_page(client):
    resp = client.get("/metodo")
    assert resp.status_code == 200
    assert "O que a nota é".encode("utf-8") in resp.data


def test_ranking_page_sem_snapshots(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server.ranking.load_snapshots", lambda: [])
    monkeypatch.setattr(
        "skinvault.public_site.server.ranking.previous_snapshot",
        lambda: None)
    resp = client.get("/ranking")
    assert resp.status_code == 200
    assert "Ainda não há ranking".encode("utf-8") in resp.data


def test_ranking_page_com_snapshots_marca_novo(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    # Snapshot anterior EXISTE mas nao tem o item X -- e' isso que gera
    # "NOVO" (previous=None geraria label vazio, nao NOVO).
    monkeypatch.setattr(
        "skinvault.public_site.server.ranking.previous_snapshot",
        lambda: {"ts": 900.0, "items": [{"name": "Y", "score": 1, "position": 1}]})
    body = client.get("/ranking").data.decode("utf-8")
    assert "selo-novo" in body


def test_ranking_page_mostra_subiu_e_desceu(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
            {"name": "Y", "score": 70, "position": 2},
        ]}])
    monkeypatch.setattr(
        "skinvault.public_site.server.ranking.previous_snapshot",
        lambda: {"ts": 900.0, "items": [
            {"name": "X", "score": 75, "position": 3},
            {"name": "Y", "score": 70, "position": 1},
        ]})
    body = client.get("/ranking").data.decode("utf-8")
    assert "tendencia-alta" in body
    assert "tendencia-baixa" in body


def test_api_health(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["scan"]["disponivel"] is True
    assert data["scan"]["itens"] == 1


def test_api_health_sem_scan(client, monkeypatch):
    monkeypatch.setattr("skinvault.scan_store.load_last_scan", lambda: None)
    resp = client.get("/api/health")
    data = resp.get_json()
    assert data["scan"]["disponivel"] is False
    assert data["scan"]["idade_segundos"] is None


# ── server: 2a rodada tecnica (500/429/admin/sobre/prefs/cookie) ──

def test_sobre_page(client):
    resp = client.get("/sobre")
    assert resp.status_code == 200
    assert "Por que isso existe".encode("utf-8") in resp.data or \
        "O que é".encode("utf-8") in resp.data


def test_500_customizado(client, monkeypatch):
    @client.application.route("/__boom")
    def _boom():
        raise RuntimeError("erro de teste")
    client.application.config["TESTING"] = False
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    resp = client.get("/__boom")
    assert resp.status_code == 500
    assert "quebrou".encode("utf-8") in resp.data


def test_429_customizado(client, monkeypatch):
    import flask
    @client.application.route("/__limite")
    def _limite():
        flask.abort(429)
    resp = client.get("/__limite")
    assert resp.status_code == 429
    assert "Muitas tentativas".encode("utf-8") in resp.data


def test_admin_sem_hash_configurado_e_404(client, monkeypatch):
    monkeypatch.setattr("skinvault.public_site.server._ADMIN_PASSWORD_HASH", "")
    assert client.get("/admin").status_code == 404
    assert client.get("/admin/login").status_code == 404


def test_admin_sem_sessao_redireciona_pro_login(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_admin_login_senha_errada_nao_autentica(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    resp = client.post("/admin/login", data={"senha": "errada"})
    assert resp.status_code == 200
    assert "incorreta" in resp.data.decode("utf-8")
    assert client.get("/admin").status_code == 302


def test_admin_login_senha_certa_autentica_e_funciona(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    login = client.post("/admin/login", data={"senha": "segredo"})
    assert login.status_code == 302
    assert client.get("/admin").status_code == 200


def test_admin_logout_encerra_sessao(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    client.post("/admin/login", data={"senha": "segredo"})
    assert client.get("/admin").status_code == 200
    client.get("/admin/logout")
    assert client.get("/admin").status_code == 302


def test_cookie_preferencia_persiste(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [])
    resp = client.get("/?compacto=1")
    assert resp.headers.get("Set-Cookie") and "pref_compacto=1" in resp.headers.get("Set-Cookie")
    # Proxima visita sem query param -- cookie decide
    client.set_cookie("pref_compacto", "1")
    body = client.get("/").data.decode("utf-8")
    assert "modo-compacto" in body


def test_status_mostra_grafico_e_buscas_populares(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server.visits.serie_por_dia",
        lambda: [("2026-10-24", 3), ("2026-10-25", 5)])
    monkeypatch.setattr(
        "skinvault.public_site.server.buscas.mais_buscados",
        lambda limite=10: [("ak-47", 4)])
    monkeypatch.setattr(
        "skinvault.public_site.server.scan_store.load_historico_ciclos",
        lambda: [])
    body = client.get("/status").data.decode("utf-8")
    assert "grafico-historico" in body
    assert "ak-47" in body


# ── server: /status ──────────────────────────────────────────

def test_status_sem_historico(client, monkeypatch, tmp_path):
    from skinvault.public_site import uptime, visits
    monkeypatch.setattr(scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(uptime, "no_ar_desde", lambda: 0.0)
    monkeypatch.setattr(visits, "total", lambda: 0)
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "Ainda não há histórico".encode("utf-8") in resp.data


def test_status_mostra_ciclos_com_falha(client, monkeypatch, tmp_path):
    from skinvault.public_site import uptime, visits
    monkeypatch.setattr(scan_store, "load_historico_ciclos", lambda: [
        {"ts": 1000.0, "itens": 0, "duracao_min": 26.4, "sucesso": False},
        {"ts": 2000.0, "itens": 185, "duracao_min": 23.1, "sucesso": True},
    ])
    monkeypatch.setattr(uptime, "no_ar_desde", lambda: 0.0)
    monkeypatch.setattr(visits, "total", lambda: 7)
    resp = client.get("/status")
    body = resp.data.decode("utf-8")
    assert "Sem sucesso (bloqueado)" in body
    assert "Sucesso" in body


# ── server: /feed.xml ────────────────────────────────────────

def test_feed_sem_scan(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/feed.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/rss+xml"
    assert b"<rss" in resp.data


def test_feed_com_scan_lista_item(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/feed.xml")
    body = resp.data.decode("utf-8")
    assert "<item>" in body
    assert "nota 85" in body
    assert "steamcommunity.com/market/listings" in body


# ── worker ───────────────────────────────────────────────────

def test_categorias_padrao_exclui_adesivos():
    cats = worker.categorias_padrao()
    for pesada in worker._CATEGORIAS_PESADAS:
        assert pesada not in cats
    assert "Caixas" in cats


def test_run_once_grava_scan_store_e_ranking(monkeypatch, tmp_path):
    resultados = [{"name": "A", "score": 80}, {"name": "B", "score": 60}]
    original_save_scan = scan_store.save_last_scan
    original_save_snapshot = ranking.save_snapshot
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None: resultados)
    scan_path = tmp_path / "scanner_last.json"
    rank_path = tmp_path / "rankings.json"
    monkeypatch.setattr(
        worker.scan_store, "save_last_scan",
        lambda cat, res: original_save_scan(cat, res, path=scan_path))
    monkeypatch.setattr(
        worker.ranking, "save_snapshot",
        lambda res: original_save_snapshot(res, path=rank_path))

    out = worker.run_once({"Facas": ["A", "B"]})
    assert out == resultados
    saved = scan_store.load_last_scan(path=scan_path)
    assert saved["results"] == resultados
    snaps = ranking.load_snapshots(path=rank_path)
    assert len(snaps) == 1
    assert [it["name"] for it in snaps[0]["items"]] == ["A", "B"]


def test_run_once_sem_resultado_nao_grava_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None: [])
    chamado = {"save": False}

    def _boom(*a, **kw):
        chamado["save"] = True

    monkeypatch.setattr(worker.scan_store, "save_last_scan", _boom)
    monkeypatch.setattr(worker.ranking, "save_snapshot", _boom)
    out = worker.run_once({"Facas": ["A"]})
    assert out == []
    assert chamado["save"] is False


def test_run_once_default_usa_categorias_padrao(monkeypatch):
    recebido = {}

    def _fake(categories, on_progress=None):
        recebido["categories"] = categories
        return []

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    worker.run_once()
    for pesada in worker._CATEGORIAS_PESADAS:
        assert pesada not in recebido["categories"]


def _worker_main_uma_volta(monkeypatch):
    """Roda `main()` e para na 1a chamada de `time.sleep` (`while True`
    de verdade pararia a suite). Devolve os segundos passados pra sleep."""
    monkeypatch.setattr(worker, "run_once", lambda: [])
    chamadas = []

    def _fake_sleep(segundos):
        chamadas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    try:
        worker.main()
    except KeyboardInterrupt:
        pass
    return chamadas


def test_main_le_intervalo_do_env(monkeypatch):
    monkeypatch.setenv("SKINVAULT_WORKER_INTERVAL_HORAS", "2")
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [2 * 3600]


def test_main_sem_env_usa_default(monkeypatch):
    monkeypatch.delenv("SKINVAULT_WORKER_INTERVAL_HORAS", raising=False)
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [worker._INTERVALO_HORAS_DEFAULT * 3600]


def test_main_parametro_explicito_ignora_env(monkeypatch):
    monkeypatch.setenv("SKINVAULT_WORKER_INTERVAL_HORAS", "99")
    monkeypatch.setattr(worker, "run_once", lambda: [])
    chamadas = []

    def _fake_sleep(segundos):
        chamadas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    try:
        worker.main(intervalo_horas=1.0)
    except KeyboardInterrupt:
        pass
    assert chamadas == [3600]


# ── server: /item/<name> (página de detalhe) ───────────────

def test_item_detail_404_para_nome_inexistente(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    resp = client.get("/item/Nao Existe")
    assert resp.status_code == 404


def test_item_detail_mostra_nota_e_preco(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "category": "Rifles",
         "breakdown": [{"factor": "mediana", "delta": 20, "label": "Preço baixo (+20)"}],
         "reasons": ["Preço abaixo da mediana"]},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/item/AK-47 | Redline (Field-Tested)")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "85" in body
    assert "R$" in body


def test_item_detail_itens_parecidos_exclui_o_proprio(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
        {"name": "Item B", "score": 78, "price": 12.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
        {"name": "Item C", "score": 20, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Luvas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/item/Item A")
    body = resp.data.decode("utf-8")
    assert "Item B" in body  # mesma categoria, nota próxima
    assert "Item C" not in body  # categoria diferente


# ── server: robots.txt / csp-report ─────────────────────────

def test_robots_txt_bloqueia_admin(client):
    resp = client.get("/robots.txt")
    assert "Disallow: /admin" in resp.data.decode("utf-8")


def test_csp_report_aceita_post_e_responde_204(client):
    resp = client.post("/api/csp-report", data='{"csp-report": {}}',
                       content_type="application/csp-report")
    assert resp.status_code == 204


# ── server: banner de scan desatualizado ────────────────────

def test_index_banner_scan_desatualizado(client, monkeypatch, tmp_path):
    resultados = [{"name": "A", "score": 80, "price": 10.0, "case_label": "",
                  "pump_risk": {"level": "low"}, "breakdown": []}]
    p = tmp_path / "scanner_last.json"
    velho = time.time() - 100 * 3600
    scan_store.save_last_scan("Facas", resultados, path=p, now=velho)
    original_load = scan_store.load_last_scan
    monkeypatch.setattr(
        scan_store, "load_last_scan", lambda: original_load(path=p))
    resp = client.get("/")
    assert "scan está mais velho" in resp.data.decode("utf-8")


def test_index_sem_banner_quando_scan_recente(client, monkeypatch, tmp_path):
    resultados = [{"name": "A", "score": 80, "price": 10.0, "case_label": "",
                  "pump_risk": {"level": "low"}, "breakdown": []}]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/")
    assert "scan está mais velho" not in resp.data.decode("utf-8")


# ── charts: css_class ────────────────────────────────────────

def test_line_chart_svg_css_class_customizavel():
    svg = charts.line_chart_svg(
        [{"total": 1}, {"total": 2}], css_class="mini-sparkline")
    assert 'class="mini-sparkline"' in svg


def test_line_chart_svg_default_mantem_classe_antiga():
    svg = charts.line_chart_svg([{"total": 1}, {"total": 2}])
    assert 'class="grafico-historico"' in svg


# ── scan_progress ─────────────────────────────────────────

def test_scan_progress_round_trip(tmp_path):
    p = tmp_path / "scan_progress.json"
    scan_progress.registrar(5, 185, "AK-47 | Redline", path=p)
    carregado = scan_progress.carregar(path=p)
    assert carregado["indice"] == 5
    assert carregado["total"] == 185
    assert carregado["item"] == "AK-47 | Redline"


def test_scan_progress_ausente_e_none(tmp_path):
    assert scan_progress.carregar(path=tmp_path / "nao_existe.json") is None


def test_admin_mostra_progresso(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "skinvault.public_site.server.scan_progress.carregar",
        lambda: {"indice": 10, "total": 185, "item": "Item X", "ts": time.time()})
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin")
    assert "Item X" in resp.data.decode("utf-8")


# ── worker_alert ─────────────────────────────────────────────

def test_worker_alert_sem_webhook_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.delenv("SKINVAULT_ADMIN_DISCORD_WEBHOOK", raising=False)
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is False


def test_worker_alert_sucesso_recente_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINVAULT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    ciclos = [{"ts": time.time() - 100, "itens": 5}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is False


def test_worker_alert_manda_quando_atrasado(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINVAULT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(worker_alert.discord_notify, "enviar", lambda url, msg: True)
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is True


def test_worker_alert_dedup_nao_manda_de_novo(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINVAULT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    chamadas = []
    monkeypatch.setattr(
        worker_alert.discord_notify, "enviar",
        lambda url, msg: chamadas.append(1) or True)
    p = tmp_path / "estado.json"
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(ciclos, path=p) is True
    assert worker_alert.verificar_e_alertar(ciclos, path=p) is False
    assert len(chamadas) == 1


# ── worker: ordenação por nota anterior + progresso ─────────

def test_ordenar_por_nota_anterior_prioriza_nota_alta(monkeypatch, tmp_path):
    scan_path = tmp_path / "scanner_last.json"
    scan_store.save_last_scan(
        "Facas", [{"name": "Baixa", "score": 10}, {"name": "Alta", "score": 90}],
        path=scan_path)
    original_load = scan_store.load_last_scan
    monkeypatch.setattr(
        worker.scan_store, "load_last_scan",
        lambda: original_load(path=scan_path))
    out = worker._ordenar_por_nota_anterior({"Facas": ["Baixa", "Alta", "Nova"]})
    assert out["Facas"][0] == "Alta"
    assert out["Facas"][1] == "Nova"  # score 50 (desconhecida) > 10
    assert out["Facas"][2] == "Baixa"


def test_on_progress_grava_scan_progress(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        worker.scan_progress, "registrar",
        lambda i, t, nome: chamadas.append((i, t, nome)))
    worker._on_progress("[3/10] AK-47 | Redline")
    assert chamadas == [(3, 10, "AK-47 | Redline")]


def test_on_progress_ignora_mensagem_sem_formato(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        worker.scan_progress, "registrar",
        lambda *a: chamadas.append(a))
    worker._on_progress("mensagem qualquer")
    assert chamadas == []


# ── server: /comparar ────────────────────────────────────────

def test_comparar_sem_nomes_mostra_vazio(client):
    resp = client.get("/comparar")
    assert resp.status_code == 200
    assert "Nenhum item selecionado" in resp.data.decode("utf-8")


def test_comparar_lista_itens_pedidos(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item B", "score": 60, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "medium"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/comparar?nomes=Item A,Item B")
    body = resp.data.decode("utf-8")
    assert "Item A" in body
    assert "Item B" in body


def test_comparar_ignora_nome_inexistente(client, monkeypatch, tmp_path):
    resultados = [{"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
                  "pump_risk": {"level": "low"}, "breakdown": []}]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/comparar?nomes=Item A,Fantasma")
    body = resp.data.decode("utf-8")
    assert "Item A" in body
    assert "Fantasma" not in body


# ── server: /readyz ──────────────────────────────────────────

def test_readyz_sem_banco_e_ready(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "skinvault.public_site.server.db_backup._DB_PATH",
        tmp_path / "nao_existe.db")
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.get_json()["ready"] is True


def test_readyz_com_banco_valido_e_ready(client, monkeypatch, tmp_path):
    import sqlite3
    db = tmp_path / "x.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.close()
    monkeypatch.setattr("skinvault.public_site.server.db_backup._DB_PATH", db)
    resp = client.get("/readyz")
    assert resp.get_json()["ready"] is True


def test_readyz_com_banco_corrompido_nao_e_ready(client, monkeypatch, tmp_path):
    db = tmp_path / "corrompido.db"
    db.write_bytes(b"isto nao e um sqlite valido nem perto")
    monkeypatch.setattr("skinvault.public_site.server.db_backup._DB_PATH", db)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["ready"] is False


# ── item.html: aposentadoria + preço coletado ──────────────

def test_item_detail_mostra_tempo_de_aposentadoria(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Chroma 2 Case", "score": 85, "price": 1.0, "case_label": "Descontinuada",
         "case_retired_at": "2020-01-01", "pump_risk": {"level": "low"},
         "category": "Caixas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/item/Chroma 2 Case")
    assert "Aposentada há" in resp.data.decode("utf-8")


def test_item_detail_sem_data_aposentadoria_nao_mostra_card(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/item/Item X")
    assert "Aposentada há" not in resp.data.decode("utf-8")


# ── erro_stats ────────────────────────────────────────────────

def test_agregar_por_tipo_conta_por_excecao():
    linhas = [
        "2026-10-25 10:00:00,000 ERROR 500 em /x: ValueError('a')",
        "2026-10-25 10:01:00,000 ERROR 500 em /y: ValueError('b')",
        "2026-10-25 10:02:00,000 ERROR 500 em /z: KeyError('c')",
        "2026-10-25 10:03:00,000 ERROR CSP violation: {}",
    ]
    out = dict(erro_stats.agregar_por_tipo(linhas))
    assert out["ValueError"] == 2
    assert out["KeyError"] == 1
    assert out["CSP violation"] == 1


def test_agregar_por_tipo_linha_sem_match_e_outro():
    out = dict(erro_stats.agregar_por_tipo(["linha qualquer sem padrao"]))
    assert out["Outro"] == 1


def test_serie_por_dia_agrupa_por_data():
    linhas = [
        "2026-10-24 10:00:00,000 ERROR x",
        "2026-10-25 10:00:00,000 ERROR x",
        "2026-10-25 11:00:00,000 ERROR x",
    ]
    out = dict(erro_stats.serie_por_dia(linhas))
    assert out["2026-10-24"] == 1
    assert out["2026-10-25"] == 2


def test_serie_por_dia_limita_quantidade_de_dias():
    linhas = [f"2026-10-{d:02d} 10:00:00,000 ERROR x" for d in range(1, 20)]
    out = erro_stats.serie_por_dia(linhas, dias=5)
    assert len(out) == 5


# ── latencia ──────────────────────────────────────────────────

def test_latencia_resumo_calcula_media():
    latencia.reset()
    latencia.registrar("index", 10.0)
    latencia.registrar("index", 20.0)
    resumo = latencia.resumo()
    assert len(resumo) == 1
    assert resumo[0]["endpoint"] == "index"
    assert resumo[0]["media_ms"] == 15.0
    assert resumo[0]["contagem"] == 2
    latencia.reset()


def test_latencia_ignora_endpoint_vazio():
    latencia.reset()
    latencia.registrar("", 10.0)
    assert latencia.resumo() == []


def test_requisicao_real_registra_latencia(client, monkeypatch, tmp_path):
    latencia.reset()
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    client.get("/")
    resumo = latencia.resumo()
    assert any(r["endpoint"] == "index" for r in resumo)
    latencia.reset()


# ── icon_cache ────────────────────────────────────────────────

def test_icon_cache_sem_hash_devolve_none():
    assert icon_cache.obter("") is None


def test_icon_cache_le_do_disco_sem_rede(monkeypatch, tmp_path):
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)
    p = icon_cache._caminho("abc123")
    p.write_bytes(b"fake-jpeg-bytes")

    def _boom(*a, **kw):
        raise AssertionError("não deveria bater na rede com cache em disco")

    import httpx
    monkeypatch.setattr(httpx, "get", _boom)
    assert icon_cache.obter("abc123") == b"fake-jpeg-bytes"


def test_icon_cache_falha_de_rede_devolve_none(monkeypatch, tmp_path):
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)

    def _boom(*a, **kw):
        raise OSError("rede fora")

    import httpx
    monkeypatch.setattr(httpx, "get", _boom)
    assert icon_cache.obter("semcache") is None


def test_rota_icone_sem_cache_redireciona_pro_cdn(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server.icon_cache.obter", lambda h: None)
    resp = client.get("/icone/abc123.jpg")
    assert resp.status_code == 302
    assert "steamstatic.com" in resp.headers["Location"]


def test_rota_icone_com_cache_serve_bytes(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server.icon_cache.obter",
        lambda h: b"dados-da-imagem")
    resp = client.get("/icone/abc123.jpg")
    assert resp.status_code == 200
    assert resp.data == b"dados-da-imagem"
    assert "max-age" in resp.headers.get("Cache-Control", "")


# ── rate limit nas rotas novas ───────────────────────────────

def test_api_recommendations_tem_rate_limit(monkeypatch):
    # Cria o app DEPOIS de patchear a constante: `rate_limited(...)` é
    # avaliado na hora da decoração (dentro de `create_app()`), não a
    # cada request -- usar o fixture `client` criaria o app antes do
    # monkeypatch valer (mesma família de gotcha do AGENTS.md #13/#17).
    monkeypatch.setattr(rate_limit, "API_MAX_HITS", 2)
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    for _ in range(2):
        assert c.get("/api/recommendations").status_code == 200
    assert c.get("/api/recommendations").status_code == 429


def test_csp_report_tem_rate_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "CSP_REPORT_MAX_HITS", 2)
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    for _ in range(2):
        assert c.post("/api/csp-report", data="{}").status_code == 204
    assert c.post("/api/csp-report", data="{}").status_code == 429


# ── PWA: manifest + service worker ──────────────────────────

def test_manifest_json_acessivel(client):
    resp = client.get("/static/manifest.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "SkinVault"
    assert data["start_url"] == "/"


def test_sw_js_na_raiz_com_scope_amplo(client):
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert resp.headers.get("Service-Worker-Allowed") == "/"


def test_index_referencia_manifest_e_theme_color(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    body = client.get("/").data.decode("utf-8")
    assert "manifest.json" in body
    assert "theme-color" in body


# ── Lote 2: testes de casos de borda (2026-10-26) ───────────

def test_item_detail_nome_com_caracteres_especiais(client, monkeypatch, tmp_path):
    nome = "StatTrak™ Karambit | Doppler (Factory New) ★"
    resultados = [{"name": nome, "score": 90, "price": 5000.0, "case_label": "",
                  "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []}]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/item/" + nome)
    assert resp.status_code == 200
    assert "90" in resp.data.decode("utf-8")


def test_sitemap_xml_bem_formado(client):
    import xml.etree.ElementTree as ET
    resp = client.get("/sitemap.xml")
    raiz = ET.fromstring(resp.data)  # levanta ParseError se malformado
    assert raiz.tag.endswith("urlset")


def test_robots_txt_conteudo_completo(client):
    corpo = client.get("/robots.txt").data.decode("utf-8")
    assert corpo.startswith("User-agent: *\n")
    assert "Allow: /\n" in corpo
    assert "Disallow: /admin\n" in corpo
    assert "Sitemap: " in corpo
    assert corpo.rstrip("\n").endswith("sitemap.xml")


def test_comparar_trunca_em_3_mesmo_com_mais_nomes(client, monkeypatch, tmp_path):
    resultados = [
        {"name": f"Item {i}", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(5)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    resp = client.get("/comparar?nomes=" + ",".join(f"Item {i}" for i in range(5)))
    body = resp.data.decode("utf-8")
    presentes = sum(1 for i in range(5) if f"Item {i}" in body)
    assert presentes == 3


def test_fmt_brl_valor_negativo():
    assert fmt.brl(-42.5) == "R$ -42,50"


def test_fmt_brl_valor_grande():
    assert fmt.brl(1234567.89) == "R$ 1.234.567,89"


def test_agrupar_por_categoria_item_sem_categoria():
    from skinvault.public_site.server import _agrupar_por_categoria
    candidatos = [{"name": "X", "score": 10}]  # sem a chave "category" de vez
    grupos = _agrupar_por_categoria(candidatos)
    assert grupos == [("Sem categoria", candidatos)]


def test_csp_report_corpo_vazio_ainda_responde_204(client):
    resp = client.post("/api/csp-report", data="")
    assert resp.status_code == 204


def test_icon_cache_caminho_sanitiza_hash_nao_alfanumerico():
    p = icon_cache._caminho("../../etc/passwd")
    assert ".." not in p.name
    assert "/" not in p.name
    assert p.parent == icon_cache._CACHE_DIR


def test_readyz_com_db_path_sendo_diretorio(client, monkeypatch, tmp_path):
    diretorio = tmp_path / "isto_e_pasta"
    diretorio.mkdir()
    monkeypatch.setattr("skinvault.public_site.server.db_backup._DB_PATH", diretorio)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    assert resp.get_json()["ready"] is False


# ── Lote 6: pagina /faq ──────────────────────────────────────

def test_faq_page(client):
    resp = client.get("/faq")
    assert resp.status_code == 200
    assert "FAQPage" in resp.data.decode("utf-8")


def test_faq_no_rodape(client):
    body = client.get("/").data.decode("utf-8")
    assert "/faq" in body


def test_sitemap_inclui_faq(client):
    body = client.get("/sitemap.xml").data.decode("utf-8")
    assert "/faq" in body


# ── Lote 8: admin -- disco, usuarios, webhook, log bruto ────

def test_admin_mostra_disco_e_usuarios(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin")
    body = resp.data.decode("utf-8")
    assert "Disco livre" in body
    assert "Contas com login" in body


def test_admin_testar_webhook_sem_sessao_e_404(client):
    resp = client.post("/admin/testar-webhook", data={})
    assert resp.status_code == 404


def test_admin_testar_webhook_sem_csrf_e_403(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.post("/admin/testar-webhook", data={})
    assert resp.status_code == 403


def test_admin_testar_webhook_com_csrf_funciona(client, monkeypatch):
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "skinvault.public_site.server.discord_notify.enviar",
        lambda url, msg: True)
    client.post("/admin/login", data={"senha": "segredo"})
    with client.session_transaction() as sess:
        token = sess.get("csrf_token")
    if not token:
        # primeira visita no admin ainda nao gerou token -- visita a
        # pagina (que agora gera via csrf_token()) antes de testar.
        client.get("/admin")
        with client.session_transaction() as sess:
            token = sess["csrf_token"]
    resp = client.post("/admin/testar-webhook", data={"csrf_token": token})
    assert resp.status_code == 302


def test_admin_log_bruto_sem_sessao_e_404(client):
    resp = client.get("/admin/log-bruto")
    assert resp.status_code == 404


def test_admin_log_bruto_com_sessao_baixa_arquivo(client, monkeypatch, tmp_path):
    log = tmp_path / "errors.log"
    log.write_text("linha de erro\n", encoding="utf-8")
    monkeypatch.setattr(
        "skinvault.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr("skinvault.public_site.server._ERROR_LOG_PATH", log)
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin/log-bruto")
    assert resp.status_code == 200
    assert b"linha de erro" in resp.data


def test_disco_info_nao_quebra_sem_dados():
    from skinvault.public_site.server import _disco_info
    info = _disco_info()
    assert "livre_fmt" in info


def test_contagem_usuarios_sem_banco_e_zero(monkeypatch, tmp_path):
    from skinvault.public_site.server import _contagem_usuarios
    monkeypatch.setattr(
        "skinvault.public_site.server.db_backup._DB_PATH",
        tmp_path / "nao_existe.db")
    assert _contagem_usuarios() == 0


# ── Guarda contra comentário CSS não fechado (achado 2026-10-26) ──

def test_style_css_comentarios_balanceados():
    """Um /* sem */ correspondente engole silenciosamente toda regra
    CSS real até o próximo fechamento -- achado ao vivo nesta mesma
    rodada (ver feedback-comentario-css-nao-fechado na memória do
    projeto). Conta simples de marcadores pega isso sem precisar de
    parser CSS de verdade."""
    import re
    from pathlib import Path

    caminho = (Path(__file__).parent.parent / "skinvault" / "public_site"
              / "static" / "style.css")
    css = caminho.read_text(encoding="utf-8")
    abre = len(re.findall(re.escape("/*"), css))
    fecha = len(re.findall(re.escape("*/"), css))
    assert abre == fecha, (
        f"{abre} '/*' contra {fecha} '*/' -- algum comentário não fechou "
        "e pode estar engolindo CSS real (ver style.css)")
