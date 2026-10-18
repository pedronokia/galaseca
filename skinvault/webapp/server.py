"""Flask app factory -- API + paginas servidas em 127.0.0.1.

So' loopback: sem CORS de proposito (ver requirements.txt) -- nenhuma
pagina aberta no navegador normal do usuario deve conseguir chamar essa
API via XHR.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from skinvault.webapp.routes.account import bp as account_bp
from skinvault.webapp.routes.misc import bp as misc_bp

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(_STATIC_DIR),
        template_folder=str(_TEMPLATES_DIR),
    )
    app.config["JSON_AS_ASCII"] = False
    app.register_blueprint(misc_bp)
    app.register_blueprint(account_bp)
    return app


def run(host: str, port: int) -> None:
    """Roda o servidor Flask (bloqueante) -- chamado numa thread daemon.

    `debug=False`/`use_reloader=False`: isto e' o build empacotado, nao
    um dev server. `threaded=True` pra uma requisicao de longa duracao
    (a conexao SSE de /api/events) nao travar as outras.
    """
    app = create_app()
    app.run(host=host, port=port, debug=False, use_reloader=False,
             threaded=True)
