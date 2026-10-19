"""Configuracao global do pytest.

Qt em modo offscreen. Sem isto, todo QApplication/QWidget criado na suite
abre janela DE VERDADE: rouba foco, pisca na tela e derruba jogo rodando em
fullscreen exclusivo (medido na pratica -- a suite leva ~5min e o CS2 era
minimizado durante a rodada inteira).

Precisa estar definido ANTES do primeiro import de PyQt6, porque o plugin de
plataforma e' escolhido no import. O pytest carrega conftest.py antes dos
modulos de teste, entao este e' o ponto certo.

Usa setdefault: quem quiser depurar vendo as janelas roda com
QT_QPA_PLATFORM=windows pytest ...
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import urllib.error
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# data/ isolado pra sessao inteira. Mesma regra do QT_QPA_PLATFORM: tem que
# valer ANTES do primeiro import de skinvault, porque varios modulos fixam
# `X_PATH = DATA_DIR / "x.json"` no import.
#
# 2026-10-17: sem isto a suite lia e GRAVAVA o data/ real do projeto. O
# PriceWorker da Conta (AccountScreen.refresh) carregava o portfolio.json de
# verdade, dezenas de itens, e consultava a Steam item a item numa thread
# daemon; a thread sobrevivia ao teste e emitia sinal pra widget ja'
# destruido -> "Windows fatal exception: access violation" no meio do
# test_ui_smoke.py, cada vez num teste diferente. A pasta chama "data" pra
# manter o contrato de test_paths_dev_branch (DATA_DIR.name == "data").
_RAIZ_TESTE = Path(tempfile.mkdtemp(prefix="skinvault-tests-"))
DATA_DIR_TESTE = _RAIZ_TESTE / "data"
DATA_DIR_TESTE.mkdir()
os.environ["SKINVAULT_DATA_DIR"] = str(DATA_DIR_TESTE)
atexit.register(shutil.rmtree, _RAIZ_TESTE, True)


@pytest.fixture(autouse=True)
def _data_dir_isolado():
    """Recoloca o _paths no data/ de teste se algum teste o tirar de la'.

    test_paths.py recarrega o modulo sem SKINVAULT_DATA_DIR e o deixa
    apontando pro data/ real ao terminar. Sem este reparo, todo modulo
    importado DEPOIS disso voltaria a ler os dados do usuario.
    """
    yield
    import importlib

    import skinvault._paths as paths
    if paths.DATA_DIR != DATA_DIR_TESTE:
        os.environ["SKINVAULT_DATA_DIR"] = str(DATA_DIR_TESTE)
        importlib.reload(paths)


@pytest.fixture(autouse=True)
def _destroi_janelas_do_teste():
    """Destroi as janelas de um teste ANTES do proximo comecar.

    2026-10-17: a suite completa nunca terminava -- access violation
    intermitente, cada rodada num teste diferente. Telas inteiras de testes
    anteriores (com timers, animacoes e threads) seguiam vivas e
    disparavam no meio dos testes seguintes. Um gc.collect() por teste foi
    tentado e NAO era necessario (so' dobrava o tempo da suite): quem
    resolve e' destruir as janelas de forma deterministica, aqui.
    """
    yield
    import sys

    comp = sys.modules.get("skinvault.ui.components")
    if comp is not None:
        comp.Toast._stack.clear()  # lista de classe: segurava toast morto
    qtw = sys.modules.get("PyQt6.QtWidgets")
    app = qtw.QApplication.instance() if qtw is not None else None
    if app is None:
        return
    from PyQt6 import sip

    # deleteLater() + processEvents() NAO destroi nada: o Qt so' entrega
    # DeferredDelete ao voltar pro loop de eventos. Os _qapp das suites
    # faziam exatamente isso, entao toda janela de toda suite ficava viva
    # (com timers e animacoes rodando) ate' o fim do processo -- foi o
    # acumulo de tres ScreenRouter que derrubou o test_toast_* (medido).
    #
    # So' as janelas SEM DONO, e na hora (sip.delete). Popup tambem e'
    # "top-level" (a lista do QCompleter, por exemplo), mas pertence a
    # outro objeto: destrui-la aqui fazia o dono destrui-la de novo depois
    # -- access violation no test_tradeup_screen. Ela morre com o dono.
    # A lista e' consultada de novo a cada exclusao: destruir uma janela
    # destroi junto os popups dela, e um popup criado pelo proprio Qt nao
    # avisa o PyQt (sip.isdeleted segue False) -- reusar a lista antiga
    # excluia memoria ja' liberada.
    from PyQt6.QtCore import Qt

    _NAO_E_NOSSA = (Qt.WindowType.Popup, Qt.WindowType.ToolTip)
    for _ in range(500):
        alvo = next(
            (w for w in app.topLevelWidgets()
             if w.parentWidget() is None
             and w.windowType() not in _NAO_E_NOSSA
             and not sip.isdeleted(w)),
            None)
        if alvo is None:
            break
        try:
            sip.delete(alvo)
        except RuntimeError:
            break
    app.processEvents()


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    """Nenhum teste fala com a internet de verdade.

    Steam, GitHub e mercados externos sao rate-limited, e chamada real na
    suite e' lenta, instavel e queima o limite do usuario. Teste que simula
    a rede patcha `urlopen`/`_http_get` por conta propria -- o patch dele e'
    aplicado depois deste e vence.
    """
    def _bloqueado(*_a, **_kw):
        raise urllib.error.URLError("rede bloqueada na suite de testes")

    monkeypatch.setattr("urllib.request.urlopen", _bloqueado)

    # icons.py / icon_backfill.py baixam imagem via httpx, nao urllib. Os
    # testes de Inventario disparavam dezenas desses downloads reais em
    # thread -- uma delas emitindo sinal enquanto a janela era destruida
    # derrubou a suite inteira (2026-10-17).
    try:
        import httpx
    except ImportError:
        return

    class _ClienteBloqueado:
        """httpx.Client que falha na hora. Bloquear so' o transporte nao
        bastava: criar o Client real monta contexto TLS (dezenas de ms), e
        com um Client por icone a thread vivia segundos -- emitindo sinal
        depois que a tela do teste ja' tinha morrido."""

        def __init__(self, *_a, **_kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def close(self):
            pass

        def request(self, method, url, *_a, **_kw):
            raise httpx.ConnectError("rede bloqueada na suite de testes")

        def get(self, url, *_a, **_kw):
            return self.request("GET", url)

    monkeypatch.setattr(httpx, "Client", _ClienteBloqueado)


@pytest.fixture(autouse=True)
def _sem_espera_de_rate_limit(monkeypatch):
    """Zera steam_api.RATE_LIMIT_DELAY_S pra suite inteira.

    2026-08-07: o delay real subiu de 1.0-2.0s pra 4.0s (pesquisa sobre
    o limite real da Steam -- ver AGENTS.md). Testes que exercitam
    _scan_item/workers de validacao sem mockar time.sleep passaram a
    dormir de verdade, +20-35s na suite inteira. Autouse em vez de
    mockar cada teste: qualquer `time.sleep(steam_api.RATE_LIMIT_DELAY_S)`
    novo ja' nasce rapido na suite sem precisar lembrar de mockar.
    Producao nunca importa conftest.py, entao o app real mantem 4.0s.
    """
    from skinvault import steam_api
    monkeypatch.setattr(steam_api, "RATE_LIMIT_DELAY_S", 0.0)


@pytest.fixture(autouse=True)
def _sem_disjuntor_de_rate_limit():
    """Zera steam_api._rate_limit_state antes e depois de cada teste.

    2026-10-19: o disjuntor (em_cooldown/_registrar_rate_limit) e' um
    dict de MODULO, persistente entre testes na mesma sessao. Um teste
    que simula 429 registrava cooldown de verdade (minutos) que
    sobrevivia pro PROXIMO teste, fazendo-o curto-circuitar pra
    rate_limited mesmo com seu proprio mock dizendo outra coisa --
    13 testes quebraram em cadeia antes disto existir."""
    from skinvault import steam_api
    steam_api._rate_limit_state.clear()
    yield
    steam_api._rate_limit_state.clear()


@pytest.fixture(autouse=True)
def _sem_welcome_dialog_modal(monkeypatch):
    """WelcomeDialog.exec() nunca abre modal de verdade na suite.

    2026-08-07: start() do ScreenRouter passou a chamar
    _maybe_show_welcome() sempre (F10/login removida, sem sessao pra
    gatear). Sem isso, qualquer teste que construa MainWindow ou chame
    ScreenRouter.start() encontra welcome_seen=False no settings.json
    real do usuario e abre um QDialog.exec() modal que trava pra sempre
    no offscreen (medido na pratica: suite travou ~2h). Patch no metodo
    exec() da classe real, nao no nome do modulo -- preserva testes que
    instanciam WelcomeDialog de verdade sem chamar exec()
    (test_welcome_dialog_instantiates).
    """
    from skinvault.ui.welcome_dialog import WelcomeDialog
    monkeypatch.setattr(WelcomeDialog, "exec", lambda self: 0)
