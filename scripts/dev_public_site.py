"""Sobe o site público (Fase 1) sozinho, pra preview no browser.

Uso: python scripts/dev_public_site.py

Mesma razão do `dev_web_server.py`: liga `TEMPLATES_AUTO_RELOAD` pra editar
template/CSS sem matar e subir o processo de novo.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skinvault._paths import ensure_data_dir
from skinvault.public_site import server

if __name__ == "__main__":
    ensure_data_dir()
    port = int(os.environ.get("PORT", 5061))
    app = server.create_app()
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False,
            threaded=True)
