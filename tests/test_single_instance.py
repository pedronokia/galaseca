"""Guarda de instancia unica.

Os testes de handshake usam QLocalServer/QLocalSocket de verdade -- named
pipe no Windows, socket unix no resto. Nao ha' rede envolvida e o pipe e'
nomeado por teste, entao nao colide com o app do usuario nem entre rodadas.
"""
from __future__ import annotations

import uuid

import pytest

from skinvault import single_instance as si


@pytest.fixture(autouse=True)
def app():
    """Mesmo ciclo de vida dos outros arquivos de UI (ver test_inventory_grid).

    QLocalServer precisa de um QCoreApplication vivo pra entregar
    newConnection; sem ele o handshake nunca completa.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()


def _unique_name() -> str:
    return "skinvault-test-" + uuid.uuid4().hex[:12]


def _pump(app, guard, tries=50):
    """Roda o event loop ate' o guarda receber a conexao pendente."""
    for _ in range(tries):
        app.processEvents()


# ── nome do pipe ───────────────────────────────────────────────────

def test_server_name_e_deterministico():
    assert si.server_name("C:/qualquer/data") == si.server_name("C:/qualquer/data")


def test_server_name_ignora_caixa():
    """C:\\SkinVault\\data e c:/skinvault/data sao o MESMO diretorio.

    Se gerassem pipes diferentes, duas copias abririam lado a lado e
    voltaria o problema que o modulo existe pra resolver.
    """
    assert si.server_name("C:/SkinVault/data") == si.server_name("c:/skinvault/DATA")


def test_server_name_separa_data_dirs_diferentes():
    """SKINVAULT_DATA_DIR distinto = nenhum arquivo em disputa = pode conviver."""
    assert si.server_name("C:/um/data") != si.server_name("C:/outro/data")


def test_server_name_default_usa_data_dir():
    from skinvault._paths import DATA_DIR
    assert si.server_name() == si.server_name(DATA_DIR)


def test_server_name_aceita_caminho_irresolvivel():
    """Caminho que nao resolve nao pode explodir o startup."""
    assert si.server_name("\0invalido").startswith("skinvault-")


# ── aquisicao ──────────────────────────────────────────────────────

def test_primeira_instancia_adquire():
    guard = si.SingleInstance(_unique_name())
    try:
        assert guard.try_acquire() is True
        assert guard.is_primary is True
    finally:
        guard.release()


def test_segunda_instancia_nao_adquire():
    name = _unique_name()
    primeira = si.SingleInstance(name)
    segunda = si.SingleInstance(name)
    try:
        assert primeira.try_acquire() is True
        assert segunda.try_acquire() is False
        assert segunda.is_primary is False
    finally:
        primeira.release()
        segunda.release()


def test_apos_release_o_nome_fica_livre():
    """Instancia que encerrou nao pode bloquear a proxima abertura."""
    name = _unique_name()
    primeira = si.SingleInstance(name)
    assert primeira.try_acquire() is True
    primeira.release()

    segunda = si.SingleInstance(name)
    try:
        assert segunda.try_acquire() is True
    finally:
        segunda.release()


def test_release_e_idempotente():
    guard = si.SingleInstance(_unique_name())
    guard.try_acquire()
    guard.release()
    guard.release()  # nao explode
    assert guard.is_primary is False


def test_release_sem_acquire_nao_explode():
    si.SingleInstance(_unique_name()).release()


# ── handshake ──────────────────────────────────────────────────────

def test_ping_da_segunda_instancia_ativa_a_primeira(app):
    """O ponto do modulo: a janela que ja' existe vem pra frente."""
    name = _unique_name()
    primeira = si.SingleInstance(name)
    ativou = []
    try:
        assert primeira.try_acquire() is True
        primeira.set_activate_callback(lambda: ativou.append(True))

        segunda = si.SingleInstance(name)
        assert segunda.try_acquire() is False
        _pump(app, primeira)
        assert ativou == [True]
    finally:
        primeira.release()


def test_conexao_crua_sem_payload_ativa(app):
    """A conexao E' o sinal -- no Windows o payload nao sobrevive ao
    disconnect do cliente (ver docstring de single_instance)."""
    from PyQt6.QtNetwork import QLocalSocket
    name = _unique_name()
    guard = si.SingleInstance(name)
    ativou = []
    try:
        assert guard.try_acquire() is True
        guard.set_activate_callback(lambda: ativou.append(True))

        sock = QLocalSocket()
        sock.connectToServer(name)
        assert sock.waitForConnected(1000)
        sock.disconnectFromServer()
        _pump(app, guard)
        assert ativou == [True]
    finally:
        guard.release()


def test_ativa_uma_vez_por_conexao(app):
    """Tres tentativas de abrir = tres subidas de janela, nem mais nem menos."""
    name = _unique_name()
    primeira = si.SingleInstance(name)
    ativou = []
    try:
        assert primeira.try_acquire() is True
        primeira.set_activate_callback(lambda: ativou.append(True))
        for _ in range(3):
            assert si.SingleInstance(name).try_acquire() is False
            _pump(app, primeira)
        assert ativou == [True, True, True]
    finally:
        primeira.release()


def test_activate_sem_callback_e_noop():
    si.SingleInstance(_unique_name()).activate()


def test_activate_engole_excecao_do_callback():
    """Callback quebrado nao pode derrubar a instancia que estava rodando."""
    guard = si.SingleInstance(_unique_name())

    def _boom():
        raise RuntimeError("janela ja' foi destruida")

    guard.set_activate_callback(_boom)
    guard.activate()  # nao propaga


def test_callback_pode_ser_removido():
    guard = si.SingleInstance(_unique_name())
    chamou = []
    guard.set_activate_callback(lambda: chamou.append(True))
    guard.set_activate_callback(None)
    guard.activate()
    assert chamou == []


def test_notify_existing_sem_ninguem_escutando():
    guard = si.SingleInstance(_unique_name())
    assert guard._notify_existing() is False


# ── degradacao ─────────────────────────────────────────────────────

def test_listen_impossivel_abre_sem_protecao(monkeypatch):
    """Se o pipe nao sobe de jeito nenhum, o app abre mesmo assim.

    Um app que se recusa a abrir sem ninguem concorrendo e' pior que um app
    sem guarda.
    """
    class FakeServer:
        def listen(self, _name):
            return False
        def errorString(self):
            return "sem permissao"
        @staticmethod
        def removeServer(_name):
            return True

    import PyQt6.QtNetwork as qtn
    monkeypatch.setattr(qtn, "QLocalServer", FakeServer)

    guard = si.SingleInstance(_unique_name())
    assert guard.try_acquire() is True
    assert guard.is_primary is False  # seguiu, mas sem guarda


def test_qtnetwork_ausente_abre_sem_protecao(monkeypatch):
    """PyQt6 sem QtNetwork nao pode impedir o app de abrir."""
    import builtins
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "PyQt6.QtNetwork":
            raise ImportError("sem QtNetwork")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    guard = si.SingleInstance(_unique_name())
    assert guard.try_acquire() is True
    assert guard.is_primary is False
