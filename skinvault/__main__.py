"""SkinVault.

  python -m skinvault                 -> banner + uso
  python -m skinvault <SteamID64>     -> avalia o inventario inteiro (CLI, com cache)
  python -m skinvault --ui            -> abre a janela (PyQt6)

Le' so' dado publico (SteamID + precos do Market). Nunca pede login.
"""
from __future__ import annotations

import sys

from skinvault import __version__, history, prices, steam_api


def _cli_value(steam_id: str) -> None:
    print(f"Lendo inventario publico de {steam_id} ...")

    def progress(i: int, n: int, name: str) -> None:
        end = "\n" if i == n else "\r"
        print(f"  avaliando {i}/{n} ...", end=end, flush=True)

    status, rows, total = prices.value_inventory(steam_id, progress=progress)

    if status == steam_api.INV_PRIVATE:
        print("Inventario nao acessivel (HTTP 400). Pode ser:")
        print("  - PRIVADO (Steam > Editar Perfil > Privacidade > Inventario: Publico), ou")
        print("  - VAZIO (a conta nao tem skins de CS2 marketaveis), ou")
        print("  - rate-limit temporario do Steam (espera ~1 min).")
        print("  Confere abrindo teu inventario no navegador, aba CS2.")
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
        print(f"R$ {row['total']:>8.2f}  {row['qty']:>3}  {row['name']}")
    print()
    print(f"TOTAL ({len(rows)} itens): R$ {total:.2f}")
    history.record_snapshot(total)
    print("(snapshot salvo -- a 2a rodada e' quase instantanea via cache)")


def main() -> None:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

    args = sys.argv[1:]
    if "--ui" in args:
        from skinvault.gui import launch
        raise SystemExit(launch())
    if args:
        _cli_value(args[0])
    else:
        print(f"SkinVault v{__version__}")
        print("  python -m skinvault <SteamID64>   avalia o inventario")
        print("  python -m skinvault --ui          abre a janela")


if __name__ == "__main__":
    main()
