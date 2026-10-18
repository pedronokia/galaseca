"""Sobe so' o Flask da UI web (sem pywebview/bandeja) pra preview no browser.

Uso: python scripts/dev_web_server.py
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
    server.run("127.0.0.1", port)
