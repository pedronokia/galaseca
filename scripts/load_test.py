"""Teste de carga leve contra o site público já implantado.

Mede latência (min/mediana/p95/max) e taxa de erro de um punhado de
requisições concorrentes contra UMA rota só-leitura (nunca `/admin`,
`/api/csp-report` ou qualquer coisa que escreva). Não serve pra achar o
limite de ruptura do servidor -- a VM é pequena de propósito (Oracle
Cloud Always Free) e o objetivo aqui é só confirmar que a rota aguenta
alguns usuários simultâneos sem degradar, não estressar até cair.

Uso:
    python scripts/load_test.py https://seudominio.com
    python scripts/load_test.py https://seudominio.com --rota /ranking -n 40 -c 8
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time

import httpx


async def _uma_requisicao(client: httpx.AsyncClient, url: str) -> tuple[int, float]:
    inicio = time.perf_counter()
    try:
        resp = await client.get(url)
        return resp.status_code, time.perf_counter() - inicio
    except httpx.HTTPError:
        return 0, time.perf_counter() - inicio


async def _executar(url: str, n: int, concorrencia: int) -> list[tuple[int, float]]:
    limitador = asyncio.Semaphore(concorrencia)

    async def _com_limite(client: httpx.AsyncClient) -> tuple[int, float]:
        async with limitador:
            return await _uma_requisicao(client, url)

    async with httpx.AsyncClient(timeout=30.0) as client:
        return await asyncio.gather(*(_com_limite(client) for _ in range(n)))


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    idx = min(int(len(ordenados) * p), len(ordenados) - 1)
    return ordenados[idx]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base_url", help="ex: https://seudominio.com")
    parser.add_argument("--rota", default="/", help="caminho a testar (default: /)")
    parser.add_argument("-n", "--requisicoes", type=int, default=20,
                        help="total de requisições (default: 20)")
    parser.add_argument("-c", "--concorrencia", type=int, default=5,
                        help="requisições simultâneas (default: 5)")
    args = parser.parse_args(argv[1:])

    url = args.base_url.rstrip("/") + args.rota
    print(f"Disparando {args.requisicoes} requisições "
          f"({args.concorrencia} simultâneas) em {url} ...")
    resultados = asyncio.run(
        _executar(url, args.requisicoes, args.concorrencia))

    latencias = [t for _, t in resultados]
    status_ok = sum(1 for s, _ in resultados if 200 <= s < 400)
    erros = len(resultados) - status_ok

    print(f"\nOK: {status_ok}/{len(resultados)}  Erros/timeout: {erros}")
    if latencias:
        print(f"Latência -- min: {min(latencias)*1000:.0f}ms  "
              f"mediana: {statistics.median(latencias)*1000:.0f}ms  "
              f"p95: {_percentil(latencias, 0.95)*1000:.0f}ms  "
              f"max: {max(latencias)*1000:.0f}ms")
    if erros:
        codigos = sorted({s for s, _ in resultados if not (200 <= s < 400)})
        print(f"Códigos de erro vistos: {codigos}")
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
