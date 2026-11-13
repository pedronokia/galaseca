"""Anúncios oficiais do CS2 (feed "steam_community_announcements" da
Steam Web API pública, sem chave).

Só o worker chama `atualizar_noticias()` -- uma requisição por ciclo, no
máximo, e nunca antes de `_INTERVALO_MIN_S` desde a última busca bem-
sucedida (reiniciar o worker não gera requisição extra). O site só LÊ o
cache com `carregar_noticias()`.

As notícias são contexto pro visitante, não entram na nota: nenhum
backtest mediu se um anúncio antecipa preço (ver AGENTS.md sobre
calibrar fator novo com `score_backtest.split_itens`).
"""
from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

from lodout import _paths, steam_api
from lodout._paths import atomic_write_text, load_json_record

_APP_CS2 = 730
_NEWS_URL = (
    "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    f"?appid={_APP_CS2}&count=10&maxlength=600&format=json"
    "&feeds=steam_community_announcements")
# Família própria no disjuntor de rate limit de steam_api: um 429 aqui
# não trava o scan de preços, e vice-versa.
_FAMILIA = "news"
_INTERVALO_MIN_S = 5 * 3600
_MAX_NOTICIAS = 10
_RESUMO_MAX = 280
# Só links da própria Steam viram <a href> -- o campo vem de fora.
_URL_OK = re.compile(
    r"^https://(store\.steampowered\.com|steamcommunity\.com|"
    r"steamstore-a\.akamaihd\.net|counter-strike\.net|www\.counter-strike\.net)/")


def _caminho() -> Path:
    return Path(_paths.DATA_DIR) / "steam_news.json"


def _texto_limpo(bruto: str) -> str:
    """BBCode/HTML/placeholders da Steam -> texto simples, encurtado."""
    t = re.sub(r"\{STEAM_CLAN_IMAGE\}\S*", " ", bruto or "")
    t = re.sub(r"\[/?[a-zA-Z0-9*]+(=[^\]]*)?\]", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r" ([.,;:!?])", r"\1", t)
    if len(t) > _RESUMO_MAX:
        t = t[:_RESUMO_MAX].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return t


def _parse(dados: dict) -> "list[dict]":
    itens = ((dados or {}).get("appnews") or {}).get("newsitems") or []
    out = []
    for n in itens:
        try:
            titulo = _texto_limpo(str(n["title"]))
            ts = float(n["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if not titulo:
            continue
        url = str(n.get("url") or "")
        out.append({
            "gid": str(n.get("gid") or ""),
            "titulo": titulo,
            "resumo": _texto_limpo(str(n.get("contents") or "")),
            "url": url if _URL_OK.match(url) else None,
            "ts": ts,
        })
    out.sort(key=lambda n: -n["ts"])
    return out[:_MAX_NOTICIAS]


def carregar_noticias() -> "list[dict]":
    dados = load_json_record(_caminho(), {})
    itens = dados.get("itens") if isinstance(dados, dict) else None
    return itens if isinstance(itens, list) else []


def atualizar_noticias(now: "float | None" = None) -> str:
    """Busca e grava os anúncios. Devolve o que aconteceu: "recente"
    (cache novo o bastante, sem requisição), "cooldown" (disjuntor
    aberto, sem requisição), "rate_limited", "erro" ou "ok"."""
    agora = time.time() if now is None else now
    dados = load_json_record(_caminho(), {})
    buscado = dados.get("buscado_em") if isinstance(dados, dict) else None
    if isinstance(buscado, (int, float)) and agora - buscado < _INTERVALO_MIN_S:
        return "recente"
    if steam_api.em_cooldown(_FAMILIA):
        return "cooldown"
    code, body = steam_api._http_get(_NEWS_URL)
    if code == 429:
        steam_api._registrar_rate_limit(_FAMILIA)
        return "rate_limited"
    if code != 200 or not body:
        return "erro"
    try:
        itens = _parse(json.loads(body))
    except ValueError:
        return "erro"
    if not itens:
        # Resposta vazia pode ser throttle silencioso (AGENTS.md): não
        # troca a lista guardada por nada.
        return "erro"
    steam_api._limpar_rate_limit(_FAMILIA)
    atomic_write_text(_caminho(), json.dumps(
        {"buscado_em": agora, "itens": itens}, ensure_ascii=False))
    return "ok"
