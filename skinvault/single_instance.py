"""Instancia unica -- impede varias copias gravando no mesmo data/.

`minimize_to_tray_on_close` faz o X esconder na bandeja em vez de encerrar.
Quem nao percebe abre de novo pelo atalho, e o processo antigo continua vivo.
Medido na pratica: 29 processos simultaneos, todos com os mesmos JSON de
data/ abertos pra escrita. Nenhum escritor tem lock -- `save_portfolio` e os
caches sobrescrevem o arquivo inteiro -- entao a ultima gravacao apaga o que
as outras 28 fizeram.

O guarda aqui e' um QLocalServer (named pipe no Windows, socket unix no
resto). Quem consegue escutar e' a instancia primaria; quem nao consegue
apenas se conecta -- o que faz a primaria aparecer na frente -- e sai com
codigo 0.

O nome do pipe deriva do DATA_DIR, nao do app: o conflito que importa e'
*gravar no mesmo diretorio*. Duas copias com SKINVAULT_DATA_DIR diferente
nao disputam arquivo nenhum e podem conviver.

## Por que o sinal e' a conexao, e nao uma mensagem

A versao obvia manda um payload ("skinvault:activate") e o servidor so'
ativa a janela se reconhecer o token. **Nao funciona no Windows.** Medido:
o cliente conecta, escreve, da' flush e chama `disconnectFromServer()`; o
servidor recebe `newConnection` com `bytesAvailable() == 0` e em seguida
`disconnected`, sem nunca disparar `readyRead`. O payload some. Nao adianta
`waitForBytesWritten`, `waitForDisconnected`, nem `waitForReadyRead` do lado
do servidor -- as quatro combinacoes foram testadas. So' entrega se o
cliente mantiver o socket vivo, e o cliente aqui e' um processo que existe
para morrer em seguida.

Entao o handshake e' a propria conexao, que chega sempre. Isso significa que
qualquer processo que abrir esse pipe faz a janela subir; e' um incomodo
teorico (o nome e' um sha1 de um caminho local) e nao vale a complexidade de
um ack bidirecional pra evitar.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable, Optional

from skinvault._paths import DATA_DIR

log = logging.getLogger(__name__)

# Conectar num pipe local e' operacao de microssegundos. O timeout existe
# so' pra nao pendurar o startup se o pipe estiver num estado estranho.
_TIMEOUT_MS = 500


def server_name(data_dir: object = None) -> str:
    """Nome do pipe/socket para um DATA_DIR.

    Case-folded e resolvido: no Windows `C:\\SkinVault\\data` e
    `c:/skinvault/data` sao o mesmo diretorio e precisam colidir.
    """
    raw = str(data_dir if data_dir is not None else DATA_DIR)
    try:
        raw = str(Path(raw).resolve())
    except (OSError, ValueError):
        pass  # caminho inacessivel ou invalido: o texto cru ja' serve de chave
    digest = hashlib.sha1(raw.casefold().encode("utf-8")).hexdigest()[:16]
    return "skinvault-" + digest


class SingleInstance:
    """Guarda de instancia unica ligado ao ciclo de vida do QApplication.

    Uso::

        guard = SingleInstance()
        if not guard.try_acquire():
            return 0            # ja' tinha uma janela; ela veio pra frente
        win = MainWindow()
        guard.set_activate_callback(win.activate)
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self._name = name or server_name()
        self._server = None
        self._callback: Optional[Callable[[], None]] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_primary(self) -> bool:
        return self._server is not None

    # ── aquisicao ────────────────────────────────────────────────
    def try_acquire(self) -> bool:
        """True se podemos seguir abrindo a janela.

        False significa exatamente uma coisa: ja' existe uma instancia viva,
        e ela foi avisada pra se mostrar. Falha em criar o servidor NAO
        devolve False -- abrir sem protecao e' ruim, mas um app que se recusa
        a abrir sem ninguem concorrendo e' pior.
        """
        try:
            from PyQt6.QtNetwork import QLocalServer
        except ImportError:  # pragma: no cover - PyQt6 sem QtNetwork
            log.warning("QtNetwork indisponivel; sem guarda de instancia.")
            return True

        if self._notify_existing():
            return False

        server = QLocalServer()
        if not server.listen(self._name):
            # Ou perdemos a corrida pra outra instancia que subiu no mesmo
            # instante, ou sobrou um socket de um processo que morreu. So'
            # da' pra distinguir tentando conectar de novo -- remover o
            # socket as cegas mataria o servidor da instancia viva.
            if self._notify_existing():
                return False
            QLocalServer.removeServer(self._name)
            if not server.listen(self._name):
                log.warning(
                    "Nao consegui abrir o guarda de instancia (%s): %s. "
                    "Seguindo sem protecao.",
                    self._name, server.errorString(),
                )
                return True

        self._server = server
        server.newConnection.connect(self._on_new_connection)
        log.info("Instancia primaria; escutando em %s", self._name)
        return True

    def set_activate_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """Define o que fazer quando outra instancia tentar abrir."""
        self._callback = callback

    def release(self) -> None:
        """Fecha o servidor. Idempotente."""
        server, self._server = self._server, None
        if server is None:
            return
        try:
            server.close()
            from PyQt6.QtNetwork import QLocalServer
            QLocalServer.removeServer(self._name)
        except Exception:  # pragma: no cover - so' acontece em shutdown sujo
            log.debug("Falha ao liberar o guarda de instancia.", exc_info=True)

    # ── lado cliente ─────────────────────────────────────────────
    def _notify_existing(self) -> bool:
        """Tenta avisar uma instancia viva. True se conseguiu falar com ela.

        Conectar ja' e' a mensagem (ver docstring do modulo).
        """
        try:
            from PyQt6.QtNetwork import QLocalSocket
        except ImportError:  # pragma: no cover
            return False
        sock = QLocalSocket()
        sock.connectToServer(self._name)
        if not sock.waitForConnected(_TIMEOUT_MS):
            return False
        sock.disconnectFromServer()
        return True

    # ── lado servidor ────────────────────────────────────────────
    def _on_new_connection(self) -> None:
        server = self._server
        if server is None:
            return
        sock = server.nextPendingConnection()
        if sock is None:
            return
        sock.disconnected.connect(sock.deleteLater)
        sock.close()
        log.info("Outra instancia tentou abrir; trazendo a janela pra frente.")
        self.activate()

    def activate(self) -> None:
        """Dispara o callback de ativacao. Exposto pra teste."""
        if self._callback is None:
            return
        try:
            self._callback()
        except Exception:  # pragma: no cover
            log.exception("Callback de ativacao falhou.")
