"""Gráfico de linha em SVG, gerado no servidor sem dependência de charting."""
from __future__ import annotations


def line_chart_svg(series: "list[dict]", width: int = 640, height: int = 160,
                   padding: int = 12, css_class: str = "grafico-historico",
                   area_fill: bool = False) -> str:
    """SVG de linha a partir de uma série [{ts, total}].

    "" se a série tiver menos de 2 pontos -- nada pra traçar uma linha.
    Os números são sempre formatados por este módulo (nunca interpolados
    de texto externo), então o SVG resultante é seguro pra embutir direto
    no template com `|safe`. `css_class` troca o estilo (ex. sparkline
    pequeno inline numa linha de tabela vs. gráfico grande de página).

    `area_fill=True` acrescenta um preenchimento em gradiente (cor atual,
    opaco no topo até transparente embaixo) sob a linha -- achado
    2026-11-03 (revisão de direção visual): uma linha nua sem contexto
    "parece wireframe". Só pro gráfico grande da página do item; os
    sparklines pequenos da tabela continuam sem fill de propósito (ruído
    visual nesse tamanho).
    """
    valores = [p["total"] for p in series]
    if len(valores) < 2:
        return ""
    minimo = min(valores)
    maximo = max(valores)
    span = maximo - minimo or 1.0
    n = len(valores)

    def _x(i: int) -> float:
        return padding + (i / (n - 1)) * (width - 2 * padding)

    def _y(v: float) -> float:
        # SVG: y cresce pra baixo -- inverte pro maior valor ficar em cima.
        return padding + (1 - (v - minimo) / span) * (height - 2 * padding)

    pontos = " ".join(
        f"{_x(i):.1f},{_y(v):.1f}" for i, v in enumerate(valores))

    defs_svg = ""
    area_svg = ""
    if area_fill:
        base = height - padding
        area_pontos = f"{_x(0):.1f},{base:.1f} {pontos} {_x(n - 1):.1f},{base:.1f}"
        grad_id = f"preenchimento-{css_class}"
        defs_svg = (
            f'<defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="currentColor" stop-opacity="0.25"/>'
            f'<stop offset="100%" stop-color="currentColor" stop-opacity="0"/>'
            f'</linearGradient></defs>'
        )
        area_svg = f'<polygon points="{area_pontos}" fill="url(#{grad_id})"/>'

    return (
        f'<svg viewBox="0 0 {width} {height}" class="{css_class}" '
        f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
        f'{defs_svg}{area_svg}'
        f'<polyline points="{pontos}" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )
