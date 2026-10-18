"""Sobe so' o Flask da UI web (sem pywebview/bandeja) pra preview no browser.

Uso: python scripts/dev_web_server.py

Diferente de `server.run()` (producao): aqui o app e' montado na mao pra
ligar `TEMPLATES_AUTO_RELOAD` -- sem isso, Flask com `debug=False`
cacheia o Jinja compilado e um `<link>`/template editado so' aparece
depois de matar e subir o processo de novo (mordeu mais de uma vez
editando CSS/HTML com o servidor ja' de pe').
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skinvault._paths import ensure_data_dir
from skinvault.webapp import server

if __name__ == "__main__":
    ensure_data_dir()
    port = int(os.environ.get("PORT", 5055))
    app = server.create_app()
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False,
             threaded=True)
