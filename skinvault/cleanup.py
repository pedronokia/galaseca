"""Limpeza do sistema -- temporarios do Windows que ocupam disco.

Cinco alvos, todos opt-in, todos MEDIDOS antes de apagar (`scan_target`)
pra tela poder mostrar quanto sai antes do usuario confirmar.

Regras que valem pra todo alvo:

* Nada aqui apaga a raiz de um alvo, so' o que esta' dentro dela. Apagar
  `C:\\Windows\\Prefetch` inteiro em vez do conteudo quebraria o Windows.
* Arquivo em uso nao e' erro, e' `skipped`. No Windows o handle aberto
  bloqueia o unlink, e a maior parte do %TEMP% de uma maquina ligada esta'
  em uso por algum processo -- tratar isso como falha faria toda limpeza
  parecer quebrada.
* `_is_protected` barra qualquer caminho que se sobreponha ao DATA_DIR do
  app ou ao `sys._MEIPASS`. O segundo importa: o PyInstaller descompacta o
  .exe DENTRO do %TEMP%, entao "limpar temporarios" apagaria os arquivos do
  proprio processo em execucao.

A lixeira nao tem diretorio: vai pelas APIs `SHQueryRecycleBinW` /
`SHEmptyRecycleBinW` do shell32, que sao as unicas que lidam com o formato
por volume e por SID de `$Recycle.Bin`.
"""
from __future__ import annotations

import ctypes
import logging
import os
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"

# Quantos caminhos com falha guardar por alvo. O resto vira contagem: uma
# limpeza de %TEMP% pode pular milhares de arquivos em uso e nao ha' o que
# fazer com uma lista desse tamanho na UI.
_MAX_ERRORS = 8


# ── alvos ────────────────────────────────────────────────────
TEMP_FILES = "temp_files"
PREFETCH = "prefetch"
RECYCLE_BIN = "recycle_bin"
WINDOWS_UPDATE = "windows_update"
THUMBNAILS = "thumbnails"


@dataclass(frozen=True)
class Target:
    """Descricao estatica de um alvo. Os textos alimentam a tela."""

    key: str
    title: str
    description: str
    dangerous: bool = False
    needs_admin: bool = False
    note: str = ""


TARGETS = (
    Target(
        TEMP_FILES,
        "Limpar Arquivos Temporários",
        "Remover arquivos temporários do sistema e do usuário.",
        note="Arquivos abertos por programas em execução são pulados.",
    ),
    Target(
        PREFETCH,
        "Limpar Arquivos Prefetch",
        "Excluir arquivos da pasta Prefetch do Windows.",
        needs_admin=True,
        note="O Windows recria o Prefetch; os primeiros arranques de cada "
             "programa ficam um pouco mais lentos até lá.",
    ),
    Target(
        RECYCLE_BIN,
        "Esvaziar Lixeira (Perigoso)",
        "Remover permanentemente arquivos da Lixeira.",
        dangerous=True,
        note="Não há como desfazer. Confira a Lixeira antes de marcar.",
    ),
    Target(
        WINDOWS_UPDATE,
        "Limpar Cache do Windows Update",
        "Remover arquivos de instalação baixados do Windows Update.",
        needs_admin=True,
        note="Atualizações já instaladas não são afetadas; as pendentes são "
             "baixadas de novo.",
    ),
    Target(
        THUMBNAILS,
        "Limpar Cache de Miniaturas",
        "Remover imagens em miniatura armazenadas em cache usadas pelo "
        "Explorador de Arquivos.",
        note="O Explorer costuma manter esses arquivos abertos; o que estiver "
             "em uso é pulado.",
    ),
)

TARGETS_BY_KEY = {t.key: t for t in TARGETS}
TARGET_KEYS = tuple(t.key for t in TARGETS)


# ── resultados ───────────────────────────────────────────────
@dataclass
class ScanResult:
    """Medicao previa de um alvo. `available` False = alvo nao existe nesta
    maquina (pasta ausente, ou nao-Windows)."""

    key: str
    files: int = 0
    bytes: int = 0
    available: bool = True


@dataclass
class CleanResult:
    key: str
    removed: int = 0
    freed: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)


# ── resolucao de caminhos ────────────────────────────────────
# Tudo lido do ambiente na HORA da chamada, nao no import: e' o que permite
# aos testes apontarem os alvos pra um tmp_path so' mexendo em env vars.
def _env_dir(name: str) -> "Path | None":
    raw = os.environ.get(name)
    return Path(raw) if raw else None


def _system_root() -> Path:
    return _env_dir("SystemRoot") or _env_dir("windir") or Path(r"C:\Windows")


def _temp_dirs() -> list:
    """%TEMP% do usuario + Temp do sistema, sem repetir."""
    out = []
    seen = set()
    cands = [_env_dir("TEMP"), _env_dir("TMP"), _system_root() / "Temp"]
    if not cands[0] and not cands[1]:
        cands.insert(0, Path(tempfile.gettempdir()))
    for c in cands:
        if c is None:
            continue
        n = _norm(c)
        if n in seen:
            continue
        seen.add(n)
        out.append(c)
    return out


