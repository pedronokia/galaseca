"""Testes de charts.py (SVG de linha gerado no servidor)."""
from __future__ import annotations

from galaseca.public_site import charts


def test_menos_de_2_pontos_devolve_vazio():
    assert charts.line_chart_svg([]) == ""
    assert charts.line_chart_svg([{"ts": 1, "total": 10.0}]) == ""


def test_dois_pontos_gera_svg():
    svg = charts.line_chart_svg([
        {"ts": 1, "total": 10.0}, {"ts": 2, "total": 20.0},
    ])
    assert svg.startswith("<svg")
    assert "<polyline" in svg
    assert svg.count(",") == 2  # 2 pontos "x,y"


def test_numero_de_pontos_na_polyline(tmp_path=None):
    serie = [{"ts": i, "total": float(i)} for i in range(5)]
    svg = charts.line_chart_svg(serie)
    # extrai o atributo points="..."
    inicio = svg.index('points="') + len('points="')
    fim = svg.index('"', inicio)
    pontos = svg[inicio:fim].split(" ")
    assert len(pontos) == 5


def test_valor_minimo_fica_no_fundo_maximo_no_topo():
    serie = [{"ts": 1, "total": 0.0}, {"ts": 2, "total": 100.0}]
    svg = charts.line_chart_svg(serie, width=100, height=100, padding=10)
    inicio = svg.index('points="') + len('points="')
    fim = svg.index('"', inicio)
    p1, p2 = svg[inicio:fim].split(" ")
    y1 = float(p1.split(",")[1])
    y2 = float(p2.split(",")[1])
    # valor 0 (minimo) -> y perto do fundo (maior); valor 100 (maximo) ->
    # y perto do topo (menor). SVG: y cresce pra baixo.
    assert y1 > y2


def test_serie_constante_nao_quebra():
    """Todos os valores iguais -- span viraria 0, nao pode dividir por 0."""
    serie = [{"ts": i, "total": 50.0} for i in range(3)]
    svg = charts.line_chart_svg(serie)
    assert svg.startswith("<svg")


def test_sem_area_fill_nao_tem_polygon_nem_gradiente():
    svg = charts.line_chart_svg([{"total": 1}, {"total": 2}])
    assert "<polygon" not in svg
    assert "<defs" not in svg


def test_area_fill_acrescenta_polygon_com_gradiente(tmp_path=None):
    svg = charts.line_chart_svg(
        [{"total": 1}, {"total": 2}], area_fill=True)
    assert "<polygon" in svg
    assert "<linearGradient" in svg
    assert 'stop-color="currentColor"' in svg
    # a linha (polyline) continua por cima do preenchimento, não some.
    assert "<polyline" in svg


def test_area_fill_com_menos_de_2_pontos_continua_vazio():
    assert charts.line_chart_svg([], area_fill=True) == ""
    assert charts.line_chart_svg(
        [{"ts": 1, "total": 10.0}], area_fill=True) == ""
