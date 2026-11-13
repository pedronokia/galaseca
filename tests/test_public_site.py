"""Testes do site público (Fase 1) -- servidor (Flask test client) + worker.

Sem rede: `server.py` só lê `scan_store`, nunca fala com a Steam. Os
testes de `worker.py` mockam `scan_engine.run_full_scan`.
"""
from __future__ import annotations

import html
import json
import re
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from werkzeug.security import generate_password_hash

from lodout import ranking, scan_store, signals
from lodout.public_site import (
    changelog, charts, erro_stats, fmt, icon_cache, latencia, rate_limit,
    scan_progress, user_store, visits, worker, worker_alert,
)
from lodout.public_site import server
from lodout.public_site.server import create_app


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
    body = resp.data.decode("utf-8")
    assert "Ainda não há dados de coleta publicados" in body
    assert 'href="/status">Acompanhar status da coleta</a>' in body


def test_navegacao_principal_indica_pagina_atual(client):
    body = client.get("/metodo").data.decode("utf-8")
    nav = body.split('class="nav-principal"', 1)[1].split("</nav>", 1)[0]
    assert 'href="/metodo" aria-current="page">Método</a>' in nav
    assert 'href="/faq"' in nav


def test_navegacao_inferior_do_celular(client):
    # item #20: barra fixa na base, só visível abaixo de 640px (o CSS
    # esconde; aqui conferimos que o markup e o estado atual existem).
    body = client.get("/ranking").data.decode("utf-8")
    nav = body.split('class="nav-inferior"', 1)[1].split("</nav>", 1)[0]
    assert 'href="/ranking" aria-current="page"' in nav
    assert 'href="/metodo"' in nav
    assert 'href="/faq"' in nav
    assert 'href="/status"' in nav
    assert "icone-ui-inicio" in nav
    assert "icone-ui-ranking" in nav


def test_rodape_mostra_grade_por_categoria(client):
    """Achado 2026-11-03: a 1a versão em grid de 3 colunas ("Explorar"/
    "Entenda"/"Mais") tinha uma caixa de destaque estranha no link da
    página atual e virava 2 colunas desalinhadas no celular -- revertida
    pra lista simples. Rodada 3 (pedido novo, referência apple.com) traz
    a grade de volta com os dois problemas corrigidos: aria-current é só
    semântico aqui (sem classe/estilo específico ligado a ele -- ver
    teste abaixo) e o CSS força 1 coluna no celular."""
    body = client.get("/").data.decode("utf-8")
    rodape = body.split("<footer", 1)[1]
    assert 'href="/privacidade"' in rodape
    assert 'href="/ranking"' in rodape
    assert "Sugerir melhoria" in rodape
    assert 'class="rodape-nav"' in rodape
    assert rodape.count('class="rodape-nav-grupo"') == 3


def test_rodape_link_da_pagina_atual_nao_tem_classe_propria(client):
    """Acompanha o achado 2026-11-03 (ver teste acima): aria-current no
    rodapé não pode carregar nenhuma classe/estilo próprio -- foi o
    "fundo + box-shadow só nele" que lia como bug da vez passada. Fica
    puramente semântico pra leitor de tela."""
    body = client.get("/").data.decode("utf-8")
    rodape = body.split("<footer", 1)[1]
    tag = re.search(r'<a\b[^>]*aria-current="page"[^>]*>', rodape)
    assert tag, "esperava um link com aria-current no rodapé"
    assert "class=" not in tag.group(0)


def test_movimento_reduzido_respeitado_no_css_e_no_botao_de_topo(client):
    css = client.get("/static/style.css").data.decode("utf-8")
    js = client.get("/static/app.js").data.decode("utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert '(prefers-reduced-motion: reduce)' in js
    assert 'behavior: reduzirMovimento ? "auto" : "smooth"' in js


def test_contraste_muted_e_alvos_do_cabecalho(client):
    css = client.get("/static/style.css").data.decode("utf-8")
    root = re.search(r":root\s*\{([^}]*)\}", css)
    assert root
    tokens = dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", root.group(1)))

    def luminancia(cor):
        canais = [int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        canais = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
                  for v in canais]
        return 0.2126 * canais[0] + 0.7152 * canais[1] + 0.0722 * canais[2]

    frente = luminancia(tokens["text-muted"])
    fundo = luminancia(tokens["surface-hover"])
    contraste = (max(frente, fundo) + 0.05) / (min(frente, fundo) + 0.05)

    assert contraste >= 4.5
    assert re.search(r"\.conta-link-entrar\s*\{[^}]*min-height:\s*44px", css)
    assert ".topo-linha > .nav-principal { grid-column: 1 / -1; grid-row: 2; }" in css


def test_index_tabela_wrap_focavel_por_teclado(client, monkeypatch, tmp_path):
    """Achado 2026-11-02 (pesquisa de acessibilidade): `.tabela-wrap` tem
    overflow-x: auto (rola a tabela em telas estreitas), mas sem
    role="region"/tabindex/aria-label não dava pra focar e rolar só com
    teclado -- só mouse/touch."""
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/?ver=lista").data.decode("utf-8")
    assert 'class="tabela-wrap" role="region" tabindex="0" aria-label="Tabela de itens recomendados, com rolagem lateral"' in body


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


def test_index_tem_popover_legenda_raridade(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert 'class="popover-legenda"' in body
    popover = body.split('class="popover-legenda"', 1)[1].split("</details>", 1)[0]
    assert "Cores da borda" in popover
    for classe, rotulo in [
        ("raridade-consumer", "Consumer Grade"),
        ("raridade-industrial", "Industrial Grade"),
        ("raridade-milspec", "Mil-Spec"),
        ("raridade-restricted", "Restricted"),
        ("raridade-classified", "Classified"),
        ("raridade-covert", "Covert"),
        ("raridade-dourado", "faca, luva ou contrabando"),
    ]:
        assert classe in popover
        assert rotulo in popover


def test_index_sem_scan_nao_mostra_popover_legenda(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    body = client.get("/").data.decode("utf-8")
    assert "popover-legenda" not in body


def test_index_mostra_resumo_do_dia_com_alta_e_queda(client, monkeypatch, tmp_path):
    # item #19 da lista de melhorias -- mesma fonte (snapshot do Top 20)
    # já usada no Ranking, agora também na home.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 90, "position": 1},
            {"name": "Y", "score": 20, "position": 2},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 60, "position": 1},
            {"name": "Y", "score": 50, "position": 2},
        ]})
    body = client.get("/").data.decode("utf-8")
    assert 'class="resumo-do-dia"' in body
    resumo = body.split('class="resumo-do-dia"', 1)[1].split("</p>", 1)[0]
    # Polimento 2026-11-13: a home não repete mais "maior alta"/"maior
    # queda" na frase -- essa informação já vem (com mais detalhe) nos
    # cards de movimentos-do-dia logo abaixo. ranking.html continua
    # citando maior_alta na própria frase (não tem os cards).
    assert "maior alta de nota foi" not in resumo
    assert "maior queda foi" not in resumo
    assert "0 itens novos" in resumo
    # item #19: mini-cards com os vaivens de nota, pra alta E pra baixa
    assert 'class="movimentos-do-dia"' in body
    cards = body.split('class="movimentos-do-dia"', 1)[1].split("</ul>", 1)[0]
    assert "X" in cards
    assert "Y" in cards
    assert "movimento-alta" in cards
    assert "movimento-baixa" in cards
    assert "+30 na nota" in cards
    assert "-30 na nota" in cards


def test_index_resumo_do_dia_mostra_mesmo_sem_mudanca_de_nota(client, monkeypatch, tmp_path):
    # item #C do planejamento de melhorias maiores (2026-11-08):
    # novos_no_top já era calculado em _resumo_do_dia mas só aparecia no
    # Ranking -- a home descartava o dado. Mostra mesmo quando nenhuma
    # nota mudou, desde que haja um snapshot antigo pra comparar.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 90, "position": 1},
            {"name": "Y", "score": 50, "position": 2},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 90, "position": 1},
        ]})
    body = client.get("/").data.decode("utf-8")
    assert 'class="resumo-do-dia"' in body
    resumo = body.split('class="resumo-do-dia"', 1)[1].split("</p>", 1)[0]
    assert "1 item novo" in resumo
    assert "maior alta de nota foi" not in resumo
    assert "movimentos-do-dia" not in body


def test_index_movimentos_do_dia_limita_a_tres_e_ordena_por_tamanho(
        client, monkeypatch, tmp_path):
    # item #19: so os 3 maiores vaivens (em modulo) viram card, sem
    # escolher "melhor" item -- alta e queda contam igual.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "A1", "score": 50, "position": 1},
            {"name": "A2", "score": 50, "position": 2},
            {"name": "A3", "score": 50, "position": 3},
            {"name": "A4", "score": 50, "position": 4},
            {"name": "A5", "score": 50, "position": 5},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "A1", "score": 45, "position": 1},   # +5
            {"name": "A2", "score": 58, "position": 2},   # -8
            {"name": "A3", "score": 30, "position": 3},   # +20
            {"name": "A4", "score": 48, "position": 4},   # +2
            {"name": "A5", "score": 39, "position": 5},   # +11
        ]})
    body = client.get("/").data.decode("utf-8")
    cards = body.split('class="movimentos-do-dia"', 1)[1].split("</ul>", 1)[0]
    assert cards.count('class="movimento-do-dia"') == 3
    # Ordem: +20 (A3), +11 (A5), -8 (A2). Os pequenos (+5, +2) ficam fora.
    pos_a3 = cards.index("A3")
    pos_a5 = cards.index("A5")
    pos_a2 = cards.index("A2")
    assert pos_a3 < pos_a5 < pos_a2
    assert "A1" not in cards
    assert "A4" not in cards


def test_index_resumo_do_dia_some_com_filtro_ativo(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 90, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 60, "position": 1},
        ]})
    body = client.get("/?nota_min=50").data.decode("utf-8")
    assert "resumo-do-dia" not in body


def test_index_resumo_do_dia_some_na_pagina_2(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": f"Item {i}", "score": 100 - i, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(15)
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 90, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 60, "position": 1},
        ]})
    body = client.get("/?pagina=2").data.decode("utf-8")
    assert "resumo-do-dia" not in body


def test_index_mostra_hero_destaque_com_maior_nota(client, monkeypatch, tmp_path):
    # Hero "nota mais alta hoje" (revisão de direção visual 2026-11-08).
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item Baixo", "score": 40, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item Alto", "score": 95, "price": 2.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 10,
                        "label": "Preço baixo (+10)"}]},
    ])
    body = client.get("/").data.decode("utf-8")
    assert 'class="hero-destaque"' in body
    hero = body.split('class="hero-destaque"', 1)[1].split("</section>", 1)[0]
    assert "Nota mais alta hoje" in hero
    assert "Item Alto" in hero
    assert "Item Baixo" not in hero
    assert ">95<" in hero
    assert 'href="/item/Item%20Alto"' in hero


def test_index_hero_destaque_some_com_filtro_ativo(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/?nota_min=50").data.decode("utf-8")
    assert "hero-destaque" not in body


def test_index_hero_destaque_some_na_pagina_2(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": f"Item {i}", "score": 100 - i, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(15)
    ])
    body = client.get("/?pagina=2").data.decode("utf-8")
    assert "hero-destaque" not in body


def test_index_hero_destaque_some_ordenado_por_preco(client, monkeypatch, tmp_path):
    # candidatos_pagina[0] só é "o maior nota" quando a ordenação é por
    # nota -- ordenado por preço, o primeiro item pode ter qualquer nota.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/?ordenar=preco").data.decode("utf-8")
    assert "hero-destaque" not in body


def test_index_hero_destaque_some_sem_candidato(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [])
    body = client.get("/").data.decode("utf-8")
    assert "hero-destaque" not in body


def test_index_hero_destaque_tem_nota_grande_sobre_100(client, monkeypatch, tmp_path):
    """Rodada 2 do visual: o anel compacto deu lugar ao número grande +
    "/100" -- é o momento tipográfico da home."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item Alto", "score": 95, "price": 2.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    hero = body.split('class="hero-destaque"', 1)[1].split("</section>", 1)[0]
    assert 'class="hero-destaque-nota-num"' in hero
    assert 'class="hero-destaque-nota-de"' in hero
    assert "/100" in hero
    assert 'class="hero-destaque-halo' in hero


def test_index_vitrine_de_cards_e_o_modo_padrao(client, monkeypatch, tmp_path):
    """Rodada 2: a home abre na Vitrine (grade de cards com imagem
    grande); a tabela continua inteira em ?ver=lista."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "icon": "skin-icon-hash", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert '<ul class="grade-cards"' in body
    assert 'class="cartao-item' in body
    assert 'class="cartao-item-nome"' in body
    assert 'class="cartao-item-imagem-link"' in body
    assert 'class="cartao-item-nota nota-alta"' in body
    assert '<table class="tabela-candidatos tabela-itens"' not in body
    assert "Deslize a tabela para o lado" not in body


def test_index_vitrine_so_os_6_primeiros_cards_carregam_eager(
        client, monkeypatch, tmp_path):
    # item de performance 2026-11-09: a primeira fileira da Vitrine (até
    # 6 cards, cobre qualquer largura) não pode ter loading="lazy" --
    # medido ao vivo que o LCP era sempre um cartao-item-icon da
    # primeira fileira, e lazy atrasava justamente essa imagem. Os
    # demais, fora da tela inicial, continuam lazy.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": f"Item {i}", "score": 100 - i, "price": 1.0,
         "icon": f"hash{i}", "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []}
        for i in range(8)
    ])
    body = client.get("/").data.decode("utf-8")
    assert body.count('class="cartao-item-icon"') == 8
    assert body.count('class="cartao-item-icon" src="/icone/') > 0
    partes = body.split('class="cartao-item-icon"')[1:]
    for i, parte in enumerate(partes):
        esperado = "eager" if i < 6 else "lazy"
        assert f'loading="{esperado}"' in parte[:200], (
            f"card {i}: esperava loading={esperado!r}")


