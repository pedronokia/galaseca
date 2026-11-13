"""Variáveis de ambiente do projeto.

O prefixo mudou de SKINVAULT_ para GALASECA_ (2026-10-29) e depois para
LODOUT_ (2026-11-13), a cada troca de nome do projeto. Parte da
configuração de produção (senha do admin, webhook do Discord) vive fora
do repositório, no ambiente da VM, então os nomes antigos continuam
aceitos como fallback: renomear lá é opcional.
"""
from __future__ import annotations

import os

_PREFIXOS = ("LODOUT_", "GALASECA_", "SKINVAULT_")


def ambiente(nome: str, padrao: "str | None" = None) -> "str | None":
    """Valor de `LODOUT_<nome>`, ou dos nomes antigos `GALASECA_<nome>` e
    `SKINVAULT_<nome>` (nessa ordem), ou `padrao`.

    Lido a cada chamada (não em tempo de import) para que testes e
    reconfigurações valham sem recarregar módulos."""
    for prefixo in _PREFIXOS:
        valor = os.environ.get(prefixo + nome)
        if valor is not None:
            return valor
    return padrao
