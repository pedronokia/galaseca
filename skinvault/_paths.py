"""Caminhos persistentes usados pelo site público e pelo worker.

Permite override via env var SKINVAULT_DATA_DIR (util pra testes
isolados e usuarios que querem persistir em outro lugar).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Sufixos de trabalho. `_TMP_SUFFIX` e' o arquivo em construcao de
# `atomic_write_text`; `CORRUPT_SUFFIX` e' onde um arquivo ilegivel vai parar.
_TMP_SUFFIX = ".tmp"
CORRUPT_SUFFIX = ".corrupt"

BASE_DIR = Path(__file__).resolve().parent.parent
_OVERRIDE = os.environ.get("SKINVAULT_DATA_DIR")
DATA_DIR = Path(_OVERRIDE) if _OVERRIDE else BASE_DIR / "data"


def _atomic_write(path: Path | str, data, mode: str,
                  encoding: "str | None") -> None:
    """Nucleo de `atomic_write_text` / `atomic_write_bytes`.

    `Path.write_text`/`write_bytes` TRUNCAM o destino e so' depois escrevem.
    Se o processo morre no meio, sobra um JSON cortado. Pior: todo loader
    tratava JSON invalido como "vazio", e o proximo save gravava o vazio por
    cima. A perda virava definitiva em silencio.

    Aqui o conteudo vai pra um temporario no MESMO diretorio (destino noutro
    volume faria `os.replace` deixar de ser atomico) e so' entao substitui o
    original. Morrer antes do replace deixa o arquivo velho intacto.

    Cria o diretorio pai, como faziam os call sites. Propaga OSError -- os
    chamadores ja' tratam.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=p.name + ".",
                               suffix=_TMP_SUFFIX)
    try:
        # newline default (nao ""): mantem a traducao pra CRLF que o
        # write_text fazia, pra troca nao reescrever todo arquivo do usuario.
        with os.fdopen(fd, mode, encoding=encoding) as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except BaseException:
        # Inclui KeyboardInterrupt/SystemExit de proposito: o temporario nao
        # pode sobreviver a nenhuma forma de aborto.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path | str, text: str,
                      encoding: str = "utf-8") -> None:
    """Grava texto sem nunca deixar o arquivo pela metade. Ver `_atomic_write`."""
    _atomic_write(path, text, "w", encoding)


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Versao binaria, usada para persistir a chave de sessão do site."""
    _atomic_write(path, data, "wb", None)


def quarantine_corrupt(path: Path | str) -> "Path | None":
    """Move um arquivo ilegivel pra `<nome>.corrupt`. Devolve o destino.

    So' faz sentido pra arquivo de REGISTRO (portfolio, trades, watchlist).
    Cache ilegivel deve mesmo virar vazio em silencio -- e' regeneravel, e
    encher data/ de .corrupt de cache seria ruido.

    Sem isto, um arquivo corrompido le' como vazio e o proximo save apaga a
    unica copia que existia. Com isto, ela fica em disco pra recuperacao
    manual.
    """
    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size == 0:
            return None  # inexistente ou vazio: nao ha' o que preservar
        dest = p.with_name(p.name + CORRUPT_SUFFIX)
        os.replace(p, dest)  # sobrescreve quarentena anterior
        return dest
    except OSError:
        return None  # preservar e' best-effort; nunca derruba o load


def load_json_record(path: Path | str, default):
    """Le' JSON de um arquivo de REGISTRO, preservando o que nao parseia.

    Use em dado do usuario (portfolio, trades, watchlist, historico), nao em
    cache: cache ilegivel deve virar vazio em silencio e ser regenerado.

    Arquivo ausente ou ilegivel devolve `default` sem drama. Ja' conteudo
    presente que NAO parseia vai pra quarentena antes de devolver o default
    -- senao o proximo save gravaria o default por cima da unica copia.

    Nao quarentena conteudo que parseia mas tem o tipo errado (um dict onde
    se esperava lista): isso e' bug de codigo ou arquivo de outra versao,
    nao truncamento, e mover o arquivo esconderia o problema.
    """
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        dest = quarantine_corrupt(p)
        log.warning(
            "%s nao e' JSON valido; preservado em %s e seguindo com o padrao.",
            p.name, dest.name if dest else "(nao foi possivel preservar)",
        )
        return default


def sweep_stale_temps(directory: Path | str | None = None) -> int:
    """Apaga temporarios que sobraram de uma escrita interrompida.

    `atomic_write_text` limpa o proprio temporario, mas um kill -9 no meio
    nao roda except nenhum. Sem varredura eles se acumulam pra sempre.
    """
    d = Path(directory) if directory is not None else DATA_DIR
    n = 0
    try:
        candidatos = list(d.glob("*" + _TMP_SUFFIX))
    except OSError:
        return 0
    for tmp in candidatos:
        try:
            tmp.unlink()
            n += 1
        except OSError:
            pass
    return n


def ensure_data_dir() -> Path:
    """Cria o diretório de dados do site e remove temporários abandonados."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sweep_stale_temps(DATA_DIR)
    return DATA_DIR
