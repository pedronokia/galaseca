"""Caminhos do SkinVault -- resolve data/ pra desenvolvimento e .exe.

Permite override via env var SKINVAULT_DATA_DIR (util pra testes
isolados e usuarios que querem persistir em outro lugar).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller .exe: data/ ao lado do executavel
    BASE_DIR = Path(sys.executable).parent
else:
    # Desenvolvimento: raiz do projeto
    BASE_DIR = Path(__file__).resolve().parent.parent

_OVERRIDE = os.environ.get("SKINVAULT_DATA_DIR")
DATA_DIR = Path(_OVERRIDE) if _OVERRIDE else (BASE_DIR / "data")