def target_roots(key: str) -> list:
    """Diretorios que o alvo pode tocar. Lista vazia = sem diretorio."""
    if key == TEMP_FILES:
        return _temp_dirs()
    if key == PREFETCH:
        return [_system_root() / "Prefetch"]
    if key == WINDOWS_UPDATE:
        return [_system_root() / "SoftwareDistribution" / "Download"]
    if key == THUMBNAILS:
        local = _env_dir("LOCALAPPDATA")
        if local is None:
            return []
        return [local / "Microsoft" / "Windows" / "Explorer"]
    return []


def _target_entries(key: str) -> list:
    """Itens de primeiro nivel que a limpeza apagaria.

    Prefetch e miniaturas filtram por padrao em vez de levar a pasta
    inteira -- ambas guardam tambem arquivos de indice que nao sao cache
    (`layout.ini`, bancos do Explorer que nao sao thumbcache).
    """
    entries = []
    for root in target_roots(key):
        try:
            if not root.is_dir():
                continue
        except OSError:
            continue
        if key == PREFETCH:
            it = sorted(root.glob("*.pf"))
        elif key == THUMBNAILS:
            it = sorted(root.glob("thumbcache_*.db"))
            it += sorted(root.glob("iconcache_*.db"))
        else:
            try:
                it = sorted(root.iterdir())
            except OSError:
                continue
        entries.extend(p for p in it if not _is_protected(p))
    return entries


# ── protecoes ────────────────────────────────────────────────
def _norm(p) -> Path:
    """Forma canonica pra comparar caminhos no Windows (case-insensitive,
    resolvendo 8.3 e junctions). Cai pro abspath se o FS nao colaborar."""
    try:
        return Path(os.path.normcase(os.path.realpath(str(p))))
    except (OSError, ValueError):
        try:
            return Path(os.path.normcase(os.path.abspath(str(p))))
        except (OSError, ValueError):
            return Path(str(p))


def _protected_paths() -> list:
    out = []
    try:
        from skinvault._paths import DATA_DIR
        out.append(_norm(DATA_DIR))
    except Exception:  # pragma: no cover - import do app nunca deve barrar
        pass
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        out.append(_norm(Path(mei)))
    return out


def _is_protected(p) -> bool:
    """True se `p` se sobrepoe a algo intocavel -- em qualquer direcao.

    Descendente E ascendente contam: apagar a pasta que CONTEM o DATA_DIR
    leva o DATA_DIR junto.
    """
    np = _norm(p)
    if np.parent == np:  # raiz de volume (C:\)
        return True
    for prot in _protected_paths():
        if np == prot or np in prot.parents or prot in np.parents:
            return True
    return False


def is_admin() -> bool:
    """True se o processo esta' elevado. Alvos com `needs_admin` funcionam
    sem isso, mas pulam quase tudo -- a tela avisa antes."""
    if not _IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


# ── lixeira (shell32) ────────────────────────────────────────
_SHERB_NOCONFIRMATION = 0x00000001
_SHERB_NOPROGRESSUI = 0x00000002
_SHERB_NOSOUND = 0x00000004

# SHEmptyRecycleBinW devolve isto quando a lixeira ja' esta' vazia. Nao e'
# falha: o estado final e' exatamente o pedido.
_E_UNEXPECTED = -0x7FFF0001  # 0x8000FFFF como HRESULT com sinal


class _RecycleBinInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


def recycle_bin_query() -> tuple:
    """(itens, bytes) na lixeira de todos os volumes. (0, 0) se indisponivel."""
    if not _IS_WINDOWS:
        return 0, 0
    info = _RecycleBinInfo()
    info.cbSize = ctypes.sizeof(_RecycleBinInfo)
    try:
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    except (AttributeError, OSError) as e:
        log.warning("SHQueryRecycleBinW indisponivel: %s", e)
        return 0, 0
    if hr != 0:
        return 0, 0
    return int(info.i64NumItems), int(info.i64Size)


def recycle_bin_empty() -> bool:
    """Esvazia a lixeira sem UI. True se o estado final e' 'vazia'."""
    if not _IS_WINDOWS:
        return False
    flags = _SHERB_NOCONFIRMATION | _SHERB_NOPROGRESSUI | _SHERB_NOSOUND
    try:
        hr = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
    except (AttributeError, OSError) as e:
        log.warning("SHEmptyRecycleBinW falhou: %s", e)
        return False
    return hr in (0, _E_UNEXPECTED, _E_UNEXPECTED & 0xFFFFFFFF)


