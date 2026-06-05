"""Gera screenshots de cada aba do SkinVault pra validacao."""
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

OUT = Path(__file__).parent / "prints"
OUT.mkdir(exist_ok=True)


def shoot():
    from skinvault.gui import MainWindow

    app = QApplication([])
    win = MainWindow()
    win.show()
    app.processEvents()

    tabs = [
        (0, "01-inventario"),
        (1, "02-portfolio"),
        (2, "03-market-browser"),
        (3, "04-watchlist"),
        (4, "05-trade-analyzer"),
        (5, "06-simulador"),
    ]

    def capture():
        for idx, name in tabs:
            win.setCurrentIndex(idx)
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
