"""Testes de skinvault.cleanup.

Nenhum teste aqui toca em pasta real do Windows: os alvos resolvem os
caminhos a partir das env vars (TEMP, SystemRoot, LOCALAPPDATA) na hora da
chamada, entao apontar tudo pra tmp_path e' suficiente pra exercitar o
codigo de verdade -- incluindo a remocao.

A lixeira nao tem caminho e cai no shell32; ali as duas funcoes do ctypes
(`recycle_bin_query`/`recycle_bin_empty`) sao o ponto de mock.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from skinvault import cleanup


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    """Trava TODA env var de caminho em tmp_path, em todo teste do modulo.

    Autouse de proposito. Este arquivo exercita remocao de arquivo de
    verdade, e uma env var esquecida nao da erro: o alvo simplesmente
    resolve pro caminho REAL da maquina e a limpeza acontece nele. Foi o
    que ocorreu quando `test_data_dir_nunca_entra_na_limpeza` patchou
    TEMP/TMP mas nao SystemRoot -- `_temp_dirs()` incluiu o
    C:\\Windows\\Temp real e apagou 22 arquivos da maquina do dev.

    Barrar por opt-in (cada teste lembrar de patchar tudo) ja' falhou uma
    vez; isolar por default nao depende de ninguem lembrar.
    """
    sandbox = tmp_path / "_env"
    sandbox.mkdir(exist_ok=True)
    for var in ("TEMP", "TMP", "SystemRoot", "windir", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(sandbox / var))
    yield sandbox


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """Aponta TODO alvo com caminho pra dentro de tmp_path, ja' com as
    pastas criadas."""
    temp = tmp_path / "temp"
    winroot = tmp_path / "Windows"
    local = tmp_path / "Local"
    for p in (temp, winroot / "Prefetch",
              winroot / "SoftwareDistribution" / "Download",
              local / "Microsoft" / "Windows" / "Explorer"):
        p.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))
    monkeypatch.setenv("SystemRoot", str(winroot))
    monkeypatch.setenv("windir", str(winroot))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    # DATA_DIR fora da arvore dos alvos: senao a protecao mataria os testes
    monkeypatch.setattr(cleanup, "_protected_paths", lambda: [])
    return {"temp": temp, "win": winroot, "local": local}


def test_isolate_env_cobre_todo_alvo_com_caminho(isolate_env):
    """Guarda do proprio fixture: se um alvo novo passar a ler outra env
    var, este teste denuncia antes de alguem apagar C:\\ de verdade."""
    for key in cleanup.TARGET_KEYS:
        for root in cleanup.target_roots(key):
            assert str(isolate_env) in str(root), (key, root)


# ── alvos / metadados ────────────────────────────────────────
def test_targets_metadata_consistente():
    assert len(cleanup.TARGETS) == 5
    assert cleanup.TARGET_KEYS == tuple(t.key for t in cleanup.TARGETS)
    assert set(cleanup.TARGETS_BY_KEY) == set(cleanup.TARGET_KEYS)
    lixeira = cleanup.TARGETS_BY_KEY[cleanup.RECYCLE_BIN]
    assert lixeira.dangerous is True
    assert cleanup.TARGETS_BY_KEY[cleanup.PREFETCH].needs_admin is True
    for t in cleanup.TARGETS:
        assert t.title and t.description


def test_clean_target_key_invalida():
    with pytest.raises(KeyError):
        cleanup.clean_target("nao_existe")


# ── medicao ──────────────────────────────────────────────────
def test_scan_temp_soma_arquivos_e_bytes(fake_env):
    temp = fake_env["temp"]
    (temp / "a.tmp").write_bytes(b"x" * 100)
    sub = temp / "sub"
    sub.mkdir()
    (sub / "b.log").write_bytes(b"y" * 50)

    res = cleanup.scan_target(cleanup.TEMP_FILES)
    assert res.available is True
    assert res.files == 2
    assert res.bytes == 150


def test_scan_prefetch_so_conta_pf(fake_env):
    pf = fake_env["win"] / "Prefetch"
    (pf / "APP.pf").write_bytes(b"a" * 10)
    (pf / "layout.ini").write_bytes(b"b" * 999)

    res = cleanup.scan_target(cleanup.PREFETCH)
    assert res.files == 1
    assert res.bytes == 10


def test_scan_thumbnails_so_conta_caches(fake_env):
    exp = fake_env["local"] / "Microsoft" / "Windows" / "Explorer"
    (exp / "thumbcache_32.db").write_bytes(b"a" * 20)
    (exp / "iconcache_16.db").write_bytes(b"b" * 5)
    (exp / "outra_coisa.db").write_bytes(b"c" * 777)

    res = cleanup.scan_target(cleanup.THUMBNAILS)
    assert res.files == 2
    assert res.bytes == 25


def test_scan_alvo_ausente_marca_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "nao_existe"))
    res = cleanup.scan_target(cleanup.PREFETCH)
    assert res.available is False
    assert res.files == 0


def test_scan_all_cobre_todos_os_alvos(fake_env, monkeypatch):
    monkeypatch.setattr(cleanup, "recycle_bin_query", lambda: (3, 300))
    out = cleanup.scan_all()
    assert set(out) == set(cleanup.TARGET_KEYS)
    assert out[cleanup.RECYCLE_BIN].files == 3
    assert out[cleanup.RECYCLE_BIN].bytes == 300


def test_scan_all_isola_falha_de_um_alvo(fake_env, monkeypatch):
    real = cleanup.scan_target

    def boom(key):
        if key == cleanup.TEMP_FILES:
            raise RuntimeError("disco pegou fogo")
        return real(key)

    monkeypatch.setattr(cleanup, "scan_target", boom)
    out = cleanup.scan_all()
    assert out[cleanup.TEMP_FILES].available is False
    assert cleanup.PREFETCH in out  # os outros seguiram


# ── remocao ──────────────────────────────────────────────────
def test_clean_temp_remove_conteudo_e_preserva_a_raiz(fake_env):
    temp = fake_env["temp"]
    (temp / "a.tmp").write_bytes(b"x" * 10)
    sub = temp / "sub"
    sub.mkdir()
    (sub / "b.log").write_bytes(b"y" * 5)

    res = cleanup.clean_target(cleanup.TEMP_FILES)
    assert res.removed == 2
    assert res.freed == 15
    assert res.skipped == 0
    assert temp.is_dir()          # a raiz do alvo NUNCA sai
    assert list(temp.iterdir()) == []


def test_clean_prefetch_nao_toca_no_layout_ini(fake_env):
    pf = fake_env["win"] / "Prefetch"
    (pf / "APP.pf").write_bytes(b"a")
    (pf / "layout.ini").write_bytes(b"b")

    res = cleanup.clean_target(cleanup.PREFETCH)
    assert res.removed == 1
    assert not (pf / "APP.pf").exists()
    assert (pf / "layout.ini").exists()


def test_clean_arquivo_readonly(fake_env):
    """Read-only sozinho nao pode virar 'em uso': o chmod resolve."""
    temp = fake_env["temp"]
    f = temp / "ro.tmp"
    f.write_bytes(b"x" * 8)
    os.chmod(str(f), 0o444)

    res = cleanup.clean_target(cleanup.TEMP_FILES)
    assert res.removed == 1
    assert res.freed == 8
    assert not f.exists()


def test_clean_arquivo_travado_conta_como_skipped(fake_env, monkeypatch):
    temp = fake_env["temp"]
    (temp / "locked.tmp").write_bytes(b"x" * 4)
    (temp / "ok.tmp").write_bytes(b"y" * 4)

    real_unlink = Path.unlink

    def unlink(self, *a, **kw):
        if self.name == "locked.tmp":
            raise PermissionError(str(self))
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(cleanup, "_force_writable", lambda p: False)

    res = cleanup.clean_target(cleanup.TEMP_FILES)
    assert res.removed == 1
    assert res.skipped == 1
    assert res.errors and "PermissionError" in res.errors[0]
    assert (temp / "locked.tmp").exists()


def test_clean_arquivo_travado_nao_aborta_a_arvore(fake_env, monkeypatch):
    """rmtree pararia a pasta inteira no primeiro erro; aqui cada filho e'
    independente."""
    temp = fake_env["temp"]
    d = temp / "dir"
    d.mkdir()
    for n in ("a", "locked", "z"):
        (d / f"{n}.tmp").write_bytes(b"x" * 2)

    real_unlink = Path.unlink

    def unlink(self, *a, **kw):
        if self.name == "locked.tmp":
            raise PermissionError(str(self))
        return real_unlink(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(cleanup, "_force_writable", lambda p: False)

    res = cleanup.clean_target(cleanup.TEMP_FILES)
    assert res.removed == 2       # os vizinhos sairam
    assert res.skipped == 1
    assert d.is_dir()             # a pasta ficou porque sobrou conteudo


def test_clean_errors_tem_teto(fake_env, monkeypatch):
    temp = fake_env["temp"]
    for i in range(cleanup._MAX_ERRORS + 5):
        (temp / f"f{i}.tmp").write_bytes(b"x")

    def unlink(self, *a, **kw):
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(cleanup, "_force_writable", lambda p: False)

    res = cleanup.clean_target(cleanup.TEMP_FILES)
    assert res.skipped == cleanup._MAX_ERRORS + 5
    assert len(res.errors) == cleanup._MAX_ERRORS


def test_clean_multiplos_alvos_respeita_ordem(fake_env, monkeypatch):
    monkeypatch.setattr(cleanup, "recycle_bin_query", lambda: (0, 0))
    monkeypatch.setattr(cleanup, "recycle_bin_empty", lambda: True)
    (fake_env["temp"] / "a.tmp").write_bytes(b"x")
    (fake_env["win"] / "Prefetch" / "A.pf").write_bytes(b"y")

    out = cleanup.clean([cleanup.PREFETCH, cleanup.TEMP_FILES])
    assert list(out) == [cleanup.TEMP_FILES, cleanup.PREFETCH]


def test_clean_ignora_chave_desconhecida(fake_env):
    out = cleanup.clean(["nao_existe"])
    assert out == {}


# ── protecoes ────────────────────────────────────────────────
def test_data_dir_nunca_entra_na_limpeza(tmp_path, monkeypatch):
    """DATA_DIR dentro do %TEMP% e' cenario real: o .exe congelado grava em
    %APPDATA%, mas SKINVAULT_DATA_DIR aponta pra onde o usuario quiser."""
    temp = tmp_path / "temp"
    data = temp / "SkinVault" / "data"
    data.mkdir(parents=True)
    (data / "trades.json").write_text("[]", encoding="utf-8")
    (temp / "lixo.tmp").write_bytes(b"x")
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setenv("windir", str(tmp_path / "Windows"))
    monkeypatch.setattr(cleanup, "_protected_paths", lambda: [cleanup._norm(data)])

    res = cleanup.clean_target(cleanup.TEMP_FILES)
    assert res.removed == 1
    assert (data / "trades.json").exists()   # o ancestral foi barrado inteiro


def test_is_protected_pega_ancestral_e_descendente(tmp_path, monkeypatch):
    prot = tmp_path / "a" / "b" / "c"
    prot.mkdir(parents=True)
    monkeypatch.setattr(cleanup, "_protected_paths",
                        lambda: [cleanup._norm(prot)])
    assert cleanup._is_protected(prot) is True
    assert cleanup._is_protected(tmp_path / "a") is True        # ancestral
    assert cleanup._is_protected(prot / "d") is True            # descendente
    assert cleanup._is_protected(tmp_path / "outro") is False


def test_is_protected_barra_raiz_de_volume(monkeypatch):
    monkeypatch.setattr(cleanup, "_protected_paths", lambda: [])
    raiz = Path(os.path.abspath(os.sep))
    assert cleanup._is_protected(raiz) is True


def test_meipass_e_protegido(tmp_path, monkeypatch):
    """O PyInstaller descompacta o .exe DENTRO do %TEMP%; apagar isso mata o
    processo em execucao."""
    mei = tmp_path / "_MEI12345"
    mei.mkdir()
    monkeypatch.setattr(cleanup.sys, "_MEIPASS", str(mei), raising=False)
    assert cleanup._norm(mei) in cleanup._protected_paths()
    assert cleanup._is_protected(mei / "python39.dll") is True


def test_temp_dirs_sem_repeticao(tmp_path, monkeypatch):
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    dirs = cleanup._temp_dirs()
    assert len({cleanup._norm(d) for d in dirs}) == len(dirs)


def test_target_roots_sem_localappdata(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert cleanup.target_roots(cleanup.THUMBNAILS) == []


def test_target_roots_lixeira_nao_tem_caminho():
    assert cleanup.target_roots(cleanup.RECYCLE_BIN) == []


# ── lixeira ──────────────────────────────────────────────────
def test_lixeira_limpa_com_sucesso(monkeypatch):
    monkeypatch.setattr(cleanup, "recycle_bin_query", lambda: (7, 4096))
    monkeypatch.setattr(cleanup, "recycle_bin_empty", lambda: True)
    res = cleanup.clean_target(cleanup.RECYCLE_BIN)
    assert res.removed == 7
    assert res.freed == 4096
    assert res.errors == []


def test_lixeira_falha_vira_skipped(monkeypatch):
    monkeypatch.setattr(cleanup, "recycle_bin_query", lambda: (2, 10))
    monkeypatch.setattr(cleanup, "recycle_bin_empty", lambda: False)
    res = cleanup.clean_target(cleanup.RECYCLE_BIN)
    assert res.removed == 0
    assert res.skipped == 2
    assert res.errors


def test_lixeira_fora_do_windows(monkeypatch):
    monkeypatch.setattr(cleanup, "_IS_WINDOWS", False)
    assert cleanup.recycle_bin_query() == (0, 0)
    assert cleanup.recycle_bin_empty() is False
    assert cleanup.is_admin() is False


def test_scan_lixeira_usa_a_api(monkeypatch):
    monkeypatch.setattr(cleanup, "recycle_bin_query", lambda: (4, 2048))
    monkeypatch.setattr(cleanup, "_IS_WINDOWS", True)
    res = cleanup.scan_target(cleanup.RECYCLE_BIN)
    assert (res.files, res.bytes, res.available) == (4, 2048, True)


# ── formatacao ───────────────────────────────────────────────
@pytest.mark.parametrize("valor,esperado", [
    (0, "0 B"),
    (512, "512 B"),
    (1024, "1,0 KB"),
    (1536, "1,5 KB"),
    (1024 ** 2, "1,0 MB"),
    (1024 ** 3 * 2, "2,0 GB"),
    (-5, "0 B"),
])
def test_human_bytes(valor, esperado):
    assert cleanup.human_bytes(valor) == esperado


def test_human_bytes_valor_invalido():
    assert cleanup.human_bytes(None) == "—"
    assert cleanup.human_bytes("abc") == "—"
