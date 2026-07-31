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


def test_frozen_data_dir_fora_do_exe(monkeypatch):
    """Congelado NAO grava ao lado do .exe -- rebuild apagaria os dados."""
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("SKINVAULT_DATA_DIR", raising=False)

    paths = _reload_paths()
    assert paths.DATA_DIR != paths.BASE_DIR / "data"
    assert paths.LEGACY_DATA_DIR == paths.BASE_DIR / "data"

    monkeypatch.undo()
    _reload_paths()


def test_legacy_data_dir_none_em_dev(monkeypatch):
    """Em dev nao existe dado legado pra migrar."""
    monkeypatch.delenv("SKINVAULT_DATA_DIR", raising=False)
    paths = _reload_paths()
    assert paths.LEGACY_DATA_DIR is None


def test_ensure_data_dir_migra_legado(monkeypatch, tmp_path):
    """Dado de build antigo e' copiado uma vez pro DATA_DIR novo."""
    paths = _reload_paths()
    legacy = tmp_path / "legacy"
    (legacy / "backups").mkdir(parents=True)
    (legacy / "trades.json").write_text('[{"id": 1}]', encoding="utf-8")
    (legacy / "backups" / "b.zip").write_bytes(b"zip")
    target = tmp_path / "novo"

    monkeypatch.setattr(paths, "DATA_DIR", target)
    monkeypatch.setattr(paths, "LEGACY_DATA_DIR", legacy)

    assert paths.ensure_data_dir() == target
    assert (target / "trades.json").read_text(encoding="utf-8") == '[{"id": 1}]'
    assert (target / "backups" / "b.zip").read_bytes() == b"zip"


def test_ensure_data_dir_nao_sobrescreve(monkeypatch, tmp_path):
    """Destino com dado e' a fonte da verdade -- legado nao sobrescreve."""
    paths = _reload_paths()
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "trades.json").write_text("legado", encoding="utf-8")
    target = tmp_path / "novo"
    target.mkdir()
    (target / "trades.json").write_text("atual", encoding="utf-8")

    monkeypatch.setattr(paths, "DATA_DIR", target)
    monkeypatch.setattr(paths, "LEGACY_DATA_DIR", legacy)
    paths.ensure_data_dir()

    assert (target / "trades.json").read_text(encoding="utf-8") == "atual"


def test_ensure_data_dir_sem_legado(monkeypatch, tmp_path):
    """Sem legado (modo dev): apenas cria o diretorio."""
    paths = _reload_paths()
    target = tmp_path / "dev"
    monkeypatch.setattr(paths, "DATA_DIR", target)
    monkeypatch.setattr(paths, "LEGACY_DATA_DIR", None)

    assert paths.ensure_data_dir() == target
    assert target.is_dir()
