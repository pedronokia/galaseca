"""Blueprint do histórico pessoal -- `/conta/historico`.

Só leitura: o ponto é gravado em `account.py:conta()` (toda visita a
`/conta` registra o valor atual, com dedup -- ver `user_history.
record_if_changed`). Esta tela só exibe a série já guardada.
"""
from __future__ import annotations

from flask import Blueprint, render_template, session

from lodout.public_site import charts, fmt, user_history
from lodout.public_site.auth import login_required

bp = Blueprint("history", __name__)


@bp.route("/conta/historico")
@login_required
def listar():
    steamid = session["steamid"]
    series = user_history.load_history(steamid)
    pontos = [
        {"data": fmt.data_hora_br(p["ts"]), "total_fmt": fmt.brl(p["total"])}
        for p in series
    ]
    pontos.reverse()

    valores = [p["total"] for p in series]
    # Mesmo padrão do gráfico de preço em /item/<name>: tooltip por ponto
    # (data + valor exato) e legenda com o range real, já que a linha
    # sozinha é normalizada entre o mínimo e o máximo da série -- sem
    # isso, uma variação de R$1 e uma de R$1000 desenham a mesma
    # inclinação, e leitor de tela não tem texto associado ao SVG.
    rotulos = [f"{fmt.data_hora_br(p['ts'])} — {fmt.brl(p['total'])}"
               for p in series]
    grafico_tendencia = None
    if len(valores) >= 2:
        if valores[-1] > valores[0]:
            grafico_tendencia = "alta"
        elif valores[-1] < valores[0]:
            grafico_tendencia = "baixa"
    grafico_legenda = (
        f"{fmt.brl(min(valores))} – {fmt.brl(max(valores))} no período"
        if len(valores) >= 2 else None)

    return render_template(
        "conta_historico.html",
        grafico=charts.line_chart_svg(series, area_fill=True, rotulos=rotulos),
        grafico_tendencia=grafico_tendencia,
        grafico_legenda=grafico_legenda,
        pontos=pontos,
    )
