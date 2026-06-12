"""Resync de validacao do market history.

Roda sync_market_history com sessao Steam real e imprime
 estatisticas. Usar apos o fix de listing_id para verificar
 que o total local aproxima 614 e que 07/06 tem ~10 eventos
 de Kilowatt Case.

Requer sessao Steam salva em data/steam_session.json.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skinvault import sync, steam_api
from skinvault.steam_session import load as load_session


def main():
    session = load_session()
    if session is None:
        print("ERRO: nenhuma sessao Steam encontrada.")
        print("Faca login no app (F10) primeiro.")
        return 1

    print("Sincronizando historico do Steam Market…")
    result = sync.sync_market_history(
        session, appid=None, max_pages=20,
    )
    print(f"  Fetchados: {result['fetched']}")
    print(f"  Novos:      {result['new']}")
    print(f"  Migrados:   {result.get('migrated', 0)}")
    print(f"  Total:      {result['total']}")
    print()
    print("Critério de aceite:")
    print(f"  - Total ≈ 614 (diferencas: eventos de outros jogos,")
    print(f"    listagens canceladas)")
    print(f"  - Spot-check 07/06: ~10 eventos Kilowatt Case")
    return 0


if __name__ == "__main__":
    sys.exit(main())
