"""Testes dos anúncios oficiais do CS2 (steam_news.py)."""
from __future__ import annotations

import json

import pytest

from galaseca import steam_api, steam_news


@pytest.fixture(autouse=True)
def _isola(monkeypatch, tmp_path):
    monkeypatch.setattr(steam_news, "_caminho", lambda: tmp_path / "n.json")
    monkeypatch.setattr(steam_api, "_rate_limit_state", {})


def _resposta(*itens):
    return json.dumps({"appnews": {"newsitems": list(itens)}})


_NOTICIA = {
    "gid": "1", "title": "Release Notes for 11/12/2026",
    "url": "https://steamstore-a.akamaihd.net/news/externalpost/x/1",
    "date": 1794500000,
    "contents": "[p]{STEAM_CLAN_IMAGE}/a/b.png [b]MAPS[/b] Fixed &amp; "
                "improved <i>Inferno</i>.[/p]",
}


def test_atualizar_grava_texto_limpo(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        steam_api, "_http_get",
        lambda url: chamadas.append(url) or (200, _resposta(_NOTICIA)))
    assert steam_news.atualizar_noticias(now=1794600000) == "ok"
    assert "appid=730" in chamadas[0]
    [n] = steam_news.carregar_noticias()
    assert n["titulo"] == "Release Notes for 11/12/2026"
    assert n["resumo"] == "MAPS Fixed & improved Inferno."
    assert n["url"].startswith("https://steamstore-a.akamaihd.net/")


def test_url_fora_da_steam_nao_vira_link(monkeypatch):
    ruim = dict(_NOTICIA, url="javascript:alert(1)")
    monkeypatch.setattr(steam_api, "_http_get",
                        lambda url: (200, _resposta(ruim)))
    steam_news.atualizar_noticias(now=1)
    assert steam_news.carregar_noticias()[0]["url"] is None


def test_cache_recente_nao_faz_requisicao(monkeypatch):
    monkeypatch.setattr(steam_api, "_http_get",
                        lambda url: (200, _resposta(_NOTICIA)))
    steam_news.atualizar_noticias(now=1000)

    def _nao_chama(url):
        raise AssertionError("não devia buscar de novo")

    monkeypatch.setattr(steam_api, "_http_get", _nao_chama)
    assert steam_news.atualizar_noticias(now=1000 + 3600) == "recente"


def test_429_abre_disjuntor_e_proxima_nao_requisita(monkeypatch):
    monkeypatch.setattr(steam_api, "_http_get", lambda url: (429, ""))
    assert steam_news.atualizar_noticias(now=1) == "rate_limited"

    def _nao_chama(url):
        raise AssertionError("disjuntor aberto, não devia buscar")

    monkeypatch.setattr(steam_api, "_http_get", _nao_chama)
    assert steam_news.atualizar_noticias(now=2) == "cooldown"


def test_resposta_vazia_mantem_lista_guardada(monkeypatch):
    monkeypatch.setattr(steam_api, "_http_get",
                        lambda url: (200, _resposta(_NOTICIA)))
    steam_news.atualizar_noticias(now=1)
    monkeypatch.setattr(steam_api, "_http_get",
                        lambda url: (200, _resposta()))
    assert steam_news.atualizar_noticias(now=1 + 6 * 3600) == "erro"
    assert len(steam_news.carregar_noticias()) == 1


def test_erro_de_rede_nao_grava(monkeypatch):
    monkeypatch.setattr(steam_api, "_http_get", lambda url: (0, None))
    assert steam_news.atualizar_noticias(now=1) == "erro"
    assert steam_news.carregar_noticias() == []


def test_resumo_longo_e_cortado_em_palavra(monkeypatch):
    longa = dict(_NOTICIA, contents="palavra " * 100)
    monkeypatch.setattr(steam_api, "_http_get",
                        lambda url: (200, _resposta(longa)))
    steam_news.atualizar_noticias(now=1)
    resumo = steam_news.carregar_noticias()[0]["resumo"]
    assert resumo.endswith("…")
    assert len(resumo) <= steam_news._RESUMO_MAX + 1
    assert "palavr…" not in resumo
