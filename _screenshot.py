"""Gera screenshots de cada tela do SkinVault pra validacao.

Atualizado pos-F11: navega via ScreenRouter em vez de QTabWidget.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

OUT = Path(__file__).parent / "prints"
OUT.mkdir(exist_ok=True)


def shoot():
    from skinvault.gui import MainWindow
    from skinvault.ui import screen_router as sr

    app = QApplication([])
    win = MainWindow()
    win.show()
    app.processEvents()

    screens = [
        (sr.SCREEN_ACCOUNT, "01-account"),
        (sr.SCREEN_HISTORY, "02-history"),
        (sr.SCREEN_SCANNER, "03-scanner"),
        (sr.SCREEN_MARKET, "04-market"),
        (sr.SCREEN_TRADES, "05-trades"),
        (sr.SCREEN_SIMULADOR, "06-simulador"),
        (sr.SCREEN_WATCHLIST, "07-watchlist"),
    ]

    def capture():
        for screen, name in screens:
            win._router.navigate(screen)
            app.processEvents()
            pix = win.grab()
            pix.save(str(OUT / f"{name}.png"))
            print(f"  salvo: prints/{name}.png")
        print("Prontos em prints/")
        app.quit()

    QTimer.singleShot(500, capture)
    app.exec()


if __name__ == "__main__":
    shoot()
