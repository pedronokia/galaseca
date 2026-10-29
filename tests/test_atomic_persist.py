"""Escrita atomica e quarentena de arquivo corrompido.

Contexto: o app rodava com `minimize_to_tray_on_close`, e chegou a ter 29
processos vivos gravando nos mesmos JSON. O single_instance fechou a
concorrencia; aqui esta' a outra metade -- `Path.write_text` TRUNCA o
destino antes de escrever, entao morrer no meio deixava JSON cortado. E
como todo loader tratava JSON invalido como "vazio", o proximo save
gravava o vazio por cima: perda definitiva, em silencio.
"""
from __future__ import annotations

import json
import os

import pytest

from skinvault import _paths


# ── atomic_write_text ──────────────────────────────────────────────

def test_grava_o_conteudo(tmp_path):
    alvo = tmp_path / "x.json"
    _paths.atomic_write_text(alvo, '{"a": 1}')
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"a": 1}


def test_cria_o_diretorio_pai(tmp_path):
    """Os call sites faziam mkdir; o helper absorveu isso."""
    alvo = tmp_path / "sub" / "dir" / "x.json"
    _paths.atomic_write_text(alvo, "[]")
    assert alvo.is_file()


def test_sobrescreve_arquivo_existente(tmp_path):
    alvo = tmp_path / "x.json"
    alvo.write_text("[1]", encoding="utf-8")
    _paths.atomic_write_text(alvo, "[2]")
    assert alvo.read_text(encoding="utf-8") == "[2]"


def test_nao_deixa_temporario_pra_tras(tmp_path):
    alvo = tmp_path / "x.json"
    _paths.atomic_write_text(alvo, "[]")
    assert list(tmp_path.glob("*.tmp")) == []


def test_temporario_fica_no_mesmo_diretorio(tmp_path, monkeypatch):
    """Temporario noutro volume faria `os.replace` deixar de ser atomico."""
    vistos = []
    real = _paths.tempfile.mkstemp

    def espiao(*a, **kw):
        vistos.append(kw.get("dir"))
        return real(*a, **kw)

    monkeypatch.setattr(_paths.tempfile, "mkstemp", espiao)
    alvo = tmp_path / "sub" / "x.json"
    _paths.atomic_write_text(alvo, "[]")
    assert vistos == [str(alvo.parent)]


# ── o ponto do exercicio: falha no meio ────────────────────────────

def test_falha_no_meio_preserva_o_arquivo_antigo(tmp_path, monkeypatch):
    """E' exatamente o que `write_text` NAO fazia."""
    alvo = tmp_path / "trades.json"
    alvo.write_text('[{"name": "AK"}]', encoding="utf-8")

    def morre(*_a, **_kw):
        raise OSError("disco cheio")

    monkeypatch.setattr(_paths.os, "fsync", morre)
    with pytest.raises(OSError):
        _paths.atomic_write_text(alvo, "[]")

    assert json.loads(alvo.read_text(encoding="utf-8")) == [{"name": "AK"}]


def test_falha_no_meio_nao_deixa_temporario(tmp_path, monkeypatch):
    alvo = tmp_path / "x.json"

    def morre(*_a, **_kw):
        raise OSError("disco cheio")

    monkeypatch.setattr(_paths.os, "fsync", morre)
    with pytest.raises(OSError):
        _paths.atomic_write_text(alvo, "[]")
    assert list(tmp_path.glob("*.tmp")) == []


def test_falha_no_replace_tambem_limpa(tmp_path, monkeypatch):
    alvo = tmp_path / "x.json"
    alvo.write_text("[1]", encoding="utf-8")

    def morre(*_a, **_kw):
        raise OSError("destino em uso")

    monkeypatch.setattr(_paths.os, "replace", morre)
    with pytest.raises(OSError):
        _paths.atomic_write_text(alvo, "[2]")
    assert alvo.read_text(encoding="utf-8") == "[1]"
    assert list(tmp_path.glob("*.tmp")) == []


