"""Metas financeiras — progresso factual de um objetivo, nunca previsão.

Cada meta é um dict {id, label, metric, target, enabled} persistido em
settings.json sob a chave "goals". Como settings.json já está no backup
(backup._DATA_FILES), metas não exigem arquivo de dados novo.

Métricas (o que a barra mede, tudo derivado do `totals` da avaliação):

  market  — valor de mercado da carteira (R$)
  net     — valor líquido, já descontada a taxa Steam (R$)
  pnl     — P&L total (R$)
  items   — total de itens

A barra mostra o progresso em direção ao alvo; o app não afirma se a meta
será atingida — só o quanto já foi.
"""
from __future__ import annotations

from skinvault import settings as _settings

#: Métricas disponíveis: chave -> rótulo pt-BR.
GOAL_METRICS = {
    "market": "Valor de mercado",
    "net": "Valor líquido",
    "pnl": "P&L total",
    "items": "Total de itens",
}

_DEFAULT_METRIC = "market"


def metric_label(metric: str) -> str:
    return GOAL_METRICS.get(metric, metric)


def parse_target(raw: str) -> float:
    """Converte o alvo digitado pra float, aceitando pt-BR e US.

    "5000" -> 5000.0; "5.000" -> 5000.0; "R$ 5.000,50" -> 5000.5.
    ValueError se não for número — o dialog usa pra validar a linha.
    """
    s = str(raw).replace("R$", "").strip()
    if not s:
        raise ValueError("alvo vazio")
    if "," in s:
        # pt-BR: "5.000,50" -> remove milhar, vira decimal
        s = s.replace(".", "").replace(",", ".")
        return float(s)
    if "." in s:
        # Sem vírgula o ponto é decimal ("1234.56") OU separador de milhar
        # ("5.000"). Num alvo em BRL, três dígitos após o último ponto = milhar.
        inteiro, _, frac = s.rpartition(".")
        if len(frac) == 3 and inteiro:
            s = s.replace(".", "")
    return float(s)


def current_value(metric: str, totals: dict) -> float:
    """Valor atual da métrica a partir do `totals` da avaliação.

    `pnl` pode vir None (sem custo conhecido): aí o valor é 0.0 — não há
    como medir progresso de lucro onde a carteira não declara custo.
    """
    if metric == "market":
        return float(totals.get("market") or 0.0)
    if metric == "net":
        return float(totals.get("net_if_sold") or 0.0)
    if metric == "pnl":
        return float(totals.get("pnl") or 0.0)
    if metric == "items":
        return float(totals.get("positions") or 0)
    return 0.0


def progress(current: float, target: float) -> dict:
    """Progresso da meta: pct 0–100, done e quanto falta.

    Alvo <= 0 não faz sentido (não há o que atingir) — pct fica 0. A
    percentagem é limitada a 100: a barra não "transborda".
    """
    if not target or target <= 0:
        return {"pct": 0.0, "done": False, "remaining": 0.0}
    pct = min(100.0, max(0.0, current / target * 100.0))
    return {
        "pct": pct,
        "done": current >= target,
        "remaining": max(0.0, target - current),
    }


def _normalize(goal: dict, idx: int) -> dict:
    """Padroniza uma meta: ids determinísticos, alvo float, métrica válida."""
    metric = goal.get("metric") or _DEFAULT_METRIC
    if metric not in GOAL_METRICS:
        metric = _DEFAULT_METRIC
    try:
        target = float(goal.get("target") or 0.0)
    except (TypeError, ValueError):
        target = 0.0
    return {
        "id": str(goal.get("id") or f"g{idx + 1}"),
        "label": str(goal.get("label") or metric_label(metric)).strip(),
        "metric": metric,
        "target": round(target, 2),
        "enabled": bool(goal.get("enabled", True)),
    }


def load_goals() -> list[dict]:
    data = _settings.load_settings()
    goals = data.get("goals")
    if not isinstance(goals, list):
        return []
    return [_normalize(g, i) for i, g in enumerate(goals)]


def save_goals(goals: list[dict]) -> None:
    data = _settings.load_settings()
    data["goals"] = [
        _normalize(g, i) for i, g in enumerate(goals or [])
    ]
    _settings.save_settings(data)


def upsert_goal(label: str, target: float, metric: str = _DEFAULT_METRIC) -> list[dict]:
    """Cria ou atualiza a meta com o mesmo rótulo. Devolve a lista salva."""
    goals = load_goals()
    goals = [g for g in goals if g["label"] != label]
    goals.append({
        "label": label,
        "metric": metric,
        "target": float(target),
        "enabled": True,
    })
    save_goals(goals)
    return load_goals()


def remove_goal(goal_id: str) -> list[dict]:
    goals = [g for g in load_goals() if g["id"] != goal_id]
    save_goals(goals)
    return load_goals()


def goal_rows(totals: dict) -> list[dict]:
    """Metas + valores atuais, prontas pra barra de progresso da UI.

    Cada entrada: {id, label, metric, target, current, pct, done,
    remaining, current_txt, target_txt}. Sem metas, devolve [] — o card
    usa isso pra mostrar o empty state.
    """
    out = []
    for g in load_goals():
        if not g["enabled"]:
            continue
        current = current_value(g["metric"], totals)
        prog = progress(current, g["target"])
        out.append({**g, "current": current, **prog})
    return out
