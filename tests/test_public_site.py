"""Testes do site público (Fase 1) -- servidor (Flask test client) + worker.

Sem rede: `server.py` só lê `scan_store`, nunca fala com a Steam. Os
testes de `worker.py` mockam `scan_engine.run_full_scan`.
"""
from __future__ import annotations

import html
import re
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from werkzeug.security import generate_password_hash

from galaseca import ranking, scan_store, signals
from galaseca.public_site import (
    charts, erro_stats, fmt, icon_cache, latencia, rate_limit, scan_progress,
    user_store, visits, worker, worker_alert,
)
from galaseca.public_site.server import create_app


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


def test_index_exibe_total_de_visitas_no_rodape(client, monkeypatch, tmp_path):
    p = tmp_path / "visitas.json"
    monkeypatch.setattr(visits, "_DEFAULT_PATH", p)
    visits.registrar(p, now=time.time())
    visits.registrar(p, now=time.time() + 5)

    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Hoje:" in body
    assert "acessos" in body
    assert "Total:" in body


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


def test_index_exibe_miniatura_e_separa_acoes_do_nome(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "icon": "skin-icon-hash", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])

    body = client.get("/").data.decode("utf-8")
    celula = re.search(
        r'<td class="celula-item"[^>]*>(.*?)</td>', body, re.DOTALL).group(1)
    principal = re.search(
        r'<div class="celula-item-principal">(.*?)</div>',
        celula, re.DOTALL).group(1)
    acoes = re.search(
        r'<div class="celula-item-acoes">(.*?)</div>',
        celula, re.DOTALL).group(1)

    assert 'class="icone-item-quadro icone-item-quadro-com-imagem"' in principal
    assert 'src="/icone/skin-icon-hash.webp?v=2"' in principal
    assert 'class="icone-item"' in principal
    assert "link-item" in principal
    assert "menu-acoes-item" in acoes
    assert "Copiar nome" in acoes
    assert "Copiar link" in acoes
    assert "SteamDB" in acoes
    assert "Detalhes" in acoes
    assert "checkbox-comparar" in acoes
    assert "botao-favorito" in acoes


def test_index_reserva_espaco_da_miniatura_sem_hash(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item sem imagem", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ])

    body = client.get("/").data.decode("utf-8")
    celula = re.search(
        r'<td class="celula-item"[^>]*>(.*?)</td>', body, re.DOTALL).group(1)

    assert 'class="icone-item-quadro"' in celula
    assert 'class="icone-item-placeholder"' in celula
    assert 'class="icone-item"' not in celula


def test_index_explicita_escala_da_nota_e_rotulo_textual_de_risco(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço baixo (+20)"}]},
    ])
    body = client.get("/").data.decode("utf-8")

    assert "Nota (0\u2013100)" in body
    assert "não é promessa nem previsão de lucro" in body
    assert "selo de risco, quando aparece, indica a possibilidade" in body
    # Risco baixo é o caso comum: sem coluna nem selo (era uma coluna
    # inteira repetindo "Baixo" em toda linha).
    assert 'class="selo-risco' not in body


def test_index_risco_medio_vira_selo_ao_lado_da_nota(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "medium"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert 'class="selo-risco risco-medium" aria-label="Risco médio"' in celula
    assert ">Risco médio</span>" in celula


def test_index_resume_um_motivo_e_preserva_fatores_completos(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item de teste", "score": 85, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [
             {"factor": "um", "delta": 20, "label": "Preço baixo"},
             {"factor": "dois", "delta": 15, "label": "Boa liquidez"},
             {"factor": "tres", "delta": 10, "label": "Caixa descontinuada"},
         ]},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")

    assert '<main id="conteudo" class="pagina-inicial">' in body
    assert '<span class="texto-motivo">Preço baixo</span>' in body
    assert '<li class="delta-positivo">Boa liquidez</li>' in body
    assert "<li class=\"delta-positivo\">Caixa descontinuada</li>" in body


def test_index_organiza_filtros_no_celular_e_avisa_rolagem_da_tabela(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item de teste", "score": 85, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")

    assert '<div class="filtros-numericos">' in body
    assert "Deslize a tabela para o lado" in body


def test_index_exibe_cartoes_mobile_com_rotulos_e_historico_acessivel(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "Caixa de teste",
         "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço abaixo do típico"}]},
    ])
    monkeypatch.setattr(signals, "load_item_history", lambda name: [
        {"ts": "2026-10-28T12:00:00", "price": 48.0},
        {"ts": "2026-10-29T12:00:00", "price": 50.0},
    ])
    body = client.get("/").data.decode("utf-8")
    css = (client.application.root_path
           + "/static/style.css")
    from pathlib import Path
    css_text = Path(css).read_text(encoding="utf-8")

    for label in ("Item", "Preço", "Histórico", "Nota", "Caixa/Cápsula",
                  "Por quê"):
        assert f'data-label="{label}"' in body
    assert "Deslize a tabela para o lado" in body
    assert 'aria-label="Ver histórico completo de AK-47 | Redline (Testada em Campo)"' in body
    assert ".pagina-inicial table.tabela-itens tbody tr" in css_text
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css_text


def test_index_marca_cabecalho_para_fixacao_no_desktop(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço baixo (+20)"}]},
    ])
    body = client.get("/").data.decode("utf-8")

    assert '<thead class="cabecalho-fixo">' in body


def test_index_filtros_ativos_removem_um_filtro_preservando_os_demais(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80,
         "price": 10.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    body = client.get(
        "/?categoria=Facas&nota_min=70&preco_max=20&q=AK-47"
        "&ordenar=preco&pagina=2").data.decode()
    hrefs = {
        filtro: parse_qs(urlsplit(html.unescape(href)).query)
        for filtro, href in re.findall(
            r'<a class="chip-filtro" data-filtro="([^"]+)" href="([^"]+)"',
            body)
    }

    assert set(hrefs) == {"categoria", "nota_min", "preco_max", "q"}
    for filtro, query in hrefs.items():
        assert filtro not in query
        assert query["ordenar"] == ["preco"]
        assert "pagina" not in query
    assert hrefs["categoria"]["nota_min"] == ["70.0"]
    assert hrefs["categoria"]["preco_max"] == ["20.0"]
    assert hrefs["categoria"]["q"] == ["AK-47"]

    limpar = re.search(
        r'<a[^>]*id="limpar-filtros-ativos"[^>]*href="([^"]+)"', body)
    assert limpar
    query_limpa = parse_qs(urlsplit(html.unescape(limpar.group(1))).query)
    assert set(query_limpa) == {"ordenar"}


def test_index_nunca_chama_rede(client, monkeypatch, tmp_path):
    """Garantia estrutural: nenhuma rota de server.py importa steam_api."""
    import galaseca.public_site.server as srv
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
         "icon": "abc123", "pump_risk": {"level": "low"}, "breakdown": []},
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
    assert data["api_version"] == 1
    assert data["candidatos"][0]["icon_url"] == "/icone/abc123.webp?v=2"
    assert data["candidatos"][0]["icon_url_2x"] == "/icone/abc123.webp?v=2"


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
    assert data["candidatos"][0]["icon_url"] is None


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


def test_index_cookie_ordenar_segue_secure_cookie_config(client):
    """achado 2026-11-01: `pref_ordenar` não tinha a flag `Secure`
    nenhuma, diferente do cookie de sessão (que já segue
    SESSION_COOKIE_SECURE, ligado em produção via
    PUBLIC_SITE_SECURE_COOKIES=1). `secure=True` fixo quebraria o dev
    local (http) -- por isso segue a MESMA config condicional, não um
    valor fixo."""
    resp = client.get("/?ordenar=preco")
    cookie = resp.headers.get("Set-Cookie", "")
    assert "pref_ordenar=preco" in cookie
    assert "Secure" not in cookie  # SESSION_COOKIE_SECURE=False no teste

    client.application.config["SESSION_COOKIE_SECURE"] = True
    resp2 = client.get("/?ordenar=preco")
    assert "Secure" in resp2.headers.get("Set-Cookie", "")


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


