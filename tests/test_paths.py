"""Testes para skinvault._paths."""
from __future__ import annotations

from pathlib import Path


def test_data_dir_dev():
    """DATA_DIR em modo dev aponta para raiz/data."""
    from skinvault._paths import DATA_DIR, BASE_DIR
    assert DATA_DIR == BASE_DIR / "data"
    assert DATA_DIR.name == "data"


def test_frozen_branch(monkeypatch):
    """Branch frozen (sys.frozen=True) usa BASE_DIR diferente."""
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    import importlib
    import skinvault._paths
    importlib.reload(skinvault._paths)

    assert skinvault._paths.BASE_DIR == Path(sys.executable).parent

    # Restaura para modo dev
    monkeypatch.undo()
    importlib.reload(skinvault._paths)
    assert skinvault._paths.BASE_DIR.name == (
        Path(__file__).resolve().parent.parent.name)
