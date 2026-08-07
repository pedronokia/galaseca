"""Gera screenshots de cada tela do SkinVault pra validacao.

Atualizado pos-F11: navega via ScreenRouter em vez de QTabWidget.

NAO usar win.show() em hipotese alguma: WA_DontShowOnScreen esconde
o widget mas Qt ainda cria HWND nativo no Windows, e a criacao do
HWND rouba foco de jogos fullscreen exclusive (CS2, etc). Em vez
disso: resize() + processEvents() + grab() — Qt nem cria janela
nativa, zero risco de roubar foco.

Guard de seguranca: aborta se cs2.exe estiver rodando.

(Nao usar QT_QPA_PLATFORM=offscreen: quebra fontes do sistema no
Windows, sai tudo como tofu boxes.)
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import QApplication

OUT = Path(__file__).parent / "prints"
OUT.mkdir(exist_ok=True)

# Tamanho usado pra layout (aproximadamente maximized em 1920x1080).
TARGET_SIZE = QSize(1920, 1200)


def _abort_if_gaming() -> None:
    """Se cs2.exe estiver rodando, aborta antes de mexer no Qt.

    Bypass: SKIP_GAME_GUARD=1 (usar so quando souber que o jogo nao
    esta em foco/fullscreen exclusive)."""
    if os.environ.get("SKIP_GAME_GUARD") == "1":
        return
    if sys.platform != "win32":
        return
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq cs2.exe", "/NH"],
            stderr=subprocess.DEVNULL, text=True, timeout=5,
        )
    except Exception:
        return
    if "cs2.exe" in out.lower():
        print("ABORT: cs2.exe esta rodando. Saia do jogo antes de rodar.")
        print("(bypass: SKIP_GAME_GUARD=1 python _screenshot.py)")
        sys.exit(2)


def shoot():
    _abort_if_gaming()

    # WelcomeDialog.exec() e' modal: se `data/settings.json` tiver
    # welcome_seen=False (sessao com login valido), MainWindow() trava pra
    # sempre esperando um clique que nunca vem neste script sem tela --
    # mesmo pitfall documentado em test_ui_smoke.py (_FakeWelcome /
    # _hermetic_welcome). Patch equivalente aqui, fora do pytest.
    import skinvault.ui.welcome_dialog as _wd

    class _FakeWelcome:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return 0

    _wd.WelcomeDialog = _FakeWelcome

    from skinvault.gui import MainWindow
    from skinvault.ui import screen_router as sr

    app = QApplication([])
    win = MainWindow()

    # CRITICO: NAO chamar win.show(). resize() + processEvents() faz
    # o Qt computar o layout sem criar HWND nativo. grab() renderiza
    # a arvore de widgets direto pra QPixmap em memoria.
    win.resize(TARGET_SIZE)
    app.processEvents()
    app.processEvents()  # 2x: deixa layout assentar

    screens = [
        (sr.SCREEN_ACCOUNT, "01-account"),
        (sr.SCREEN_INVENTORY, "02-inventory"),
        (sr.SCREEN_HISTORY, "03-history"),
        (sr.SCREEN_SCANNER, "04-scanner"),
        (sr.SCREEN_MARKET, "05-market"),
        (sr.SCREEN_TRADES, "06-trades"),
        (sr.SCREEN_WATCHLIST, "07-watchlist"),
        (sr.SCREEN_CLEANUP, "08-cleanup"),
        (sr.SCREEN_SETTINGS, "09-settings"),
    ]

    for screen, name in screens:
        win._router.navigate(screen)
        app.processEvents()
        app.processEvents()
        if screen == sr.SCREEN_CLEANUP:
            # A medicao roda em worker; sem esperar, o print sai com
            # "Medindo..." em vez dos tamanhos.
            import time
            for _ in range(40):
                if not win._router._cleanup_screen._scan_worker.running:
                    break
                time.sleep(0.25)
                app.processEvents()
            app.processEvents()
        pix = win.grab()
        pix.save(str(OUT / f"{name}.png"))
        print(f"  salvo: prints/{name}.png")
    print("Prontos em prints/")


if __name__ == "__main__":
    shoot()
