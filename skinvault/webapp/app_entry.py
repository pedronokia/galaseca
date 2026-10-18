"""Ponto de entrada da UI web -- equivalente a `gui.launch()` pro `--web`."""
from __future__ import annotations

import logging
import socket
import threading
import time

from skinvault._paths import ensure_data_dir
from skinvault.settings import load_settings
from skinvault.webapp import server, tray, window
from skinvault.webapp.single_instance_socket import SingleInstanceSocket, port_for

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _wait_for_server(host: str, port: int, timeout_s: float = 5.0) -> bool:
    """Espera o Flask (rodando em outra thread) aceitar conexao.

    Evita a corrida em que o pywebview navega pro endereco antes do
    `app.run()` terminar de fazer bind -- o werkzeug e' rapido, mas nao
    instantaneo.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def launch_web() -> int:
    ensure_data_dir()
    _setup_logging()

    guard = SingleInstanceSocket()
    if not guard.try_acquire():
        log.info("Ja' existe uma instancia web rodando; trazendo pra frente.")
        return 0

    settings = load_settings()
    web_port = port_for(base=55000)

    threading.Thread(
        target=server.run, args=("127.0.0.1", web_port),
        daemon=True, name="skinvault-web-server",
    ).start()

    if not _wait_for_server("127.0.0.1", web_port):
        log.warning("Servidor web nao respondeu a tempo; seguindo mesmo "
                     "assim (pywebview vai tentar de novo ao navegar).")

    tray.start()
    window.create(
        url=f"http://127.0.0.1:{web_port}/",
        overlay_mode=settings.get("overlay_mode", False),
    )
    guard.set_activate_callback(window.restore)

    try:
        import webview
        webview.start()
    finally:
        guard.release()
        tray.stop()
    return 0
