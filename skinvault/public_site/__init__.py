"""Site público do SkinVault -- Fase 1: dashboard de recomendações.

Pacote separado de `skinvault/webapp/` de propósito: o webapp atual é pra
UM usuário local (sem login, sem isolamento por visitante, roda só em
127.0.0.1 dentro de uma janela pywebview). Misturar os dois exporia rotas
de dado pessoal (trades, watchlist, backup/restore) pra qualquer visitante
sem conta nem banco multi-usuário.

`public_site` importa só módulos sem Qt e sem estado pessoal
(`recommendations`, `scan_store`, `ranking`, `scan_engine`) e nunca fala
com a Steam por requisição de visitante -- só o `worker.py` (processo
separado) faz scraping, respeitando o `RATE_LIMIT_DELAY_S` de sempre.
"""
