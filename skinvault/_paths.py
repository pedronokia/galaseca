"""Caminhos do SkinVault -- resolve data/ pra desenvolvimento e .exe.

Permite override via env var SKINVAULT_DATA_DIR (util pra testes
isolados e usuarios que querem persistir em outro lugar).

Em build congelado os dados NAO ficam mais ao lado do executavel: o
PyInstaller recria dist/ inteiro a cada build, levando junto trades,
watchlist e historico; e uma instalacao em Program Files nem e' gravavel
pro usuario comum. Congelado grava no perfil do usuario.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_FROZEN = bool(getattr(sys, "frozen", False))

if _FROZEN:
    # PyInstaller .exe: pasta do executavel (so' pra achar dado legado)
    BASE_DIR = Path(sys.executable).parent
else:
    # Desenvolvimento: raiz do projeto
    BASE_DIR = Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    """Diretorio de dados por usuario -- gravavel em qualquer instalacao."""
    appdata = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if appdata:
        return Path(appdata) / "SkinVault" / "data"
    return Path.home() / ".local" / "share" / "SkinVault" / "data"


# Onde os builds antigos gravavam. So' existe em modo congelado.
LEGACY_DATA_DIR: Path | None = (BASE_DIR / "data") if _FROZEN else None

_OVERRIDE = os.environ.get("SKINVAULT_DATA_DIR")
if _OVERRIDE:
    DATA_DIR = Path(_OVERRIDE)
elif _FROZEN:
    DATA_DIR = _user_data_dir()
else:
    DATA_DIR = BASE_DIR / "data"


def ensure_data_dir() -> Path:
    """Cria DATA_DIR e migra dado legado uma unica vez. Retorna DATA_DIR.

    Chamado no startup (gui.launch). Importar este modulo continua sem
    efeito colateral de I/O -- os testes recarregam _paths varias vezes, e
    criar diretorio no import sujaria a maquina a cada reload.

    A migracao e' best-effort e nunca sobrescreve: se o destino ja' tem
    qualquer arquivo, assume-se que ele e' a fonte da verdade.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    legacy = LEGACY_DATA_DIR
    if legacy is None or legacy == DATA_DIR or not legacy.is_dir():
        return DATA_DIR
    if any(DATA_DIR.iterdir()):
        return DATA_DIR
    for src in legacy.iterdir():
        dest = DATA_DIR / src.name
        try:
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
        except OSError:
            pass  # dado legado fica onde esta'; nao vale abortar o startup
    return DATA_DIR
