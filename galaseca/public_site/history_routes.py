"""Blueprint do histórico pessoal -- `/conta/historico`.

Só leitura: o ponto é gravado em `account.py:conta()` (toda visita a
`/conta` registra o valor atual, com dedup -- ver `user_history.
record_if_changed`). Esta tela só exibe a série já guardada.
"""
from __future__ import annotations

from flask import Blueprint, render_template, session

from galaseca.public_site import charts, fmt, user_history
from galaseca.public_site.auth import login_required

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
    return render_template(
        "conta_historico.html",
        grafico=charts.line_chart_svg(series),
        pontos=pontos,
    )
