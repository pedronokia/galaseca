"""Engine de alertas para watchlist.

Avalia regras configuradas por item e retorna alertas disparados.
Suporta:
- price_below: preco atual <= target
- price_drop_pct: preco caiu X% vs baseline (ex.: 15)
- volume_spike: volume_anomaly ratio >= X (ex.: 3.0)
- supply_drop: supply_anomaly direction == 'abaixo' com ratio >= X
- score_above: enhanced_score atual >= X (ex.: 85)

Tudo deterministico: dado mesmo input, mesmo output.
Logging em data/alerts_log.json (cap 500 entries).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from skinvault import signals
from skinvault._paths import (
    DATA_DIR, atomic_write_text, load_json_record,
)

_ALERTS_LOG_PATH = DATA_DIR / "alerts_log.json"
_LOG_CAP = 500


def evaluate_item(
    item: dict,
    current_price: float | None,
    volume_history: list[dict] | None = None,
    supply_history: list[dict] | None = None,
    current_score: int | None = None,
) -> list[dict]:
    """Avalia regras de um item da watchlist e retorna alertas disparados.

    Retorna lista de {rule, label, value, severity}.
    severity: 'info' | 'opportunity' | 'warning'.

    current_score: enhanced_score do item agora (0-100). Se None, regra
    score_above e' ignorada.
    """
    alerts: list[dict] = []
    rules = item.get("rules") or {}
    name = item.get("name", "")

    # 1. Preco abaixo do alvo (target legado funciona como price_below;
    # regra vinda do RulesDialog tambem vale — o dialog grava em rules)
    target = item.get("target") or (rules.get("price_below") or None)
    if target and current_price is not None and current_price <= target:
        alerts.append({
            "rule": "price_below",
            "label": f"Preço atingiu alvo ({current_price:.2f} <= {target:.2f})",
            "value": current_price,
            "severity": "opportunity",
        })

    # 2. Queda percentual vs baseline
    drop_pct = rules.get("price_drop_pct")
    baseline = item.get("baseline_price")
    if drop_pct and baseline and current_price is not None and baseline > 0:
        change = ((current_price - baseline) / baseline) * 100
        if change <= -abs(drop_pct):
            alerts.append({
                "rule": "price_drop_pct",
                "label": f"Caiu {change:.1f}% vs baseline ({baseline:.2f})",
                "value": change,
                "severity": "opportunity",
            })

    # 3. Volume spike (anomalia acima)
    vol_factor = rules.get("volume_spike")
    if vol_factor and volume_history:
        anom = signals.volume_anomaly(volume_history, factor=float(vol_factor))
        if anom.get("is_anomaly") and anom.get("direction") == "acima":
            alerts.append({
                "rule": "volume_spike",
                "label": f"Volume {anom['ratio']:.1f}x acima da média (gatilho {vol_factor}x)",
                "value": anom["ratio"],
                "severity": "info",
            })

    # 4. Queda na oferta (anomalia abaixo)
    sup_factor = rules.get("supply_drop")
    if sup_factor and supply_history:
        anom_s = signals.volume_anomaly(supply_history, factor=float(sup_factor))
        if anom_s.get("is_anomaly") and anom_s.get("direction") == "abaixo":
            alerts.append({
                "rule": "supply_drop",
                "label": f"Oferta {anom_s['ratio']:.2f}x da média (queda)",
                "value": anom_s["ratio"],
                "severity": "opportunity",
            })

    # 5. Score acima do threshold (validado empiricamente: 85+ retorna +50%)
    score_thr = rules.get("score_above")
    if score_thr and current_score is not None and current_score >= int(score_thr):
        alerts.append({
            "rule": "score_above",
            "label": f"Score atingiu {current_score} (gatilho >= {int(score_thr)})",
            "value": current_score,
            "severity": "opportunity",
        })

    return alerts


def diff_new_alerts(item: dict, fresh: list[dict]) -> list[dict]:
    """Retorna apenas alertas que ainda nao foram disparados no estado atual.

    Usa item['triggered_rules'] como conjunto de regras ja notificadas.
    Mutates item['triggered_rules'].
    """
    triggered = set(item.get("triggered_rules") or [])
    new_alerts = []
    rules_now = set()
    for a in fresh:
        rules_now.add(a["rule"])
        if a["rule"] not in triggered:
            new_alerts.append(a)
    # Reseta triggers que nao estao mais ativos (auto-rearm)
    item["triggered_rules"] = sorted(rules_now)
    return new_alerts


def record_alert(name: str, alert: dict,
                 path: Path | str = _ALERTS_LOG_PATH) -> None:
    """Persiste um alerta no log. Cap em _LOG_CAP entradas."""
    p = Path(path)
    try:
        data = load_json_record(p, [])
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    data.append({
        "ts": time.time(),
        "name": name,
        "rule": alert.get("rule"),
        "label": alert.get("label"),
        "severity": alert.get("severity"),
        "value": alert.get("value"),
    })
    if len(data) > _LOG_CAP:
        data = data[-_LOG_CAP:]
    try:
        atomic_write_text(p, json.dumps(data, indent=2))
    except OSError as e:
        print(f"WARNING: failed to save alerts log: {e}",
              file=__import__('sys').stderr)


def load_alerts_log(path: Path | str = _ALERTS_LOG_PATH) -> list[dict]:
    """Retorna o log de alertas (mais recente por ultimo)."""
    p = Path(path)
    data = load_json_record(p, [])
    return data if isinstance(data, list) else []


def clear_alerts_log(path: Path | str = _ALERTS_LOG_PATH) -> None:
    """Limpa o log de alertas."""
    try:
        atomic_write_text(path, "[]")
    except OSError as e:
        print(f"WARNING: failed to clear alerts log: {e}",
              file=__import__('sys').stderr)


def format_rules_summary(rules: dict | None) -> str:
    """Texto curto descrevendo as regras ativas (pra coluna do table)."""
    if not rules:
        return ""
    parts = []
    if rules.get("price_below"):
        parts.append(f"abaixo de R$ {rules['price_below']:.0f}")
    if rules.get("price_drop_pct"):
        # price_drop_pct e' ponto percentual 0-100 (AGENTS.md #1)
        parts.append(f"queda {rules['price_drop_pct']:g}%")
    if rules.get("volume_spike"):
        parts.append(f"vol {rules['volume_spike']:g}x")
    if rules.get("supply_drop"):
        parts.append(f"oferta {rules['supply_drop']:g}x")
    if rules.get("score_above"):
        parts.append(f"score >={int(rules['score_above'])}")
    return ", ".join(parts)
