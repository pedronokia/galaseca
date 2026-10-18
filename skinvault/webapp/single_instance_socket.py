"""Guarda de instancia unica via socket TCP loopback (sem Qt).

Mesmo design de `skinvault.single_instance`: a CONEXAO e' a mensagem,
nunca um payload (ver a docstring daquele modulo pro porque -- medido no
Windows que QLocalSocket nunca dispara `readyRead`; o equivalente TCP
tem o mesmo problema de confiabilidade de payload e a mesma solucao).
Reusa `single_instance.server_name()` -- puro, sem Qt -- pra derivar a
mesma chave sha1-de-DATA_DIR, e dai' deriva uma porta TCP fixa em
loopback.

Os dois comportamentos do AGENTS.md #9 preservados:
  (a) falha ao criar o servidor ainda abre sem protecao (nunca recusa a
      abrir so' porque o guarda falhou);
  (b) SO_REUSEADDR so' entra depois de uma segunda tentativa de
      listen() falhar E uma segunda notificacao sem resposta -- nunca no
      primeiro bind, pra nao açambarcar a porta de uma instancia viva.
"""
from __future__ import annotations

import hashlib
import logging
import socket
import threading
from typing import Callable, Optional

from skinvault.single_instance import server_name

log = logging.getLogger(__name__)

_TIMEOUT_S = 0.5
_HOST = "127.0.0.1"


def port_for(name: Optional[str] = None, base: int = 51000, span: int = 4000) -> int:
    """Porta TCP deterministica derivada do nome do guarda (sha1 do DATA_DIR).

    `base`/`span` deslocam a faixa: o guarda de instancia e o servidor
    web usam faixas diferentes (bases diferentes) pra nunca colidir
    entre si, mesmo derivando do mesmo DATA_DIR.
    """
    key = name or server_name()
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return base + (int(digest[:8], 16) % span)


class SingleInstanceSocket:
    """Guarda de instancia unica equivalente a `single_instance.SingleInstance`.

    Uso::

        guard = SingleInstanceSocket()
        if not guard.try_acquire():
            return 0            # ja' tinha uma janela; ela veio pra frente
        ...
        guard.set_activate_callback(window.restore)
    """

    def __init__(self, name: Optional[str] = None, port: Optional[int] = None) -> None:
        self._name = name or server_name()
        self._port = port if port is not None else port_for(self._name)
        self._server: Optional[socket.socket] = None
        self._callback: Optional[Callable[[], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_primary(self) -> bool:
        return self._server is not None

    # ── aquisicao ────────────────────────────────────────────────
    def try_acquire(self) -> bool:
        """True se podemos seguir abrindo a janela.

        False significa exatamente uma coisa: ja' existe uma instancia
        viva, e ela foi avisada pra se mostrar. Falha em criar o
        servidor NAO devolve False -- abrir sem protecao e' ruim, mas um
        app que se recusa a abrir sem ninguem concorrendo e' pior.
        """
        if self._notify_existing():
            return False
        if self._listen():
            return True
        # Ou perdemos a corrida pra outra instancia que subiu no mesmo
        # instante, ou sobrou uma porta em TIME_WAIT de um processo que
        # morreu. So' da' pra distinguir tentando notificar de novo --
        # forcar SO_REUSEADDR as cegas poderia roubar a porta de uma
        # instancia viva.
        if self._notify_existing():
            return False
        if self._listen(force=True):
            return True
        log.warning(
            "Nao consegui abrir o guarda de instancia (porta %s). "
            "Seguindo sem protecao.", self._port,
        )
        return True

    def _listen(self, force: bool = False) -> bool:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if force:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((_HOST, self._port))
            srv.listen(5)
        except OSError:
            srv.close()
            return False
        srv.settimeout(0.5)
        self._server = srv
        self._thread = threading.Thread(
            target=self._serve_forever, daemon=True,
            name="skinvault-single-instance",
        )
        self._thread.start()
        log.info("Instancia primaria; escutando em %s:%s", _HOST, self._port)
        return True

    def _serve_forever(self) -> None:
        srv = self._server
        if srv is None:
            return
        while not self._stop.is_set():
            try:
                conn, _addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.close()
            except OSError:
                pass
            log.info("Outra instancia tentou abrir; trazendo a janela pra frente.")
            self.activate()

    def set_activate_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Define o que fazer quando outra instancia tentar abrir."""
        self._callback = callback

    def release(self) -> None:
        """Fecha o servidor. Idempotente."""
        self._stop.set()
        srv, self._server = self._server, None
        if srv is not None:
            try:
                srv.close()
            except OSError:
                pass

    # ── lado cliente ─────────────────────────────────────────────
    def _notify_existing(self) -> bool:
        """Tenta avisar uma instancia viva. True se conseguiu falar com ela.

        Conectar ja' e' a mensagem (ver docstring do modulo).
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_TIMEOUT_S)
        try:
            sock.connect((_HOST, self._port))
        except OSError:
            return False
        finally:
            sock.close()
        return True

    # ── lado servidor ────────────────────────────────────────────
    def activate(self) -> None:
        """Dispara o callback de ativacao. Exposto pra teste."""
        if self._callback is None:
            return
        try:
            self._callback()
        except Exception:
            log.exception("Callback de ativacao falhou.")