def test_index_modo_lista_mostra_a_tabela_e_nao_a_vitrine(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    assert '<table class="tabela-candidatos tabela-itens">' in body
    assert "Deslize a tabela para o lado" in body
    assert '<ul class="grade-cards"' not in body
    assert 'class="cartao-item' not in body


def test_index_seletor_de_visao_preserva_os_filtros(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "category": "Rifles",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get(
        "/?categoria=Rifles&nota_min=70").data.decode("utf-8")
    barra = body.split('class="barra-visao"', 1)[1].split("</nav>", 1)[0]
    hrefs = [html.unescape(h) for h in re.findall(r'href="([^"]+)"', barra)]
    # Os dois primeiros são o seletor de modo (ordem fixa no template).
    assert [
        parse_qs(urlsplit(h).query)["ver"][0] for h in hrefs[:2]
    ] == ["vitrine", "lista"]

    for href in hrefs:
        query = parse_qs(urlsplit(href).query)
        assert query["categoria"] == ["Rifles"]
        assert query["nota_min"] == ["70.0"]
        assert query["ver"] in (["vitrine"], ["lista"])
    # A ordenação na Vitrine aparece como links próprios, também com ver.
    assert "Ordenar por:" in barra
    assert 'aria-current="page"' in barra


def test_index_guarda_modo_de_visao_em_cookie(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    resp = client.get("/?ver=lista")
    cookie = resp.headers.get("Set-Cookie", "")
    assert "pref_ver=lista" in cookie
    assert "Max-Age=31536000" in cookie
    assert "SameSite=Lax" in cookie

    # Sem ?ver na URL, o cookie decide -- a próxima visita continua Lista.
    body = client.get("/").data.decode("utf-8")
    assert '<table class="tabela-candidatos tabela-itens">' in body


def test_index_ver_invalido_cai_na_vitrine(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    body = client.get("/?ver=tabela").data.decode("utf-8")
    assert '<ul class="grade-cards"' in body
    assert '<table class="tabela-candidatos tabela-itens"' not in body


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

    body = client.get("/?ver=lista").data.decode("utf-8")
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


def test_index_borda_de_raridade_tem_explicacao_no_title(
        client, monkeypatch, tmp_path):
    """achado 2026-11-07: a borda colorida de raridade (cor oficial do
    CS2) não tinha nenhuma explicação na tela -- quem não manja das
    cores via só uma borda sem significado. O `title` (hover) cobre
    quem usa mouse; a explicação completa fica no glossário."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "icon": "skin-icon-hash", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "name_color": "EB4B4B"},
    ])

    body = client.get("/?ver=lista").data.decode("utf-8")
    principal = re.search(
        r'<div class="celula-item-principal">(.*?)</div>',
        body, re.DOTALL).group(1)

    assert "raridade-covert" in principal
    assert 'title="Raridade: Covert (vermelho)"' in principal


def test_index_sem_raridade_nao_tem_classe_nem_title(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "icon": "skin-icon-hash", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])

    body = client.get("/?ver=lista").data.decode("utf-8")
    principal = re.search(
        r'<div class="celula-item-principal">(.*?)</div>',
        body, re.DOTALL).group(1)

    assert "raridade-" not in principal
    assert "Raridade:" not in principal


def test_raridade_faca_luva_usa_quality_id_nao_cor_covert(
        client, monkeypatch, tmp_path):
    """achado 2026-11-07, bug real visto em produção (Ranking, "Sport
    Gloves | Big Game" com borda vermelha em vez de dourada): facas e
    luvas (quality_id="unusual", prefixo ★) chegam da Steam com
    name_color/rarity_id IDÊNTICOS aos de uma skin Covert comum --
    valores reais checados numa Karambit e numas Sport Gloves de
    verdade (lodout.steam_api.get_market_page_data, request único).
    Sem checar quality_id ANTES do mapa de cor/raridade, toda faca/luva
    do site saía com borda vermelha."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "★ Karambit | Doppler (Factory New)", "score": 90,
         "price": 2000.0, "icon": "hash", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "name_color": "eb4b4b", "rarity_id": "Rarity_Ancient_Weapon",
         "quality_id": "unusual"},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    principal = re.search(
        r'<div class="celula-item-principal">(.*?)</div>',
        body, re.DOTALL).group(1)
    assert "raridade-dourado" in principal
    assert "raridade-covert" not in principal


def test_index_reserva_espaco_da_miniatura_sem_hash(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item sem imagem", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ])

    body = client.get("/?ver=lista").data.decode("utf-8")
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


def test_index_nota_no_teto_mostra_margem_alem_de_100(client, monkeypatch, tmp_path):
    # Soma dos deltas = 84 sobre a base 50 -> nota crua 134, cortada em
    # 100. Achado de auditoria da nota, 2026-11-04: sem a margem, esse
    # item e outro bem menos bom que também bateu 100 ficavam idênticos
    # na tela.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 100, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 84,
                       "label": "Preço muito abaixo do típico (+84)"}]},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert '<span class="nota-margem"' in celula
    assert ">+34</span>" in celula


def test_index_nota_no_piso_mostra_margem_abaixo_de_0(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 0, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": -84,
                       "label": "Preço muito acima do típico (-84)"}]},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert '<span class="nota-margem"' in celula
    assert ">-34</span>" in celula


def test_index_nota_sem_corte_nao_mostra_margem(client, monkeypatch, tmp_path):
    # score=70 bate exatamente com a soma do breakdown (50+20) -- não
    # houve corte nenhum, então não aparece margem nenhuma.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"},
         "breakdown": [{"factor": "mediana", "delta": 20,
                       "label": "Preço abaixo do típico (+20)"}]},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert "nota-margem" not in celula


def test_index_confianca_baixa_vira_selo_ao_lado_da_nota(client, monkeypatch, tmp_path):
    # achado 2026-11-04: signals.data_quality() era calculado a cada
    # scan e nunca exibido -- um item com pouco histórico calculava a
    # MESMA nota que um com dado rico, sem nenhum aviso.
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "data_quality": {"confidence": 0.1, "n": 3, "age_days": 60.0,
                          "level": "low", "label": "Confiança low"}},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert 'class="selo-confianca-baixa"' in celula
    assert "icone-ui-dado-limitado" in celula
    assert ">Dado limitado</span>" in celula
    assert "só 3 pontos de histórico" in celula
    assert "60 dias atrás" in celula


def test_index_confianca_alta_nao_mostra_selo(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "data_quality": {"confidence": 0.9, "n": 180, "age_days": 1.0,
                          "level": "high", "label": "Confiança high"}},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert "confianca-baixa" not in celula


def test_index_sem_historico_nenhum_mostra_selo_com_texto_proprio(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "data_quality": {"confidence": 0.0, "n": 0, "age_days": None,
                          "level": "none", "label": "sem dados"}},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    celula = body.split('class="celula-nota"', 1)[1].split("</td>", 1)[0]
    assert 'class="selo-confianca-baixa"' in celula
    assert "sem histórico de preço da Steam" in celula


def test_index_risco_medio_vira_selo_ao_lado_da_nota(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 70, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "medium"}, "breakdown": []},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    body = client.get("/?ver=lista").data.decode("utf-8")

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
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    body = client.get("/?ver=lista").data.decode("utf-8")

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
        "&ordenar=preco&ver=lista&pagina=2").data.decode()
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
        assert query["ver"] == ["lista"]
        assert "pagina" not in query
    assert hrefs["categoria"]["nota_min"] == ["70.0"]
    assert hrefs["categoria"]["preco_max"] == ["20.0"]
    assert hrefs["categoria"]["q"] == ["AK-47"]

    limpar = re.search(
        r'<a[^>]*id="limpar-filtros-ativos"[^>]*href="([^"]+)"', body)
    assert limpar
    query_limpa = parse_qs(urlsplit(html.unescape(limpar.group(1))).query)
    assert set(query_limpa) == {"ordenar", "ver"}


def test_index_sem_atalhos_de_filtro(client, monkeypatch, tmp_path):
    """Pedido do usuário 2026-11-09: remove as pílulas de atalho
    (nota/liquidez/preço) adicionadas na pesquisa de referência
    financeira (TradingView/Finviz) -- fora do site, sem resquício."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80,
         "price": 10.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    assert "atalhos-filtro" not in body
    assert "Liquidez alta" not in body


def test_index_nunca_chama_rede(client, monkeypatch, tmp_path):
    """Garantia estrutural: nenhuma rota de server.py importa steam_api."""
    import lodout.public_site.server as srv
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
    # icon_url_2x pede 384px (2x de 192) desde 2026-11-08 -- antes era
    # cópia do icon_url de 192px (perda de nitidez no hero/vitrine).
    assert (data["candidatos"][0]["icon_url_2x"]
            == "/icone/abc123.webp?v=2&tam=384")


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


def test_index_liquidez_min_filtra(client, monkeypatch, tmp_path):
    """Pedido numa pesquisa de como outros sites de skin expõem
    liquidez (2026-11-02) -- "pelo menos X" usa a ordem de
    `_LIQUIDEZ_ORDEM` (pior pro melhor), não igualdade exata."""
    resultados = [
        {"name": "Item muito líquido", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": [],
         "liquidity_depth": {"band": "muito_liquido"}},
        {"name": "Item liquidez moderada", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": [],
         "liquidity_depth": {"band": "moderado"}},
        {"name": "Item iliquido demais", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": [],
         "liquidity_depth": {"band": "iliquido"}},
        {"name": "Item sem dado nenhum", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/?liquidez_min=moderado").data.decode("utf-8")
    assert "Item muito líquido" in body
    assert "Item liquidez moderada" in body
    assert "Item iliquido demais" not in body
    # Sem o dado, não dá pra confirmar que atende o mínimo pedido.
    assert "Item sem dado nenhum" not in body


def test_index_sem_liquidez_min_mostra_tudo(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Sem dado de liquidez", "score": 50, "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "Sem dado de liquidez" in body


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
    # 25 itens / 10 por página = 3 páginas -- cabem todas na janela, sem
    # reticências.
    for pagina_corpo in (pagina1, pagina2, pagina3):
        numeros = pagina_corpo.split('class="paginacao-numeros"', 1)[1].split("</div>", 1)[0]
        assert "paginacao-reticencias" not in numeros
        for n in (1, 2, 3):
            assert f">{n}</a>" in numeros
    atual = pagina2.split('class="paginacao-numeros"', 1)[1].split("</div>", 1)[0]
    assert 'aria-current="page">2</a>' in atual


def test_index_paginacao_numerada_com_muitas_paginas_usa_reticencias(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": f"Item {i}", "score": 100 - (i % 100), "price": 1.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(173)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/?pagina=9").data.decode("utf-8")
    numeros = body.split('class="paginacao-numeros"', 1)[1].split("</div>", 1)[0]
    # 173 itens / 10 por página = 18 páginas. Na página 9, janela de 2:
    # 1 … 7 8 9 10 11 … 18 -- primeira e última sempre visíveis, sem
    # listar as 18 todas.
    assert "paginacao-reticencias" in numeros
    assert 'aria-current="page">9</a>' in numeros
    for n in (1, 7, 8, 9, 10, 11, 18):
        assert f">{n}</a>" in numeros
    assert ">3</a>" not in numeros
    assert ">15</a>" not in numeros


def test_index_paginacao_numerada_some_com_1_pagina_so(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item único", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/").data.decode("utf-8")
    assert "paginacao-numeros" not in body


def test_index_descontinuada_ganha_selo(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Caixa Velha", "score": 80, "price": 1.0,
         "case_label": "Alguma Caixa (descontinuada, 2018)",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    assert "lodout_notas" in body
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
    assert "icone-ui-lupa" in resp.data.decode("utf-8")


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
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    # `open`), dando a impressão de que não dava mais pra recolher. Cada
    # ocorrência DENTRO DA LINHA continua única (o que esta asserção
    # protege); o total é 2 porque o item "X" aqui é o único candidato,
    # então também vira destaque_hero (hero "nota mais alta hoje",
    # 2026-11-08) -- a 2a ocorrência é o resumo do hero, uma seção
    # diferente da linha da tabela, não a mesma duplicação de novo.
    assert body.count("Preço baixo · +10 pts") == 2


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
    # Linha do tempo (item #16 da lista de melhorias) -- cada entrada
    # vira uma <section> dentro do wrapper com o trilho via CSS.
    assert 'class="changelog-timeline"' in body
    assert body.count('class="changelog-entrada"') == len(changelog.ENTRADAS)


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
    assert "github.com/pedronokia/lodout/issues/new" in body
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
        "lodout.public_site.server._enriquecer_com_historico",
        marca_tendencia_alta)
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    assert "tendencia-alta" in body
    assert "> Subiu</span>" in body
    assert "class=\"celula-preco\"" in body


def test_index_tendencia_mostra_variacao_percentual(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
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
        "lodout.public_site.server.signals.load_item_history",
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
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    # Decisão 2026-11-11: as abas voltaram a ser só nome + contagem, sem
    # pictograma na frente da palavra.
    assert 'aria-current="page">Rifles <span class="aba-contagem">1</span>' in abas
    assert ">Facas <span" not in abas
    assert "<svg" not in abas


def test_index_abas_de_categoria_sem_icone(client, monkeypatch, tmp_path):
    """Decisão de 2026-11-11: os ícones que ficavam na frente do nome de
    cada categoria saíram -- a barra fica só com nome e contagem."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "category": "Rifles", "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Y", "score": 70, "price": 1.0, "case_label": "",
         "category": "Luvas", "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/").data.decode("utf-8")
    abas = body.split('class="abas-categoria"', 1)[1].split("</nav>", 1)[0]
    assert "icone-ui" not in abas
    assert "<svg" not in abas
    assert ">Rifles <span" in abas
    assert ">Luvas <span" in abas


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
    """Decisão de 2026-11-11: a marca escrita (208px) deu lugar a um
    símbolo do tamanho de um ícone de barra e, depois, só às aspas
    soltas (sem disco atrás) -- o nome completo continua no aria-label
    do link."""
    _salva_scan(tmp_path, monkeypatch, [])
    body = client.get("/").data.decode("utf-8")
    assert 'class="logo"' in body
    assert 'class="logo-icone"' in body
    assert 'class="logo-aspas"' in body
    assert 'aria-label="Lodout — página inicial"' in body
    assert 'class="logo-cheia"' not in body
    # A marca agora é só o desenho das aspas: nada de disco/círculo atrás.
    logo = body.split('class="logo"', 1)[1].split("</a>", 1)[0]
    assert "<circle" not in logo


def test_titulos_das_paginas_usam_o_nome_lodout(client):
    """Decisão de 2026-11-11: nos títulos de página o nome é "Lodout"
    (G maiúsculo). O resto do texto do site continua "lodout"."""
    assert "<title>Lodout</title>" in client.get("/").data.decode("utf-8")
    ranking = client.get("/ranking").data.decode("utf-8")
    assert "<title>Ranking — Lodout</title>" in ranking
    assert "— lodout</title>" not in ranking


def test_index_tem_input_tag_local(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "X", "score": 80, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
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
    body = client.get("/?ver=lista").data.decode("utf-8")
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
        "lodout.public_site.server.buscas.registrar",
        lambda termo: chamados.append(termo))
    monkeypatch.setattr("lodout.scan_store.load_last_scan", lambda: None)
    client.get("/?q=redline")
    assert chamados == ["redline"]


def test_index_sem_busca_nao_registra_termo(client, monkeypatch):
    chamados = []
    monkeypatch.setattr(
        "lodout.public_site.server.buscas.registrar",
        lambda termo: chamados.append(termo))
    monkeypatch.setattr("lodout.scan_store.load_last_scan", lambda: None)
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
        "lodout.public_site.server.ranking.load_snapshots", lambda: [])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    resp = client.get("/ranking")
    assert resp.status_code == 200
    assert "Ainda não há ranking".encode("utf-8") in resp.data


