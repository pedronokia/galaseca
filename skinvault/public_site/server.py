"""Flask app factory do site público -- só leitura, sem login.

Serve só o que `worker.py` (processo separado) já escreveu em
`scan_store.json`/`rankings.json`. NUNCA fala com a Steam por requisição
de visitante -- ver AGENTS.md e o plano desta fase (Fase 1: dashboard
público, sem conta, sem dado pessoal). `recommendations.buy_candidates`
roda com `owned_names=set()`: ninguém é "dono" de nada aqui, então é
sempre a visão pública completa.
"""
from __future__ import annotations

import os
import secrets
import urllib.parse
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from skinvault import __version__, recommendations, scan_store, scan_targets
from skinvault._paths import DATA_DIR, atomic_write_bytes
from skinvault.localization import localize_name
from skinvault.public_site import fmt, visits

_MARKET_LISTING_URL = "https://steamcommunity.com/market/listings/730/{name}"
# Mesmo template de icons.py:_CDN_URL_TPL -- não importado de lá porque é
# um nome privado do módulo; o site público nunca baixa/cacheia o ícone
# (isso é coisa do app desktop), só referencia a URL pública do CDN direto
# no <img>, pro navegador do visitante buscar.
_ICON_CDN_URL = (
    "https://community.cloudflare.steamstatic.com/economy/image/"
    "{hash}/96fx96f"
)
from skinvault.public_site.account import bp as account_bp
from skinvault.public_site.history_routes import bp as history_bp
from skinvault.public_site.trades_routes import bp as trades_bp
from skinvault.public_site.watchlist_routes import bp as watchlist_bp

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_LIMIT_CANDIDATOS = 20
_PAGINA_TAMANHO = 20
_INTERVALO_HORAS_DEFAULT = 6.0
_SECRET_KEY_PATH = DATA_DIR / "public_site_secret.key"


def _parse_float_arg(nome: str) -> float | None:
    """Lê um query param numérico opcional. Vazio/inválido -> None --
    nunca `or 0`, que confundiria "não informado" com "zero" (AGENTS.md
    gotcha #15)."""
    valor = request.args.get(nome)
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _parse_int_arg(nome: str, default: int) -> int:
    valor = request.args.get(nome)
    if valor is None or valor == "":
        return default
    try:
        return max(1, int(valor))
    except ValueError:
        return default


def _load_or_create_secret_key() -> bytes:
    """Chave de assinatura da sessão do Flask, gerada uma vez e persistida.

    Sem isto, toda troca de processo (ou um `app.secret_key` hardcoded no
    código) invalidaria sessões -- ou peor, usaria a mesma chave previsível
    em toda instalação. Gerada com `secrets.token_bytes` (criptográfico),
    gravada com `atomic_write_bytes` (mesma disciplina de escrita atômica
    de sempre).
    """
    if _SECRET_KEY_PATH.exists():
        return _SECRET_KEY_PATH.read_bytes()
    key = secrets.token_bytes(32)
    atomic_write_bytes(_SECRET_KEY_PATH, key)
    return key


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(_STATIC_DIR),
        template_folder=str(_TEMPLATES_DIR),
    )
    app.config["JSON_AS_ASCII"] = False
    app.secret_key = _load_or_create_secret_key()
    app.register_blueprint(account_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(history_bp)

    # Em produção, um proxy (Render/Fly.io/nginx) termina o HTTPS e fala
    # com o gunicorn em texto puro -- sem isto, `request.url_root` (usado
    # pelo login Steam OpenID pra montar `realm`/`return_to`) reportaria
    # "http://" mesmo com o visitante em "https://", e a Steam devolveria
    # a um endereço que não bate com o que foi mandado. Inócuo localmente:
    # sem cabeçalho X-Forwarded-*, não muda nada.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # "Secure" exige HTTPS -- ligar sempre quebraria o dev local (http).
    # Produção seta SKINVAULT_PUBLIC_SITE_SECURE_COOKIES=1 (ver
    # skinvault/public_site/README.md).
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SKINVAULT_PUBLIC_SITE_SECURE_COOKIES") == "1")

    @app.context_processor
    def _inject_versao():
        return {"versao": __version__}

    @app.route("/")
    def index():
        visits.registrar()
        scan = scan_store.load_last_scan()
        categoria = request.args.get("categoria") or None
        nota_min = _parse_float_arg("nota_min")
        preco_max = _parse_float_arg("preco_max")
        busca = (request.args.get("q") or "").strip() or None
        ordenar = request.args.get("ordenar") or "nota"
        if ordenar not in ("nota", "preco"):
            ordenar = "nota"
        pagina = _parse_int_arg("pagina", 1)

        todos = _candidatos_filtrados(
            scan, categoria, nota_min, preco_max, busca, ordenar)
        inicio = (pagina - 1) * _PAGINA_TAMANHO
        intervalo_horas = float(os.environ.get(
            "SKINVAULT_WORKER_INTERVAL_HORAS", _INTERVALO_HORAS_DEFAULT))
        return render_template(
            "index.html",
            candidatos=todos[inicio:inicio + _PAGINA_TAMANHO],
            scan=scan,
            idade=scan_store.idade_txt(scan["ts"]) if scan else None,
            proximo_scan=(scan_store.proxima_txt(scan["ts"], intervalo_horas)
                         if scan else None),
            categorias=sorted(scan_targets.SCAN_BY_CATEGORY.keys()),
            categoria_sel=categoria,
            nota_min_sel=nota_min,
            preco_max_sel=preco_max,
            busca_sel=busca,
            ordenar_sel=ordenar,
            pagina=pagina,
            tem_proxima_pagina=len(todos) > inicio + _PAGINA_TAMANHO,
            tem_pagina_anterior=pagina > 1,
            total_candidatos=len(todos),
        )

    @app.route("/api/recommendations")
    def api_recommendations():
        scan = scan_store.load_last_scan()
        return jsonify({
            "ultimo_scan": {
                "categoria": scan["category"] if scan else None,
                "ts": scan["ts"] if scan else None,
            },
            "candidatos": _candidatos_filtrados(scan)[:_LIMIT_CANDIDATOS],
        })

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.route("/privacidade")
    def privacidade():
        return render_template("privacidade.html")

    return app


def _candidatos_filtrados(
        scan: "dict | None", categoria: "str | None" = None,
        nota_min: "float | None" = None,
        preco_max: "float | None" = None,
        busca: "str | None" = None,
        ordenar: str = "nota") -> list[dict]:
    """Candidatos públicos: sem dono (sem login ainda), já filtrados.

    Sem limite aqui de propósito -- a paginação é responsabilidade de quem
    chama (a rota), não desta função. `buy_candidates` já ordena por nota
    (desc); `ordenar="preco"` reordena por preço (asc) depois.
    """
    if not scan:
        return []
    candidatos = recommendations.buy_candidates(
        scan["results"], owned_names=set(), limit=len(scan["results"]) or 1)
    busca_lower = busca.lower() if busca else None
    out = []
    for c in candidatos:
        if categoria and c.get("category") != categoria:
            continue
        if nota_min is not None and (c.get("score") or 0) < nota_min:
            continue
        if preco_max is not None and (c.get("price") or 0) > preco_max:
            continue
        name_fmt = localize_name(c.get("name") or "")
        if busca_lower and busca_lower not in name_fmt.lower():
            continue
        c["price_fmt"] = fmt.brl(c.get("price"))
        c["name_fmt"] = name_fmt
        c["icon_url"] = (
            _ICON_CDN_URL.format(hash=c["icon"]) if c.get("icon") else None)
        c["market_url"] = _MARKET_LISTING_URL.format(
            name=urllib.parse.quote(c.get("name") or "", safe=""))
        c["descontinuada"] = "descontinuada" in (c.get("case_label") or "")
        out.append(c)
    if ordenar == "preco":
        out.sort(key=lambda c: c.get("price") if c.get("price") is not None
                 else float("inf"))
    return out


def run(host: str = "127.0.0.1", port: int = 5050) -> None:
    """Dev server do Flask. Produção troca por gunicorn/waitress (Fase 3)."""
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
