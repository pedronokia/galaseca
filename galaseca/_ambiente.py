"""Variáveis de ambiente do projeto.

O prefixo mudou de SKINVAULT_ para GALASECA_ com a troca de nome
(2026-10-29). Parte da configuração de produção (senha do admin, webhook
do Discord) vive fora do repositório, no ambiente da VM, então o nome
antigo continua aceito como fallback: renomear lá é opcional.
"""
from __future__ import annotations

import os

_PREFIXOS = ("GALASECA_", "SKINVAULT_")


def ambiente(nome: str, padrao: "str | None" = None) -> "str | None":
    """Valor de `GALASECA_<nome>`, ou de `SKINVAULT_<nome>`, ou `padrao`.

    Lido a cada chamada (não em tempo de import) para que testes e
    reconfigurações valham sem recarregar módulos."""
    for prefixo in _PREFIXOS:
        valor = os.environ.get(prefixo + nome)
        if valor is not None:
            return valor
    return padrao