def test_ranking_page_com_snapshots_marca_novo(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    # Snapshot anterior EXISTE mas nao tem o item X -- e' isso que gera
    # "NOVO" (previous=None geraria label vazio, nao NOVO).
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: {"ts": 900.0, "items": [{"name": "Y", "score": 1, "position": 1}]})
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: None)
    body = client.get("/ranking?periodo=scan").data.decode("utf-8")
    assert "selo-novo" in body


def test_ranking_page_tem_popover_legenda_raridade(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot", lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert 'class="popover-legenda"' in body
    assert "Cores da borda" in body


def test_ranking_page_item_linka_pra_pagina_de_detalhe(client, monkeypatch):
    """O nome do item no Ranking precisa ser link pro /item/<nome> --
    sem isso, quem via o Top 20 e queria o histórico/motivo completo
    tinha que voltar pra home e buscar manualmente."""
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot", lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert 'href="/item/AK-47%20%7C%20Redline%20(Field-Tested)"' in body


def test_ranking_page_mostra_icone_e_raridade_do_scan_atual(
        client, monkeypatch, tmp_path):
    """achado 2026-11-07: o snapshot de ranking.py grava só
    name/score/position (formato estável pro histórico) -- ícone e
    raridade vêm de cruzar o nome com o scan atual (_icone_raridade),
    mesma fonte que já alimenta a home."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 80,
         "price": 50.0, "icon": "skin-icon-hash", "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "name_color": "EB4B4B"},
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "AK-47 | Redline (Field-Tested)", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot", lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking?ver=lista").data.decode("utf-8")
    assert "icone-item-quadro-compacto" in body
    assert "icone-item-quadro-com-imagem" in body
    assert "raridade-covert" in body
    assert 'title="Raridade: Covert (vermelho)"' in body


def test_ranking_page_item_fora_do_scan_atual_sem_icone(client, monkeypatch):
    """Item do snapshot que não está mais no scan atual (saiu do top, ou
    nenhum scan rodou ainda) cai pro placeholder sem ícone/raridade, em
    vez de quebrar a página -- sem scan salvo neste teste de propósito."""
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "Item sumido do scan", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot", lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    resp = client.get("/ranking?ver=lista")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # "raridade-" aparece em algum lugar da página por causa do popover
    # de legenda (item #4 da lista de melhorias, sempre presente perto
    # da tabela) -- o que este teste garante é que a CÉLULA do item vem
    # sem raridade/imagem, não a página inteira.
    celula = body.split('class="celula-item-ranking"', 1)[1].split("</td>", 1)[0]
    assert "raridade-" not in celula
    assert "icone-item-quadro-com-imagem" not in celula


def test_ranking_page_mostra_subiu_e_desceu(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
            {"name": "Y", "score": 70, "position": 2},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: {"ts": 900.0, "items": [
            {"name": "X", "score": 75, "position": 3},
            {"name": "Y", "score": 70, "position": 1},
        ]})
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: None)
    body = client.get("/ranking?periodo=scan").data.decode("utf-8")
    assert "tendencia-alta" in body
    assert "tendencia-baixa" in body


def _ranking_com_historico(monkeypatch, agora=1_000_000.0):
    """Atual + snapshots de ~6h, ~1 dia e ~7 dias atrás, com
    `latest_before` de verdade (mais recente com ts < limite)."""
    h = 3600.0
    snaps = [
        {"ts": agora - 7 * 24 * h, "items": [
            {"name": "X", "score": 50, "position": 5},
            {"name": "Y", "score": 90, "position": 1}]},
        {"ts": agora - 24 * h, "items": [
            {"name": "X", "score": 70, "position": 3},
            {"name": "Y", "score": 72, "position": 1}]},
        {"ts": agora - 6 * h, "items": [
            {"name": "X", "score": 80, "position": 1},
            {"name": "Y", "score": 70, "position": 2}]},
        {"ts": agora, "items": [
            {"name": "X", "score": 80, "position": 1},
            {"name": "Y", "score": 70, "position": 2}]},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots", lambda: snaps)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: snaps[-2])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: next((s for s in reversed(snaps) if s["ts"] < ts), None))
    return snaps


def test_ranking_padrao_compara_com_24h_nas_setas_e_no_resumo(
        client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking?ver=lista").data.decode("utf-8")
    # Contra 24h: X subiu de 3 pra 1 (+2) e ganhou 10 de nota; Y caiu 2.
    assert 'aria-current="true">24 horas<' in body
    assert "+2" in body
    assert "+10 na nota" in body
    assert "−2 na nota" in body
    # A frase usa a mesma base: maior alta é X (70 -> 80).
    assert "maior alta de nota foi" in body


def test_ranking_periodo_scan_compara_com_o_scan_anterior(
        client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking?periodo=scan&ver=lista").data.decode("utf-8")
    assert 'aria-current="true">Último scan<' in body
    # Sem mudança entre os dois últimos scans.
    assert "tendencia-alta" not in body
    assert "nota igual" in body
    assert "maior alta de nota foi" not in body


def test_ranking_periodo_7d_usa_snapshot_de_uma_semana(client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking?periodo=7d&ver=lista").data.decode("utf-8")
    assert "+30 na nota" in body
    assert "−20 na nota" in body


def test_ranking_periodo_sem_historico_avisa_em_vez_de_comparar(
        client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking?periodo=30d").data.decode("utf-8")
    assert "Ainda não há ranking salvo de 30 dias atrás" in body
    assert "na nota" not in body
    assert "Comparado com o ranking de" not in body


def test_ranking_periodo_invalido_cai_no_padrao(client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking?periodo=<x>").data.decode("utf-8")
    assert 'aria-current="true">24 horas<' in body
    assert "<x>" not in body


def test_ranking_links_preservam_periodo_e_visao(client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking?periodo=7d&ver=lista").data.decode("utf-8")
    assert 'href="/ranking?periodo=30d&amp;ver=lista"' in body
    assert 'href="/ranking?ver=vitrine&amp;periodo=7d"' in body


def test_ranking_page_resumo_do_dia_sem_snapshot_antigo(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert "resumo-do-dia" not in body


def test_ranking_page_resumo_do_dia_com_snapshot_antigo(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 90, "position": 1},
            {"name": "Y", "score": 70, "position": 2},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
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
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 40, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: {"ts": 900.0, "items": [
            {"name": "X", "score": 90, "position": 1},
        ]})
    body = client.get("/ranking").data.decode("utf-8")
    assert "resumo-do-dia" in body
    assert "0 itens novos no Top 20" in body.replace("\n", " ")
    assert "maior alta" not in body


def test_ranking_page_vitrine_mostra_cards_com_posicao_e_nota(
        client, monkeypatch):
    # Vitrine (rodada 3) é o padrão, igual a home -- o snapshot do
    # ranking só tem name/score/position, então o card aqui é mais
    # enxuto que o da home (sem preço/motivo).
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
             "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    assert '<ul class="grade-cards"' in body
    assert 'class="cartao-item cartao-item-ranking' in body
    assert "#1" in body
    assert 'href="/item/AK-47%20%7C%20Redline%20(Field-Tested)"' in body
    assert '<table class="tabela-candidatos">' not in body


def test_ranking_page_vitrine_so_os_6_primeiros_cards_carregam_eager(
        client, monkeypatch, tmp_path):
    # Mesmo achado de performance de index.html, aplicado ao Ranking
    # (também abre na Vitrine por padrão).
    nomes = [f"Item {i}" for i in range(8)]
    _salva_scan(tmp_path, monkeypatch, [
        {"name": nome, "score": 100 - i, "price": 1.0, "icon": f"hash{i}",
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i, nome in enumerate(nomes)
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": nome, "score": 100 - i, "position": i + 1}
            for i, nome in enumerate(nomes)
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking").data.decode("utf-8")
    partes = body.split('class="cartao-item-icon"')[1:]
    assert len(partes) == 8
    for i, parte in enumerate(partes):
        esperado = "eager" if i < 6 else "lazy"
        assert f'loading="{esperado}"' in parte[:200], (
            f"card {i}: esperava loading={esperado!r}")


def test_ranking_page_cookie_pref_ver_lista_mantem_tabela(
        client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    resp = client.get("/ranking?ver=lista")
    cookie = resp.headers.get("Set-Cookie", "")
    assert "pref_ver=lista" in cookie
    # Sem ?ver na URL, o cookie decide -- mesmo cookie da home, então
    # quem escolheu Lista lá não volta pra Vitrine aqui sem pedir.
    body = client.get("/ranking").data.decode("utf-8")
    assert '<table class="tabela-candidatos">' in body
    assert '<ul class="grade-cards"' not in body


def test_ranking_page_ver_invalido_cai_na_vitrine(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [{"ts": 1000.0, "items": [
            {"name": "X", "score": 80, "position": 1},
        ]}])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.previous_snapshot",
        lambda: None)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before", lambda ts: None)
    body = client.get("/ranking?ver=tabela").data.decode("utf-8")
    assert '<ul class="grade-cards"' in body
    assert '<table class="tabela-candidatos">' not in body


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
        "lodout.public_site.profile_fetcher._AVATARS_DIR", tmp_path)
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
        "lodout.public_site.profile_fetcher._AVATARS_DIR", tmp_path)
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/ranking").data.decode("utf-8")
    assert "conta-avatar" not in body
    assert client.get("/conta/avatar.jpg").status_code == 404


def test_rota_avatar_serve_o_arquivo_do_usuario_logado(
        client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "lodout.public_site.profile_fetcher._AVATARS_DIR", tmp_path)
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


def test_cta_login_sem_legenda_na_barra(client):
    """Revisão da decisão anterior (2026-11-10, cabeçalho estilo Apple):
    a barra agora é marca + menu de ponta a ponta + botão, sem texto de
    apoio no meio -- a legenda saiu para o menu usar toda a largura. O
    "por que logar" continua no FAQ ("Preciso fazer login pra usar?")."""
    body = client.get("/").data.decode("utf-8")
    assert "entrar-cta-legenda" not in body
    assert "Entrar com Steam" in body


def test_usuario_logado_nao_mostra_cta_de_login(client, monkeypatch):
    monkeypatch.setattr(
        user_store, "get_user",
        lambda steamid, path=None: {
            "steamid": steamid, "persona_name": "Fulano",
            "avatar_url": "https://example.com/a.jpg",
        })
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/").data.decode("utf-8")
    assert "entrar-cta" not in body
    assert "conta-pill" in body


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
    monkeypatch.setattr("lodout.scan_store.load_last_scan", lambda: None)
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


# ── server: erros em /api/* devolvem JSON, não HTML ──────────
# Achado da skill api-and-interface-design (2026-11-05): os handlers de
# 404/500/429 devolviam a mesma página HTML pra qualquer rota, inclusive
# pra quem consome /api/* programaticamente.

def test_api_404_devolve_json(client):
    resp = client.get("/api/isso-nao-existe")
    assert resp.status_code == 404
    assert resp.content_type.startswith("application/json")
    assert resp.get_json()["erro"] == "nao_encontrado"


def test_api_500_devolve_json(client):
    @client.application.route("/api/__boom")
    def _api_boom():
        raise RuntimeError("erro de teste")
    client.application.config["TESTING"] = False
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    resp = client.get("/api/__boom")
    assert resp.status_code == 500
    assert resp.content_type.startswith("application/json")
    assert resp.get_json()["erro"] == "erro_interno"


def test_api_429_devolve_json(client):
    import flask
    @client.application.route("/api/__limite")
    def _api_limite():
        flask.abort(429)
    resp = client.get("/api/__limite")
    assert resp.status_code == 429
    assert resp.content_type.startswith("application/json")
    assert resp.get_json()["erro"] == "limite_excedido"


def test_pagina_normal_continua_em_html_nos_erros(client):
    """Garantia de que o JSON é só pra /api/*: uma rota fora dali
    continua devolvendo a página de erro de sempre."""
    resp = client.get("/isso-nao-existe")
    assert resp.content_type.startswith("text/html")


def test_admin_sem_hash_configurado_e_404(client, monkeypatch):
    monkeypatch.setattr("lodout.public_site.server._ADMIN_PASSWORD_HASH", "")
    assert client.get("/admin").status_code == 404
    assert client.get("/admin/login").status_code == 404


def test_admin_sem_sessao_redireciona_pro_login(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    resp = client.get("/admin")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_admin_login_senha_errada_nao_autentica(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    resp = client.post("/admin/login", data={"senha": "errada"})
    assert resp.status_code == 200
    assert "incorreta" in resp.data.decode("utf-8")
    assert client.get("/admin").status_code == 302


def test_admin_login_senha_certa_autentica_e_funciona(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    login = client.post("/admin/login", data={"senha": "segredo"})
    assert login.status_code == 302
    assert client.get("/admin").status_code == 200


def test_admin_logout_encerra_sessao(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
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
        "lodout.public_site.server.visits.serie_por_dia",
        lambda: [("2026-10-24", 3), ("2026-10-25", 5)])
    monkeypatch.setattr(
        "lodout.public_site.server.buscas.mais_buscados",
        lambda limite=10: [("ak-47", 4)])
    monkeypatch.setattr(
        "lodout.public_site.server.scan_store.load_historico_ciclos",
        lambda: [])
    body = client.get("/status").data.decode("utf-8")
    assert "grafico-historico" in body
    assert "ak-47" in body
    # mesmo padrão de tooltip por ponto do gráfico de /item e /conta/historico
    assert "<title>24/10/2026 — 3 visitas</title>" in body
    assert "<title>25/10/2026 — 5 visitas</title>" in body


# ── server: /status ──────────────────────────────────────────

def test_status_sem_historico(client, monkeypatch, tmp_path):
    from lodout.public_site import uptime, visits
    monkeypatch.setattr(scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(uptime, "no_ar_desde", lambda: 0.0)
    monkeypatch.setattr(visits, "total", lambda: 0)
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "Ainda não há histórico".encode("utf-8") in resp.data
    assert "saude-ciclos" not in resp.data.decode("utf-8")


def test_status_mostra_ciclos_com_falha(client, monkeypatch, tmp_path):
    from lodout.public_site import uptime, visits
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
    # Tira de saúde (item #9 da lista de melhorias) -- 1 de 2 ciclos
    # com sucesso, 1 "ok" e 1 "falha".
    faixa = body.split('class="saude-ciclos"', 1)[1].split("</div>", 1)[0]
    assert faixa.count("saude-ciclo-ok") == 1
    assert faixa.count("saude-ciclo-falha") == 1
    assert "1 de 2 ciclos com sucesso" in body


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
                        lambda categories, on_progress=None, **kw: resultados)
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
                        lambda categories, on_progress=None, **kw: resultados)
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
                        lambda categories, on_progress=None, **kw: [])
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

    def _fake(categories, on_progress=None, **kw):
        recebido["categories"] = categories
        return []

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    worker.run_once()
    for pesada in worker._CATEGORIAS_PESADAS:
        assert pesada not in recebido["categories"]


def test_run_once_checa_arquivos_do_jogo_antes_do_scan(monkeypatch):
    ordem = []
    monkeypatch.setattr(
        worker.gamedata, "check_for_updates",
        lambda: ordem.append("gamedata") or {
            "changed": False, "events": [], "commit": None, "error": None})

    def _fake(categories, on_progress=None, **kw):
        ordem.append("scan")
        return []

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    worker.run_once({"Facas": ["A"]})
    assert ordem == ["gamedata", "scan"]


def test_run_once_falha_nos_arquivos_do_jogo_nao_impede_scan(
        monkeypatch, caplog):
    def _boom():
        raise RuntimeError("github fora")

    monkeypatch.setattr(worker.gamedata, "check_for_updates", _boom)
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None, **kw: [])
    with caplog.at_level("WARNING", logger="lodout.worker"):
        assert worker.run_once({"Facas": ["A"]}) == []
    assert "checagem dos arquivos do jogo falhou" in caplog.text


def test_run_once_registra_erro_e_mudanca_dos_arquivos_do_jogo(
        monkeypatch, caplog):
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None, **kw: [])
    monkeypatch.setattr(
        worker.gamedata, "check_for_updates",
        lambda: {"changed": False, "events": [], "commit": None,
                 "error": "network"})
    with caplog.at_level("INFO", logger="lodout.worker"):
        worker.run_once({"Facas": ["A"]})
    assert "erro de network" in caplog.text

    caplog.clear()
    monkeypatch.setattr(
        worker.gamedata, "check_for_updates",
        lambda: {"changed": True, "events": [{"type": "x"}] * 2,
                 "commit": {"sha": "abcdef1234", "date": "2026-11-12"},
                 "error": None})
    with caplog.at_level("INFO", logger="lodout.worker"):
        worker.run_once({"Facas": ["A"]})
    assert "Arquivos do jogo mudaram (abcdef1, 2026-11-12): 2 evento(s)" \
        in caplog.text


def test_run_once_busca_noticias_depois_do_scan(monkeypatch):
    ordem = []
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(
        worker.scan_engine, "run_full_scan",
        lambda categories, on_progress=None, **kw: ordem.append("scan") or [])
    monkeypatch.setattr(worker.steam_news, "atualizar_noticias",
                        lambda: ordem.append("noticias") or "ok")
    worker.run_once({"Facas": ["A"]})
    assert ordem == ["scan", "noticias"]


def test_run_once_falha_nas_noticias_nao_derruba_ciclo(monkeypatch, caplog):
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None, **kw: [])

    def _boom():
        raise RuntimeError("fora do ar")

    monkeypatch.setattr(worker.steam_news, "atualizar_noticias", _boom)
    registrou = []
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda *a, **kw: registrou.append(a))
    with caplog.at_level("WARNING", logger="lodout.worker"):
        assert worker.run_once({"Facas": ["A"]}) == []
    assert "busca de notícias falhou" in caplog.text
    assert registrou


def test_manter_do_ciclo_anterior_so_alvos_recentes_que_falharam():
    agora = 1_000_000.0
    anterior = {"ts": agora - 6 * 3600, "results": [
        {"name": "Veio", "score": 10, "coletado_em": agora - 6 * 3600},
        {"name": "Falhou", "score": 20, "coletado_em": agora - 6 * 3600},
        {"name": "SemData", "score": 25},
        {"name": "Velho", "score": 30, "coletado_em": agora - 49 * 3600},
        {"name": "ForaDaLista", "score": 40, "coletado_em": agora - 3600},
    ]}
    mantidos = worker._manter_do_ciclo_anterior(
        [{"name": "Veio", "score": 11}], anterior,
        alvos={"Veio", "Falhou", "SemData", "Velho"}, agora=agora)
    assert [m["name"] for m in mantidos] == ["Falhou", "SemData"]
    assert all(m["mantido_do_ciclo_anterior"] for m in mantidos)
    # Sem data própria, vale a data do scan anterior.
    assert mantidos[1]["coletado_em"] == agora - 6 * 3600
    assert worker._manter_do_ciclo_anterior([], None, {"X"}) == []


def test_run_once_mantem_item_que_falhou_e_registra_cobertura(
        monkeypatch, tmp_path):
    original_save = scan_store.save_last_scan
    original_load = scan_store.load_last_scan
    scan_path = tmp_path / "scanner_last.json"
    original_save("Todas", [
        {"name": "A", "score": 80, "coletado_em": time.time() - 3600},
        {"name": "B", "score": 70, "coletado_em": time.time() - 3600},
    ], path=scan_path)
    monkeypatch.setattr(worker.scan_store, "load_last_scan",
                        lambda: original_load(path=scan_path))
    monkeypatch.setattr(
        worker.scan_store, "save_last_scan",
        lambda cat, res: original_save(cat, res, path=scan_path))
    monkeypatch.setattr(worker.ranking, "save_snapshot", lambda res: None)
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [])
    monkeypatch.setattr(worker.steam_news, "atualizar_noticias", lambda: "ok")

    def _fake(categories, on_progress=None, falhas=None, **kw):
        falhas.append("B")
        return [{"name": "A", "score": 81, "coletado_em": time.time()}]

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    registrado = {}
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda itens, dur, **kw: registrado.update(
                            itens=itens, **kw))
    out = worker.run_once({"Facas": ["A", "B"]})
    nomes = {r["name"]: r for r in out}
    assert set(nomes) == {"A", "B"}
    assert nomes["B"].get("mantido_do_ciclo_anterior") is True
    assert "mantido_do_ciclo_anterior" not in nomes["A"]
    salvo = {r["name"] for r in original_load(path=scan_path)["results"]}
    assert salvo == {"A", "B"}
    assert {k: registrado[k] for k in ("itens", "alvos", "mantidos",
                                       "falhas")} == {
        "itens": 1, "alvos": 2, "mantidos": 1, "falhas": ["B"]}
    assert registrado["extras"]["ritmo"] == 1.0


def test_run_once_bloqueio_total_nao_regrava_scan(monkeypatch):
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [])
    monkeypatch.setattr(worker.steam_news, "atualizar_noticias", lambda: "ok")
    monkeypatch.setattr(
        worker.scan_store, "load_last_scan",
        lambda: {"ts": time.time(), "results": [
            {"name": "A", "score": 1, "coletado_em": time.time()}]})
    monkeypatch.setattr(worker.scan_engine, "run_full_scan",
                        lambda categories, on_progress=None, **kw: [])
    gravou = []
    monkeypatch.setattr(worker.scan_store, "save_last_scan",
                        lambda *a: gravou.append(a))
    monkeypatch.setattr(worker.ranking, "save_snapshot",
                        lambda *a: gravou.append(a))
    assert worker.run_once({"Facas": ["A"]}) == []
    assert gravou == []


def test_com_containers_novos_inclui_caixa_e_capsula(monkeypatch):
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [
        {"type": "new_container", "internal": "crate_community_40",
         "name": "Nova Case"},
        {"type": "xpshop_added", "internal": "crate_sticker_pack_x",
         "name": "Nova Sticker Capsule"},
        # Sem tradução: nome interno não existe no Market.
        {"type": "new_container", "internal": "crate_y", "name": "crate_y"},
        # Já está na lista.
        {"type": "new_container", "internal": "crate_z", "name": "Kilowatt Case"},
        # Pacote de souvenir: sufixo não reconhecido, fica de fora.
        {"type": "new_container", "internal": "crate_w",
         "name": "Austin 2025 Inferno Souvenir Package"},
        # Coleção do drop semanal não é container.
        {"type": "drop_pool_added", "internal": "set_x", "name": "X Case"},
    ])
    cats = worker._com_containers_novos(
        {"Caixas": ["Kilowatt Case"], "Cápsulas": [], "Facas": ["F"]})
    assert cats == {"Caixas": ["Kilowatt Case", "Nova Case"],
                    "Cápsulas": ["Nova Sticker Capsule"], "Facas": ["F"]}


def test_com_containers_novos_sem_eventos_devolve_igual(monkeypatch):
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [])
    cats = {"Caixas": ["A"]}
    assert worker._com_containers_novos(cats) is cats


def test_status_mostra_cobertura_e_falhas_do_ultimo_ciclo(client, monkeypatch):
    monkeypatch.setattr(
        scan_store, "load_historico_ciclos",
        lambda: [{"ts": time.time() - 60, "itens": 180, "duracao_min": 29.0,
                  "sucesso": True, "alvos": 185, "mantidos": 5,
                  "falhas": ["Kilowatt Case", "<b>x</b>"]}])
    body = client.get("/status").data.decode("utf-8")
    assert "<strong>180 de 185</strong> itens vieram com preço novo" in body
    assert "5 continuam no site com o dado do ciclo anterior" in body
    assert "Itens que ficaram sem preço novo (2)" in body
    assert "&lt;b&gt;x&lt;/b&gt;" in body
    assert "(+5 mantidos)" in body


def test_status_ciclo_antigo_sem_cobertura_nao_quebra(client, monkeypatch):
    monkeypatch.setattr(
        scan_store, "load_historico_ciclos",
        lambda: [{"ts": time.time() - 60, "itens": 178, "duracao_min": 28.5,
                  "sucesso": True}])
    body = client.get("/status").data.decode("utf-8")
    assert "vieram com preço novo" not in body
    assert "<td>178</td>" in body


def test_item_avisa_quando_dado_e_do_ciclo_anterior(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "A", "score": 70, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "mantido_do_ciclo_anterior": True},
    ])
    body = client.get("/item/A").data.decode("utf-8")
    assert "A Steam não devolveu preço novo no último ciclo" in body


def test_ritmo_sobe_com_429_e_volta_devagar():
    assert worker._ritmo_do_ciclo([]) == 1.0
    # Ciclo antigo, sem o campo: não inventa.
    assert worker._ritmo_do_ciclo([{"ts": 1}]) == 1.0
    assert worker._ritmo_do_ciclo([{"ts": 1, "pausas_429": 2}]) == 1.25
    assert worker._ritmo_do_ciclo(
        [{"ts": 1, "pausas_429": 1, "ritmo": 1.9}]) == worker._RITMO_MAX
    assert worker._ritmo_do_ciclo(
        [{"ts": 1, "pausas_429": 0, "ritmo": 1.5}]) == 1.35
    assert worker._ritmo_do_ciclo(
        [{"ts": 1, "pausas_429": 0, "ritmo": 1.05}]) == 1.0


def test_sem_anuncio_conta_falhas_e_poe_em_espera():
    agora = 1_000_000.0
    reg = {}
    for i in range(3):
        reg = worker._atualizar_sem_anuncio(reg, set(), ["Morto"], agora + i)
    assert reg["Morto"]["seguidas"] == 3
    cats, fora = worker._tirar_itens_em_espera(
        {"Caixas": ["Morto", "Vivo"]}, reg, agora + 3600)
    assert cats == {"Caixas": ["Vivo"]} and fora == ["Morto"]
    # Passado um dia, volta a ser tentado.
    cats, fora = worker._tirar_itens_em_espera(
        {"Caixas": ["Morto"]}, reg, agora + 25 * 3600)
    assert cats == {"Caixas": ["Morto"]} and fora == []
    # Trouxe preço: sai do registro.
    assert worker._atualizar_sem_anuncio(reg, {"Morto"}, [], agora) == {}


def test_sem_anuncio_duas_falhas_ainda_e_tentado():
    reg = {"X": {"seguidas": 2, "ultima": 999.0}}
    cats, fora = worker._tirar_itens_em_espera({"C": ["X"]}, reg, 1000.0)
    assert cats == {"C": ["X"]} and fora == []


def test_run_once_usa_ritmo_e_registra_espera(monkeypatch, tmp_path):
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [])
    monkeypatch.setattr(worker.steam_news, "atualizar_noticias", lambda: "ok")
    monkeypatch.setattr(worker, "_caminho_sem_anuncio",
                        lambda: tmp_path / "sem.json")
    (tmp_path / "sem.json").write_text(
        '{"Morto": {"seguidas": 3, "ultima": %f}}' % time.time())
    monkeypatch.setattr(
        worker.scan_store, "load_historico_ciclos",
        lambda: [{"ts": 1, "pausas_429": 1, "ritmo": 1.0}])
    recebido = {}

    def _fake(categories, on_progress=None, falhas=None, ritmo=1.0,
              relatorio=None, **kw):
        recebido.update(categories=categories, ritmo=ritmo)
        relatorio.update(pausas_429=0, sem_preco=["B"],
                         comparacao_fontes={"razao_preco": 1.0})
        falhas.append("B")
        return [{"name": "A", "score": 1}]

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    monkeypatch.setattr(worker.scan_store, "save_last_scan", lambda *a: None)
    monkeypatch.setattr(worker.ranking, "save_snapshot", lambda *a: None)
    registrado = {}
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda itens, dur, **kw: registrado.update(kw))
    worker.run_once({"Caixas": ["A", "B", "C", "D", "E", "F", "Morto"]})
    assert recebido["ritmo"] == 1.25
    assert "Morto" not in recebido["categories"]["Caixas"]
    assert registrado["extras"]["em_espera"] == ["Morto"]
    assert registrado["extras"]["comparacao_fontes"] == {"razao_preco": 1.0}
    salvo = json.loads((tmp_path / "sem.json").read_text())
    assert salvo["B"]["seguidas"] == 1
    assert salvo["Morto"]["seguidas"] == 3


def test_run_once_falha_geral_nao_conta_como_sem_anuncio(
        monkeypatch, tmp_path):
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [])
    monkeypatch.setattr(worker.steam_news, "atualizar_noticias", lambda: "ok")
    monkeypatch.setattr(worker, "_caminho_sem_anuncio",
                        lambda: tmp_path / "sem.json")
    nomes = [f"I{i}" for i in range(10)]

    def _fake(categories, on_progress=None, falhas=None, relatorio=None,
              **kw):
        relatorio.update(pausas_429=0, sem_preco=nomes[1:])
        return [{"name": "I0", "score": 1}]

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    monkeypatch.setattr(worker.scan_store, "save_last_scan", lambda *a: None)
    monkeypatch.setattr(worker.ranking, "save_snapshot", lambda *a: None)
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda *a, **kw: None)
    worker.run_once({"C": nomes})
    assert json.loads((tmp_path / "sem.json").read_text()) == {}


def test_ordenar_poe_atrasados_na_frente(monkeypatch):
    monkeypatch.setattr(worker.scan_store, "load_last_scan", lambda: {
        "ts": 1, "results": [
            {"name": "Alta", "score": 90},
            {"name": "Atrasado", "score": 10,
             "mantido_do_ciclo_anterior": True}]})
    out = worker._ordenar_por_nota_anterior(
        {"C": ["Alta", "Novo", "Atrasado"]})
    assert out == {"C": ["Atrasado", "Alta", "Novo"]}


@pytest.fixture(autouse=True)
def _sem_handler_de_sinal_real(monkeypatch):
    """`worker.main()` instala um handler de SIGTERM -- nos testes ele
    não pode vazar pro processo do pytest."""
    monkeypatch.setattr(worker.signal, "signal", lambda *a, **kw: None)
    monkeypatch.setattr(worker, "_parar", False)
    monkeypatch.setattr(worker, "_escaneando", False)


def _worker_isolado(monkeypatch, tmp_path):
    monkeypatch.setattr(worker.gamedata, "check_for_updates",
                        lambda: {"changed": False, "error": None})
    monkeypatch.setattr(worker.gamedata, "load_events_log", lambda: [])
    monkeypatch.setattr(worker.steam_news, "atualizar_noticias", lambda: "ok")
    monkeypatch.setattr(worker, "_caminho_sem_anuncio",
                        lambda: tmp_path / "sem.json")
    monkeypatch.setattr(worker, "_caminho_checkpoint",
                        lambda: tmp_path / "parcial.json")
    monkeypatch.setattr(worker.scan_store, "load_last_scan", lambda: None)
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos",
                        lambda: [])
    monkeypatch.setattr(worker.scan_store, "registrar_ciclo",
                        lambda *a, **kw: None)
    salvos = {}
    monkeypatch.setattr(worker.scan_store, "save_last_scan",
                        lambda cat, res: salvos.update(scan=res))
    monkeypatch.setattr(worker.ranking, "save_snapshot",
                        lambda res: salvos.update(ranking=res))
    return salvos


def test_run_once_grava_checkpoint_e_apaga_no_fim(monkeypatch, tmp_path):
    salvos = _worker_isolado(monkeypatch, tmp_path)
    vistos_no_meio = []

    def _fake(categories, on_resultado=None, **kw):
        out = []
        for i in range(6):
            r = {"name": f"I{i}", "score": i}
            out.append(r)
            on_resultado(r)
            if i == 4:
                vistos_no_meio.append(json.loads(
                    (tmp_path / "parcial.json").read_text()))
        return out

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    worker.run_once({"C": [f"I{i}" for i in range(6)]})
    assert len(vistos_no_meio[0]["results"]) == 5
    assert len(salvos["scan"]) == 6
    assert not (tmp_path / "parcial.json").exists()


def test_run_once_retoma_do_checkpoint(monkeypatch, tmp_path):
    salvos = _worker_isolado(monkeypatch, tmp_path)
    (tmp_path / "parcial.json").write_text(json.dumps({
        "inicio": time.time() - 600,
        "results": [{"name": "A", "score": 90}, {"name": "B", "score": 80}]}))
    recebido = {}

    def _fake(categories, pular=None, **kw):
        recebido["pular"] = pular
        return [{"name": "C", "score": 70}]

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    out = worker.run_once({"X": ["A", "B", "C"]})
    assert recebido["pular"] == {"A", "B"}
    assert [r["name"] for r in out] == ["A", "B", "C"]
    assert {r["name"] for r in salvos["scan"]} == {"A", "B", "C"}
    assert not (tmp_path / "parcial.json").exists()


def test_checkpoint_velho_ou_ruim_e_ignorado(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "_caminho_checkpoint",
                        lambda: tmp_path / "parcial.json")
    agora = time.time()
    assert worker._carregar_checkpoint(agora) is None
    (tmp_path / "parcial.json").write_text("{quebrado")
    assert worker._carregar_checkpoint(agora) is None
    (tmp_path / "parcial.json").write_text(json.dumps(
        {"inicio": agora - 4 * 3600, "results": [{"name": "A", "score": 1}]}))
    assert worker._carregar_checkpoint(agora) is None
    (tmp_path / "parcial.json").write_text(json.dumps(
        {"inicio": agora - 60, "results": [{"name": "A", "score": 1}, "lixo"]}))
    assert worker._carregar_checkpoint(agora)["results"] == [
        {"name": "A", "score": 1}]


def test_run_once_parada_no_meio_guarda_checkpoint_sem_gravar_scan(
        monkeypatch, tmp_path):
    salvos = _worker_isolado(monkeypatch, tmp_path)

    def _fake(categories, on_resultado=None, cancelled=None, **kw):
        on_resultado({"name": "A", "score": 1})
        worker._parar = True
        assert cancelled() is True
        return [{"name": "A", "score": 1}]

    monkeypatch.setattr(worker.scan_engine, "run_full_scan", _fake)
    assert worker.run_once({"C": ["A", "B"]}) == []
    assert salvos == {}
    dados = json.loads((tmp_path / "parcial.json").read_text())
    assert [r["name"] for r in dados["results"]] == ["A"]


def test_sigterm_fora_do_scan_sai_e_dentro_so_marca(monkeypatch):
    monkeypatch.setattr(worker, "_escaneando", True)
    worker._ao_receber_sigterm(15, None)
    assert worker._parar is True
    monkeypatch.setattr(worker, "_escaneando", False)
    with pytest.raises(SystemExit):
        worker._ao_receber_sigterm(15, None)


def test_main_com_checkpoint_recente_retoma_sem_esperar(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "_caminho_checkpoint",
                        lambda: tmp_path / "parcial.json")
    (tmp_path / "parcial.json").write_text(json.dumps(
        {"inicio": time.time() - 60, "results": []}))
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos",
                        lambda: [{"ts": time.time() - 60}])
    rodou = []
    monkeypatch.setattr(worker, "run_once", lambda: rodou.append(1) or [{"name": "x"}])
    chamadas = []

    def _fake_sleep(segundos):
        chamadas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        worker.main(intervalo_horas=6)
    # Sem a espera inicial: rodou o ciclo e só então dormiu o intervalo.
    assert rodou == [1]
    assert chamadas == [6 * 3600]


def _worker_main_uma_volta(monkeypatch):
    """Roda `main()` e para na 1a chamada de `time.sleep` (`while True`
    de verdade pararia a suite). Devolve os segundos passados pra sleep."""
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(worker, "run_once", lambda: [{"name": "x"}])
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
    monkeypatch.setenv("LODOUT_WORKER_INTERVAL_HORAS", "2")
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [2 * 3600]


def test_main_sem_env_usa_default(monkeypatch):
    monkeypatch.delenv("LODOUT_WORKER_INTERVAL_HORAS", raising=False)
    chamadas = _worker_main_uma_volta(monkeypatch)
    assert chamadas == [worker._INTERVALO_HORAS_DEFAULT * 3600]


def test_main_parametro_explicito_ignora_env(monkeypatch):
    monkeypatch.setenv("LODOUT_WORKER_INTERVAL_HORAS", "99")
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(worker, "run_once", lambda: [{"name": "x"}])
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
    # achado 2026-11-08 (referência visual: FACEIT): nota grande só no
    # card de destaque da página do item (um item em foco), diferente
    # do anel compacto de listas/tabelas (home/ranking/comparar/
    # parecidos/watchlist/trades/portfólio).
    assert 'class="card-valor nota nota-grande nota-alta"' in body


def test_item_detail_tem_hero_cinematografico(client, monkeypatch, tmp_path):
    """Rodada 2: cabeçalho virou hero com listras, brilho da raridade e
    a imagem grande inclinada -- sem perder o h1 nem os links."""
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85, "price": 50.0,
         "icon": "skin-icon-hash", "case_label": "", "category": "Rifles",
         "name_color": "EB4B4B", "pump_risk": {"level": "low"},
         "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/AK-47 | Redline (Field-Tested)").data.decode("utf-8")

    assert 'class="hero-item raridade-covert"' in body
    assert 'class="hero-item-glow"' in body
    assert 'class="hero-item-imagem"' in body
    assert 'class="icone-item-quadro hero-item-quadro' in body
    assert 'class="titulo-item"' in body
    assert "Ver no Steam Market" in body


def test_item_detail_fileira_de_stats_com_nota_em_destaque(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85, "price": 50.0,
         "case_label": "", "category": "Rifles",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "liquidity_depth": {"days": 45.0, "avg_volume": 2.0, "supply": 90,
                             "band": "fino",
                             "label": "~45d de listagens no ritmo atual (2/dia)"}},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/AK-47 | Redline (Field-Tested)").data.decode("utf-8")

    assert 'class="resumo-cards resumo-cards-item"' in body
    assert 'class="card card-nota-destaque"' in body
    assert 'class="card-valor liquidez liquidez-fino"' in body
    # A fileira é escopada à página do item -- as páginas internas
    # continuam com os cards normais.
    assert "resumo-cards-item" in body


def test_item_detail_mostra_card_de_liquidez(client, monkeypatch, tmp_path):
    """`signals.liquidity_depth()` já calcula isto em todo scan, mas até
    2026-11-02 não aparecia em lugar nenhum da UI -- achado numa
    pesquisa de como outros sites de skin expõem liquidez."""
    resultados = [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "category": "Rifles",
         "breakdown": [],
         "liquidity_depth": {"days": 45.0, "avg_volume": 2.0, "supply": 90,
                             "band": "fino",
                             "label": "~45d de listagens no ritmo atual (2/dia)"}},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/AK-47 | Redline (Field-Tested)").data.decode("utf-8")
    assert "Liquidez" in body
    assert "Baixa liquidez" in body
    assert 'class="card-valor liquidez liquidez-fino"' in body
    assert "~45d de listagens no ritmo atual (2/dia)" in body


def test_item_detail_sem_liquidity_depth_nao_mostra_card(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert "Liquidez" not in body


def test_item_detail_mostra_seletor_de_periodo(client, monkeypatch, tmp_path):
    """Achado 2026-11-02 (pesquisa de sites de skin): o gráfico de
    histórico não tinha seletor de período -- sempre os últimos 60
    pontos, sem jeito de ver só os últimos 7/30/90 dias."""
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 100 * 86400, "price": 10.0},
        {"ts": agora - 2 * 86400, "price": 12.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert "seletor-periodo" in body
    assert "grafico-historico" in body
    assert 'aria-current="true">Tudo</a>' in body


def test_item_detail_periodo_filtra_o_grafico(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 100 * 86400, "price": 10.0},
        {"ts": agora - 2 * 86400, "price": 12.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X?periodo=7d").data.decode("utf-8")
    assert 'aria-current="true">7d</a>' in body
    # só o ponto de 2 dias atrás cai dentro de 7d -- 1 ponto não dá pra
    # traçar linha (charts.line_chart_svg exige pelo menos 2).
    assert "Sem preços registrados nesse período." in body
    assert "grafico-historico" not in body


def test_item_detail_periodo_invalido_cai_no_padrao(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 100 * 86400, "price": 10.0},
        {"ts": agora - 2 * 86400, "price": 12.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X?periodo=1ano").data.decode("utf-8")
    assert 'aria-current="true">Tudo</a>' in body
    assert "grafico-historico" in body


def test_item_detail_grafico_tem_preenchimento_em_gradiente(client, monkeypatch, tmp_path):
    """Achado 2026-11-03 (revisão de direção visual): uma linha nua sem
    nenhum preenchimento "parece wireframe" -- só no gráfico grande da
    página do item (não no sparkline pequeno da tabela, que continua
    sem fill de propósito)."""
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 2 * 86400, "price": 10.0},
        {"ts": agora - 1 * 86400, "price": 12.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert "<linearGradient" in body
    assert "<polygon" in body


def test_item_detail_grafico_tem_tooltip_por_ponto(client, monkeypatch, tmp_path):
    """Item #8 da lista de melhorias -- cada ponto do gráfico grande vira
    um <circle> com <title> (data + preço), tooltip nativo do navegador
    sem precisar de JS (o CSP do site bloqueia estilo inline até via JS,
    então um tooltip flutuante posicionado por JS não daria)."""
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 2 * 86400, "price": 10.0},
        {"ts": agora - 1 * 86400, "price": 12.5},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X").data.decode("utf-8")
    # Escopo na SVG do gráfico grande, não na página inteira -- o anel
    # de nota também usa <circle> (fundo + progresso), sem relação com
    # os pontos do gráfico.
    grafico = body.split("grafico-card", 1)[1].split("</svg>", 1)[0]
    assert grafico.count("<circle") == 2
    assert "R$ 10,00</title>" in grafico
    assert "R$ 12,50</title>" in grafico
    assert 'fill="transparent"' in grafico


def test_item_detail_grafico_colorido_pela_tendencia_do_periodo(
        client, monkeypatch, tmp_path):
    """achado 2026-11-07: decisão revista -- o gráfico grande ficava
    sempre neutro de propósito (cor podia parecer um "veredito" sobre o
    preço), mas o mini-sparkline da listagem já ficou colorido por
    tendência desde 2026-11-06, deixando o site inconsistente (pedido
    do usuário pra uniformizar). A cor segue o PERÍODO EXIBIDO (primeiro
    vs. último ponto do recorte), não só os 2 últimos pontos crus do
    histórico -- trocar de período muda a cor se mudar a direção."""
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 2 * 86400, "price": 10.0},
        {"ts": agora - 1 * 86400, "price": 12.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert 'class="card grafico-card grafico-tendencia-alta"' in body

    hist_baixa = [
        {"ts": agora - 2 * 86400, "price": 12.0},
        {"ts": agora - 1 * 86400, "price": 10.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist_baixa)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert 'class="card grafico-card grafico-tendencia-baixa"' in body


def test_item_detail_grafico_estavel_fica_na_cor_neutra(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 2 * 86400, "price": 10.0},
        {"ts": agora - 1 * 86400, "price": 10.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/item/Item X").data.decode("utf-8")
    assert 'class="card grafico-card">' in body
    assert "grafico-tendencia-" not in body


def test_index_sparkline_nao_tem_preenchimento_em_gradiente(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    agora = time.time()
    hist = [
        {"ts": agora - 2 * 86400, "price": 10.0},
        {"ts": agora - 1 * 86400, "price": 12.0},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: hist)
    body = client.get("/").data.decode("utf-8")
    assert "<linearGradient" not in body
    assert "<polygon" not in body


def test_item_detail_sem_historico_nao_mostra_seletor(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item X", "score": 50, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: [])
    body = client.get("/item/Item X").data.decode("utf-8")
    assert "seletor-periodo" not in body
    assert "Histórico de preço" not in body


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


def test_item_detail_itens_parecidos_mostra_icone_e_anel(
        client, monkeypatch, tmp_path):
    """achado 2026-11-07: "Itens parecidos" era texto puro (nome + "nota
    X, R$ Y") -- _itens_parecidos já reaproveita os candidatos de
    _candidatos_filtrados, que já tinham icon_url/raridade_classe, só o
    template não usava. Pedido do usuário pra deixar consistente com o
    resto do site (ícone compacto + anel de nota, mesmo do Ranking)."""
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": []},
        {"name": "Item B", "score": 78, "price": 12.0, "case_label": "",
         "pump_risk": {"level": "low"}, "category": "Facas", "breakdown": [],
         "icon": "hash-b", "name_color": "EB4B4B"},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/item/Item A").data.decode("utf-8")
    lista = re.search(
        r'<ul class="lista-parecidos">(.*?)</ul>', body, re.DOTALL).group(1)
    assert "icone-item-quadro-compacto" in lista
    assert "icone-item-quadro-com-imagem" in lista
    assert "raridade-covert" in lista
    assert '<span class="nota-numero">78</span>' in lista


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
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "lodout.public_site.server.scan_progress.carregar",
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
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    ts_fixo = 1700000000.0  # epoch arbitrário, fixo -- não depende do "agora"
    monkeypatch.setattr(
        "lodout.public_site.server.scan_store.load_historico_ciclos",
        lambda: [{"ts": ts_fixo, "itens": 152,
                 "duracao_min": 22.3, "sucesso": True}])
    client.post("/admin/login", data={"senha": "segredo"})
    body = client.get("/admin").data.decode("utf-8")
    assert "152 itens" in body
    assert "há " in body
    assert str(int(ts_fixo)) not in body  # nenhum epoch cru na página


# ── worker_alert ─────────────────────────────────────────────

def test_worker_alert_sem_webhook_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.delenv("LODOUT_ADMIN_DISCORD_WEBHOOK", raising=False)
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is False


def test_worker_alert_sucesso_recente_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    ciclos = [{"ts": time.time() - 100, "itens": 5}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is False


def test_worker_alert_manda_quando_atrasado(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(worker_alert.discord_notify, "enviar", lambda url, msg: True)
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(
        ciclos, path=tmp_path / "estado.json") is True


def test_worker_alert_dedup_nao_manda_de_novo(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    chamadas = []
    monkeypatch.setattr(
        worker_alert.discord_notify, "enviar",
        lambda url, msg: chamadas.append(1) or True)
    p = tmp_path / "estado.json"
    ciclos = [{"ts": time.time() - 10 * 3600, "itens": 0}]
    assert worker_alert.verificar_e_alertar(ciclos, path=p) is True
    assert worker_alert.verificar_e_alertar(ciclos, path=p) is False
    assert len(chamadas) == 1


# ── worker_alert: disco cheio ─────────────────────────────────
# `verificar_disco_e_alertar` não tinha NENHUM teste (achado de
# auditoria de cobertura, 2026-11-04) -- justo o alerta pensado pra
# avisar antes do disco da VM encher sem ninguém notar (ver docstring
# do módulo).

def _uso_disco(total=100.0, livre=50.0):
    return SimpleNamespace(total=total, used=total - livre, free=livre)


def test_worker_alert_disco_sem_webhook_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.delenv("LODOUT_ADMIN_DISCORD_WEBHOOK", raising=False)
    monkeypatch.setattr(
        worker_alert.shutil, "disk_usage",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError(
            "não devia nem checar o disco sem webhook configurado")))
    assert worker_alert.verificar_disco_e_alertar(
        path=tmp_path / "estado.json") is False


def test_worker_alert_disco_acima_do_limite_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(
        worker_alert.shutil, "disk_usage",
        lambda *a, **k: _uso_disco(total=100.0, livre=50.0))
    assert worker_alert.verificar_disco_e_alertar(
        path=tmp_path / "estado.json") is False


def test_worker_alert_disco_abaixo_do_limite_manda(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(
        worker_alert.shutil, "disk_usage",
        lambda *a, **k: _uso_disco(total=100.0, livre=5.0))
    chamadas = []
    monkeypatch.setattr(
        worker_alert.discord_notify, "enviar",
        lambda url, msg: chamadas.append(msg) or True)
    assert worker_alert.verificar_disco_e_alertar(
        path=tmp_path / "estado.json") is True
    assert "5.0%" in chamadas[0]


def test_worker_alert_disco_dedup_nao_manda_de_novo(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(
        worker_alert.shutil, "disk_usage",
        lambda *a, **k: _uso_disco(total=100.0, livre=5.0))
    chamadas = []
    monkeypatch.setattr(
        worker_alert.discord_notify, "enviar",
        lambda url, msg: chamadas.append(1) or True)
    p = tmp_path / "estado.json"
    assert worker_alert.verificar_disco_e_alertar(path=p) is True
    assert worker_alert.verificar_disco_e_alertar(path=p) is False
    assert len(chamadas) == 1


def test_worker_alert_disco_erro_ao_checar_nao_alerta(monkeypatch, tmp_path):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")

    def _falha(*a, **k):
        raise OSError("disco inacessível")

    monkeypatch.setattr(worker_alert.shutil, "disk_usage", _falha)
    assert worker_alert.verificar_disco_e_alertar(
        path=tmp_path / "estado.json") is False


def test_worker_alert_disco_total_zero_nao_alerta(monkeypatch, tmp_path):
    # Guarda contra divisão por zero (partição relatando total=0) --
    # sem o `if not uso.total` no código, isto levantaria ZeroDivisionError.
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    monkeypatch.setattr(
        worker_alert.shutil, "disk_usage",
        lambda *a, **k: _uso_disco(total=0.0, livre=0.0))
    assert worker_alert.verificar_disco_e_alertar(
        path=tmp_path / "estado.json") is False


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


def test_comparar_mostra_icone_com_raridade(client, monkeypatch, tmp_path):
    """achado 2026-11-07: o cabeçalho de /comparar mostrava a imagem
    solta (sem o quadro nem a borda de raridade que a home já tinha) --
    _candidatos_filtrados já calculava icon_url/raridade_classe pra
    esses itens, só o template não usava."""
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "icon": "hash-a", "name_color": "EB4B4B"},
    ])
    body = client.get("/comparar?nomes=Item A").data.decode("utf-8")
    # Tamanho cheio (88px) desde 2026-11-08 -- até 3 itens lado a lado
    # cabe o mesmo tratamento do destaque da vitrine, não a moldura
    # compacta de 40px (essa continua só em Ranking/listas densas).
    assert "icone-item-quadro-compacto" not in body
    assert "icone-item-quadro-com-imagem" in body
    assert "raridade-covert" in body
    assert 'title="Raridade: Covert (vermelho)"' in body


def test_comparar_mostra_liquidez(client, monkeypatch, tmp_path):
    """Achado 2026-11-02 (varredura de código morto/consistência): a
    tabela de /comparar tinha Preço/Nota/Caixa/Risco/Tendência mas não
    Liquidez, mesmo o dado já vindo em cada item (mesmo campo usado no
    index e no card de item.html)."""
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "liquidity_depth": {"days": 45.0, "avg_volume": 2.0, "supply": 90,
                             "band": "fino",
                             "label": "~45d de listagens no ritmo atual (2/dia)"}},
        {"name": "Item B", "score": 60, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "medium"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A,Item B").data.decode("utf-8")
    assert "<td>Liquidez</td>" in body
    assert 'class="liquidez liquidez-fino"' in body
    assert "~45d de listagens no ritmo atual (2/dia)" in body


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
    item.html) -- .nota tem display:inline-grid (anel), que tira o <td> do
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
    # Item A (80, a maior nota da linha) ganha o destaque descritivo --
    # ver test_comparar_destaca_menor_preco_e_maior_nota_na_linha.
    assert '<td class="valor-destaque-linha"><span class="nota nota-alta">' in body
    assert '<td><span class="nota nota-media">' in body
    assert '<span class="nota-numero">80</span>' in body
    assert '<span class="nota-numero">60</span>' in body


def test_comparar_destaca_menor_preco_e_maior_nota_na_linha(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item B", "score": 60, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item C", "score": 70, "price": 20.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A,Item B,Item C").data.decode("utf-8")
    linha_preco = body.split(">Preço<", 1)[1].split("</tr>", 1)[0]
    linha_nota = body.split(">Nota<", 1)[1].split("</tr>", 1)[0]
    # Item B tem o menor preço (5.0) e Item A a maior nota (80) -- só
    # esses dois ganham o destaque, nunca um "melhor" geral.
    celulas_preco = linha_preco.split("<td")[1:]
    assert "valor-destaque-linha" in celulas_preco[1]  # Item B
    assert "valor-destaque-linha" not in celulas_preco[0]
    assert "valor-destaque-linha" not in celulas_preco[2]
    assert "menor preço nesta linha" in celulas_preco[1]
    celulas_nota = linha_nota.split("<td")[1:]
    assert "valor-destaque-linha" in celulas_nota[0]  # Item A
    assert "valor-destaque-linha" not in celulas_nota[1]
    assert "valor-destaque-linha" not in celulas_nota[2]
    assert "maior nota nesta linha" in celulas_nota[0]


def test_comparar_sem_destaque_quando_valores_empatam(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 70, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item B", "score": 70, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A,Item B").data.decode("utf-8")
    assert "valor-destaque-linha" not in body


def test_comparar_sem_destaque_com_1_item_so(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 70, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A").data.decode("utf-8")
    assert "valor-destaque-linha" not in body


def test_comparar_com_1_item_mostra_aviso_pra_adicionar_mais(
        client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 70, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A").data.decode("utf-8")
    assert "Só 1 item selecionado" in body
    assert "comparação fica mais útil com 2 ou 3" in body


def test_comparar_com_2_itens_nao_mostra_aviso(client, monkeypatch, tmp_path):
    resultados = [
        {"name": "Item A", "score": 70, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
        {"name": "Item B", "score": 60, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    body = client.get("/comparar?nomes=Item A,Item B").data.decode("utf-8")
    assert "Só 1 item selecionado" not in body


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
        "lodout.public_site.server.db_backup._DB_PATH",
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
    monkeypatch.setattr("lodout.public_site.server.db_backup._DB_PATH", db)
    resp = client.get("/readyz")
    assert resp.get_json()["ready"] is True


def test_readyz_com_banco_corrompido_nao_e_ready(client, monkeypatch, tmp_path):
    db = tmp_path / "corrompido.db"
    db.write_bytes(b"isto nao e um sqlite valido nem perto")
    monkeypatch.setattr("lodout.public_site.server.db_backup._DB_PATH", db)
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
    p = icon_cache._caminho("abc123", icon_cache.TAMANHO_PADRAO)
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
    assert icon_cache._caminho(_HASH_REAL, icon_cache.TAMANHO_PADRAO).exists()


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
    caminho = icon_cache._caminho("novohash", icon_cache.TAMANHO_PADRAO)
    assert caminho.suffix == ".webp"
    assert caminho.read_bytes() == resultado


def test_rota_icone_sem_cache_redireciona_pro_cdn(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.icon_cache.obter", lambda h, t: None)
    resp = client.get("/icone/abc123.webp")
    assert resp.status_code == 302
    assert "steamstatic.com" in resp.headers["Location"]


def test_rota_icone_com_cache_serve_bytes(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server.icon_cache.obter",
        lambda h, t: b"dados-da-imagem")
    resp = client.get("/icone/abc123.webp")
    assert resp.status_code == 200
    assert resp.data == b"dados-da-imagem"
    assert resp.mimetype == "image/webp"
    assert "max-age" in resp.headers.get("Cache-Control", "")


def test_rota_icone_tam_384_passa_pro_icon_cache(client, monkeypatch):
    # srcset 2x pede ?tam=384 (2026-11-08) -- confere que a rota repassa
    # o tamanho pro icon_cache.obter() em vez de ignorar a query string.
    chamadas = []

    def _obter(hash_icone, tamanho):
        chamadas.append(tamanho)
        return b"dados-384"

    monkeypatch.setattr(
        "lodout.public_site.server.icon_cache.obter", _obter)
    resp = client.get("/icone/abc123.webp?tam=384")
    assert resp.status_code == 200
    assert resp.data == b"dados-384"
    assert chamadas == [384]


def test_rota_icone_tam_invalido_cai_no_padrao(client, monkeypatch):
    chamadas = []

    def _obter(hash_icone, tamanho):
        chamadas.append(tamanho)
        return b"x"

    monkeypatch.setattr(
        "lodout.public_site.server.icon_cache.obter", _obter)
    resp = client.get("/icone/abc123.webp?tam=9999")
    assert resp.status_code == 200
    assert chamadas == [icon_cache.TAMANHO_PADRAO]


def test_icon_cache_obter_tamanho_fora_da_lista_cai_no_padrao(
        monkeypatch, tmp_path):
    monkeypatch.setattr(icon_cache, "_CACHE_DIR", tmp_path)
    p = tmp_path / "abc123.v3.192.webp"
    p.write_bytes(b"ja-em-cache-192")
    # tamanho=999 não existe em TAMANHOS_PERMITIDOS -- cai pro padrão
    # (192) e lê o mesmo arquivo que um `obter("abc123")` sem tamanho leria.
    assert icon_cache.obter("abc123", 999) == b"ja-em-cache-192"


def test_rota_icone_tem_rate_limit(monkeypatch):
    """Sem login, cache miss grava arquivo novo em disco -- sem limite,
    um hash diferente por chamada enche o disco sem fim (achado
    2026-10-27 junto da sanitização em icon_cache.obter()). Mesmo
    gotcha de `rate_limited` avaliado na decoração: patcha ANTES de
    `create_app()`."""
    monkeypatch.setattr(
        "lodout.public_site.server.icon_cache.obter", lambda h, t: b"x")
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

def test_fonte_inter_serve_com_mime_de_fonte(client):
    """A webfont sai como font/woff2 (a stdlib não conhece .woff2 e o
    server.py registra o tipo) -- application/octet-stream acende
    aviso no console de alguns navegadores."""
    resp = client.get("/static/fonts/inter-latin-opsz-normal.woff2?v=1")
    assert resp.status_code == 200
    assert resp.mimetype == "font/woff2"
    assert resp.data[:4] == b"wOF2"


def test_manifest_json_acessivel(client):
    resp = client.get("/static/manifest.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "Lodout"
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


def test_icones_do_site_usam_a_marca_das_aspas(client):
    """Decisão de 2026-11-11: o ícone da aba e o do celular passaram a ser
    as mesmas aspas da barra -- a vela vermelha da marca antiga saiu."""
    svg = client.get("/static/favicon.svg").data.decode("utf-8")
    assert "#dc2626" not in svg                # vermelho da vela antiga
    assert "#ffffff" in svg                    # aspas em branco
    assert "M12 12a1 1 0 0 0 1-1" in svg       # desenho das aspas

    from PIL import Image
    import io
    for nome, lado in (("icon-192.png", 192), ("icon-512.png", 512)):
        dados = client.get(f"/static/{nome}").data
        img = Image.open(io.BytesIO(dados)).convert("RGB")
        assert img.size == (lado, lado)
        px = img.load()
        brancos = sum(1 for y in range(lado) for x in range(lado)
                      if sum(px[x, y]) > 600)
        escuros = sum(1 for y in range(lado) for x in range(lado)
                      if sum(px[x, y]) < 200)
        assert brancos > lado * lado * 0.05   # aspas
        assert escuros > lado * lado * 0.70   # fundo escuro


def test_apple_touch_icon_usa_png_nao_svg(client, monkeypatch):
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    body = client.get("/").data.decode("utf-8")
    assert 'rel="apple-touch-icon" href="/static/icon-192.png' in body


def test_sem_preload_de_fonte_custom(client, monkeypatch):
    """Identidade 3.0 (2026-11-09): uma família só, do stack de sistema,
    em todo o site -- Poppins SemiBold não é mais usada como @font-face
    em texto nenhum (só a logo, como contorno SVG). O preload que
    existia pra ela virou peso morto (baixava um arquivo que nenhum CSS
    referenciava mais); removido junto com o arquivo."""
    monkeypatch.setattr(scan_store, "load_last_scan", lambda: None)
    body = client.get("/").data.decode("utf-8")
    assert "Poppins" not in body
    # O preload da fonte Inter (referenciada pelo @font-face do CSS) é
    # intencional: acelera o LCP. O que não pode mais existir é preload
    # de fonte custom não usada (Poppins).
    assert 'Poppins' not in body
    assert 'inter-latin-opsz-normal.woff2' in body
    # Não deve haver preload de arquivo de fonte Poppins.
    assert not any(
        'rel="preload"' in linha and 'Poppins' in linha
        for linha in body.splitlines()
    )


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
    p = icon_cache._caminho("../../etc/passwd", icon_cache.TAMANHO_PADRAO)
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
    monkeypatch.setattr("lodout.public_site.server.db_backup._DB_PATH", diretorio)
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
    assert body.count('"@type": "DefinedTerm"') == body.count("<dt ")
    assert "Steam Community Market" in body
    assert "Procura × Oferta" in body
    assert '<dt id="termo-liquidez"><strong>Liquidez</strong></dt>' in body
    assert 'aria-label="Índice do glossário"' in body
    assert 'href="#termo-procura-oferta"' in body
    assert '<dt id="termo-procura-oferta"' in body
    assert 'href="#termo-raridade"' in body
    assert '<dt id="termo-raridade"><strong>Raridade</strong></dt>' in body
    # Termos do glossário não devem ter tabindex="-1": precisam ser
    # alcançáveis com a tecla Tab (WCAG 2.1.1 Keyboard).
    assert 'tabindex="-1"' not in body


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
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
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
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.post("/admin/testar-webhook", data={})
    assert resp.status_code == 403


def test_admin_testar_webhook_com_csrf_funciona(client, monkeypatch):
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "lodout.public_site.server.discord_notify.enviar",
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
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr("lodout.public_site.server._ERROR_LOG_PATH", log)
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin/log-bruto")
    assert resp.status_code == 200
    assert b"linha de erro" in resp.data


def test_admin_grafico_erros_tem_tooltip_por_ponto(client, monkeypatch, tmp_path):
    # mesma ronda de /status e /conta/historico: o gráfico de erros do
    # admin também chamava charts.line_chart_svg sem rotulos.
    log = tmp_path / "errors.log"
    log.write_text(
        "2026-11-07 10:00:00,000 ERROR algo\n"
        "2026-11-08 09:00:00,000 ERROR outro\n"
        "2026-11-08 11:00:00,000 ERROR outro2\n",
        encoding="utf-8")
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr("lodout.public_site.server._ERROR_LOG_PATH", log)
    client.post("/admin/login", data={"senha": "segredo"})
    body = client.get("/admin").data.decode("utf-8")
    assert "grafico-erros" in body
    assert "<title>07/11/2026 — 1 erro</title>" in body
    assert "<title>08/11/2026 — 2 erros</title>" in body


def test_admin_backup_download_sem_sessao_e_404(client):
    resp = client.get("/admin/backup/public_site-20261026-120000.db")
    assert resp.status_code == 404


def test_admin_backup_download_com_sessao_baixa_arquivo(client, monkeypatch, tmp_path):
    backup = tmp_path / "public_site-20261026-120000.db"
    backup.write_bytes(b"dados falsos de sqlite")
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "lodout.public_site.server.db_backup._BACKUP_DIR", tmp_path)
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
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "lodout.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    for nome in ("../secreto.txt", "secreto.txt", "public_site-123.db",
                "public_site-20261026-120000.db.bak"):
        resp = client.get(f"/admin/backup/{nome}")
        assert resp.status_code in (404, 400), nome


def test_admin_backup_download_arquivo_inexistente_e_404(client, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "lodout.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    resp = client.get("/admin/backup/public_site-20261026-120000.db")
    assert resp.status_code == 404


def test_admin_lista_backups_tem_link_de_download(client, monkeypatch, tmp_path):
    backup = tmp_path / "public_site-20261026-120000.db"
    backup.write_bytes(b"x")
    monkeypatch.setattr(
        "lodout.public_site.server._ADMIN_PASSWORD_HASH",
        generate_password_hash("segredo"))
    monkeypatch.setattr(
        "lodout.public_site.server.db_backup._BACKUP_DIR", tmp_path)
    client.post("/admin/login", data={"senha": "segredo"})
    body = client.get("/admin").data.decode("utf-8")
    assert "/admin/backup/public_site-20261026-120000.db" in body


def test_disco_info_nao_quebra_sem_dados():
    from lodout.public_site.server import _disco_info
    info = _disco_info()
    assert "livre_fmt" in info


def test_contagem_usuarios_sem_banco_e_zero(monkeypatch, tmp_path):
    from lodout.public_site.server import _contagem_usuarios
    monkeypatch.setattr(
        "lodout.public_site.server.db_backup._DB_PATH",
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

    caminho = (Path(__file__).parent.parent / "lodout" / "public_site"
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

    raiz = Path(__file__).parent.parent / "lodout" / "public_site"
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

    css = (Path(__file__).parent.parent / "lodout" / "public_site"
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

    raiz = Path(__file__).parent.parent / "lodout" / "public_site" / "templates"
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

    raiz = Path(__file__).parent.parent / "lodout" / "public_site"
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

    raiz = Path(__file__).parent.parent / "lodout" / "public_site" / "templates"
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

    raiz = Path(__file__).parent.parent / "lodout" / "public_site" / "templates"
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

    raiz = Path(__file__).parent.parent / "lodout" / "public_site" / "templates"
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
        "lodout.public_site.server.user_store.get_user",
        lambda steamid, path=None: None)
    with client.session_transaction() as sess:
        sess["steamid"] = "123"
    body = client.get("/conta/trades").data.decode("utf-8")
    assert 'href="/conta/trades" aria-current="page"' in body
    assert 'href="/conta/watchlist" aria-current="page"' not in body


# ── Rodada 3: performance -- historico so' pra fatia visivel ──

def test_candidatos_filtrados_sem_historico_nao_calcula_sparkline():
    from lodout.public_site.server import _candidatos_filtrados
    scan = {"ts": time.time(), "category": "x", "results": [
        {"name": "Item A", "score": 80, "price": 10.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ]}
    out = _candidatos_filtrados(scan, com_historico=False)
    assert "sparkline" not in out[0]
    assert "tendencia" not in out[0]


def test_enriquecer_com_historico_preenche_campos(monkeypatch):
    from lodout.public_site.server import _enriquecer_com_historico
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: [{"ts": 1, "price": 10.0}, {"ts": 2, "price": 12.0}])
    candidatos = [{"name": "Item A"}]
    _enriquecer_com_historico(candidatos)
    assert candidatos[0]["tendencia"] == "alta"
    assert "mini-sparkline" in candidatos[0]["sparkline"]
    # 2 pontos é pouco -- a linha ficava tão "confiante" quanto uma de
    # 20 sem nenhum aviso (achado 2026-11-02).
    assert candidatos[0]["historico_curto"] is True
    assert candidatos[0]["historico_pontos"] == 2


def test_index_mostra_selo_de_historico_curto(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    monkeypatch.setattr(signals, "load_item_history", lambda name: [
        {"ts": "2026-10-28T12:00:00", "price": 48.0},
        {"ts": "2026-10-29T12:00:00", "price": 50.0},
    ])
    body = client.get("/?ver=lista").data.decode("utf-8")
    assert "selo-historico-curto" in body
    assert "histórico curto".encode("utf-8") in body.encode("utf-8")


def test_index_nao_mostra_selo_com_historico_suficiente(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 85,
         "price": 50.0, "case_label": "", "pump_risk": {"level": "low"},
         "breakdown": []},
    ])
    monkeypatch.setattr(
        signals, "load_item_history",
        lambda name: [{"ts": str(i), "price": 50.0 + i} for i in range(10)])
    body = client.get("/").data.decode("utf-8")
    assert "selo-historico-curto" not in body


def test_enriquecer_com_historico_nao_marca_curto_com_pontos_suficientes(
        monkeypatch):
    from lodout.public_site.server import _enriquecer_com_historico
    monkeypatch.setattr(
        "lodout.public_site.server.signals.load_item_history",
        lambda name: [{"ts": i, "price": 10.0 + i} for i in range(5)])
    candidatos = [{"name": "Item A"}]
    _enriquecer_com_historico(candidatos)
    assert candidatos[0]["historico_curto"] is False
    assert candidatos[0]["historico_pontos"] == 5


# ── Rodada 4: performance -- icone so' pra fatia visivel ────────

def test_candidatos_filtrados_sem_icone_nao_builda_url(client):
    # mesmo achado de performance que com_historico=False: profiling
    # 2026-11-09 mostrou url_for("icone_cache", ...) como 42% do tempo
    # de / inteiro, rodando pros ~150-180 candidatos quando só 10
    # aparecem na página.
    from lodout.public_site.server import _candidatos_filtrados
    scan = {"ts": time.time(), "category": "x", "results": [
        {"name": "Item A", "score": 80, "price": 10.0, "icon": "hash123",
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]}
    out = _candidatos_filtrados(scan, com_historico=False, com_icone=False)
    assert out[0]["icon_url"] is None
    assert out[0]["icon_url_2x"] is None


def test_enriquecer_com_icone_preenche_campos(client):
    from lodout.public_site.server import _enriquecer_com_icone
    candidatos = [{"name": "Item A", "icon": "hash123"},
                 {"name": "Item B", "icon": None}]
    with client.application.test_request_context():
        _enriquecer_com_icone(candidatos)
    assert candidatos[0]["icon_url"] == "/icone/hash123.webp?v=2"
    assert candidatos[0]["icon_url_2x"] == "/icone/hash123.webp?v=2&tam=384"
    assert candidatos[1]["icon_url"] is None
    assert candidatos[1]["icon_url_2x"] is None


def test_candidatos_filtrados_com_icone_default_continua_preenchendo(
        client):
    # default (sem passar com_icone) continua True -- nenhum caller que
    # não foi atualizado explicitamente perde o ícone sem querer.
    from lodout.public_site.server import _candidatos_filtrados
    scan = {"ts": time.time(), "category": "x", "results": [
        {"name": "Item A", "score": 80, "price": 10.0, "icon": "hash123",
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ]}
    with client.application.test_request_context():
        out = _candidatos_filtrados(scan, com_historico=False)
    assert out[0]["icon_url"] == "/icone/hash123.webp?v=2"


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
        "lodout.public_site.server.signals.load_item_history", _contado)
    resp = client.get("/")
    assert resp.status_code == 200
    assert len(chamadas) <= 15  # página de 10 + folga, nunca os 152


def test_index_so_builda_icone_da_pagina_atual(client, monkeypatch, tmp_path):
    """Mesma família -- url_for("icone_cache", ...) não pode rodar pros
    152 candidatos inteiros quando só 10 aparecem na página (achado de
    performance 2026-11-09, ver _enriquecer_com_icone)."""
    resultados = [
        {"name": f"Item {i:03d}", "score": 50, "price": 1.0, "icon": "h",
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []}
        for i in range(152)
    ]
    _salva_scan(tmp_path, monkeypatch, resultados)
    from lodout.public_site import server as server_mod
    real_url_for = server_mod.url_for
    chamadas = []

    def _contado(endpoint, *a, **kw):
        if endpoint == "icone_cache":
            chamadas.append(endpoint)
        return real_url_for(endpoint, *a, **kw)

    monkeypatch.setattr(server_mod, "url_for", _contado)
    resp = client.get("/")
    assert resp.status_code == 200
    # 10 da página x 2 (icon_url + icon_url_2x) + folga, nunca os 152
    assert len(chamadas) <= 25


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
        "lodout.public_site.server.signals.load_item_history", _contado)
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
        "lodout.public_site.server.signals.load_item_history", _contado)
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
    assert "<title>Lodout</title>" in body


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
                        lambda categories, on_progress=None, **kw: resultados)
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


# ── /novidades, saídas do Top 20, histórico no item ─────────────

_EVENTO_ARMORY = {
    "type": "xpshop_removed", "internal": "crate_community_33",
    "name": "Kilowatt Case", "summary": "...", "ts": 1794500000.0,
    "commit_sha": "abc", "commit_date": "2026-11-10T15:00:00Z",
}


def test_novidades_vazia_explica_o_que_vai_aparecer(client, monkeypatch):
    monkeypatch.setattr(server.gamedata, "load_events_log", lambda: [])
    monkeypatch.setattr(server.gamedata, "load_state", lambda: None)
    monkeypatch.setattr(server.steam_news, "carregar_noticias", lambda: [])
    resp = client.get("/novidades")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Nenhuma mudança detectada até agora" in body
    assert "depois do próximo ciclo de coleta" in body


def test_novidades_mostra_evento_e_noticia(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Kilowatt Case", "score": 70, "price": 5.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ], category="Caixas")
    monkeypatch.setattr(server.gamedata, "load_events_log",
                        lambda: [_EVENTO_ARMORY, {"type": "desconhecido"}])
    monkeypatch.setattr(server.gamedata, "load_state",
                        lambda: {"fetched_at": time.time() - 60})
    monkeypatch.setattr(
        server.steam_news, "carregar_noticias",
        lambda: [{"titulo": "<script>x</script> Notas", "resumo": "Mapa",
                  "url": "https://steamcommunity.com/games/CSGO/1",
                  "ts": 1794500000.0}])
    body = client.get("/novidades").data.decode("utf-8")
    assert "saiu do Armory" in body
    assert "10/11/2026" in body
    assert 'href="/item/Kilowatt%20Case"' in body
    assert "&lt;script&gt;x&lt;/script&gt; Notas" in body
    assert "<script>x</script>" not in body
    assert 'href="https://steamcommunity.com/games/CSGO/1"' in body
    assert "desconhecido" not in body


def test_rodape_linka_novidades(client):
    body = client.get("/sobre").data.decode("utf-8")
    assert 'href="/novidades"' in body


def test_ranking_mostra_quem_saiu_do_top(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Z", "score": 41, "price": 1.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    h = 3600.0
    snaps = [
        {"ts": 1000 * h - 24 * h, "items": [
            {"name": "X", "score": 70, "position": 1},
            {"name": "Z", "score": 60, "position": 2},
            {"name": "Sumiu", "score": 55, "position": 3}]},
        {"ts": 1000 * h, "items": [{"name": "X", "score": 80, "position": 1}]},
    ]
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots", lambda: snaps)
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.latest_before",
        lambda ts: next((s for s in reversed(snaps) if s["ts"] < ts), None))
    body = client.get("/ranking").data.decode("utf-8")
    assert "Saíram do Top 20" in body
    assert "era #2 com nota 60; agora nota 41" in body
    assert 'href="/item/Z"' in body
    # Fora do scan atual: sem link (a página do item daria 404).
    assert 'href="/item/Sumiu"' not in body
    assert "era #3 com nota 55" in body


def test_ranking_sem_saidas_nao_mostra_secao(client, monkeypatch):
    _ranking_com_historico(monkeypatch)
    body = client.get("/ranking").data.decode("utf-8")
    assert "Saíram do Top 20" not in body


def test_item_mostra_historico_no_ranking_e_eventos(
        client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Kilowatt Case", "score": 70, "price": 5.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": [],
         "category": "Caixas"},
    ], category="Caixas")
    agora = time.time()
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots",
        lambda: [
            {"ts": agora - 86400, "items": [
                {"name": "Kilowatt Case", "score": 70, "position": 4}]},
            {"ts": agora, "items": [
                {"name": "Kilowatt Case", "score": 70, "position": 2}]},
        ])
    monkeypatch.setattr(server.gamedata, "load_events_log",
                        lambda: [_EVENTO_ARMORY,
                                 dict(_EVENTO_ARMORY, name="Outra Caixa")])
    body = client.get("/item/Kilowatt Case").data.decode("utf-8")
    assert "Hoje está em <strong>#2</strong> do Top 20." in body
    assert "<strong>2 de 2</strong> dias" in body
    assert "melhor posição: <strong>#2</strong>" in body
    assert body.count('class="faixa-dia faixa-dia-') == 30 + 3
    assert "Mudanças no jogo" in body
    assert "saiu do Armory" in body
    assert "Outra Caixa" not in body


def test_item_sem_ranking_salvo_avisa(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "A", "score": 70, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    monkeypatch.setattr(
        "lodout.public_site.server.ranking.load_snapshots", lambda: [])
    monkeypatch.setattr(server.gamedata, "load_events_log", lambda: [])
    body = client.get("/item/A").data.decode("utf-8")
    assert "Ainda não há ranking salvo nos últimos 30 dias" in body
    assert "Mudanças no jogo" not in body


def test_status_mostra_ritmo_e_itens_em_espera(client, monkeypatch):
    monkeypatch.setattr(
        scan_store, "load_historico_ciclos",
        lambda: [{"ts": time.time() - 60, "itens": 180, "duracao_min": 33.0,
                  "sucesso": True, "alvos": 184, "mantidos": 0,
                  "falhas": [], "ritmo": 1.25, "pausas_429": 0,
                  "em_espera": ["Kilowatt Case"]}])
    body = client.get("/status").data.decode("utf-8")
    assert "1,25× o intervalo normal" in body
    assert "Itens em espera (1)" in body
    assert "Caixa Kilowatt" in body


def test_api_health_expoe_diagnostico_do_ultimo_ciclo(client, monkeypatch):
    monkeypatch.setattr(
        scan_store, "load_historico_ciclos",
        lambda: [{"ts": 1.0, "itens": 1, "duracao_min": 1.0, "sucesso": True,
                  "pausas_429": 2,
                  "comparacao_fontes": {"razao_preco": 0.01}}])
    dados = client.get("/api/health").get_json()
    assert dados["ultimo_ciclo_worker"]["pausas_429"] == 2
    assert dados["ultimo_ciclo_worker"]["comparacao_fontes"]["razao_preco"] == 0.01


def test_item_mostra_outras_versoes(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "AK-47 | Redline (Field-Tested)", "score": 70, "price": 50.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": [],
         "variantes": [
             {"name": "AK-47 | Redline (Minimal Wear)", "mediana": 120.5,
              "ts": time.time() - 3600, "compras_24h": 12},
             {"name": "StatTrak™ AK-47 | Redline (Field-Tested)",
              "mediana": 99.0, "ts": time.time(), "compras_24h": 3},
         ]},
        {"name": "AK-47 | Redline (Minimal Wear)", "score": 60, "price": 120.0,
         "case_label": "", "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/item/AK-47 | Redline (Field-Tested)").data.decode("utf-8")
    assert "Outras versões desta skin" in body
    assert "R$ 120,50" in body
    # Versão acompanhada pelo site: link interno.
    assert 'href="/item/AK-47%20%7C%20Redline%20(Minimal%20Wear)"' in body
    # Versão fora do site: link pro Market.
    assert ("https://steamcommunity.com/market/listings/730/"
            "StatTrak%E2%84%A2%20AK-47%20%7C%20Redline%20%28Field-Tested%29") in body


def test_item_sem_variantes_nao_mostra_secao(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "A", "score": 70, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    body = client.get("/item/A").data.decode("utf-8")
    assert "Outras versões desta skin" not in body


# ── alerta de qualidade do scan ─────────────────────────────

def _alerta_qualidade(monkeypatch):
    monkeypatch.setenv("LODOUT_ADMIN_DISCORD_WEBHOOK", "https://discord/x")
    msgs = []
    monkeypatch.setattr(worker_alert.discord_notify, "enviar",
                        lambda url, msg: msgs.append(msg) or True)
    return msgs


def test_alerta_qualidade_cobertura_baixa(monkeypatch, tmp_path):
    msgs = _alerta_qualidade(monkeypatch)
    ciclos = [{"ts": 1.0, "itens": 120, "alvos": 185}]
    assert worker_alert.verificar_qualidade_e_alertar(
        ciclos, now=1_000_000.0, path=tmp_path / "q.json") is True
    assert "só 120 de 185 itens (65%)" in msgs[0]
    # Dedup de 24 h.
    assert worker_alert.verificar_qualidade_e_alertar(
        ciclos, now=1_000_100.0, path=tmp_path / "q.json") is False


def test_alerta_qualidade_throttle_silencioso(monkeypatch, tmp_path):
    msgs = _alerta_qualidade(monkeypatch)
    ciclos = [{"ts": 1.0, "itens": 184, "alvos": 185,
               "throttle_silencioso": 2}]
    assert worker_alert.verificar_qualidade_e_alertar(
        ciclos, path=tmp_path / "q.json") is True
    assert "throttle silencioso detectado 2x" in msgs[0]


def test_alerta_qualidade_ciclo_bom_ou_antigo_nao_alerta(monkeypatch, tmp_path):
    msgs = _alerta_qualidade(monkeypatch)
    p = tmp_path / "q.json"
    assert worker_alert.verificar_qualidade_e_alertar(
        [{"ts": 1.0, "itens": 180, "alvos": 185}], path=p) is False
    assert worker_alert.verificar_qualidade_e_alertar(
        [{"ts": 1.0, "itens": 50}], path=p) is False
    # Zero item é do alerta de atraso, não deste.
    assert worker_alert.verificar_qualidade_e_alertar(
        [{"ts": 1.0, "itens": 0, "alvos": 185}], path=p) is False
    assert msgs == []


def test_alerta_qualidade_sem_webhook_nao_faz_nada(monkeypatch, tmp_path):
    monkeypatch.delenv("LODOUT_ADMIN_DISCORD_WEBHOOK", raising=False)
    assert worker_alert.verificar_qualidade_e_alertar(
        [{"ts": 1.0, "itens": 1, "alvos": 185}],
        path=tmp_path / "q.json") is False


def test_espera_apos_ciclo_vazio_tenta_antes_com_backoff():
    assert worker._espera_apos_ciclo(6, 0) == 6 * 3600
    assert worker._espera_apos_ciclo(6, 1) == 1 * 3600
    assert worker._espera_apos_ciclo(6, 2) == 2 * 3600
    assert worker._espera_apos_ciclo(6, 3) == 4 * 3600
    assert worker._espera_apos_ciclo(6, 9) == 4 * 3600
    # Nunca depois do intervalo normal.
    assert worker._espera_apos_ciclo(1.5, 3) == 1.5 * 3600


def test_main_ciclo_vazio_dorme_so_1h(monkeypatch):
    monkeypatch.setattr(worker.scan_store, "load_historico_ciclos", lambda: [])
    monkeypatch.setattr(worker, "run_once", lambda: [])
    chamadas = []

    def _fake_sleep(segundos):
        chamadas.append(segundos)
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        worker.main(intervalo_horas=6)
    assert chamadas == [3600]


def test_prioridade_do_scan_anterior(monkeypatch):
    monkeypatch.setattr(worker.scan_store, "load_last_scan", lambda: {
        "ts": 1, "results": [
            {"name": "Alta", "score": 90},
            {"name": "Baixa", "score": 10},
            {"name": "Atrasado", "score": 5,
             "mantido_do_ciclo_anterior": True}]})
    p = worker._prioridade_do_scan_anterior()
    assert sorted(p, key=p.get) == ["Atrasado", "Alta", "Baixa"]
    monkeypatch.setattr(worker.scan_store, "load_last_scan", lambda: None)
    assert worker._prioridade_do_scan_anterior() == {}


def test_status_mostra_ciclo_encerrado_cedo(client, monkeypatch):
    monkeypatch.setattr(
        scan_store, "load_historico_ciclos",
        lambda: [{"ts": time.time() - 60, "itens": 0, "duracao_min": 1.5,
                  "sucesso": False, "alvos": 185, "abortado": True,
                  "falhas": []}])
    body = client.get("/status").data.decode("utf-8")
    assert "Steam sem resposta (encerrado cedo)" in body


def test_estado_do_scan_em_andamento_com_previsao():
    agora = 1_000_000.0
    ciclos = [{"ts": agora - 3600, "itens": 180, "alvos": 180,
               "duracao_min": 30.0, "sucesso": True}]
    e = server._estado_do_scan(
        {"indice": 60, "total": 180, "item": "Kilowatt Case",
         "ts": agora - 10}, ciclos, 6, now=agora)
    # 30 min / 180 itens = 10 s/item; faltam 120 -> 20 min.
    assert e == {"rodando": True, "indice": 60, "total": 180,
                 "item_fmt": "Caixa Kilowatt", "faltam_txt": "~20 min"}


def test_estado_do_scan_parado_mostra_proximo():
    agora = 1_000_000.0
    ciclos = [{"ts": agora - 2 * 3600, "itens": 180, "sucesso": True}]
    # Progresso velho (ciclo já acabou) não conta como "rodando".
    e = server._estado_do_scan(
        {"indice": 180, "total": 180, "item": "X", "ts": agora - 2 * 3600},
        ciclos, 6, now=agora)
    assert e == {"rodando": False, "proximo_txt": "em ~4 h"}
    assert server._estado_do_scan(None, [], 6, now=agora) == {
        "rodando": False, "proximo_txt": None}
    e = server._estado_do_scan(
        {"indice": 3, "total": 180, "item": "X", "ts": agora - 600},
        ciclos, 6, now=agora)
    assert e["rodando"] is False


def test_status_mostra_scan_em_andamento(client, monkeypatch):
    monkeypatch.setattr(
        server.scan_progress, "carregar",
        lambda: {"indice": 42, "total": 185, "item": "<b>x</b>",
                 "ts": time.time()})
    monkeypatch.setattr(
        scan_store, "load_historico_ciclos",
        lambda: [{"ts": time.time() - 6 * 3600, "itens": 185, "alvos": 185,
                  "duracao_min": 30.0, "sucesso": True}])
    body = client.get("/status").data.decode("utf-8")
    assert "item <strong>42 de 185</strong>" in body
    assert 'value="42" max="185"' in body
    assert "&lt;b&gt;x&lt;/b&gt;" in body
    assert "termina em ~" in body


def test_home_marca_item_com_preco_do_ciclo_anterior(client, monkeypatch, tmp_path):
    _salva_scan(tmp_path, monkeypatch, [
        {"name": "Velho", "score": 70, "price": 5.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": [],
         "mantido_do_ciclo_anterior": True,
         "coletado_em": time.time() - 7 * 3600},
        {"name": "Novo", "score": 60, "price": 6.0, "case_label": "",
         "pump_risk": {"level": "low"}, "breakdown": []},
    ])
    for ver in ("vitrine", "lista"):
        body = client.get(f"/?ver={ver}").data.decode("utf-8")
        rotulo = ">Preço do ciclo anterior<" if ver == "vitrine" else ">Ciclo anterior<"
        assert body.count(rotulo) == 1
        assert "(coletado há 7 h)" in body


def test_fonte_do_ciclo_desligada_por_padrao(monkeypatch):
    monkeypatch.delenv("LODOUT_SCAN_FONTE", raising=False)
    boa = {"comparacao_fontes": {"itens_preco": 170, "razao_preco": 0.01,
                                 "preco_concorda_pct": 99.0}}
    assert worker._fonte_do_ciclo([boa]) == ("ambas", None)


def test_fonte_do_ciclo_ligada_exige_medicao_boa(monkeypatch):
    monkeypatch.setenv("LODOUT_SCAN_FONTE", "pagina")
    boa = {"comparacao_fontes": {"itens_preco": 170, "razao_preco": 0.01,
                                 "preco_concorda_pct": 99.0,
                                 "mediana_concorda_pct": 95.0,
                                 "volume_concorda_pct": 93.8}}
    sem_mediana = {"comparacao_fontes": {"itens_preco": 170,
                                         "razao_preco": 0.01,
                                         "preco_concorda_pct": 100.0,
                                         "volume_concorda_pct": 93.8}}
    assert worker._fonte_do_ciclo([sem_mediana]) == ("ambas", None)
    ruim = {"comparacao_fontes": {"itens_preco": 170, "razao_preco": 0.01,
                                  "preco_concorda_pct": 80.0}}
    pouca = {"comparacao_fontes": {"itens_preco": 5, "razao_preco": 0.01,
                                   "preco_concorda_pct": 100.0}}
    assert worker._fonte_do_ciclo([boa]) == ("pagina", 0.01)
    # Ciclo no modo página sem comparação nova: vale a última boa.
    assert worker._fonte_do_ciclo([boa, {"comparacao_fontes": None},
                                   pouca]) == ("pagina", 0.01)
    # A medição mais recente reprovou: volta pro modo completo.
    assert worker._fonte_do_ciclo([boa, ruim]) == ("ambas", None)
    assert worker._fonte_do_ciclo([]) == ("ambas", None)
