"""Caminhos do SkinVault -- resolve data/ pra desenvolvimento e .exe."""
from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller .exe: data/ ao lado do executavel
    BASE_DIR = Path(sys.executable).parent
else:
    # Desenvolvimento: raiz do projeto
    BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
