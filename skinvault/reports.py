"""Exportação de relatórios — CSV/JSON/HTML print-friendly.

Fontes de dados (as mesmas que a UI exibe, sem re-buscar nada):

  - inventário: rows/positions da avaliação (portfolio.evaluate_portfolio)
    + `mercados` opcional ({nome: [{source, net_brl, ...}]}), o que a
    InventoryScreen já resolveu — sem ele a coluna "Melhor fora" fica vazia.
  - histórico do portfólio: série de history.json ({ts, total}).

Os serializadores são PURE (devolvem str/dict) — escrever em disco é
`write_export()`, que adiciona BOM UTF-8 no CSV pro Excel pt-BR abrir sem
corromper acento/™ (AGENTS.md: nunca usar Set-Content pra UTF-8).
"""
from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime
from pathlib import Path

from skinvault._paths import atomic_write_text

#: Rótulo pt-BR dos marketplaces externos — espelho de InventoryTile.
_NOME_MERCADO = {"skinport": "Skinport", "csgotm": "CS.MONEY/TM"}

#: Colunas do CSV de inventário (delimitador ;, pt-BR Excel).
INVENTORY_HEADERS = [
    "Item", "Quantidade", "Preço unit.", "Valor bruto", "Líquido Steam",
    "Melhor fora", "Onde", "Custo", "Lucro/prejuízo", "Origem",
    "Categoria",
]


def brl(v: float | None) -> str:
    """Formata pt-BR sem depender do PyQt (theme.brl importa Qt)."""
    if v is None:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(v: float | None) -> str:
    """Número pt-BR pra CSV ("1234,56"); None vira string vazia."""
    if v is None:
        return ""
    return f"{float(v):.2f}".replace(".", ",")


def _mercado_de(nome: str, mercados: dict) -> "dict | None":
    if not mercados:
        return None
    lista = mercados.get(nome) or []
    return lista[0] if lista else None


def inventory_records(rows: list[dict], positions: list[dict] | None = None,
                      mercados: dict | None = None) -> list[dict]:
    """Linhas avaliadas -> records planos pra CSV/JSON/HTML.

    `mercados`: {nome: [marketplaces ordenados por líquido]} — o shape que a
    InventoryScreen monta. "Melhor fora" usa o net_brl do melhor marketplace
    vezes a quantidade (total do lote, como na tela).
    """
    from skinvault import portfolio

    positions = list(positions or [])
    out = []
    for i, r in enumerate(rows or []):
        pos = positions[i] if i < len(positions) else {}
        origem = ("Steam" if pos.get("source") == "steam_sync" else "Manual")
        tem_custo = portfolio.has_cost_basis(pos)
        custo = pos.get("cost") if tem_custo else None
        melhor = _mercado_de(r.get("name") or "", mercados)
        qty = int(r.get("quantity") or 1)
        out.append({
            "nome": r.get("name") or "",
            "quantidade": qty,
            "preco_unitario": r.get("price"),
            "valor_bruto": r.get("market"),
            "liquido_steam": r.get("net_if_sold"),
            "melhor_fora": (round(melhor["net_brl"] * qty, 2)
                            if melhor else None),
            "onde": (_NOME_MERCADO.get(melhor["source"], melhor["source"])
                     if melhor else None),
            "custo": custo,
            "pnl": r.get("pnl"),
            "origem": origem,
            "categoria": portfolio.classify_item(r.get("name") or ""),
        })
    return out


