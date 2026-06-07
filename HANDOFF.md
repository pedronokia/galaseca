# SkinVault — Handoff (2026-06-07)

Documento pra continuar a sessão em outra ferramenta (OpenCode/etc).

## Estado atual

- **1156 testes passando** (`python -m pytest`)
- Python 3.9 compat, PyQt6 GUI, Steam-only
- Backtest infraestrutura completa + score validado em 9996 amostras / 44 itens
- Aggregate correlation Pearson: **+0.1173** (score atual com `rel_ath` universal)
- Modo overlay ativo (jogar enquanto usa)

## Filosofia (NÃO mudar)

- **Nunca prever futuro; apenas descrever dados factualmente** — comentários e labels usam "tendência subiu X%", nunca "vai valorizar"
- Tudo em `gui.py` salvo lógica pura; análise vai em `signals.py`/`cases.py`/`alerts.py`/`backtest.py`
- Steam-only por enquanto

## Score: fatores integrados (signals.enhanced_score)

| Fator | Peso | Sinal |
|---|---|---|
| mediana (diff_pct) | ±35 | preço vs mediana histórica |
| spread | ±25 | spread bid/ask do order book |
| book | ±20 | dominância buy vs sell |
| trend | ±15 | direção dos últimos preços |
| supply_demand | ±15 | volume/sell_count |
| multi_period | ±10 | concordância 24h/7d/30d/90d |
| **rel_ath** | ±10 | distância ao all-time high (universal) |
| momentum | ±5 | preço vs SMA recente |
| liquidity | +5 | volume alto |
| case | +5/+3 | caixa descontinuada/rara |

## Descobertas empíricas chave (memória persistida)

Ver `~/.claude/projects/C--SkinVault/memory/`:
- **score-90d-horizon.md** — score é sinal de 60-90d, não curto prazo. Bucket 70-84: +27% / hit 62%. Bucket 85-100: +50% / hit 75%.
- **bucket-85-outliers.md** — bucket de elite é dominado por containers (Chroma 2 +80%, Spectrum +46%, Prisma +38%)
- **clutch-case-falling-knife.md** — anti-padrão que motivou `rel_ath`. Containers em squeeze inicial (centavos) ganham; tardio (dólares) perdem.
- **bucket-0-29-negative-finding.md** — noise heterogêneo, sem fix sistêmico (skins icônicos como Asiimov bagunçam)

## Infraestrutura empírica

**Engine:** `skinvault/backtest.py`
- `simulate_item(name, ph, horizon_days=90, step_days=14)` — gera samples
- `score_from_history(name, ph)` — score atual usado em watchlist/portfolio
- `aggregate_by_bucket(samples)` + `correlation(samples)` + `format_report(...)`

**Cache:** `skinvault/ssr_cache.py`
- `PriceHistoryCache` TTL 24h em `data/ssr_cache.json`
- `cached_price_history(name, cache=...)` — usa cache senão fetch
- CLI suporta `--no-cache` pra force refresh

**CLI:** `python -m skinvault --backtest "<item>"` ou `--from-portfolio` (default 90d/14d)

## UI completa (3 telas com Validar Score + Score column)

| Tela | Botão | Coluna Score | Persistência |
|---|---|---|---|
| Scanner | "Validar Score" | Score + Conf. + filtro | per-scan |
| Watchlist | "Validar Score" | Sim + schedule 30min | `current_score` em watchlist.json |
| Portfolio (AccountScreen) | "Validar Score do Portfolio" | Sim + schedule 30min | `current_score` em portfolio.json |

Tooltip mostra retorno empírico do bucket por tipo (skin vs container).

## Alertas score-based (end-to-end funcional)

- `alerts.evaluate_item(..., current_score=N)` aceita score
- Regra `score_above` no `_RulesDialog` (recomendado: 85 alta convicção, 70 ampla cobertura)
- Watchlist worker chama `evaluate_item` durante "Validar Score"
- Fluxo: `bridge.alert_fired` → `notification_requested` (signal) → router re-emit → MainWindow → `tray_icon.showMessage`
- Respeita `settings.tray_notifications`

## Modo overlay (CS fullscreen)

- Toggle via tray menu "Modo overlay (CS fullscreen)"
- Flags: `WindowStaysOnTopHint` + `WA_ShowWithoutActivating`
- Setting `overlay_mode` em `settings.py` DEFAULTS

## Arquivos chave

```
skinvault/
  signals.py           — sinais factuais + enhanced_score + price_zscore, drawdown, data_quality, relative_to_ath
  backtest.py          — engine de validação + score_from_history
  ssr_cache.py         — cache 24h de price_history
  cases.py             — case_status, is_container
  alerts.py            — engine de regras (5 tipos incl. score_above)
  __main__.py          — CLI com --backtest, --no-cache
  gui.py               — MainWindow, tray, overlay
  ui/
    scanner_screen.py  — Scanner + Validar Score + Conf. filter + scatter
    watchlist_screen.py — Watchlist + Score column + alerts wiring
    account_screen.py  — Portfolio + Score column
    screen_router.py   — sinais routing (notification_requested)
```

## Methodology (que funcionou)

```
1. Observação: bucket X tem comportamento Y
2. Investigação direcionada: comparar com bucket vizinho ou outliers
3. Hipótese mecânica: explicação concreta com critério verificável
4. Experimento: implementar com gate fácil de reverter
5. Validação: backtest agregado COM critério de sucesso pré-acordado
6. Decisão: keep se passa critério, revert se não
7. Documentar: memory file pro próximo ciclo
```

Resultados de 4 experimentos:
- z-score reversion → regrediu, reverted, documented
- drawdown → +0.0017 marginal win, kept
- rel_ath (containers) → +37% relativo, kept
- rel_ath (universal) → +7% adicional, kept

## Pending features

All 7 tasks from F12 concluídas. Nenhuma pendente no momento.

## Comandos úteis

```bash
# Rodar testes
python -m pytest

# Rodar app
python -m skinvault --ui

# Backtest CLI
python -m skinvault --backtest "AK-47 | Redline (Field-Tested)"
python -m skinvault --backtest --from-portfolio
python -m skinvault --backtest "<item>" --no-cache  # force refresh

# Validar mudança no score
# 1. Implementar com gate fácil de reverter (if False and ...)
# 2. Rodar backtest em 21+ itens diversos
# 3. Comparar agg corr vs +0.1173 baseline
# 4. Se passar: remover gate, atualizar _BUCKET_HISTORY_90D + memória
# 5. Se falhar: reverter, documentar negative finding
```

## Números chave pra referência

- **Baseline correlação:** +0.1173 (44 itens / 9996 amostras / rel_ath universal)
- **Bucket 70-84:** +26.99% avg, 62% hit, n=1639
- **Bucket 85-100:** +50.26% avg, 75% hit, n=186
- **Por tipo (70-84):** skin +7.5% / container +32.9%
- **Por tipo (85-100):** skin +21.3% / container +52.2%
- **Cache TTL:** 24h em `data/ssr_cache.json`
- **Horizon padrão:** 90d (CLI + simulate_item)
