"""Changelog público do site -- mantido manualmente, não gerado do git.

Cada entrada: {data, titulo, itens}. Mais recente primeiro. Existe
porque "Status" (scan_historico) mostra SE o site está saudável, mas não
O QUE mudou -- esta página é sobre produto, não operação.
"""
from __future__ import annotations

ENTRADAS = [
    {
        "data": "2026-10-27",
        "titulo": "Tabela mais leve e CTA de login explicado",
        "itens": [
            "Página principal mostra 10 itens por vez em vez de 20 -- "
            "rola menos pra achar o botão \"Ver mais\"",
            "A nota pessoal por item some atrás de um ícone até você "
            "clicar nele, em vez de ocupar espaço em toda linha",
            "O selo de \"mudou desde sua última visita\" agora tem uma "
            "forma diferente do ▲/▼ de preço, pra não confundir os dois",
            "\"Entrar com Steam\" ganhou uma frase explicando o que você "
            "ganha ao logar (portfólio, trades e watchlist)",
            "Mais acessível pra quem usa leitor de tela nos formulários "
            "de conta, trades, watchlist e login do painel interno",
        ],
    },
    {
        "data": "2026-10-26",
        "titulo": "Página de item, login, PWA, e uma correção de verdade no scan",
        "itens": [
            "Página de detalhe por item, comparador lado a lado, "
            "favoritos, buscas salvas, exportar CSV",
            "Site instalável (PWA) e login do painel interno trocado "
            "por senha de verdade, sem token na URL",
            "Corrigido um bug real que travava o scan inteiro num item "
            "sem preço médio disponível",
            "FAQ, exportar seus próprios dados em JSON, e mais de 50 "
            "ajustes de acessibilidade, SEO e segurança",
        ],
    },
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
