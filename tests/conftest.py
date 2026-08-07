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

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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
