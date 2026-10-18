"""Flask app factory -- API + paginas servidas em 127.0.0.1.

So' loopback: sem CORS de proposito (ver requirements.txt) -- nenhuma
pagina aberta no navegador normal do usuario deve conseguir chamar essa
API via XHR.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from skinvault import __version__
from skinvault.webapp.routes.account import bp as account_bp
from skinvault.webapp.routes.history import bp as history_bp
from skinvault.webapp.routes.inventory import bp as inventory_bp
from skinvault.webapp.routes.misc import bp as misc_bp
from skinvault.webapp.routes.settings import bp as settings_bp
from skinvault.webapp.routes.trades import bp as trades_bp
from skinvault.webapp.routes.tradeup import bp as tradeup_bp
from skinvault.webapp.routes.watchlist import bp as watchlist_bp

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
    app.register_blueprint(inventory_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(tradeup_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(watchlist_bp)

    @app.context_processor
    def _inject_versao():
        # Toda pagina estende base.html, que usa {{ versao }} no rodape --
        # injetar aqui poupa toda rota de passar o mesmo valor na mao.
        return {"versao": __version__}

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
