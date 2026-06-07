"""SkinVault.

  python -m skinvault                          banner + uso
  python -m skinvault <SteamID64>              avalia o inventario publico (CLI)
  python -m skinvault --ui                     abre a janela (PyQt6)
  python -m skinvault --portfolio              meu portfolio (lucro REAL pos-taxa)
  python -m skinvault --add "<nome>" <custo> [qtd]   adiciona uma posicao

Le' so' dado publico (SteamID + precos do Market). Nunca pede login.
"""
from __future__ import annotations

import sys

from skinvault import (
    __version__,
    backtest as backtest_mod,
    history,
    portfolio,
    prices,
    ssr_cache,
    steam_api,
)


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cli_value(steam_id: str) -> None:
    print(f"Lendo inventario publico de {steam_id} ...")

    def progress(i: int, n: int, name: str) -> None:
        end = "\n" if i == n else "\r"
        print(f"  avaliando {i}/{n} ...", end=end, flush=True)

    status, rows, total = prices.value_inventory(steam_id, progress=progress)
    if status == steam_api.INV_PRIVATE:
        print("Inventario nao acessivel (400): privado, vazio (sem skins CS2),")
        print("  ou rate-limit. Confere no navegador, aba CS2.")
        return
    if status == steam_api.INV_RATE_LIMITED:
        print("Steam limitou (rate-limit). Espera ~1 min e roda de novo.")
        return
    if status == steam_api.INV_EMPTY:
        print("Inventario publico, mas sem itens de CS2 marketaveis.")
        return
    if status != steam_api.INV_OK or not rows:
        print("Nao consegui ler agora (rede/erro). Tenta de novo.")
        return
    print()
    print(f"{'VALOR':>11}  {'QTD':>3}  ITEM")
    for row in rows[:15]:
        print(f"{_brl(row['total']):>11}  {row['qty']:>3}  {row['name']}")
    print()
    print(f"TOTAL ({len(rows)} itens): {_brl(total)}")
    history.record_snapshot(total)


def _cli_portfolio() -> None:
    positions = portfolio.load_portfolio()
    if not positions:
        print("Portfolio vazio. Adiciona uma posicao com:")
        print('  python -m skinvault --add "AK-47 | Redline (Field-Tested)" 180 1')
        return
    print(f"Avaliando {len(positions)} posicoes (preco ao vivo, com cache)...")
    cache = prices.PriceCache()
    result = portfolio.evaluate_portfolio(
        positions, lambda n: prices.cached_price(n, cache)
    )
    print()
    print(f"{'CUSTO':>10} {'VALE':>10} {'RECEBE':>10} {'LUCRO REAL':>12} "
          f"{'BREAK-EVEN':>11}  ITEM")
    for r in result["rows"]:
        if r.get("pnl") is None:
            print(f"{_brl(r['cost']):>10} {'--':>10} {'--':>10} {'sem preco':>12} "
                  f"{'--':>11}  {r['name']}")
            continue
        tag = "+" if r["pnl"] >= 0 else ""
        print(f"{_brl(r['cost_total']):>10} {_brl(r['market']):>10} "
              f"{_brl(r['net_if_sold']):>10} {tag + _brl(r['pnl']):>12} "
              f"{_brl(r['break_even']):>11}  {r['name']}")
    t = result["totals"]
    print()
    sign = "+" if t["pnl"] >= 0 else ""
    print(f"TOTAIS  custo {_brl(t['cost'])}  |  vale {_brl(t['market'])}  |  "
          f"recebe {_brl(t['net_if_sold'])}  |  LUCRO REAL {sign}{_brl(t['pnl'])} "
          f"({t['pnl_pct']:+.1f}%)")
    print("(LUCRO REAL = o que voce recebe pos-taxa 15% menos o que pagou. "
          "'Vale' e' so' aparencia.)")


def _cli_add(args: list[str]) -> None:
    if len(args) < 2:
        print('Uso: python -m skinvault --add "<nome exato>" <custo> [qtd]')
        return
    name = args[0]
    try:
        cost = float(args[1].replace(",", "."))
    except ValueError:
        print("Custo invalido."); return
    qty = int(args[2]) if len(args) >= 3 else 1
    portfolio.add_position(name, cost, qty)
    print(f"Adicionado: {qty}x {name} @ {_brl(cost)} (break-even "
          f"{_brl(portfolio.break_even_price(cost))})")


def _cli_check(market_hash_name: str) -> None:
    print(f"Consultando preco de: {market_hash_name}")
    overview = steam_api.get_market_overview(market_hash_name)
    if overview is None:
        print("  Nao consegui obter dados do Market (rede ou item inexistente).")
        return
    lowest = overview["lowest"]
    median = overview["median"]
    volume = overview["volume"]
    verdict = steam_api.fair_value_verdict(lowest, median)

    print(f"  Menor listagem: {_brl(lowest) if lowest else 'N/D':>12}")
    print(f"  Mediana:        {_brl(median) if median else 'N/D':>12}")
    print(f"  Volume (24h):   {volume if volume else 'N/D':>12}")
    print(f"  {'-' * 40}")
    print(f"  VEREDITO: {verdict['message']}")