# ── medicao ──────────────────────────────────────────────────
def _entry_size(p: Path) -> tuple:
    """(arquivos, bytes) de um arquivo ou de uma arvore inteira."""
    try:
        is_dir = p.is_dir() and not p.is_symlink()
    except OSError:
        return 0, 0
    if not is_dir:
        try:
            return 1, p.stat().st_size
        except OSError:
            return 1, 0
    files = 0
    total = 0
    # followlinks=False (default): junction pra fora do alvo nao entra na conta
    for dirpath, _dirnames, filenames in os.walk(str(p), onerror=None):
        for fn in filenames:
            files += 1
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
            except OSError:
                pass
    return files, total


def scan_target(key: str) -> ScanResult:
    """Mede um alvo sem apagar nada."""
    if key == RECYCLE_BIN:
        items, size = recycle_bin_query()
        return ScanResult(key, items, size, available=_IS_WINDOWS)
    roots = target_roots(key)
    available = any(_safe_is_dir(r) for r in roots)
    files = 0
    total = 0
    for entry in _target_entries(key):
        f, b = _entry_size(entry)
        files += f
        total += b
    return ScanResult(key, files, total, available=available)


def _safe_is_dir(p) -> bool:
    try:
        return Path(p).is_dir()
    except OSError:
        return False


def scan_all(keys=None) -> dict:
    """Mede varios alvos. Falha num alvo nao derruba os outros."""
    out = {}
    for key in (keys if keys is not None else TARGET_KEYS):
        try:
            out[key] = scan_target(key)
        except Exception as e:  # pragma: no cover - rede de seguranca
            log.warning("scan de %s falhou: %s", key, e)
            out[key] = ScanResult(key, available=False)
    return out


# ── remocao ──────────────────────────────────────────────────
def _force_writable(p: Path) -> bool:
    """Tira o read-only. No Windows ele sozinho ja' faz o unlink falhar."""
    try:
        os.chmod(str(p), stat.S_IWRITE)
        return True
    except OSError:
        return False


def _remove_path(p: Path, res: CleanResult) -> None:
    """Apaga arquivo ou arvore, contabilizando o que saiu e o que ficou.

    Recursao propria em vez de `shutil.rmtree`: rmtree aborta a arvore
    inteira no primeiro arquivo em uso, e em %TEMP% sempre ha' um. Aqui
    cada filho e' independente -- um handle aberto custa um `skipped`, nao
    a pasta toda.
    """
    try:
        is_dir = p.is_dir() and not p.is_symlink()
    except OSError:
        res.skipped += 1
        return

    if is_dir:
        try:
            children = list(p.iterdir())
        except OSError:
            res.skipped += 1
            return
        for child in children:
            _remove_path(child, res)
        try:
            p.rmdir()
        except OSError:
            # Sobrou conteudo dentro (algo em uso) -- ja' contabilizado nos
            # filhos; a pasta em si nao vira erro novo.
            pass
        return

    try:
        size = p.stat().st_size
    except OSError:
        size = 0
    try:
        p.unlink()
    except PermissionError:
        if _force_writable(p):
            try:
                p.unlink()
            except OSError as e:
                _record_skip(res, p, e)
                return
        else:
            _record_skip(res, p, PermissionError(p))
            return
    except OSError as e:
        _record_skip(res, p, e)
        return
    res.removed += 1
    res.freed += size


def _record_skip(res: CleanResult, p: Path, exc: BaseException) -> None:
    res.skipped += 1
    if len(res.errors) < _MAX_ERRORS:
        res.errors.append(f"{p}: {exc.__class__.__name__}")


def clean_target(key: str) -> CleanResult:
    """Executa a limpeza de UM alvo. Nunca levanta: falha vira contagem."""
    res = CleanResult(key)
    if key not in TARGETS_BY_KEY:
        raise KeyError(key)

    if key == RECYCLE_BIN:
        items, size = recycle_bin_query()
        if recycle_bin_empty():
            res.removed = items
            res.freed = size
        else:
            res.skipped = items
            res.errors.append("Não foi possível esvaziar a Lixeira.")
        return res

    for entry in _target_entries(key):
        _remove_path(entry, res)
    return res


def clean(keys) -> dict:
    """Limpa varios alvos, na ordem em que aparecem em TARGETS."""
    wanted = [k for k in TARGET_KEYS if k in set(keys)]
    out = {}
    for key in wanted:
        try:
            out[key] = clean_target(key)
        except Exception as e:  # pragma: no cover - rede de seguranca
            log.warning("limpeza de %s falhou: %s", key, e)
            r = CleanResult(key)
            r.errors.append(str(e))
            out[key] = r
    return out


# ── formatacao ───────────────────────────────────────────────
def human_bytes(n) -> str:
    """Tamanho legivel em pt-BR (virgula decimal). 0 vira '0 B'."""
    try:
        v = float(n)
    except (TypeError, ValueError):
        return "—"
    if v < 0:
        v = 0.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(v)} {unit}"
            return f"{v:.1f}".replace(".", ",") + f" {unit}"
        v /= 1024.0
    return f"{v:.1f} TB"  # pragma: no cover - inalcancavel
