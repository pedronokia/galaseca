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

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
