"""Verifica quantos dias faltam pro certificado TLS de um domínio expirar.

O Caddy renova o certificado Let's Encrypt sozinho (ver README), mas
"renova sozinho" não é "nunca falha" -- um domínio que parou de apontar
pro IP certo, ou uma falha persistente de renovação, só apareceria pro
dono quando o navegador de alguém já estivesse mostrando erro. Este
script é a verificação proativa: conecta de verdade na porta 443 e lê
a validade do certificado, sem depender de nenhuma lib nova (só
`ssl`/`socket` da stdlib).

Uso:
    python scripts/check_tls_expiry.py seudominio.com [dias_limite]

Sai com código 1 (e imprime um aviso) se faltarem menos de `dias_limite`
dias (default 14) -- pensado pra virar um passo de CI (ver
.github/workflows/tls-check.yml) ou um cron manual.
"""
from __future__ import annotations

import socket
import ssl
import sys
from datetime import datetime, timezone

_DIAS_LIMITE_DEFAULT = 14
_TIMEOUT = 10.0


def dias_restantes(dominio: str, porta: int = 443) -> float:
    contexto = ssl.create_default_context()
    with socket.create_connection((dominio, porta), timeout=_TIMEOUT) as sock:
        with contexto.wrap_socket(sock, server_hostname=dominio) as ssock:
            cert = ssock.getpeercert()
    expira_em = datetime.strptime(
        cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return (expira_em - datetime.now(timezone.utc)).total_seconds() / 86400


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python scripts/check_tls_expiry.py <dominio> [dias_limite]")
        return 2
    dominio = argv[1]
    limite = float(argv[2]) if len(argv) > 2 else _DIAS_LIMITE_DEFAULT
    try:
        dias = dias_restantes(dominio)
    except (socket.error, ssl.SSLError, ValueError) as e:
        print(f"FALHA verificando {dominio}: {e}")
        return 1
    print(f"{dominio}: certificado expira em {dias:.1f} dias")
    if dias < limite:
        print(f"AVISO: menos de {limite} dias restantes.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
