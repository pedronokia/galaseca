"""Shared isolation for tests of the public website and scan worker."""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import urllib.error
from pathlib import Path

import pytest

_TEST_ROOT = Path(tempfile.mkdtemp(prefix="galaseca-tests-"))
DATA_DIR_TESTE = _TEST_ROOT / "data"
DATA_DIR_TESTE.mkdir()
os.environ["GALASECA_DATA_DIR"] = str(DATA_DIR_TESTE)
# Nome antigo (ainda aceito como fallback) não pode vazar do ambiente.
os.environ.pop("SKINVAULT_DATA_DIR", None)
atexit.register(shutil.rmtree, _TEST_ROOT, True)


@pytest.fixture(autouse=True)
def _data_dir_isolado():
    yield
    import importlib

    import galaseca._paths as paths

    if paths.DATA_DIR != DATA_DIR_TESTE:
        os.environ["GALASECA_DATA_DIR"] = str(DATA_DIR_TESTE)
        importlib.reload(paths)


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    def _bloqueado(*_args, **_kwargs):
        raise urllib.error.URLError("rede bloqueada na suite de testes")

    monkeypatch.setattr("urllib.request.urlopen", _bloqueado)

    import httpx

    def _httpx_bloqueado(*_args, **_kwargs):
        raise httpx.ConnectError("rede bloqueada na suite de testes")

    monkeypatch.setattr(httpx, "get", _httpx_bloqueado)


@pytest.fixture(autouse=True)
def _sem_espera_de_rate_limit(monkeypatch):
    from galaseca import steam_api

    monkeypatch.setattr(steam_api, "RATE_LIMIT_DELAY_S", 0.0)


@pytest.fixture(autouse=True)
def _sem_disjuntores_de_rate_limit():
    from galaseca import steam_api
    from galaseca.public_site import rate_limit

    steam_api._rate_limit_state.clear()
    rate_limit.reset()
    yield
    steam_api._rate_limit_state.clear()
    rate_limit.reset()
