"""Gráfico de linha em SVG, gerado no servidor sem dependência de charting."""
from __future__ import annotations


def line_chart_svg(series: "list[dict]", width: int = 640, height: int = 160,
                   padding: int = 12, css_class: str = "grafico-historico") -> str:
    """SVG de linha a partir de uma série [{ts, total}].

    "" se a série tiver menos de 2 pontos -- nada pra traçar uma linha.
    Os números são sempre formatados por este módulo (nunca interpolados
    de texto externo), então o SVG resultante é seguro pra embutir direto
    no template com `|safe`. `css_class` troca o estilo (ex. sparkline
    pequeno inline numa linha de tabela vs. gráfico grande de página).
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
    return (
        f'<svg viewBox="0 0 {width} {height}" class="{css_class}" '
        f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{pontos}" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )
