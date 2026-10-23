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
from pathlib import Path

from flask import Flask, jsonify, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from skinvault import __version__, recommendations, scan_store
from skinvault._paths import DATA_DIR, atomic_write_bytes
from skinvault.localization import localize_name
from skinvault.public_site import fmt
from skinvault.public_site.account import bp as account_bp
from skinvault.public_site.trades_routes import bp as trades_bp
from skinvault.public_site.watchlist_routes import bp as watchlist_bp

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_LIMIT_CANDIDATOS = 20
_SECRET_KEY_PATH = DATA_DIR / "public_site_secret.key"


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
        scan = scan_store.load_last_scan()
        return render_template(
            "index.html",
            candidatos=_candidatos(scan),
            scan=scan,
            idade=scan_store.idade_txt(scan["ts"]) if scan else None,
        )

    @app.route("/api/recommendations")
    def api_recommendations():
        scan = scan_store.load_last_scan()
        return jsonify({
            "ultimo_scan": {
                "categoria": scan["category"] if scan else None,
                "ts": scan["ts"] if scan else None,
            },
            "candidatos": _candidatos(scan),
        })

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True})

    return app


def _candidatos(scan: dict | None) -> list[dict]:
    """Candidatos públicos: sem dono (sem login ainda), limitado ao topo."""
    if not scan:
        return []
    candidatos = recommendations.buy_candidates(
        scan["results"], owned_names=set(), limit=_LIMIT_CANDIDATOS)
    for c in candidatos:
        c["price_fmt"] = fmt.brl(c.get("price"))
        c["name_fmt"] = localize_name(c.get("name") or "")
    return candidatos


def run(host: str = "127.0.0.1", port: int = 5050) -> None:
    """Dev server do Flask. Produção troca por gunicorn/waitress (Fase 3)."""
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
