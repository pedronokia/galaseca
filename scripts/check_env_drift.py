"""Verifica se as env vars esperadas pelo site público estão definidas
no ambiente atual.

Roda manualmente ou como passo informativo de deploy (SSH na VM) --
NUNCA automaticamente de dentro do app (ler env var de produção já é
coisa do próprio `server.py`; isto é só um script de apoio, pensado pra
rodar contra o ambiente real na hora de investigar um deploy estranho).

Uso:
    python scripts/check_env_drift.py
    # ou, dentro do container:
    docker compose exec web python scripts/check_env_drift.py
"""
from __future__ import annotations

import os
import sys

# (variável, descrição, obrigatória?)
_ESPERADAS: list[tuple[str, str, bool]] = [
    ("SITE_DOMAIN", "domínio público servido pelo Caddy", True),
    ("SKINVAULT_DATA_DIR", "pasta de dados persistida (volume)", True),
    ("SKINVAULT_ADMIN_TOKEN", "token do painel /admin", False),
    ("SKINVAULT_PUBLIC_SITE_SECURE_COOKIES", "cookies Secure (HTTPS)", False),
    ("SKINVAULT_WORKER_INTERVAL_HORAS", "intervalo do worker (default 6h)", False),
    ("SKINVAULT_ADMIN_DISCORD_WEBHOOK", "alerta Discord de worker atrasado", False),
    ("SKINVAULT_WORKER_ALERT_HORAS", "limite de horas pro alerta acima", False),
]


def main() -> int:
    faltando_obrigatorias = []
    for nome, desc, obrigatoria in _ESPERADAS:
        presente = nome in os.environ and os.environ[nome] != ""
        estado = "OK" if presente else "AUSENTE"
        marca = " (obrigatória)" if obrigatoria and not presente else ""
        print(f"{estado:8} {nome:42} {desc}{marca}")
        if obrigatoria and not presente:
            faltando_obrigatorias.append(nome)

    if faltando_obrigatorias:
        print(f"\nFALTAM OBRIGATÓRIAS: {', '.join(faltando_obrigatorias)}")
        return 1
    print("\nTudo que é obrigatório está presente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