def test_aborto_nao_deixa_temporario(tmp_path, monkeypatch):
    """KeyboardInterrupt nao herda de Exception -- daí o `except BaseException`."""
    alvo = tmp_path / "x.json"

    def morre(*_a, **_kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr(_paths.os, "fsync", morre)
    with pytest.raises(KeyboardInterrupt):
        _paths.atomic_write_text(alvo, "[]")
    assert list(tmp_path.glob("*.tmp")) == []


def test_bytes_gravam_e_sao_atomicos(tmp_path, monkeypatch):
    """O restore de backup sobrescreve dado VIVO -- falhar no meio la'
    quebraria o arquivo que o usuario ainda esta' usando."""
    alvo = tmp_path / "x.bin"
    _paths.atomic_write_bytes(alvo, b"novo")
    assert alvo.read_bytes() == b"novo"

    def morre(*_a, **_kw):
        raise OSError("disco cheio")

    monkeypatch.setattr(_paths.os, "fsync", morre)
    with pytest.raises(OSError):
        _paths.atomic_write_bytes(alvo, b"quebrado")
    assert alvo.read_bytes() == b"novo"
    assert list(tmp_path.glob("*.tmp")) == []


def test_acentos_sobrevivem(tmp_path):
    alvo = tmp_path / "x.json"
    texto = json.dumps({"n": "Caixa Fênix ★ StatTrak™"}, ensure_ascii=False)
    _paths.atomic_write_text(alvo, texto)
    assert json.loads(alvo.read_text(encoding="utf-8"))["n"] == \
        "Caixa Fênix ★ StatTrak™"


# ── quarantine_corrupt ─────────────────────────────────────────────

def test_quarentena_move_o_arquivo(tmp_path):
    alvo = tmp_path / "trades.json"
    alvo.write_text("{lixo", encoding="utf-8")
    dest = _paths.quarantine_corrupt(alvo)
    assert dest == tmp_path / "trades.json.corrupt"
    assert dest.read_text(encoding="utf-8") == "{lixo"
    assert not alvo.exists()


def test_quarentena_ignora_inexistente(tmp_path):
    assert _paths.quarantine_corrupt(tmp_path / "nada.json") is None


def test_quarentena_ignora_vazio(tmp_path):
    """Arquivo de 0 byte nao tem nada a preservar."""
    alvo = tmp_path / "x.json"
    alvo.touch()
    assert _paths.quarantine_corrupt(alvo) is None


def test_quarentena_sobrescreve_a_anterior(tmp_path):
    alvo = tmp_path / "x.json"
    alvo.write_text("primeiro", encoding="utf-8")
    _paths.quarantine_corrupt(alvo)
    alvo.write_text("segundo", encoding="utf-8")
    dest = _paths.quarantine_corrupt(alvo)
    assert dest.read_text(encoding="utf-8") == "segundo"


# ── load_json_record ───────────────────────────────────────────────

def test_load_devolve_o_conteudo(tmp_path):
    alvo = tmp_path / "x.json"
    alvo.write_text('[1, 2]', encoding="utf-8")
    assert _paths.load_json_record(alvo, []) == [1, 2]


def test_load_ausente_devolve_default(tmp_path):
    assert _paths.load_json_record(tmp_path / "nada.json", []) == []


def test_load_ausente_nao_cria_quarentena(tmp_path):
    _paths.load_json_record(tmp_path / "nada.json", [])
    assert list(tmp_path.glob("*.corrupt")) == []


def test_load_corrompido_preserva_e_devolve_default(tmp_path):
    alvo = tmp_path / "trades.json"
    alvo.write_text('[{"name": "AK"', encoding="utf-8")  # cortado no meio
    assert _paths.load_json_record(alvo, []) == []
    assert (tmp_path / "trades.json.corrupt").exists()


def test_load_tipo_errado_nao_vai_pra_quarentena(tmp_path):
    """Parseia mas nao e' a forma esperada: bug de codigo ou arquivo de
    outra versao, nao truncamento. Mover esconderia o problema."""
    alvo = tmp_path / "x.json"
    alvo.write_text('"uma string"', encoding="utf-8")
    assert _paths.load_json_record(alvo, []) == "uma string"
    assert list(tmp_path.glob("*.corrupt")) == []


# ── sweep_stale_temps ──────────────────────────────────────────────

def test_sweep_apaga_temporarios(tmp_path):
    """kill -9 no meio da escrita nao roda except nenhum."""
    (tmp_path / "a.json.abc.tmp").write_text("x", encoding="utf-8")
    (tmp_path / "b.json.def.tmp").write_text("y", encoding="utf-8")
    (tmp_path / "keep.json").write_text("[]", encoding="utf-8")
    assert _paths.sweep_stale_temps(tmp_path) == 2
    assert (tmp_path / "keep.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_sweep_em_diretorio_inexistente(tmp_path):
    assert _paths.sweep_stale_temps(tmp_path / "nao_existe") == 0


# ── ponta a ponta: o cenario que motivou tudo ──────────────────────

def test_trades_corrompido_nao_e_apagado_pelo_proximo_save(tmp_path):
    """Antes: le' vazio -> grava vazio por cima -> os trades somem.
    Agora: le' vazio, mas a copia velha fica em disco."""
    from skinvault import trades as trades_mod
    p = tmp_path / "trades.json"
    p.write_text('[{"name": "AK", "pnl": 7', encoding="utf-8")

    assert trades_mod.load_trades(p) == []
    trades_mod.record_trade("AWP", 10.0, 20.0, path=p)

    assert len(trades_mod.load_trades(p)) == 1
    preservado = tmp_path / "trades.json.corrupt"
    assert preservado.exists()
    assert "AK" in preservado.read_text(encoding="utf-8")


def test_portfolio_corrompido_e_preservado(tmp_path):
    from skinvault import portfolio as portfolio_mod
    p = tmp_path / "portfolio.json"
    p.write_text('[{"name": "Kilowatt Case",', encoding="utf-8")
    assert portfolio_mod.load_portfolio(p) == []
    assert (tmp_path / "portfolio.json.corrupt").exists()
