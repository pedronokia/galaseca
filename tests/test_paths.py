"""Testes para skinvault._paths."""
from __future__ import annotations

import importlib
from pathlib import Path


def _reload_paths():
    import skinvault._paths
    importlib.reload(skinvault._paths)
    return skinvault._paths


def test_data_dir_dev(monkeypatch):
    """DATA_DIR em modo dev aponta para raiz/data."""
    monkeypatch.delenv("SKINVAULT_DATA_DIR", raising=False)
    paths = _reload_paths()
    assert paths.DATA_DIR == paths.BASE_DIR / "data"
    assert paths.DATA_DIR.name == "data"


def test_env_var_override(monkeypatch, tmp_path):
    """SKINVAULT_DATA_DIR no env sobrescreve DATA_DIR."""
    monkeypatch.setenv("SKINVAULT_DATA_DIR", str(tmp_path))
    paths = _reload_paths()
    assert paths.DATA_DIR == tmp_path
    monkeypatch.delenv("SKINVAULT_DATA_DIR")
    _reload_paths()  # restaura


def test_frozen_branch(monkeypatch):
    """Branch frozen (sys.frozen=True) usa BASE_DIR diferente."""
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("SKINVAULT_DATA_DIR", raising=False)

    paths = _reload_paths()
    assert paths.BASE_DIR == Path(sys.executable).parent

    # Restaura para modo dev
    monkeypatch.undo()
    paths = _reload_paths()
    assert paths.BASE_DIR.name == (
        Path(__file__).resolve().parent.parent.name)