def _records_to_csv(records: list[dict], headers: list[str],
                    campos: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(headers)
    for rec in records:
        celulas = []
        for c in campos:
            v = rec.get(c)
            if isinstance(v, int):
                celulas.append(str(v))
            elif isinstance(v, float):
                celulas.append(_num(v))
            else:
                celulas.append(v or "")
        w.writerow(celulas)
    return buf.getvalue()


def inventory_csv(rows: list[dict], positions: list[dict] | None = None,
                  mercados: dict | None = None) -> str:
    records = inventory_records(rows, positions, mercados)
    return _records_to_csv(
        records, INVENTORY_HEADERS,
        ["nome", "quantidade", "preco_unitario", "valor_bruto",
         "liquido_steam", "melhor_fora", "onde", "custo", "pnl",
         "origem", "categoria"])


def inventory_json(rows: list[dict], positions: list[dict] | None = None,
                   mercados: dict | None = None) -> str:
    return json.dumps(inventory_records(rows, positions, mercados),
                      ensure_ascii=False, indent=2)


def history_records(series: list[dict]) -> list[dict]:
    """Série {ts, total} -> records {ts, date, total}."""
    out = []
    for p in series or []:
        ts = float(p.get("ts") or 0)
        data = (datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
                if ts else "")
        out.append({"ts": ts, "date": data, "total": p.get("total")})
    return out


def history_csv(series: list[dict]) -> str:
    return _records_to_csv(history_records(series), ["Data", "Total"],
                           ["date", "total"])


def history_json(series: list[dict]) -> str:
    return json.dumps(history_records(series), ensure_ascii=False, indent=2)


def _total(totals: dict, key: str) -> "float | None":
    v = totals.get(key)
    return v if v is not None else None


def _totals_from_rows(rows: list[dict]) -> dict:
    """Totals resumidos derivados das linhas avaliadas.

    Usado quando quem exporta não tem o `totals` da avaliação (ex.:
    InventoryScreen). Só soma o que está na linha — `pnl` entra apenas
    onde existe custo conhecido, com a mesma semântica do evaluate.
    """
    market = sum(r.get("market") or 0 for r in rows)
    net = sum(r.get("net_if_sold") or 0 for r in rows)
    pnl_vals = [r.get("pnl") for r in rows if r.get("pnl") is not None]
    cost_known = sum(r.get("cost_total") or 0 for r in rows
                     if r.get("has_cost"))
    return {
        "market": round(market, 2),
        "net_if_sold": round(net, 2),
        "pnl": round(sum(pnl_vals), 2) if pnl_vals else None,
        "cost_known": round(cost_known, 2),
        "positions": len(rows),
    }


def _svg_sparkline(series: list[dict], width: int = 720,
                   height: int = 120) -> str:
    """Mini gráfico de linha inline (SVG puro, sem lib).

    Print-friendly: tinta única (preto) com um ponto por snapshot do
    histórico. Menos de 2 pontos vira um retângulo vazio — a mesma regra
    do ValueChart (2 pontos = reta que não informa tendência).
    """
    vals = [float(p.get("total") or 0) for p in series]
    if len(vals) < 2 or max(vals) == min(vals):
        return ""
    pad = 4
    w, h = width, height
    x0, x1 = pad, w - pad
    vmax, vmin = max(vals), min(vals)
    span = (vmax - vmin) or 1.0
    pts = []
    n = len(vals)
    for i, v in enumerate(vals):
        x = x0 + i * (x1 - x0) / (n - 1)
        y = h - pad - (v - vmin) / span * (h - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
            f'style="width:100%;height:auto;">'
            f'<polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="#1c1c1c" stroke-width="2"/>'
            f'<circle cx="{pts[0].split(",")[0]}" cy="{pts[0].split(",")[1]}" '
            f'r="3" fill="#1c1c1c"/>'
            f'<circle cx="{pts[-1].split(",")[0]}" cy="{pts[-1].split(",")[1]}" '
            f'r="3" fill="#1c1c1c"/>'
            f'</svg>')


def html_report(rows: list[dict], series: list[dict],
                totals: "dict | None" = None,
                positions: list[dict] | None = None,
                mercados: dict | None = None) -> str:
    """Relatório standalone print-friendly (fundo branco, tinta escura).

    Resumo (bruto/líquido/P&L/itens/investido), tabela do inventário e
    histórico de valor com sparkline SVG. Sem JS, sem assets externos —
    imprime direto. Sem `totals`, o resumo é derivado das linhas.
    """
    records = inventory_records(rows, positions, mercados)
    hist = history_records(series)
    totals = totals if isinstance(totals, dict) and totals else _totals_from_rows(rows)
    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")

    def cel(v, money=True):
        if v is None:
            return '<td class="muted">—</td>'
        return f"<td>{brl(v) if money else str(v)}</td>"

    linhas = []
    for rec in records:
        linhas.append(
            f"<tr><td class='nome'>{html.escape(rec['nome'])}</td>"
            f"<td>{rec['quantidade']}</td>"
            f"{cel(rec['preco_unitario'])}"
            f"{cel(rec['valor_bruto'])}"
            f"{cel(rec['liquido_steam'])}"
            f"{cel(rec['melhor_fora'])}"
            f"<td>{html.escape(rec['onde'] or '—')}</td>"
            f"{cel(rec['custo'])}"
            f"{cel(rec['pnl'])}"
            f"<td>{html.escape(rec['origem'])}</td>"
            f"<td>{html.escape(rec['categoria'])}</td></tr>")
    linhas_tbl = "\n".join(linhas) or (
        '<tr><td colspan="11" class="muted">Sem itens.</td></tr>')

    hist_rows = "\n".join(
        f"<tr><td>{html.escape(p['date'])}</td>{cel(p['total'])}</tr>"
        for p in hist[-60:])  # último ano se houver, pra não estourar a página

    spark = _svg_sparkline(series)
    hist_bloco = ""
    if hist:
        hist_bloco = (
            f"<section><h2>Histórico do valor da carteira</h2>"
            f"<p class='sub'>Série de avaliações — {len(hist)} ponto(s).</p>"
            + (f"<div class='spark'>{spark}</div>" if spark else "")
            + ("<table><thead><tr><th>Data</th><th>Total</th></tr></thead>"
               f"<tbody>{hist_rows}</tbody></table></section>"))

    pnl = _total(totals, "pnl")
    cards = [
        ("Valor bruto", brl(_total(totals, "market"))),
        ("Valor líquido", brl(_total(totals, "net_if_sold"))),
        ("Lucro/prejuízo total", brl(pnl)),
        ("Total investido", brl(_total(totals, "cost_known"))),
        ("Total de itens", str(totals.get("positions", 0))),
    ]
    cards_html = "\n".join(
        f"<div class='card'><div class='k'>{html.escape(k)}</div>"
        f"<div class='v'>{html.escape(v)}</div></div>"
        for k, v in cards)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>SkinVault — Relatório do portfólio</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #1c1c1c;
          background: #fff; margin: 0; padding: 32px 40px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: #555; font-size: 12px; margin: 0 0 16px; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 16px 0 24px; }}
  .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px 16px;
          min-width: 140px; }}
  .card .k {{ font-size: 11px; color: #555; }}
  .card .v {{ font-size: 16px; font-weight: 600; margin-top: 2px; }}
  section {{ margin: 24px 0; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px;
           margin-top: 8px; }}
  th, td {{ border: 1px solid #ddd; padding: 5px 8px; text-align: right; }}
  th {{ background: #f5f5f5; }}
  td.nome, td:first-child, td:last-child {{ text-align: left; }}
  td.nome {{ max-width: 340px; overflow: hidden; text-overflow: ellipsis;
             white-space: nowrap; }}
  .muted {{ color: #999; }}
  .spark {{ margin: 12px 0; }}
  @media print {{ body {{ padding: 8px 0; }}
                 section {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>SkinVault — Relatório do portfólio</h1>
<p class="sub">Gerado em {gerado}. Valores em BRL; o líquido já desconta a
taxa. Steam é saldo — não saca pra conta.</p>
<div class="cards">
{cards_html}
</div>
<section>
<h2>Inventário</h2>
<p class="sub">{len(records)} item(ns).</p>
<table>
<thead><tr><th>Item</th><th>Qtd</th><th>Preço unit.</th><th>Valor bruto</th>
<th>Líquido Steam</th><th>Melhor fora</th><th>Onde</th><th>Custo</th>
<th>Lucro/prejuízo</th><th>Origem</th><th>Categoria</th></tr></thead>
<tbody>
{linhas_tbl}
</tbody>
</table>
</section>
{hist_bloco}
</body>
</html>
"""


def write_export(path: "Path | str", content: str, kind: str = "csv") -> None:
    """Grava arquivo de exportação com escrita atômica.

    CSV ganha BOM UTF-8: sem ele o Excel pt-BR interpreta UTF-8 como
    ANSI e corrompe acento e ™. JSON/HTML vão como estão.
    """
    body = ("\ufeff" + content) if kind == "csv" else content
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_write_text(p, body)
    except OSError as exc:
        raise OSError(f"Falha ao gravar {p}: {exc}") from exc
