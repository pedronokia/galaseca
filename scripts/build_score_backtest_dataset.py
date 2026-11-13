"""Monta um dataset de backtest puxando price_history REAL da Steam.

NÃO roda sozinho em nenhum lugar -- faz requisições de rede de verdade,
respeitando o MESMO rate limit do worker ao vivo (`steam_api.
RATE_LIMIT_DELAY_S`, consultado na hora, nunca copiado). Pra N nomes
isso leva perto de N * RATE_LIMIT_DELAY_S segundos -- mas cada página de
listagem também semeia o histórico de até ~10 variantes irmãs (wear/
StatTrak/Normal) na mesma requisição (ver `steam_api.get_market_page_
data`), então N pode ser bem menor que "quantos itens eu quero no
dataset".

Uso:
  python scripts/build_score_backtest_dataset.py --out data/backtest_dataset.json --limit 30

Grava um JSON: [{"name", "price_history", "is_container"}, ...], pronto
pra `lodout.score_backtest.avaliar()` (ver `scripts/run_score_backtest.py`).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lodout import cases, scan_targets, steam_api


def _nomes_alvo(limit: "int | None") -> list[str]:
    vistos: set[str] = set()
    out: list[str] = []
    for fallback in scan_targets.SCAN_BY_CATEGORY.values():
        for nome in fallback:
            if nome not in vistos:
                vistos.add(nome)
                out.append(nome)
    if limit:
        out = out[:limit]
    return out


def montar_dataset(nomes: list[str],
                   on_progress=None) -> list[dict]:
    """Puxa price_history de cada nome (+ variantes irmãs) e monta as
    linhas do dataset. Pausa `steam_api.RATE_LIMIT_DELAY_S` entre
    requisições -- igual ao worker, sem pressa nenhuma pra terminar."""
    coletados: dict[str, list[dict]] = {}
    for i, nome in enumerate(nomes):
        if nome in coletados:
            continue
        if on_progress:
            on_progress(f"[{i + 1}/{len(nomes)}] {nome}")
        try:
            page = steam_api.get_market_page_data(nome)
        except Exception as e:
            print(f"AVISO: falhou {nome}: {e}", file=sys.stderr)
            page = None
        if page:
            if page.get("price_history"):
                coletados[nome] = page["price_history"]
            for nome_variante, serie in (page.get("variants") or {}).items():
                if serie and nome_variante not in coletados:
                    coletados[nome_variante] = serie
        time.sleep(steam_api.RATE_LIMIT_DELAY_S)

    return [
        {
            "name": nome,
            "price_history": serie,
            "is_container": cases.is_container(nome),
        }
        for nome, serie in coletados.items()
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="Caminho do JSON de saída")
    ap.add_argument("--limit", type=int, default=30,
                    help="Quantos nomes-base buscar (variantes vêm de graça)")
    args = ap.parse_args()

    nomes = _nomes_alvo(args.limit)
    print(f"Buscando {len(nomes)} nomes-base (+ variantes irmãs)...")
    dataset = montar_dataset(nomes, on_progress=print)
    Path(args.out).write_text(json.dumps(dataset), encoding="utf-8")
    print(f"OK: {len(dataset)} séries salvas em {args.out}")


if __name__ == "__main__":
    main()
