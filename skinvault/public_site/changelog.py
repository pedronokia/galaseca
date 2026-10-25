"""Changelog público do site -- mantido manualmente, não gerado do git.

Cada entrada: {data, titulo, itens}. Mais recente primeiro. Existe
porque "Status" (scan_historico) mostra SE o site está saudável, mas não
O QUE mudou -- esta página é sobre produto, não operação.
"""
from __future__ import annotations

ENTRADAS = [
    {
        "data": "2026-10-25",
        "titulo": "Polimentos e infraestrutura técnica",
        "itens": [
            "Copiar nome do item com um clique, agrupar por categoria, "
            "atalho de teclado \"/\" pra buscar",
            "Expandir qualquer linha pra ver o cálculo completo da nota, "
            "não só os 3 motivos principais",
            "Compressão gzip, cache nos arquivos estáticos, "
            "robots.txt/sitemap.xml, página 404 própria",
            "Esta página de changelog e a documentação da API pública",
        ],
    },
    {
        "data": "2026-10-24",
        "titulo": "Redesign visual e correção de um bug real de rate limit",
        "itens": [
            "Visual novo (paleta azul escuro, inspirada na Steam)",
            "Busca por nome, ordenar clicando na coluna, filtros "
            "(categoria/nota/preço), paginação",
            "Ícone de cada item, nome linkado pro Steam Market, "
            "selo pra caixa descontinuada",
            "Página /status com histórico de scans (inclusive os que "
            "falharam) e contador de visitas",
            "Corrigido bug onde o scan martelava a Steam por ~26min "
            "mesmo já bloqueado, sem desistir cedo",
        ],
    },
    {
        "data": "2026-10-23",
        "titulo": "Site público no ar",
        "itens": [
            "Deploy na Oracle Cloud (Always Free), com Docker e HTTPS "
            "automático via Caddy",
            "Login com Steam, portfólio/trades/watchlist/histórico "
            "pessoais, proteção contra abuso",
            "Página de privacidade e exclusão de conta",
        ],
    },
]