def _cli_backtest(args: list[str]) -> None:
    """Roda backtest do enhanced_score.

    Uso:
      --backtest "<item>"                  um item
      --backtest --from-portfolio          todos os itens do portfolio
      --backtest <...> --horizon 90        horizonte em dias (default 90)
      --backtest <...> --step 14           passo entre simulacoes (default 14)
      --backtest <...> --min-confidence 0.5  filtra amostras com confianca < N (default 0)

    Default 90d porque empiricamente o score e' sinal de medio prazo:
    bucket 70-84 retorna +19% em 90d vs +4.7% em 30d.

    Cache local (data/ssr_cache.json, TTL 24h) acelera reruns. Use
    --no-cache pra forcar refresh.
    """
    horizon = 90
    step = 14
    use_cache = "--no-cache" not in args
    if "--horizon" in args:
        try:
            horizon = int(args[args.index("--horizon") + 1])
        except (IndexError, ValueError):
            print("--horizon precisa de um numero em dias.")
            return
    if "--step" in args:
        try:
            step = int(args[args.index("--step") + 1])
        except (IndexError, ValueError):
            print("--step precisa de um numero em dias.")
            return
    if "--min-confidence" in args:
        try:
            min_confidence = float(args[args.index("--min-confidence") + 1])
            if not (0.0 <= min_confidence <= 1.0):
                print("--min-confidence precisa estar entre 0 e 1.")
                return
        except (IndexError, ValueError):
            print("--min-confidence precisa de um numero (0.0 a 1.0).")
            return

    items: list[str] = []
    if "--from-portfolio" in args:
        positions = portfolio.load_portfolio()
        items = sorted({p["name"] for p in positions})
        if not items:
            print("Portfolio vazio. Use --add primeiro.")
            return
        print(f"Backtest do portfolio: {len(items)} itens unicos.")
    else:
        skip_values = {str(horizon), str(step)}
        if min_confidence > 0:
            skip_values.add(str(min_confidence))
        positional = [a for a in args if not a.startswith("--")
                       and a not in skip_values]
        if not positional:
            print('Uso: python -m skinvault --backtest "<item>" '
                  "[--horizon 90] [--step 14]")
            print("     python -m skinvault --backtest --from-portfolio")
            return
        items = [" ".join(positional)]

    cache = ssr_cache.PriceHistoryCache() if use_cache else None
    all_samples: list[dict] = []
    hits, misses = 0, 0
    for i, name in enumerate(items, start=1):
        if cache and cache.has(name):
            print(f"[{i}/{len(items)}] CACHE HIT: {name}")
            price_history = cache.get(name)
            hits += 1
        else:
            print(f"[{i}/{len(items)}] Buscando: {name}")
            price_history = ssr_cache.cached_price_history(name, cache=cache)
            misses += 1
        if not price_history:
            print("  sem price_history (rede/item invalido). Pulando.")
            continue
        samples = backtest_mod.simulate_item(
            name, price_history,
            horizon_days=horizon, step_days=step,
        )
        if not samples:
            print(f"  historico curto demais. Pulando.")
            continue
        print(f"  {len(samples)} simulacoes geradas.")
        all_samples.extend(samples)

    if cache:
        print(f"\nCache: {hits} HITs, {misses} fetches "
              f"(total cached: {cache.size()})")

    if not all_samples:
        print("\nNenhuma amostra gerada. Sem dados para reportar.")
        return

    if min_confidence > 0:
        before = len(all_samples)
        all_samples = [s for s in all_samples
                        if s.get("confidence", 0) >= min_confidence]
        filtered = before - len(all_samples)
        if filtered:
            print(f"\nFiltro de confianca >= {min_confidence}: "
                  f"{filtered} amostras removidas ({len(all_samples)} restantes).")

    buckets = backtest_mod.aggregate_by_bucket(all_samples)
    corr = backtest_mod.correlation(all_samples)
    print()
    print(backtest_mod.format_report(
        buckets, correlation_value=corr,
        horizon_days=horizon, total_samples=len(all_samples),
    ))


def main() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    args = sys.argv[1:]
    if "--ui" in args:
        if sys.platform == "win32" and sys.executable.endswith("python.exe"):
            import subprocess
            pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            try:
                subprocess.Popen([pythonw, "-m", "skinvault", "--ui"],
                                 shell=False)
                return
            except FileNotFoundError:
                pass
        from skinvault.gui import launch
        raise SystemExit(launch())
    if "--portfolio" in args:
        _cli_portfolio()
    elif "--check" in args:
        _cli_check(" ".join(args[args.index("--check") + 1:]))
    elif "--add" in args:
        _cli_add(args[args.index("--add") + 1:])
    elif "--backtest" in args:
        _cli_backtest(args[args.index("--backtest") + 1:])
    elif args and not args[0].startswith("--"):
        _cli_value(args[0])
    else:
        print(f"SkinVault v{__version__}")
        print("  python -m skinvault <SteamID64>     avalia o inventario")
        print("  python -m skinvault --portfolio     lucro REAL pos-taxa")
        print('  python -m skinvault --add "<nome>" <custo> [qtd]')
        print('  python -m skinvault --check "<nome>" fair-value (anti-ripoff)')
        print('  python -m skinvault --backtest "<nome>" [--horizon 90] [--step 14] [--min-confidence 0.5]')
        print("  python -m skinvault --ui            abre a janela")


if __name__ == "__main__":
    main()
