"""Rotas gerais (misc.py) -- so' o que ganhou cobertura nova: servir
icone de item (/api/icon/<hash>). As demais (/, /api/ping, /api/events)
ja' sao exercitadas indiretamente pelos testes de cada tela.
"""
from __future__ import annotations

import pytest

from skinvault import icons as icons_mod
from skinvault.webapp.server import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_icon_404_quando_sem_cache_e_rede_falha(client, monkeypatch):
    monkeypatch.setattr(icons_mod, "fetch", lambda h, timeout=10.0: None)
    resp = client.get("/api/icon/algum-hash")
    assert resp.status_code == 404


def test_icon_serve_arquivo_do_cache(client, monkeypatch, tmp_path):
    arquivo = tmp_path / "icone.png"
    arquivo.write_bytes(b"\x89PNG\r\n fake-bytes")
    monkeypatch.setattr(icons_mod, "fetch", lambda h, timeout=10.0: arquivo)
    resp = client.get("/api/icon/algum-hash")
    assert resp.status_code == 200
    assert resp.mimetype == "image/png"
    assert resp.data == arquivo.read_bytes()


def test_icon_aceita_hash_com_barra(client, monkeypatch, tmp_path):
    # icons.py: o hash as vezes vem com '/' -- a rota precisa aceitar
    # na URL (<path:...>), nao so' o nome de arquivo local sanitizado.
    arquivo = tmp_path / "icone.png"
    arquivo.write_bytes(b"fake")
    recebido = {}

    def fake_fetch(h, timeout=10.0):
        recebido["hash"] = h
        return arquivo

    monkeypatch.setattr(icons_mod, "fetch", fake_fetch)
    resp = client.get("/api/icon/abc/def-123")
    assert resp.status_code == 200
    assert recebido["hash"] == "abc/def-123"


def test_classes_com_hidden_tem_guarda_display_none():
    """Gotcha #16 do AGENTS.md: `.classe { display: ... }` tem
    especificidade maior que o `[hidden]` da UA stylesheet sozinho, então
    um elemento que nasce `hidden` no HTML aparece visível mesmo assim se
    a classe define `display`. Já mordeu `.status-line` nesta rodada
    (inventory.html: #import-status nasce hidden e sem texto, mas
    renderizava como linha flex vazia) -- mesma família de bug que já
    morava no site público (.add-item-form/.stat-row/.barra-comparar).
    Porta a mesma varredura de `test_public_site.py` pra este módulo,
    que tem CSS espalhado em vários arquivos (`static/css/*.css`), não
    um `style.css` só."""
    import re
    from pathlib import Path

    raiz = Path(__file__).parent.parent / "skinvault" / "webapp"
    css = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted((raiz / "static" / "css").glob("*.css")))

    classes_com_hidden = set()
    for template in (raiz / "templates").rglob("*.html"):
        html = template.read_text(encoding="utf-8")
        for tag in re.findall(r"<[a-z][^>]*>", html):
            if re.search(r"\bhidden\b", tag):
                m = re.search(r'class="([^"]+)"', tag)
                if m:
                    classes_com_hidden.update(m.group(1).split())

    css_sem_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)

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
        "-- o elemento aparece mesmo hidden (AGENTS.md gotcha #16)")
