"""Flask app factory -- API + paginas servidas em 127.0.0.1.

So' loopback: sem CORS de proposito (ver requirements.txt) -- nenhuma
pagina aberta no navegador normal do usuario deve conseguir chamar essa
API via XHR.
"""
from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from skinvault import __version__
from skinvault.webapp.routes.account import bp as account_bp
from skinvault.webapp.routes.cleanup import bp as cleanup_bp
from skinvault.webapp.routes.history import bp as history_bp
from skinvault.webapp.routes.inventory import bp as inventory_bp
from skinvault.webapp.routes.market import bp as market_bp
from skinvault.webapp.routes.misc import bp as misc_bp
from skinvault.webapp.routes.scanner import bp as scanner_bp
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
    app.register_blueprint(cleanup_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(scanner_bp)

    @app.context_processor
    def _inject_versao():
        # Toda pagina estende base.html, que usa {{ versao }} no rodape --
        # injetar aqui poupa toda rota de passar o mesmo valor na mao.
        return {"versao": __version__}

    # Sem isto, uma URL digitada errada ou um erro real mostra a pagina
    # branca padrao do Flask/Werkzeug -- quebra o tema escuro igual o
    # confirm() nativo quebrava (ver commit do skinvaultConfirm). /api/
    # continua devolvendo JSON, que e' o que o JS dos fetch() espera.
    @app.errorhandler(HTTPException)
    def _handle_http_error(err: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify(error=err.name), err.code
        # err.name/description vem em ingles do Werkzeug -- nao usar
        # como texto visivel (gotcha #14 do AGENTS.md).
        is_404 = err.code == 404
        return render_template(
            "error.html",
            title="Página não encontrada" if is_404 else f"Erro {err.code}",
            message="O endereço não existe ou não está mais disponível."
                    if is_404 else
                    "Algo não saiu como esperado processando este pedido.",
            hint="Confira o link ou volte para o início.",
        ), err.code

    @app.errorhandler(Exception)
    def _handle_unexpected_error(err: Exception):
        app.logger.exception("Erro não tratado em %s", request.path)
        if request.path.startswith("/api/"):
            return jsonify(error="Erro interno."), 500
        return render_template(
            "error.html",
            title="Erro inesperado",
            message="Algo deu errado processando esta página.",
            hint="Tente voltar para o início.",
        ), 500

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
