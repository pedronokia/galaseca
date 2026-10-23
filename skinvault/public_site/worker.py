"""Worker do site público -- o ÚNICO processo que fala com a Steam.

Roda em loop, separado do servidor web: escaneia (respeitando o mesmo
`RATE_LIMIT_DELAY_S`/disjuntor de sempre), grava em `scan_store.json`/
`rankings.json`, dorme, repete. `server.py` só LÊ esses arquivos --
nenhum visitante do site dispara uma chamada à Steam (ver AGENTS.md e o
plano desta fase: 1000 visitantes não multiplicam o tráfego porque não
existe "scraping por visitante").

Uso: `python -m skinvault.public_site.worker` (num processo "worker"
separado do "web" no provedor de hospedagem -- Fase 3).
"""
from __future__ import annotations

import os
import sys
import time

from skinvault import ranking, scan_engine, scan_store, scan_targets

_INTERVALO_HORAS_DEFAULT = 6.0
_TOP_RANKING = 20

# Adesivos somam ~9700 itens entre as 4 categorias (torneio/autógrafo/
# comunidade/evento) -- um ciclo completo incluindo eles levaria ~22h por
# forca do RATE_LIMIT_DELAY_S (2 req/item x 4s x ~9900 itens). Sem eles, o
# ciclo cobre ~170 itens (armas/caixas/cápsulas) em ~23min, o que cabe num
# intervalo de poucas horas. Adesivos podem entrar numa varredura própria,
# mais espaçada, se um dia fizer sentido pro produto.
_CATEGORIAS_PESADAS = (
    "Adesivos de torneio", "Adesivos de autógrafo",
    "Adesivos da comunidade", "Adesivos de evento",
)


def categorias_padrao() -> "dict[str, list[str]]":
    """`scan_targets.SCAN_BY_CATEGORY` sem as categorias de adesivo."""
    return {k: v for k, v in scan_targets.SCAN_BY_CATEGORY.items()
            if k not in _CATEGORIAS_PESADAS}


def run_once(categories: "dict[str, list[str]] | None" = None) -> list[dict]:
    """Um ciclo: escaneia, grava scan_store + ranking. Devolve os resultados."""
    if categories is None:
        categories = categorias_padrao()
    inicio = time.time()
    resultados = scan_engine.run_full_scan(
        categories, on_progress=lambda msg: print(msg, file=sys.stderr))
    if resultados:
        scan_store.save_last_scan("Todas as categorias", resultados)
        ranking.save_snapshot(resultados[:_TOP_RANKING])
    duracao_min = (time.time() - inicio) / 60
    print(f"Ciclo concluído: {len(resultados)} itens em {duracao_min:.1f}min",
          file=sys.stderr)
    return resultados


def main(intervalo_horas: "float | None" = None) -> None:
    """`intervalo_horas=None` lê `SKINVAULT_WORKER_INTERVAL_HORAS` (env),
    com fallback pro default -- pra ajustar a cadência em produção sem
    mudar código."""
    if intervalo_horas is None:
        intervalo_horas = float(
            os.environ.get("SKINVAULT_WORKER_INTERVAL_HORAS",
                           _INTERVALO_HORAS_DEFAULT))
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"WARNING: ciclo do worker falhou: {e}", file=sys.stderr)
        time.sleep(intervalo_horas * 3600)


if __name__ == "__main__":
    main()
