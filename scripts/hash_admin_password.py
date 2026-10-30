"""Gera o hash pra `GALASECA_ADMIN_PASSWORD_HASH` (login real do /admin).

O `/admin` trocou o token fixo em URL por um login de verdade (usuário
único, sem "esqueci a senha" -- é literalmente o dono do site). A senha
em si NUNCA fica em disco nem em env var em texto puro -- só o hash
(`werkzeug.security.generate_password_hash`, PBKDF2/scrypt, já vem com
o Flask, zero dependência nova).

Uso:
    python scripts/hash_admin_password.py
    # digita a senha quando pedir, copia o hash impresso pra
    # GALASECA_ADMIN_PASSWORD_HASH no ambiente do `web`.
"""
from __future__ import annotations

import getpass
import sys

from werkzeug.security import generate_password_hash


def main() -> int:
    senha = getpass.getpass("Senha do admin: ")
    if not senha:
        print("Senha vazia -- cancelado.")
        return 1
    confirmacao = getpass.getpass("Confirme a senha: ")
    if senha != confirmacao:
        print("As senhas não bateram -- cancelado.")
        return 1
    print("\nGALASECA_ADMIN_PASSWORD_HASH=" + generate_password_hash(senha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