@pytest.mark.parametrize(("parametro", "valor"), [
    ("nota_min", "nan"),
    ("nota_min", "inf"),
    ("nota_min", "-inf"),
    ("preco_max", "nan"),
    ("preco_max", "inf"),
    ("preco_max", "-inf"),
])
def test_index_ignora_filtros_nao_finitos(client, monkeypatch, tmp_path,
                                           parametro, valor):
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item B", "score": 60, "price": 20.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get(f"/?{parametro}={valor}").data.decode("utf-8")
    assert "Item A" in body
    assert "Item B" in body
    assert f'value="{valor}"' not in body


def test_index_pagina_2(client, monkeypatch, tmp_path):
    resultados = [
        {"name": f"Item {i}", "score": 100 - i, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(25)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    pagina1 = client.get("/").data.decode("utf-8")
    pagina2 = client.get("/?pagina=2").data.decode("utf-8")
    pagina3 = client.get("/?pagina=3").data.decode("utf-8")
    assert "Item 0" in pagina1
    assert "Item 0" not in pagina2
    assert "Item 10" in pagina2
    assert "Mostrando 1–10 de 25 itens" in pagina1
    assert "Mostrando 11–20 de 25 itens" in pagina2
    assert "Mostrando 21–25 de 25 itens" in pagina3


def test_index_descontinuada_ganha_selo(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caixa Velha", "score": 80, "price": 1.0,
         "case_label": "Alguma Caixa (descontinuada, 2018)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "selo-descontinuada" in body


def test_index_aposentada_com_data_tambem_ganha_selo(client, monkeypatch,
                                                      tmp_path):
    """achado 2026-10-30: com data exata registrada em retirements.py,
    cases.py gera "aposentada em DD/MM/AAAA" em vez de "descontinuada"
    -- esse rótulo (o mais confiável, por ter fonte factual) ficava sem
    o selo .selo-descontinuada."""
    resultados = [
        {"name": "Caixa Gallery", "score": 80, "price": 1.0,
         "case_label": "Caixa Gallery (aposentada em 01/10/2025)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "selo-descontinuada" in body


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
    assert "galaseca_notas" in body
    assert "mouseover" in body and "prefetch" in body


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


def test_index_linha_tem_data_nota_pro_selo_de_mudanca(client, monkeypatch,
                                                        tmp_path):
    """app.js compara data-nota de cada <tr> com o que salvou na última
    visita (localStorage) pra desenhar .selo-mudou-nota -- sem o atributo
    certo na linha, a comparação de "o que mudou" nunca dispara."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 73, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert 'data-nome="X"' in body
    assert 'data-nota="73"' in body


def test_index_detalhe_motivo_mostra_breakdown_completo(client, monkeypatch,
                                                         tmp_path):
    resultados = [
        {"name": "X", "score": 60, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [
             {"factor": "mediana", "delta": 10, "label": "Preço baixo (+10)"},
             {"factor": "liquidez", "delta": 5, "label": "Bônus de liquidez (+5)"},
             {"factor": "momentum", "delta": -5, "label": "Subiu rápido (-5)"},
         ]},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "lista-breakdown" in body
    # "(+10)" é contribuição pra nota, não porcentagem -- vira "+10 pts".
    # Espaço fixo ( ) entre "·"/número/"pts" pra não quebrar linha
    # deixando "pts" sozinho -- ver _motivo_fmt.
    assert "Preço baixo · +10 pts" in body
    assert "Bônus de liquidez · +5 pts" in body
    assert "Subiu rápido · -5 pts" in body
    assert "(+10)" not in body
    assert "delta-positivo" in body
    assert "delta-negativo" in body
    # O motivo de maior peso (reasons[0]) já aparece no resumo -- repeti-lo
    # como item da lista abaixo criava uma linha idêntica logo após o
    # resumo; clicar nela não fechava o <details> (só <summary> alterna
    # `open`), dando a impressão de que não dava mais pra recolher.
    assert body.count("Preço baixo · +10 pts") == 1


def test_index_dica_expandir_so_aparece_com_breakdown(client, monkeypatch,
                                                       tmp_path):
    """.dica-expandir ("ver mais") só faz sentido quando há algo a mais
    pra revelar -- sem breakdown, ou com um breakdown que é só o motivo
    já mostrado no resumo, o <details> não abre em nada novo."""
    resultados = [
        {"name": "Com motivo extra", "score": 60, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [
             {"factor": "mediana", "delta": 10, "label": "Preço baixo (+10)"},
             {"factor": "momentum", "delta": -5, "label": "Subiu rápido (-5)"},
         ]},
        {"name": "Só o motivo do resumo", "score": 55, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 10,
                        "label": "Preço baixo (+10)"}]},
        {"name": "Sem breakdown", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert body.count("dica-expandir") == 1
    # "recolher" fica depois da lista (fora do <summary>) -- aparece
    # junto com "ver mais", na mesma linha que tem algo a mais pra
    # mostrar.
    assert body.count("botao-recolher-motivo") == 1


def test_changelog_page(client):
    resp = client.get("/changelog")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Tabela mais clara e ações organizadas" in body
    assert "O espaço da miniatura fica reservado" in body
    assert "2026-10-25" in body
    assert "Formulários e documentação mais claros" in body
    assert "retorno pertence à sessão" in body
    assert "Tabela mais larga em telas grandes" in body


def test_api_docs_page(client):
    resp = client.get("/api")
    assert resp.status_code == 200
    assert b"/api/recommendations" in resp.data
    body = " ".join(resp.data.decode("utf-8").split())
    assert "60 consultas por minuto por IP" in body
    assert "HTTP 429" in body
    assert "sem limite de taxa específico" not in body
    assert '"api_version": 1' in body
    assert '"icon_url": "/icone/' in body
    assert "community.cloudflare.steamstatic.com" not in body
    assert "o valor é <code>null</code> quando" in body


def test_rodape_tem_link_feedback_changelog_api(client):
    body = client.get("/").data.decode("utf-8")
    assert "github.com/pedronokia/galaseca/issues/new" in body
    assert "/changelog" in body
    assert "/api" in body


def test_rodape_nao_afirma_data_futura(client):
    body = client.get("/").data.decode("utf-8")
    assert "Criado por" in body
    assert "desde novembro de 2026" not in body


# ── server: rodada final (tendência/ranking/método/health/etc) ──

def test_index_mostra_tendencia_alta(client, monkeypatch, tmp_path):
    def marca_tendencia_alta(candidatos):
        for candidato in candidatos:
            candidato["tendencia"] = "alta"

    monkeypatch.setattr(
        "galaseca.public_site.server._enriquecer_com_historico",
        marca_tendencia_alta)
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "tendencia-alta" in body
    assert "> Subiu</span>" in body
    assert "class=\"celula-preco\"" in body


def test_index_tendencia_mostra_variacao_percentual(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "galaseca.public_site.server.signals.load_item_history",
        lambda name: [{"ts": 1, "price": 10.0}, {"ts": 2, "price": 9.68}])
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 9.68, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "tendencia-baixa" in body
    assert "> 3,2%</span>" in body
    assert 'title="Preço caiu 3,2% desde o scan anterior"' in body


def test_index_sem_historico_nao_mostra_tendencia(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "galaseca.public_site.server.signals.load_item_history",
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


def test_index_sem_selo_maior_nota(client, monkeypatch, tmp_path):
    # A lista já vem ordenada pela nota: o selo só repetia isso.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    assert "selo-top" not in client.get("/").data.decode("utf-8")


def test_index_abas_de_categoria_so_com_dados(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "category": "Rifles", "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/?categoria=Rifles").data.decode("utf-8")
    abas = body.split('class="abas-categoria"', 1)[1].split("</nav>", 1)[0]
    assert ">Todas <span" in abas
    assert 'aria-current="page">Rifles <span class="aba-contagem">1</span>' in abas
    assert ">Facas <span" not in abas


def test_index_aba_todas_bate_com_total_mostrado(client, monkeypatch, tmp_path):
    """achado 2026-10-30: a aba "Todas" contava `scan["results"]` cru,
    mas a lista abaixo usa `buy_candidates`, que descarta risco alto de
    pump -- a aba dizia um número e "Mostrando ... de N itens" dizia
    outro, sem explicação nenhuma pro visitante."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Y", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "high"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    abas = body.split('class="abas-categoria"', 1)[1].split("</nav>", 1)[0]
    assert ">Todas <span class=\"aba-contagem\">1</span>" in abas
    assert "Mostrando 1–1 de 1 itens" in body


def test_index_logo_no_topo(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [])
    body = client.get("/").data.decode("utf-8")
    assert 'class="logo"' in body
    assert 'class="logo-cheia"' in body
    assert 'class="logo-marca-ponto"' in body
    assert 'aria-label="sai daí, galaseca — página inicial"' in body
    assert 'class="logo-compacta"' in body


def test_index_tem_input_tag_local(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "input-tag-local" in body
    assert "static/app.js" in body  # localStorage mora no JS externo (CSP)


def test_index_campo_nota_pessoal_nasce_escondido_atras_de_botao(
        client, monkeypatch, tmp_path):
    """O campo de nota ocupava espaço em toda linha da tabela mesmo pra
    quem nunca usa -- nasce `hidden`, só .botao-nota-toggle revela (JS)."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "botao-nota-toggle" in body
    assert 'class="input-tag-local" data-item="X"' in body
    assert body.count("input-tag-local") >= 1
    # O <input> precisa estar hidden por padrão -- sem isso a correção
    # de 2026-10-27 regrediu (volta a aparecer em toda linha).
    idx = body.index('class="input-tag-local"')
    tag_fechamento = body.index(">", idx)
    assert "hidden" in body[idx:tag_fechamento]


def test_index_registra_termo_buscado(client, monkeypatch, tmp_path):
    chamados = []
    monkeypatch.setattr(
        "galaseca.public_site.server.buscas.registrar",
        lambda termo: chamados.append(termo))
    monkeypatch.setattr("galaseca.scan_store.load_last_scan", lambda: None)
    client.get("/?q=redline")
    assert chamados == ["redline"]


def test_index_sem_busca_nao_registra_termo(client, monkeypatch):
    chamados = []
    monkeypatch.setattr(
        "galaseca.public_site.server.buscas.registrar",
        lambda termo: chamados.append(termo))
    monkeypatch.setattr("galaseca.scan_store.load_last_scan", lambda: None)
    client.get("/")
    assert chamados == []


def test_changelog_feed_xml(client):
    resp = client.get("/changelog.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/rss+xml"
    assert b"<rss" in resp.data
    # Opcional pela spec RSS 2.0, mas sem isso o item não tinha pra
    # onde clicar (achado 2026-11-01).
    body = resp.data.decode("utf-8")
    assert body.count("<link>") == body.count("<item>") + 1  # +1 do <channel>
    assert "<link>http://localhost/changelog</link>" in body


def test_metodo_page(client):
    resp = client.get("/metodo")
    assert resp.status_code == 200
    assert "O que a nota é".encode("utf-8") in resp.data


def test_ranking_page_sem_snapshots(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots", lambda: [])
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot",
        lambda: None)
    resp = client.get("/ranking")
    assert resp.status_code == 200
    assert "Ainda não há ranking".encode("utf-8") in resp.data


def test_ranking_page_com_snapshots_marca_novo(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    # Snapshot anterior EXISTE mas nao tem o item X -- e' isso que gera
    # "NOVO" (previous=None geraria label vazio, nao NOVO).
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot",
        lambda: {"ts": 900.0, "items": [{"name": "Y", "score": 1, "position": 1}]})
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.latest_before",
        lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert "selo-novo" in body


def test_ranking_page_item_linka_pra_pagina_de_detalhe(client, monkeypatch):
    """O nome do item no Ranking precisa ser link pro /item/<nome> --
    sem isso, quem via o Top 20 e queria o histórico/motivo completo
    tinha que voltar pra home e buscar manualmente."""
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot", lambda: None)
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert 'href="/item/AK-47%20%7C%20Redline%20(Field-Tested)"' in body


def test_ranking_page_mostra_subiu_e_desceu(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
            {"name": "Y", "score": 70, "position": 2},
        ]}])
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot",
        lambda: {"ts": 900.0, "items": [
            {"name": "X", "score": 75, "position": 3},
            {"name": "Y", "score": 70, "position": 1},
        ]})
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.latest_before",
        lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert "tendencia-alta" in body
    assert "tendencia-baixa" in body


def test_ranking_page_resumo_do_dia_sem_snapshot_antigo(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.latest_before",
        lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert "resumo-do-dia" not in body


def test_ranking_page_resumo_do_dia_com_snapshot_antigo(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 90, "position": 1},
            {"name": "Y", "score": 70, "position": 2},
        ]}])
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 60, "position": 2},
        ]})
    body = client.get("/ranking").data.decode("utf-8")
    assert "resumo-do-dia" in body
    assert "1 item novo no Top 20" in body
    assert "X" in body


def test_ranking_page_resumo_do_dia_sem_alta_nenhuma(client, monkeypatch):
    # Unico item em comum caiu de nota -- "maior alta" nao deve aparecer,
    # so' a contagem de novos (0, aqui).
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 40, "position": 1},
        ]}])
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "galaseca.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 90, "position": 1},
        ]})
    body = client.get("/ranking").data.decode("utf-8")
    assert "resumo-do-dia" in body
    assert "0 itens novos no Top 20" in body.replace("\n", " ")
    assert "maior alta" not in body


def test_usuario_logado_aparece_fora_de_conta(client, monkeypatch, tmp_path):
    """O context processor `_inject_usuario` deve disponibilizar
    `usuario` em QUALQUER página, não só nas rotas de /conta que já
    passavam explicitamente -- achado 2026-10-26: `/ranking` (e as
    outras 20 páginas com `_conta_link.html`) mostravam "Minha conta"
    genérico mesmo logado, porque `usuario` nunca chegava até elas."""
    monkeypatch.setattr(
        user_store, "get_user",
        lambda steamid, path=None: {
            "steamid": steamid, "persona_name": "Fulano",
            "avatar_url": "https://example.com/a.jpg",
        })
    monkeypatch.setattr(
        "galaseca.public_site.profile_fetcher._AVATARS_DIR", tmp_path)
    (tmp_path / "123.jpg").write_bytes(b"jpeg")
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/ranking").data.decode("utf-8")
    assert "Fulano" in body
    assert '<span class="conta-nome">Minha conta</span>' not in body
    assert 'class="conta-avatar" src="/conta/avatar.jpg"' in body
    # Nunca o host da Steam direto: fora da CSP, a imagem saía quebrada.
    assert "example.com/a.jpg" not in body


def test_avatar_sem_arquivo_em_disco_nao_renderiza_img(
        client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        user_store, "get_user",
        lambda steamid, path=None: {
            "steamid": steamid, "persona_name": "Fulano",
            "avatar_url": "https://example.com/a.jpg",
        })
    monkeypatch.setattr(
        "galaseca.public_site.profile_fetcher._AVATARS_DIR", tmp_path)
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/ranking").data.decode("utf-8")
    assert "conta-avatar" not in body
    assert client.get("/conta/avatar.jpg").status_code == 404


def test_rota_avatar_serve_o_arquivo_do_usuario_logado(
        client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "galaseca.public_site.profile_fetcher._AVATARS_DIR", tmp_path)
    (tmp_path / "123.jpg").write_bytes(b"jpeg-do-123")
    (tmp_path / "456.jpg").write_bytes(b"jpeg-do-456")
    assert client.get("/conta/avatar.jpg").status_code == 302  # sem login
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    resp = client.get("/conta/avatar.jpg")
    assert resp.status_code == 200
    assert resp.data == b"jpeg-do-123"


def test_usuario_nao_logado_mostra_entrar_com_steam(client):
    body = client.get("/ranking").data.decode("utf-8")
    assert "Entrar com Steam" in body
    assert "conta-pill" not in body


def test_cta_login_tem_legenda_de_proposito(client):
    """O botão sozinho não dizia por que logar -- legenda curta embaixo."""
    body = client.get("/").data.decode("utf-8")
    assert "entrar-cta-legenda" in body
    assert "portfólio" in body.lower()


def test_usuario_logado_nao_mostra_legenda_do_cta(client, monkeypatch):
    monkeypatch.setattr(
        user_store, "get_user",
        lambda steamid, path=None: {
            "steamid": steamid, "persona_name": "Fulano",
            "avatar_url": "https://example.com/a.jpg",
        })
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/").data.decode("utf-8")
    assert "entrar-cta-legenda" not in body


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
    monkeypatch.setattr("galaseca.scan_store.load_last_scan", lambda: None)
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
    monkeypatch.setattr("galaseca.public_site.server._ADMIN_PASSWORD_HASH", "")
    assert client.get("/admin").status_code == 404
    assert client.get("/admin/login").status_code == 404


def test_admin_sem_sessao_redireciona_pro_login(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_admin_login_senha_errada_nao_autentica(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    resp = client.post("/admin/login", data={"senha": "errada"})
    assert resp.status_code == 200
    assert "incorreta" in resp.data.decode("utf-8")
    assert client.get("/admin").status_code == 302


def test_admin_login_senha_certa_autentica_e_funciona(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    login = client.post("/admin/login", data={"senha": "segredo"})
    assert login.status_code == 302
    assert client.get("/admin").status_code == 200


def test_admin_logout_encerra_sessao(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    client.post("/admin/login", data={"senha": "segredo"})
    assert client.get("/admin").status_code == 200
    assert client.get("/admin/logout").status_code == 405
    assert client.post("/admin/logout", data={}).status_code == 403
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    logout = client.post("/admin/logout", data={"csrf_token": token})
    assert logout.status_code == 302
    assert client.get("/admin").status_code == 302


def test_status_mostra_grafico_e_buscas_populares(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.visits.serie_por_dia",
        lambda: [("2026-10-24", 3), ("2026-10-25", 5)])
    monkeypatch.setattr(
        "galaseca.public_site.server.buscas.mais_buscados",
        lambda limite=10: [("ak-47", 4)])
    monkeypatch.setattr(
        "galaseca.public_site.server.scan_store.load_historico_ciclos",
        lambda: [])
    body = client.get("/status").data.decode("utf-8")
    assert "grafico-historico" in body
    assert "ak-47" in body


# ── server: /status ──────────────────────────────────────────

def test_status_sem_historico(client, monkeypatch, tmp_path):
    from galaseca.public_site import uptime, visits
    monkeypatch.setattr(scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(uptime, "no_ar_desde", lambda: 0.0)
    monkeypatch.setattr(visits, "total", lambda: 0)
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "Ainda não há histórico".encode("utf-8") in resp.data


def test_status_mostra_ciclos_com_falha(client, monkeypatch, tmp_path):
    from galaseca.public_site import uptime, visits
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
    # Link da própria página do item, não da listagem da Steam --
    # achado 2026-11-01: quem clicava a partir do feed pulava direto
    # pra Steam, sem ver a nota/motivo que é o diferencial do feed.
    assert "<link>http://localhost/item/AK-47%20%7C%20Redline%20(Field-Tested)</link>" in body
    assert "steamcommunity.com/market/listings" not in body


def test_feed_filtrado_por_categoria(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [], "category": "Rifles"},
        {"name": "M9 Bayonet | Doppler", "score": 60,
         "price": 500.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [], "category": "Facas"},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/feed.xml?categoria=Facas").data.decode("utf-8")
    assert "M9 Bayonet" in body
    assert "AK-47" not in body
    # categoria inexistente -- ignora o filtro em vez de devolver vazio
    body_invalida = client.get("/feed.xml?categoria=NaoExiste").data.decode("utf-8")
    assert "AK-47" in body_invalida
    assert "M9 Bayonet" in body_invalida


def test_opensearch_xml(client):
    resp = client.get("/opensearch.xml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/opensearchdescription+xml"
    assert b"OpenSearchDescription" in resp.data
    assert b"searchTerms" in resp.data


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


def test_run_once_ranking_usa_maiores_notas_de_todo_o_scan(
        monkeypatch, tmp_path):
    # Ordem do scan: 25 itens nota 50 e só depois os dois melhores --
    # cortar antes de ordenar deixava os dois de fora do Top 20.
    resultados = ([{"name": f"R{i}", "score": 50} for i in range(25)]
                  + [{"name": "Caixa", "score": 90},
                     {"name": "Capsula", "score": 85}])
    original_save_snapshot = ranking.save_snapshot
    rank_path = tmp_path / "rankings.json"
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None: resultados)
    monkeypatch.setattr(worker.scan_store, "save_last_scan",
                        lambda cat, res: None)
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        worker.ranking, "save_snapshot",
        lambda res: original_save_snapshot(res, path=rank_path))

    worker.run_once({"Rifles": ["x"]})
    itens = ranking.load_snapshots(path=rank_path)[0]["items"]
    assert len(itens) == 20
    assert [it["name"] for it in itens[:2]] == ["Caixa", "Capsula"]


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
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [])
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
    monkeypatch.setenv("GALASECA_WORKER_INTERVAL_HORAS", "2")
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [2 * 3600]


def test_main_sem_env_usa_default(monkeypatch):
    monkeypatch.delenv("GALASECA_WORKER_INTERVAL_HORAS", raising=False)
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [worker._INTERVALO_HORAS_DEFAULT * 3600]


def test_main_parametro_explicito_ignora_env(monkeypatch):
    monkeypatch.setenv("GALASECA_WORKER_INTERVAL_HORAS", "99")
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [])
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
    body = resp.data.decode("utf-8")
    assert "scan está mais velho" in body
    assert "status-scan-desatualizado" in body
    assert "Dados coletados:" in body


def test_index_sem_banner_quando_scan_recente(client, monkeypatch, tmp_path):
    resultados = [{"name": "A", "score": 80, "price": 10.0, "case_label": "",
                  "pump_risk": {"level": "low"}, "breakdown": []}]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "scan está mais velho" not in body
    assert "status-scan-recente" in body


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
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "galaseca.public_site.server.scan_progress.carregar",
        lambda: {"indice": 10, "total": 185, "item": "Item X", "ts": time.time()})
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin")
    assert "Item X" in resp.data.decode("utf-8")


def test_admin_formata_quando_dos_ciclos_em_vez_de_timestamp_cru(
        client, monkeypatch):
    """Achado 2026-10-27: /status já formatava `c["ts"]` com idade_txt
    ("há X min") antes de passar pro template; /admin lia a mesma lista
    de scan_store.load_historico_ciclos e mostrava o epoch cru
    (`{{ c.ts|int }}`, tipo "1792500195") porque nunca recebeu o mesmo
    tratamento."""
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    ts_fixo = 1700000000.0  # epoch arbitrário, fixo -- não depende do "agora"
    monkeypatch.setattr(
        "galaseca.public_site.server.scan_store.load_historico_ciclos",
        lambda: [{"ts": ts_fixo, "itens": 152,
                 "duracao_min": 22.3, "sucesso": True}])
    client.post("/admin/login", data={"senha": "segredo"})
    body = client.get("/admin").data.decode("utf-8")
    assert "152 itens" in body
    assert "há " in body
    assert str(int(ts_fixo)) not in body  # nenhum epoch cru na página


# ── worker_alert ─────────────────────────────────────────────

def test_worker_alert_sem_webhook_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.delenv("GALASECA_ADMIN_DISCORD_WEBHOOK", raising=False)
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is False


def test_worker_alert_sucesso_recente_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.setenv("GALASECA_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    ciclos = [{"ts": time.time() - 100, "itens": 5}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is False


def test_worker_alert_manda_quando_atrasado(monkeypatch, tmp_path):
    monkeypatch.setenv("GALASECA_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(worker_alert.discord_notify, "enviar", lambda url, msg: True)
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is True


def test_worker_alert_dedup_nao_manda_de_novo(monkeypatch, tmp_path):
    monkeypatch.setenv("GALASECA_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
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


def test_comparar_main_sem_pagina_texto(client):
    """.pagina-texto trava <main> em 640px -- bom pra prosa, estreito
    demais pra uma tabela de 2-3 itens: com nome comprido, o texto do
    cabeçalho vazava visualmente pra fora da tabela (achado 2026-11-01).
    /comparar precisa da largura cheia de <main> (960px)."""
    body = client.get("/comparar").data.decode("utf-8")
    assert '<main id="conteudo">' in body
    assert 'class="pagina-texto"' not in body


def test_comparar_nota_fica_dentro_da_celula_certa(client, monkeypatch,
                                                    tmp_path):
    """achado 2026-10-31: a linha "Nota" aplicava class="nota ..." no
    próprio <td> (não num <span> dentro dele, como em index.html/
    item.html) -- .nota tem display:inline-block, que tira o <td> do
    layout de tabela e todas as notas colapsavam visualmente na
    primeira coluna. A nota precisa estar num <span> dentro do <td>."""
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item B", "score": 60, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A,Item B").data.decode("utf-8")
    assert '<td class="nota' not in body
    assert '<td><span class="nota nota-alta">80</span></td>' in body
    assert '<td><span class="nota nota-media">60</span></td>' in body


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
        "galaseca.public_site.server.db_backup._DB_PATH",
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
    monkeypatch.setattr("galaseca.public_site.server.db_backup._DB_PATH", db)
    resp = client.get("/readyz")
    assert resp.get_json()["ready"] is True


def test_readyz_com_banco_corrompido_nao_e_ready(client, monkeypatch, tmp_path):
    db = tmp_path / "corrompido.db"
    db.write_bytes(b"isto nao e um sqlite valido nem perto")
    monkeypatch.setattr("galaseca.public_site.server.db_backup._DB_PATH", db)
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


def test_item_detail_mostra_itens_da_caixa(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Chroma 2 Case", "score": 85, "price": 1.0, "case_label": "Descontinuada",
         "case": "Chroma 2 Case", "pump_risk": {"level": "low"},
         "category": "Caixas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/Chroma 2 Case").data.decode("utf-8")
    assert "Itens desta caixa" in body


def test_item_detail_sem_caixa_nao_mostra_card_de_itens(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert "Itens desta caixa" not in body


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

def _jpeg_minimo() -> bytes:
    """JPEG de verdade (2x2), não só bytes arbitrários -- a partir de
    2026-11-01 `icon_cache.obter()` reencoda pra WebP (ver
    `_reencodar_webp`), e `Image.open()` rejeita bytes que não são uma
    imagem válida."""
    from io import BytesIO as _BytesIO
    from PIL import Image
    buf = _BytesIO()
    Image.new("RGB", (2, 2), (200, 50, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def test_icon_cache_sem_hash_devolve_none():
    assert icon_cache.obter("") is None


def test_icon_cache_le_do_disco_sem_rede(monkeypatch, tmp_path):
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)
    p = icon_cache._caminho("abc123")
    # Leitura de cache-hit não reencoda -- devolve o que já tá no disco,
    # bytes arbitrários servem pra testar só esse caminho.
    p.write_bytes(b"fake-webp-bytes")

    def _boom(*a, **kw):
        raise AssertionError("não deveria bater na rede com cache em disco")

    import httpx
    monkeypatch.setattr(httpx, "get", _boom)
    assert icon_cache.obter("abc123") == b"fake-webp-bytes"


def test_icon_cache_falha_de_rede_devolve_none(monkeypatch, tmp_path):
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)

    def _boom(*a, **kw):
        raise OSError("rede fora")

    import httpx
    monkeypatch.setattr(httpx, "get", _boom)
    assert icon_cache.obter("semcache") is None


_HASH_REAL = (
    "i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM"
    "-vMGmW8VNxu5Dx60noTyL8ypexwjFS4_ega6F_H_eAMWrEwL9JtORqRiSygRI1jDCAnobsLGXB"
    "awMlXJohFLRY5BO5kILiMuzrsQTWi9gWnyr9insYuCZj5LtQVaEk5OSJ2CFIuQ75")


def test_icon_cache_preserva_hash_real_na_url(monkeypatch, tmp_path):
    """Hash da Steam tem "-" e "_" e ~200 caracteres. Um filtro
    `isalnum()[:128]` montava URL que dava 404 pra todo item -- nenhum
    ícone aparecia no site (2026-10-30)."""
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)
    pedidas = []

    class _Resp:
        status_code = 200
        content = _jpeg_minimo()

    def _get(url, **kw):
        pedidas.append((url, kw))
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    # Reencodado pra WebP (ver _reencodar_webp) -- não é mais o mesmo
    # byte-a-byte que `content`, só confere a assinatura do formato.
    assert icon_cache.obter(_HASH_REAL)[:4] == b"RIFF"
    url, kw = pedidas[0]
    assert f"/economy/image/{_HASH_REAL}/" in url
    assert kw.get("follow_redirects") is True
    assert icon_cache._caminho(_HASH_REAL).exists()


def test_icon_cache_sanitiza_hash_malicioso():
    assert icon_cache._sanitizar("../../etc/passwd") == "etcpasswd"


def test_icon_cache_reencodar_webp_converte_jpeg_valido():
    from PIL import Image
    from io import BytesIO
    saida = icon_cache._reencodar_webp(_jpeg_minimo())
    assert saida[:4] == b"RIFF"
    assert saida[8:12] == b"WEBP"
    with Image.open(BytesIO(saida)) as im:
        assert im.format == "WEBP"
        assert im.size == (2, 2)


def test_icon_cache_reencodar_webp_preserva_transparencia():
    from PIL import Image
    from io import BytesIO

    origem = BytesIO()
    imagem = Image.new("RGBA", (2, 2), (220, 40, 30, 255))
    imagem.putpixel((0, 0), (0, 0, 0, 0))
    imagem.save(origem, format="PNG")

    saida = icon_cache._reencodar_webp(origem.getvalue())

    with Image.open(BytesIO(saida)) as resultado:
        assert resultado.mode == "RGBA"
        assert resultado.getpixel((0, 0))[3] == 0
        assert resultado.getpixel((1, 1))[3] == 255


def test_icon_cache_reencodar_webp_bytes_invalidos_devolve_none():
    assert icon_cache._reencodar_webp(b"isso nao e uma imagem") is None


def test_icon_cache_obter_cacheia_webp_em_disco(monkeypatch, tmp_path):
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)

    class _Resp:
        status_code = 200
        content = _jpeg_minimo()

    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: _Resp())
    resultado = icon_cache.obter("novohash")
    assert resultado[:4] == b"RIFF"
    caminho = icon_cache._caminho("novohash")
    assert caminho.suffix == ".webp"
    assert caminho.read_bytes() == resultado


def test_rota_icone_sem_cache_redireciona_pro_cdn(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.icon_cache.obter", lambda h: None)
    resp = client.get("/icone/abc123.webp")
    assert resp.status_code == 302
    assert "steamstatic.com" in resp.headers["Location"]


def test_rota_icone_com_cache_serve_bytes(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.icon_cache.obter",
        lambda h: b"dados-da-imagem")
    resp = client.get("/icone/abc123.webp")
    assert resp.status_code == 200
    assert resp.data == b"dados-da-imagem"
    assert resp.mimetype == "image/webp"
    assert "max-age" in resp.headers.get("Cache-Control", "")


def test_rota_icone_tem_rate_limit(monkeypatch):
    """Sem login, cache miss grava arquivo novo em disco -- sem limite,
    um hash diferente por chamada enche o disco sem fim (achado
    2026-10-27 junto da sanitização em icon_cache.obter()). Mesmo
    gotcha de `rate_limited` avaliado na decoração: patcha ANTES de
    `create_app()`."""
    monkeypatch.setattr(
        "galaseca.public_site.server.icon_cache.obter", lambda h: b"x")
    monkeypatch.setattr(rate_limit, "ICON_MAX_HITS", 2)
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    for _ in range(2):
        assert c.get("/icone/abc123.webp").status_code == 200
    assert c.get("/icone/abc123.webp").status_code == 429


# ── rate limit nas rotas novas ───────────────────────────────

def test_api_recommendations_tem_rate_limit(monkeypatch):
    # Cria o app DEPOIS de patchear a constante: `rate_limited(...)` é
    # avaliado na hora da decoração (dentro de `create_app()`), não a
    # cada request -- usar o fixture `client` criaria o app antes do
    # monkeypatch valer; os limites são capturados ao criar o app.
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
    assert data["name"] == "sai daí, galaseca"
    assert data["start_url"] == "/"


def test_manifest_json_tem_icones_png(client):
    """iOS Safari historicamente não aceita SVG em apple-touch-icon, e o
    manifest do Android quer pelo menos um PNG 192x192/512x512 pra não
    cair num ícone genérico ao instalar -- antes só tinha o SVG (achado
    2026-11-01)."""
    data = client.get("/static/manifest.json").get_json()
    tamanhos = {icone["sizes"] for icone in data["icons"]}
    assert "192x192" in tamanhos
    assert "512x512" in tamanhos
    assert all(icone["type"] == "image/png" for icone in data["icons"]
               if icone["sizes"] != "any")

    for nome in ("icon-192.png", "icon-512.png"):
        resp = client.get(f"/static/{nome}")
        assert resp.status_code == 200
        assert resp.mimetype == "image/png"


def test_apple_touch_icon_usa_png_nao_svg(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    body = client.get("/").data.decode("utf-8")
    assert 'rel="apple-touch-icon" href="/static/icon-192.png' in body


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


def test_csp_report_corpo_vazio_ainda_responde_204(client):
    resp = client.post("/api/csp-report", data="")
    assert resp.status_code == 204


def test_icon_cache_caminho_sanitiza_hash_nao_alfanumerico():
    p = icon_cache._caminho("../../etc/passwd")
    assert ".." not in p.name
    assert "/" not in p.name
    assert p.parent == icon_cache._CACHE_DIR


def test_icon_cache_requisicao_de_rede_usa_hash_sanitizado(monkeypatch, tmp_path):
    """A rota `/icone/<hash>.webp` repassa o `<hash>` da URL direto pra
    `obter()`, sem validar -- qualquer visitante, sem login. Até
    2026-10-27 só `_caminho()` (o nome do arquivo em disco) sanitizava;
    a chamada de rede usava o hash cru. Trava que a URL batida de
    verdade contém só a parte alfanumérica, nunca o valor original com
    caractere estranho."""
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)
    urls_chamadas = []

    class _RespostaFalsa:
        status_code = 200
        content = _jpeg_minimo()

    def _get_falso(url, timeout=None, **kw):
        urls_chamadas.append(url)
        return _RespostaFalsa()

    import httpx
    monkeypatch.setattr(httpx, "get", _get_falso)

    resultado = icon_cache.obter("abc/../123?x=1")
    assert resultado[:4] == b"RIFF"
    assert len(urls_chamadas) == 1
    assert "abc123" in urls_chamadas[0]
    assert ".." not in urls_chamadas[0]
    assert "?x=1" not in urls_chamadas[0]


def test_readyz_com_db_path_sendo_diretorio(client, monkeypatch, tmp_path):
    diretorio = tmp_path / "isto_e_pasta"
    diretorio.mkdir()
    monkeypatch.setattr("galaseca.public_site.server.db_backup._DB_PATH", diretorio)
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


def test_faq_menciona_instalacao_pwa(client):
    body = client.get("/faq").data.decode("utf-8")
    assert "tela inicial" in body
    assert body.count('"@type": "Question"') == body.count("<h2 class=\"secao-titulo\">")


def test_glossario_page(client):
    resp = client.get("/glossario")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "DefinedTermSet" in body
    assert body.count('"@type": "DefinedTerm"') == body.count("<dt><strong>")
    assert "Steam Community Market" in body
    assert "Procura × Oferta" in body


def test_sitemap_inclui_faq(client):
    body = client.get("/sitemap.xml").data.decode("utf-8")
    assert "/faq" in body


def test_sitemap_inclui_paginas_de_item_mas_nao_as_de_risco_alto(
        client, monkeypatch, tmp_path):
    """Cada página de item já tem título/descrição/JSON-LD própria --
    sem link no sitemap, um crawler só as acha via paginação da home.
    Mas a lista precisa ser a MESMA que `item_detail` serve (mesmo
    filtro de `_candidatos_filtrados`): um nome fora dela dá 404 na
    página de item, então não pode aparecer aqui -- caso contrário o
    próprio sitemap manda o crawler pra uma URL quebrada."""
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 70, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "AWP | Dragon Lore (Factory New)", "score": 80,
         "price": 5000.0, "case_label": "",
         "pump_risk": {"level": "high"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/sitemap.xml").data.decode("utf-8")
    assert "/item/AK-47%20%7C%20Redline%20(Field-Tested)" in body
    assert "Dragon%20Lore" not in body
    assert client.get(
        "/item/AK-47 | Redline (Field-Tested)").status_code == 200


# ── Lote 8: admin -- disco, usuarios, webhook, log bruto ────

def test_admin_mostra_disco_e_usuarios(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
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
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.post("/admin/testar-webhook", data={})
    assert resp.status_code == 403


def test_admin_testar_webhook_com_csrf_funciona(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "galaseca.public_site.server.discord_notify.enviar",
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
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr("galaseca.public_site.server._ERROR_LOG_PATH", log)
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin/log-bruto")
    assert resp.status_code == 200
    assert b"linha de erro" in resp.data


def test_admin_backup_download_sem_sessao_e_404(client):
    resp = client.get("/admin/backup/public_site-20261026-120000.db")
    assert resp.status_code == 404


def test_admin_backup_download_com_sessao_baixa_arquivo(client, monkeypatch, tmp_path):
    backup = tmp_path / "public_site-20261026-120000.db"
    backup.write_bytes(b"dados falsos de sqlite")
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "galaseca.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin/backup/public_site-20261026-120000.db")
    assert resp.status_code == 200
    assert resp.data == b"dados falsos de sqlite"


def test_admin_backup_download_rejeita_nome_fora_do_padrao(client, monkeypatch, tmp_path):
    # Caso que a validação por regex existe pra pegar: nome que tenta
    # escapar do diretório de backups ou que simplesmente não é um
    # backup de verdade.
    alvo = tmp_path / "secreto.txt"
    alvo.write_text("não deveria ser servido", encoding="utf-8")
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "galaseca.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    for nome in ("../secreto.txt", "secreto.txt", "public_site-123.db",
                "public_site-20261026-120000.db.bak"):
        resp = client.get(f"/admin/backup/{nome}")
        assert resp.status_code in (404, 400), nome


def test_admin_backup_download_arquivo_inexistente_e_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "galaseca.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin/backup/public_site-20261026-120000.db")
    assert resp.status_code == 404


def test_admin_lista_backups_tem_link_de_download(client, monkeypatch, tmp_path):
    backup = tmp_path / "public_site-20261026-120000.db"
    backup.write_bytes(b"x")
    monkeypatch.setattr(
        "galaseca.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "galaseca.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    body = client.get("/admin").data.decode("utf-8")
    assert "/admin/backup/public_site-20261026-120000.db" in body


def test_disco_info_nao_quebra_sem_dados():
    from galaseca.public_site.server import _disco_info
    info = _disco_info()
    assert "livre_fmt" in info


def test_contagem_usuarios_sem_banco_e_zero(monkeypatch, tmp_path):
    from galaseca.public_site.server import _contagem_usuarios
    monkeypatch.setattr(
        "galaseca.public_site.server.db_backup._DB_PATH",
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

    caminho = (Path(__file__).parent.parent / "galaseca" / "public_site"
              / "static" / "style.css")
    css = caminho.read_text(encoding="utf-8")
    abre = len(re.findall(re.escape("/*"), css))
    fecha = len(re.findall(re.escape("*/"), css))
    assert abre == fecha, (
        f"{abre} '/*' contra {fecha} '*/' -- algum comentário não fechou "
        "e pode estar engolindo CSS real (ver style.css)")


def test_classes_com_hidden_tem_guarda_display_none():
    """Gotcha #16 do AGENTS.md: `.classe { display: ... }` tem
    especificidade maior que o `[hidden]` da UA stylesheet sozinho, então
    um elemento que nasce `hidden` no HTML aparece visível mesmo assim se
    a classe define `display`. Já mordeu 3 vezes (.add-item-form,
    .stat-row, .barra-comparar -- achada ao vivo nesta rodada: a barra de
    comparar aparecia com "0/3 selecionados" na tela toda, mesmo sem
    nada marcado). Esta varredura confere TODA classe usada junto de
    `hidden` num template contra uma guarda `.classe[hidden] { display:
    none; }` no CSS, pra pegar a próxima de uma vez."""
    import re
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "galaseca" / "public_site"
    css = (raiz / "static" / "style.css").read_text(encoding="utf-8")

    classes_com_hidden = set()
    for template in (raiz / "templates").rglob("*.html"):
        html = template.read_text(encoding="utf-8")
        for tag in re.findall(r"<[a-z][^>]*>", html):
            if re.search(r"\bhidden\b", tag):
                m = re.search(r'class="([^"]+)"', tag)
                if m:
                    classes_com_hidden.update(m.group(1).split())

    # Regras CSS sem comentario, pra nao confundir selector comentado.
    css_sem_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

    # Só SELETORES COMPOSTOS SIMPLES contam pra "define display" -- um
    # seletor descendente tipo ".modo-apresentacao .classe { display:
    # none }" é condicional a um ancestral, não sobrescreve o `[hidden]`
    # sozinho (e já é `display: none`, então nem seria o bug mesmo).
    regras_simples = []  # [(seletor_composto, corpo)]
    for seletores, corpo in re.findall(r"([^{}]+)\{([^{}]*)\}", css_sem_comentarios):
        for sel in seletores.split(","):
            sel = sel.strip()
            if sel and not re.search(r"[\s>+~]", sel):
                regras_simples.append((sel, corpo))

    sem_guarda = []
    for classe in sorted(classes_com_hidden):
        token = f".{classe}"
        define_display = any(
            token in sel and "[hidden]" not in sel and "display" in corpo
            for sel, corpo in regras_simples)
        if not define_display:
            continue  # classe nunca define display sozinha -- [hidden] da UA basta
        tem_guarda = any(
            token in sel and "[hidden]" in sel
            and re.search(r"display\s*:\s*none", corpo)
            for sel, corpo in regras_simples)
        if not tem_guarda:
            sem_guarda.append(classe)

    assert not sem_guarda, (
        f"Classe(s) usadas com `hidden` no HTML, com `display` no CSS, "
        f"sem guarda `.classe[hidden] {{ display: none; }}`: {sem_guarda} "
        "-- o elemento aparece mesmo hidden")


def test_todas_as_custom_properties_usadas_estao_definidas():
    """`var(--token)` sem a definição correspondente em `:root` cai pro
    valor inicial da propriedade em vez de dar erro -- quebra silenciosa
    (ex. `border-radius: var(--raio-sm)` com typo vira `border-radius:
    0`, sem aviso nenhum no navegador). Varredura pega isso sem precisar
    de um parser CSS de verdade."""
    import re
    from pathlib import Path

    css = (Path(__file__).parent.parent / "galaseca" / "public_site"
          / "static" / "style.css").read_text(encoding="utf-8")
    m = re.search(r":root\s*\{([^}]*)\}", css)
    definidas = set(re.findall(r"--([\w-]+)\s*:", m.group(1)))
    usadas = set(re.findall(r"var\(--([\w-]+)\)", css))
    faltando = usadas - definidas
    assert not faltando, f"var(--x) sem definição em :root: {faltando}"


def test_nenhum_template_usa_style_inline():
    """O CSP do site (`style-src 'self'`, sem 'unsafe-inline') bloqueia
    TODO atributo `style="..."` -- o navegador descarta em silêncio, só
    com um aviso no console, sem quebrar a página visivelmente na hora.
    Achado ao vivo em 2026-10-27: `<col style="width: 28%">` no
    colgroup_itens() nunca funcionou em produção por causa disso --
    table-layout:fixed sem nenhuma largura aplicada caiu pra distribuição
    ~igual entre colunas, truncando o nome do item pra "P…". Largura
    (ou qualquer outro valor) tem que vir de uma classe CSS, nunca de
    `style=` inline."""
    import re
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "galaseca" / "public_site" / "templates"
    com_style_inline = []
    for template in raiz.rglob("*.html"):
        html = template.read_text(encoding="utf-8")
        if re.search(r'''\sstyle\s*=\s*["']''', html):
            com_style_inline.append(str(template.relative_to(raiz)))

    assert not com_style_inline, (
        f"Template(s) com style=\"...\" inline, bloqueado pelo CSP "
        f"style-src 'self': {com_style_inline}")


def test_colunas_da_tabela_principal_somam_100_por_cento():
    """As classes que substituíram `<col style="width: ...">` (ver teste
    acima) precisam continuar somando 100% -- senão table-layout:fixed
    sobra/falta espaço na última coluna."""
    import re
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "galaseca" / "public_site"
    css = (raiz / "static" / "style.css").read_text(encoding="utf-8")
    html = (raiz / "templates" / "index.html").read_text(encoding="utf-8")

    classes_no_colgroup = re.findall(r'<col class="(col-\w+)">', html)
    assert len(classes_no_colgroup) == 6, (
        f"Esperava 6 colunas no colgroup_itens(), achei {len(classes_no_colgroup)}")

    total = 0
    for classe in classes_no_colgroup:
        m = re.search(r"\." + re.escape(classe) + r"\s*\{\s*width:\s*(\d+)%", css)
        assert m, f"Classe {classe} usada no colgroup mas sem regra de largura em style.css"
        total += int(m.group(1))
    assert total == 100, f"Larguras das colunas somam {total}%, não 100%"


# ── Rodada 4: acessibilidade -- skip-link + noindex em todo template ──

def test_todo_template_tem_skip_link_e_main_com_id():
    """Até 2026-10-26 só `index.html` tinha o link "Pular pro conteúdo"
    e `id="conteudo"` no `<main>` -- as outras 21 páginas (item, ranking,
    conta/*, admin/*, erro 404/429/500 etc.) não tinham nenhum dos dois,
    deixando quem navega só por teclado sem atalho pra pular a barra
    superior. Varredura genérica pra nunca faltar de novo numa página
    nova."""
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "galaseca" / "public_site" / "templates"
    sem_skip_link = []
    sem_main_id = []
    for template in raiz.glob("*.html"):  # só as páginas, não partials/
        html = template.read_text(encoding="utf-8")
        if "link-pular-conteudo" not in html:
            sem_skip_link.append(template.name)
        if 'id="conteudo"' not in html:
            sem_main_id.append(template.name)

    assert not sem_skip_link, f"Sem skip-link: {sem_skip_link}"
    assert not sem_main_id, f"<main> sem id=\"conteudo\": {sem_main_id}"


def test_paginas_de_conta_sao_noindex():
    """Páginas pessoais atrás de login nunca devem ser indexadas --
    defesa em profundidade (já não aparecem em sitemap.xml, mas um
    crawler pode achar por outro caminho, ex. um link direto)."""
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "galaseca" / "public_site" / "templates"
    paginas = ["conta.html", "conta_excluir.html", "conta_historico.html",
              "conta_trades.html", "conta_watchlist.html"]
    sem_noindex = [
        p for p in paginas
        if "noindex" not in (raiz / p).read_text(encoding="utf-8")
    ]
    assert not sem_noindex, f"Sem <meta name=\"robots\" content=\"noindex\">: {sem_noindex}"


def test_todo_campo_de_formulario_tem_nome_acessivel():
    """Até 2026-10-27, as 4 telas de /conta (adicionar posição, editar
    custo, registrar trade, adicionar à watchlist, webhook do Discord) e
    o login do /admin usavam só `placeholder=`/`title=` pra identificar
    cada campo -- nenhum dos dois é nome acessível de verdade (o
    placeholder some ao digitar, e leitor de tela não anuncia `title`
    como rótulo). `index.html`/`404.html` já faziam certo com `<label>`
    envolvendo o campo; as telas de `/conta` ficaram pra trás. Varredura
    genérica, no mesmo espírito de `test_todo_template_tem_skip_link_e_
    main_com_id`, pra nenhum campo novo repetir o gap: todo `<input>`
    visível (não hidden/submit/checkbox) precisa ter `aria-label=` OU
    estar dentro de um `<label>...</label>`."""
    import re
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "galaseca" / "public_site" / "templates"
    sem_nome_acessivel = []
    for template in raiz.rglob("*.html"):
        html = template.read_text(encoding="utf-8")
        blocos_label = re.findall(r"<label\b.*?</label>", html, flags=re.S)
        for campo in re.findall(r"<input\b[^>]*>", html):
            tipo = re.search(r'type="([^"]+)"', campo)
            if tipo and tipo.group(1) in ("hidden", "submit", "checkbox", "radio"):
                continue
            if "aria-label=" in campo or "aria-labelledby=" in campo:
                continue
            if any(campo in bloco for bloco in blocos_label):
                continue
            sem_nome_acessivel.append(f"{template.name}: {campo[:70]}")

    assert not sem_nome_acessivel, (
        "Campo(s) sem aria-label nem <label> envolvendo: " + "; ".join(sem_nome_acessivel))


def test_nav_de_conta_marca_pagina_ativa(client, monkeypatch):
    monkeypatch.setattr(
        "galaseca.public_site.server.user_store.get_user",
        lambda steamid, path=None: None)
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/conta/trades").data.decode("utf-8")
    assert 'href="/conta/trades" aria-current="page"' in body
    assert 'href="/conta/watchlist" aria-current="page"' not in body


# ── Rodada 3: performance -- historico so' pra fatia visivel ──

def test_candidatos_filtrados_sem_historico_nao_calcula_sparkline():
    from galaseca.public_site.server import _candidatos_filtrados
    scan = {"ts": time.time(), "category": "x", "results": [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]}
    out = _candidatos_filtrados(scan, com_historico=False)
    assert "sparkline" not in out[0]
    assert "tendencia" not in out[0]


def test_enriquecer_com_historico_preenche_campos(monkeypatch):
    from galaseca.public_site.server import _enriquecer_com_historico
    monkeypatch.setattr(
        "galaseca.public_site.server.signals.load_item_history",
        lambda name: [{"ts": 1, "price": 10.0}, {"ts": 2, "price": 12.0}])
    candidatos = [{"name": "Item A"}]
    _enriquecer_com_historico(candidatos)
    assert candidatos[0]["tendencia"] == "alta"
    assert "mini-sparkline" in candidatos[0]["sparkline"]


def test_index_so_enriquece_a_pagina_atual(client, monkeypatch, tmp_path):
    """152 candidatos, só 10 por página -- load_item_history não pode
    ser chamado mais que o necessário pra essa página (acrescido de uma
    pequena folga, caso algum outro ponto do request chame por outro
    motivo)."""
    resultados = [
        {"name": f"Item {i:03d}", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(152)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    chamadas = []

    def _contado(name, *a, **kw):
        chamadas.append(name)
        return []

    monkeypatch.setattr(
        "galaseca.public_site.server.signals.load_item_history", _contado)
    resp = client.get("/")
    assert resp.status_code == 200
    assert len(chamadas) <= 15  # página de 10 + folga, nunca os 152


def test_item_detail_nao_calcula_historico_dos_outros_candidatos(client, monkeypatch, tmp_path):
    """Mesma família do teste acima (`test_index_so_enriquece_a_pagina_
    atual`) -- `/item/<nome>` mostra UM item, mas até 2026-10-27 chamava
    `_candidatos_filtrados` com o default `com_historico=True`, lendo
    tendência/sparkline dos ~150 candidatos inteiros à toa (nem
    `item.html` nem `_itens_parecidos` usam esses dois campos vindos
    dali -- o gráfico da página usa `signals.load_item_history`
    diretamente, numa chamada à parte)."""
    resultados = [
        {"name": f"Item {i:03d}", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(152)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    chamadas = []

    def _contado(name, *a, **kw):
        chamadas.append(name)
        return []

    monkeypatch.setattr(
        "galaseca.public_site.server.signals.load_item_history", _contado)
    resp = client.get("/item/Item 000")
    assert resp.status_code == 200
    assert len(chamadas) <= 2  # só a chamada do gráfico da própria página


def test_comparar_so_enriquece_os_itens_comparados(client, monkeypatch, tmp_path):
    """Mesma família -- `/comparar` mostra no máximo 3 itens
    (`comparar.html` usa `tendencia`), mas até 2026-10-27 calculava
    histórico dos ~150 candidatos inteiros pra exibir só os comparados."""
    resultados = [
        {"name": f"Item {i:03d}", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(152)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    chamadas = []

    def _contado(name, *a, **kw):
        chamadas.append(name)
        return []

    monkeypatch.setattr(
        "galaseca.public_site.server.signals.load_item_history", _contado)
    resp = client.get("/comparar?nomes=Item 000,Item 001,Item 002")
    assert resp.status_code == 200
    assert len(chamadas) <= 3  # só os 3 itens comparados, nunca os 152


def test_index_explica_categoria_sem_coleta(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "category": "Rifles", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ], category="Rifles")
    body = client.get("/?categoria=Facas").data.decode("utf-8")

    assert "A categoria Facas ainda não tem itens coletados" in body
    assert "Nenhum candidato com esses filtros" not in body
    assert "Facas (sem dados ainda)" in body


def test_item_detail_nao_repete_motivos(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço 18% abaixo do típico (+20)"}]},
    ])
    body = client.get("/item/AK-47 | Redline (Field-Tested)").data.decode(
        "utf-8")
    main = body[body.index("<main"):]

    assert main.count("Preço 18% abaixo do típico (+20)") == 1


def test_index_traduz_caixa_igual_coluna_item(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AWP | Lightning Strike (Factory New)", "score": 70,
         "price": 600.0,
         "case_label": "CS:GO Weapon Case (descontinuada, 2013)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")

    assert ">Caixa CS:GO Weapon (descontinuada, 2013)</span>" in body
    assert "<title>sai daí, galaseca</title>" in body


def test_feed_e_api_nao_leem_historico_de_todos_os_itens(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": f"Item {i}", "score": 60, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(30)
    ])
    lidos = []
    monkeypatch.setattr(signals, "load_item_history",
                        lambda name: lidos.append(name) or [])

    assert client.get("/feed.xml").status_code == 200
    assert lidos == []

    resp = client.get("/api/recommendations")
    assert len(resp.get_json()["candidatos"]) == 20
    assert len(lidos) == 20
    assert "sparkline" in resp.get_json()["candidatos"][0]


def test_coluna_caixa_nao_repete_nome_da_propria_capsula(
        client, monkeypatch, tmp_path):
    nome = "Shanghai 2024 Legends Sticker Capsule"
    _salva_scan(tmp_path, monkeypatch, [
        {"name": nome, "score": 82, "price": 3.07,
         "case_label": f"{nome} (descontinuada, 2024)",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "AK-47 | Redline (Field-Tested)", "score": 69, "price": 170.0,
         "case_label": "Operation Phoenix Weapon Case (descontinuada, 2014)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")

    assert ">Descontinuada · 2024</span>" in body
    assert f">{nome} (descontinuada, 2024)</span>" not in body
    assert ">Caixa Fênix da Operação (descontinuada, 2014)</span>" in body


def test_favoritos_fora_da_pagina_e_estilos_da_tabela(client):
    from pathlib import Path
    body = client.get("/").data.decode("utf-8")
    static = Path(client.application.root_path) / "static"
    css = (static / "style.css").read_text(encoding="utf-8")
    js = (static / "app.js").read_text(encoding="utf-8")

    assert 'id="lista-favoritos-fora"' in body or "Ainda não há" in body
    assert "mostrarFavoritosFora(Object.keys(favoritos))" in js
    assert "a.textContent = nome" in js  # nunca innerHTML com dado do usuário
    ordenar = css[css.index(".link-ordenar {"):]
    assert "font-size: inherit" in ordenar[:ordenar.index("}")]
    checkbox = css[css.index(".checkbox-comparar {"):]
    assert "appearance: none" in checkbox[:checkbox.index("}")]


def test_run_once_registra_itens_sem_miniatura(monkeypatch, caplog):
    import logging
    resultados = [{"name": "A", "score": 60, "icon": "h"},
                  {"name": "B", "score": 50}]
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None: resultados)
    monkeypatch.setattr(worker.scan_store, "save_last_scan", lambda *a: None)
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda *a, **kw: None)
    monkeypatch.setattr(worker.ranking, "save_snapshot", lambda res: None)

    with caplog.at_level(logging.INFO):
        worker.run_once({"Rifles": ["A", "B"]})
    assert "Itens sem miniatura: 1 de 2" in caplog.text


def test_espera_ate_proximo_ciclo_conta_do_ultimo_ciclo(monkeypatch):
    agora = 1_800_000_000.0
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [
        {"ts": agora - 5 * 3600}, {"ts": agora - 3600}])

    assert worker.espera_ate_proximo_ciclo(6, now=agora) == 5 * 3600
    assert worker.espera_ate_proximo_ciclo(0.5, now=agora) == 0.0


def test_espera_ate_proximo_ciclo_sem_historico_e_zero(monkeypatch):
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [])
    assert worker.espera_ate_proximo_ciclo(6) == 0.0


def test_main_reiniciado_logo_apos_ciclo_espera_antes_de_escanear(
        monkeypatch):
    # Reiniciar o worker (deploy) não pode disparar um scan fora da cadência.
    agora = time.time()
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos",
                        lambda: [{"ts": agora - 3600}])
    escaneou = []
    monkeypatch.setattr(worker, "run_once", lambda: escaneou.append(1))
    esperas = []

    def _fake_sleep(segundos):
        esperas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    try:
        worker.main(intervalo_horas=6)
    except KeyboardInterrupt:
        pass
    assert escaneou == []
    assert 5 * 3600 - 5 < esperas[0] <= 5 * 3600
