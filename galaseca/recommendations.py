"""Recomendações -- cruza o último scan com o portfólio.

Compra: melhores notas do último scan (Scanner) que você ainda não tem,
descontando alerta de subida rápida. Venda: posições que você já tem e
que estão perto do maior preço já registrado, ou com o mesmo alerta de
subida rápida.

Não inventa sinal novo: só reusa o que `signals.py`/`cases.py` já
calculam e o que o Scanner/"Validar score" já persistem. Mesma regra do
resto do projeto -- nunca prever futuro, só descrever dados (AGENTS.md).
"""
from __future__ import annotations

from galaseca import signals

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
_EXIT_LEVEL_ORDER = {"baixo": 0, "meio": 1, "alto": 2, "topo": 3}


def buy_candidates(scan_results: list[dict],
                   owned_names: "set[str] | None" = None,
                   max_pump_risk: str = "medium",
                   limit: int = 10) -> list[dict]:
    """Candidatos de compra: melhores notas do último scan.

    scan_results: linhas no formato de `ScannerScreen._scan_item`
    (precisa de `name` e `score`; usa `price`/`verdict`/`case_label`/
    `pump_risk`/`breakdown`/`is_container` quando vierem).

    Descarta o que já está no portfólio (`owned_names`) e o que tem
    alerta de subida rápida acima de `max_pump_risk` ("low" exclui
    qualquer alerta; "high" não filtra nada por risco).

    Cada item sai com `reasons`: até 3 motivos factuais (os fatores que
    SOMARAM pontos no score), extraídos do próprio breakdown -- não é
    texto novo, é o que `enhanced_score` já calculou.
    """
    owned = {n.strip().lower() for n in (owned_names or ())}
    max_n = _RISK_ORDER.get(max_pump_risk, 1)
    out = []
    for r in scan_results:
        name = r.get("name")
        if not name or name.strip().lower() in owned:
            continue
        risco = (r.get("pump_risk") or {}).get("level", "low")
        if _RISK_ORDER.get(risco, 0) > max_n:
            continue
        reasons = [b["label"] for b in (r.get("breakdown") or [])
                   if b.get("delta", 0) > 0][:3]
        out.append({**r, "reasons": reasons})
    # Desempate pela nota bruta (antes do clamp em 100) -- sem isso,
    # itens empatados na nota exibida ficavam em ordem arbitrária.
    out.sort(key=lambda r: (
        -(r.get("score") or 0), -signals.raw_score(r.get("breakdown"))))
    return out[:limit]


def sell_watch(positions: list[dict],
               pump_risk_by_name: "dict[str, dict] | None" = None,
               min_level: str = "alto") -> list[dict]:
    """Posições do portfólio que merecem atenção na venda.

    positions: formato de `portfolio.load_portfolio()` (precisa de
    `name`; usa `quantity`/`exit_ctx`/`current_score`/`score_ts` quando
    vierem -- `exit_ctx` é gravado por "Validar score" em Minha Conta).

    pump_risk_by_name: {name: {level, reasons}}, calculado pelo chamador
    a partir de cache local (sem rede) -- opcional.

    Só entram posições com o contexto de saída no nível mínimo (ou
    acima) OU com alerta de subida rápida médio/alto. As demais não têm
    nada de notável pra mostrar aqui -- continuam visíveis no
    Inventário, só não entram nesta lista.
    """
    from galaseca import cases, signals

    min_n = _EXIT_LEVEL_ORDER.get(min_level, 2)
    pr_map = pump_risk_by_name or {}
    out = []
    for pos in positions:
        name = pos.get("name")
        if not name:
            continue
        ctx = pos.get("exit_ctx")
        formatted = None
        if ctx:
            try:
                formatted = signals.format_exit_context(
                    float(ctx["pct_of_ath"]), float(ctx["ath"]),
                    float(ctx["current"]), cases.is_container(name),
                    bool(ctx.get("at_launch")))
            except (KeyError, TypeError, ValueError):
                formatted = None
        pr = pr_map.get(name, {})
        exit_level_n = _EXIT_LEVEL_ORDER.get(
            (formatted or {}).get("level"), -1)
        risk_n = _RISK_ORDER.get(pr.get("level", "low"), 0)
        if exit_level_n < min_n and risk_n < 1:
            continue
        out.append({
            "name": name,
            "quantity": pos.get("quantity", 1),
            "current_score": pos.get("current_score"),
            "score_ts": pos.get("score_ts"),
            "exit_context": formatted,
            "pump_risk": pr,
        })
    out.sort(key=lambda r: (
        _EXIT_LEVEL_ORDER.get((r["exit_context"] or {}).get("level"), -1),
        _RISK_ORDER.get(r["pump_risk"].get("level", "low"), 0),
    ), reverse=True)
    return out


def missing_validation(positions: list[dict]) -> list[str]:
    """Nomes de posições que nunca passaram por "Validar score".

    Só informa -- não filtra nada em `sell_watch`. Usado pra avisar o
    usuário que o contexto de saída dessas posições ainda não existe.
    """
    return [p["name"] for p in positions
            if p.get("name") and not p.get("exit_ctx")]
