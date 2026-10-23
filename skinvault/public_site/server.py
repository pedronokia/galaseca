"""Flask app factory do site público -- só leitura, sem login.

Serve só o que `worker.py` (processo separado) já escreveu em
`scan_store.json`/`rankings.json`. NUNCA fala com a Steam por requisição
de visitante -- ver AGENTS.md e o plano desta fase (Fase 1: dashboard
público, sem conta, sem dado pessoal). `recommendations.buy_candidates`
roda com `owned_names=set()`: ninguém é "dono" de nada aqui, então é
sempre a visão pública completa.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template

from skinvault import __version__, recommendations, scan_store
from skinvault.localization import localize_name

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_LIMIT_CANDIDATOS = 20


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(_STATIC_DIR),
        template_folder=str(_TEMPLATES_DIR),
    )
    app.config["JSON_AS_ASCII"] = False

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


def _brl(v: float | None) -> str:
    """Formata BRL pt-BR. Cópia mínima de `ui/theme.py:brl` sem o import de
    PyQt6 que esse módulo carrega -- o servidor público não precisa dele."""
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _candidatos(scan: dict | None) -> list[dict]:
    """Candidatos públicos: sem dono (sem login ainda), limitado ao topo."""
    if not scan:
        return []
    candidatos = recommendations.buy_candidates(
        scan["results"], owned_names=set(), limit=_LIMIT_CANDIDATOS)
    for c in candidatos:
        c["price_fmt"] = _brl(c.get("price"))
        c["name_fmt"] = localize_name(c.get("name") or "")
    return candidatos


def run(host: str = "127.0.0.1", port: int = 5050) -> None:
    """Dev server do Flask. Produção troca por gunicorn/waitress (Fase 3)."""
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
