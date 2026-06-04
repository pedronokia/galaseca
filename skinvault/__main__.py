"""Momento magico do SkinVault.

  python -m skinvault                 -> banner + uso
  python -m skinvault <SteamID64>     -> avalia o inventario publico

Le' so' dado publico (SteamID + precos do Market). Nunca pede login.
"""
from __future__ import annotations

import sys
import time

from skinvault import __version__, steam_api

_PRIVATE_HELP = (
    "Inventario PRIVADO (separado da privacidade do perfil!).\n"
    "  Libera em: Steam > Editar Perfil > Privacidade > Inventario: Publico."
)


def value_inventory(steam_id: str, max_items: int = 25, delay: float = 1.5) -> None:
    print(f"Lendo inventario publico de {steam_id} ...")
    status, items = steam_api.fetch_inventory(steam_id)

    if status == steam_api.INV_PRIVATE:
        print(_PRIVATE_HELP)
        return
    if status == steam_api.INV_RATE_LIMITED:
        print("Steam limitou (rate-limit). Espera ~1 min e roda de novo.")
        return
    if status == steam_api.INV_EMPTY:
        print("Inventario publico, mas sem itens de CS2 marketaveis aqui.")
        return
    if status != steam_api.INV_OK or not items:
        print("Nao consegui ler agora (rede/erro). Tenta de novo.")
        return

    print(f"{len(items)} itens marketaveis unicos. Consultando precos "
          f"(throttle p/ poupar o rate-limit do Steam)...")
    subset = items[:max_items]
    rows: list[tuple[float, int, str, float]] = []
    total = 0.0
    valued = 0
    for it in subset:
        price = steam_api.get_market_price(it["name"])
        if price is not None:
            line = price * it["quantity"]
            total += line
            valued += 1
            rows.append((line, it["quantity"], it["name"], price))
        time.sleep(delay)

    rows.sort(reverse=True)
    print()
    print(f"{'VALOR':>11}  {'QTD':>3}  ITEM")
    for line, qty, name, _price in rows[:15]:
        print(f"R$ {line:>8.2f}  {qty:>3}  {name}")
    print()
    print(f"Avaliados {valued}/{len(subset)} itens. Parcial: R$ {total:.2f}")
    if len(items) > max_items:
        print(f"(demo limitada a {max_items} itens -- a v1 avalia o inventario "
              f"inteiro com cache + backoff)")


def main() -> None:
    # Console do Windows (cp1252) quebra com nome de skin que tem '*'/'TM'.
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    args = sys.argv[1:]
    if args:
        value_inventory(args[0])
    else:
        print(f"SkinVault v{__version__} -- esqueleto pronto.")
        print("Uso: python -m skinvault <SteamID64>   (17 digitos)")


if __name__ == "__main__":
    main()
