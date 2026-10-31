"""Snapshots de ranking do scanner.

Cada snapshot grava {ts, items: [{name, score, position}]}.
Permite comparar posicao atual vs anterior (delta).
Cap em 50 snapshots (volume historico controlado).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from galaseca._paths import (
    DATA_DIR, atomic_write_text, load_json_record,
)
from galaseca import signals

_RANKINGS_PATH = DATA_DIR / "rankings.json"
_SNAPSHOT_CAP = 50


def save_snapshot(results: list[dict],
                  path: Path | str = _RANKINGS_PATH) -> dict:
    """Grava snapshot dos resultados de um scan.

    results: lista de {name, score, ...} ordenada por score desc.
    Retorna o snapshot gravado.
    """
    # Desempate pela nota bruta (antes do clamp em 100) -- mesmo
    # motivo de recommendations.buy_candidates: sem isso, itens
    # empatados em 100 (comum: o modelo não tem teto antes do clamp)
    # ficavam em ordem arbitrária no Top 20.
    sorted_r = sorted(results, key=lambda r: (
        -r.get("score", 0), -signals.raw_score(r.get("breakdown"))))
    items = [
        {
            "name": r["name"],
            "score": int(r.get("score", 0)),
            "position": i + 1,
        }
        for i, r in enumerate(sorted_r)
    ]
    snapshot = {"ts": time.time(), "items": items}

    p = Path(path)
    data = load_json_record(p, [])
    if not isinstance(data, list):
        data = []
    data.append(snapshot)
    if len(data) > _SNAPSHOT_CAP:
        data = data[-_SNAPSHOT_CAP:]
    try:
        atomic_write_text(p, json.dumps(data, indent=2))
    except OSError as e:
        print(f"WARNING: failed to save ranking snapshot: {e}",
              file=__import__('sys').stderr)
    return snapshot


def load_snapshots(path: Path | str = _RANKINGS_PATH) -> list[dict]:
    """Retorna todos os snapshots (mais recente por ultimo)."""
    p = Path(path)
    data = load_json_record(p, [])
    return data if isinstance(data, list) else []


def previous_snapshot(path: Path | str = _RANKINGS_PATH) -> dict | None:
    """Retorna o penultimo snapshot (o ultimo e o atual recem-gravado)."""
    snaps = load_snapshots(path)
    if len(snaps) < 2:
        return None
    return snaps[-2]


def latest_before(ts: float, path: Path | str = _RANKINGS_PATH) -> dict | None:
    """Retorna o snapshot mais recente anterior a ts (ex: snapshot de uma semana atras)."""
    snaps = load_snapshots(path)
    candidates = [s for s in snaps if s.get("ts", 0) < ts]
    return candidates[-1] if candidates else None


def position_delta(name: str, current_position: int,
                   previous: dict | None) -> dict:
    """Calcula mudanca de posicao do item entre snapshot anterior e atual.

    Retorna:
    - {delta: int, prev_pos: int, label: str}   - subiu/caiu/igual
    - {delta: 0, prev_pos: None, label: 'NOVO'} - nao estava antes
    - {delta: 0, prev_pos: None, label: ''}     - sem snapshot anterior
    """
    if not previous or not previous.get("items"):
        return {"delta": 0, "prev_pos": None, "label": ""}
    for it in previous["items"]:
        if it.get("name") == name:
            prev = int(it.get("position", 0))
            delta = prev - current_position  # positivo = subiu
            if delta > 0:
                label = f"+{delta}"
            elif delta < 0:
                label = f"{delta}"
            else:
                label = "="
            return {"delta": delta, "prev_pos": prev, "label": label}
    return {"delta": 0, "prev_pos": None, "label": "NOVO"}


def clear_rankings(path: Path | str = _RANKINGS_PATH) -> None:
    """Limpa todos os snapshots."""
    try:
        atomic_write_text(path, "[]")
    except OSError as e:
        print(f"WARNING: failed to clear rankings: {e}",
              file=__import__('sys').stderr)
