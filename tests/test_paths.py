"""Caminhos de dados do site público."""
from __future__ import annotations

import importlib
from pathlib import Path


def _reload_paths():
    import galaseca._paths
    importlib.reload(galaseca._paths)
    return galaseca._paths


def test_data_dir_padrao(monkeypatch):
    monkeypatch.delenv("GALASECA_DATA_DIR", raising=False)
    paths = _reload_paths()

    assert paths.DATA_DIR == paths.BASE_DIR / "data"


def test_env_var_override(monkeypatch, tmp_path):
    monkeypatch.setenv("GALASECA_DATA_DIR", str(tmp_path))
    paths = _reload_paths()

    assert paths.DATA_DIR == tmp_path


def test_ensure_data_dir_cria_e_limpa_temporarios(monkeypatch, tmp_path):
    paths = _reload_paths()
    data_dir = tmp_path / "data"
    monkeypatch.setattr(paths, "DATA_DIR", data_dir)

    assert paths.ensure_data_dir() == data_dir
    abandoned = data_dir / "registro.json.tmp"
    abandoned.write_text("parcial", encoding="utf-8")

    assert paths.ensure_data_dir() == data_dir
    assert not abandoned.exists()


def test_nome_antigo_da_variavel_continua_valendo(monkeypatch, tmp_path):
    # Configuração da VM fica fora do repositório: SKINVAULT_* segue aceito.
    from galaseca._ambiente import ambiente
    monkeypatch.delenv("GALASECA_WORKER_INTERVAL_HORAS", raising=False)
    monkeypatch.setenv("SKINVAULT_WORKER_INTERVAL_HORAS", "3")
    assert ambiente("WORKER_INTERVAL_HORAS") == "3"
    monkeypatch.setenv("GALASECA_WORKER_INTERVAL_HORAS", "4")
    assert ambiente("WORKER_INTERVAL_HORAS") == "4"
    monkeypatch.delenv("GALASECA_WORKER_INTERVAL_HORAS")
    monkeypatch.delenv("SKINVAULT_WORKER_INTERVAL_HORAS")
    assert ambiente("WORKER_INTERVAL_HORAS", "6") == "6"
