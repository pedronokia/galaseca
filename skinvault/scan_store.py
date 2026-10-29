"""Ultimo scan do Scanner, persistido.

Sem isso a tela abria vazia a cada execucao, e o unico jeito de rever o
resultado era escanear de novo -- dezenas de chamadas num endpoint que a
Steam bloqueia por dezenas de minutos. O resultado volta marcado com a
hora: a tela diz "ultimo scan ha' X", nunca finge que o dado e' de agora.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text

_DEFAULT_PATH = DATA_DIR / "scanner_last.json"
_HISTORICO_PATH = DATA_DIR / "scan_historico.json"
_HISTORICO_MAX = 20


def save_last_scan(category: str, results: list,
                   path: Path | str = _DEFAULT_PATH,
                   now: float | None = None) -> None:
    """Grava o scan concluido. Falha de disco nao derruba o scan."""
    data = {"ts": time.time() if now is None else now,
            "category": category or "", "results": list(results or [])}
    try:
        atomic_write_text(path, json.dumps(data, ensure_ascii=False,
                                           default=str))
    except OSError:
        pass


def load_last_scan(path: Path | str = _DEFAULT_PATH) -> "dict | None":
    """{ts, category, results} ou None (ausente, ilegivel ou vazio).

    E' cache: arquivo ruim vira None em silencio, sem quarentena.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return None
    if not all(isinstance(r, dict) and "name" in r and "score" in r
               for r in results):
        return None
    return {"ts": float(data.get("ts") or 0),
            "category": str(data.get("category") or ""),
            "results": results}


def registrar_ciclo(itens: int, duracao_min: float,
                    path: "Path | str | None" = None,
                    now: float | None = None) -> None:
    """Soma um ciclo ao histórico (cap em `_HISTORICO_MAX`, mais novo por
    último). Existe pra página `/status` -- achado real de 2026-10-24: sem
    isso não tinha como distinguir "scan nunca rodou" de "scan rodou e
    falhou várias vezes seguidas" olhando só pro `scanner_last.json`
    (que só guarda o ÚLTIMO SUCESSO, nunca as falhas).

    `path=None` resolvido aqui dentro, não como default de parâmetro, para
    que o chamador possa redirecionar o arquivo em tempo de chamada."""
    p = Path(path) if path is not None else _HISTORICO_PATH
    historico = load_historico_ciclos(p)
    historico.append({
        "ts": time.time() if now is None else now,
        "itens": itens,
        "duracao_min": round(duracao_min, 1),
        "sucesso": itens > 0,
    })
    historico = historico[-_HISTORICO_MAX:]
    try:
        atomic_write_text(p, json.dumps(historico, ensure_ascii=False))
    except OSError:
        pass


def load_historico_ciclos(path: "Path | str | None" = None) -> list[dict]:
    """Lista de ciclos, mais antigo primeiro. [] se ausente/ilegível.

    Descarta entradas sem "ts" (achado 2026-10-26): `worker_alert.
    verificar_e_alertar` faz `historico[0]["ts"]` sem `.get` -- uma
    entrada malformada ali derrubaria o alerta de worker atrasado, que
    existe justamente pra avisar quando algo está errado."""
    p = Path(path) if path is not None else _HISTORICO_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [c for c in data if isinstance(c, dict) and "ts" in c]


def idade_txt(ts: float, now: float | None = None) -> str:
    """"agora há pouco", "há 5 min", "há 2 h", "há 3 dias"."""
    seg = max(0.0, (time.time() if now is None else now) - (ts or 0))
    if seg < 60:
        return "agora há pouco"
    if seg < 3600:
        return f"há {int(seg // 60)} min"
    if seg < 86400:
        return f"há {int(seg // 3600)} h"
    dias = int(seg // 86400)
    return f"há {dias} dia{'s' if dias != 1 else ''}"


def proxima_txt(ts: float, intervalo_horas: float,
                now: float | None = None) -> str:
    """"em ~5 h", "em ~20 min", "a qualquer momento" (atrasado).

    `ts` é o fim do último scan (gravado por `worker.run_once`);
    `intervalo_horas` é o mesmo valor usado pra dormir entre ciclos
    (ver `SKINVAULT_WORKER_INTERVAL_HORAS`). Só uma estimativa visual --
    o worker pode demorar mais se o ciclo anterior ainda estiver rodando.
    """
    agora = time.time() if now is None else now
    falta = max(0.0, (ts or 0) + intervalo_horas * 3600 - agora)
    if falta < 60:
        return "a qualquer momento"
    if falta < 3600:
        return f"em ~{int(falta // 60)} min"
    return f"em ~{int(falta // 3600)} h"
