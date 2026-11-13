"""Roda lodout.score_backtest sobre um dataset já coletado e imprime
um relatório Sp/Pe por horizonte -- mesmo formato dos comentários de
validação já existentes em signals.py.

Uso:
  python scripts/run_score_backtest.py data/backtest_dataset.json
  python scripts/run_score_backtest.py data/backtest_dataset.json --horizontes 7,90,365
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lodout import score_backtest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dataset", help="JSON gerado por build_score_backtest_dataset.py")
    ap.add_argument("--horizontes", default="7,90,365",
                    help="Dias, separados por vírgula (default: 7,90,365)")
    ap.add_argument("--intervalo-dias", type=float, default=30.0,
                    help="Espaçamento entre amostras dentro de cada série")
    ap.add_argument("--nota-exibida", action="store_true",
                    help="Usa a nota cortada em [0,100] em vez da nota crua "
                         "(default: nota crua, mesmo motivo de signals.raw_score)")
    args = ap.parse_args()

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    horizontes = [float(h) for h in args.horizontes.split(",")]

    print(f"Dataset: {len(dataset)} séries, de {args.dataset}\n")
    for h in horizontes:
        r = score_backtest.avaliar(
            dataset, horizon_days=h, intervalo_dias=args.intervalo_dias,
            usar_raw_score=not args.nota_exibida)
        sp = f"{r['spearman']:.4f}" if r["spearman"] is not None else "n/a"
        pe = f"{r['pearson']:.4f}" if r["pearson"] is not None else "n/a"
        print(f"{h:>5.0f}d  n={r['n']:<6} Sp={sp:>8}  Pe={pe:>8}")


if __name__ == "__main__":
    main()
