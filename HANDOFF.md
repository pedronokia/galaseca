# SkinVault — Handoff (2026-06-08)

Documento auto-suficiente para continuar a sessão em outra ferramenta
(OpenCode/etc).

## Estado atual

- **1231 testes passando** (726 unit + 505 UI smoke)
- Python 3.9 compat, PyQt6 GUI, Steam-only
- Catálogo de eventos da Valve ativo
- Scanner com 5 categorias: Caixas (24), Cápsulas (58), Autographs (30), Stickers (37), Skins
- 3 negative findings documentados (vintage v1, vintage v2, pump_risk
  como penalty) — gated, fáceis de revisitar

## Filosofia (NÃO mudar)

- **Nunca prever futuro; apenas descrever dados factualmente** — labels usam
  "tendência subiu X%", nunca "vai valorizar"
- Tudo em `gui.py` salvo lógica pura; análise vai em `signals.py`/
  `cases.py`/`alerts.py`/`backtest.py`/`valve_events.py`
- Steam-only por enquanto
- **Updates da Valve são o maior catalyst E maior risco**
  ([[feedback-valve-updates-influenciam-mercado]]) — pesquisar updates
  recentes antes de recomendar investimento em uma categoria

## Score: fatores integrados (signals.enhanced_score)

| Fator | Peso | Sinal | Status |
|---|---|---|---|
| mediana (diff_pct) | ±35 | preço vs mediana histórica | ✓ |
| spread | ±25 | spread bid/ask | ✓ |
| book | ±20 | dominância buy vs sell | ✓ |
| trend | ±15 | direção dos últimos preços | ✓ |
| supply_demand | ±15 | volume/sell_count | ✓ |
| multi_period | ±10 | concordância 24h/7d/30d/90d | ✓ |
| rel_ath | ±10 | distância ao all-time high (universal) | ✓ |
| momentum | ±5 | preço vs SMA recente | ✓ |
| liquidity | +5 | volume alto | ✓ |
| case | +5/+3 | caixa descontinuada/rara | ✓ |
| **vintage** | +3 | descontinuado >= 8 anos | gated False |
| **pump_risk** | -10 | level=='high' (combinação >= 2 flags) | gated False |

## Bug fixes desta sessão (2026-06-08)

1. **`backtest.simulate_item` / `score_from_history` não passavam
   `case_status` para `enhanced_score`.** Todos os baselines empíricos
   anteriores eram subestimativas (Pearson caixas era reportado
   +0.1164, real +0.1243). Fix aplicado em `backtest.py`.
2. **`cases.is_container("EMS Katowice 2014 Legends")` retornava False.**
   Cápsulas pré-2020 não terminam com " Capsule" — terminam com
   "Legends", "Challengers", "(Holo-Foil)" etc. Fix: lookup direto em
   `_CAPSULES` antes do match de sufixo. Tests adicionados.
3. **CLI `--backtest` sem `--min-confidence` quebrava com
   UnboundLocalError.** Default `0.0` adicionado.

## Descobertas empíricas chave (memória persistida)

Ver `~/.claude/projects/C--SkinVault/memory/`:
- **caixas-amplificam-bucket-alto** — 22 caixas, Pearson real **+0.1243**
  (pós-bug-fix); bucket 85+ a +56.0% / 71% hit (n=312)
- **capsulas-amplificam-mais-que-caixas** — 58/58 cápsulas, 8518 amostras;
  Pearson +0.0383; bucket 70-84 é **sweet spot** (+22% / 64% hit, n=872);
  bucket 85+ a +68.9% / 58% hit (n=48). Catálogo heterogêneo por idade
  dilui Pearson agregado.
- **feedback-valve-updates-influenciam-mercado** — feedback: pesquisar
  updates Valve antes de qualquer recomendação. Catalogados:
  out/2025 trade-up knife (-$2B), dez/2025 rare drops removidos
  (+40-57%), mai/2026 Cologne capsule abolition.
- **score-90d-horizon** — score é sinal de 60-90d
- **bucket-85-outliers** — bucket 85+ dominado por cases descontinuadas
- **clutch-case-falling-knife** — anti-padrão; squeeze tardio em dólares
- **bucket-0-29-negative-finding** — noise heterogêneo

## Negative findings ativos (fáceis de revisitar)

1. **vintage v1 (universal)** — bonus +3 para descontinuado >= 8 anos
   piorou skins (-0.0033 Pearson). Memória:
   `negative-finding-vintage-bonus`. Variantes para revisitar
   documentadas (multiplicativo, gate negativo).
2. **vintage v2 (containers-only)** — Pearson sobe em caixas (+0.0051,
   passa) mas marginal em cápsulas (+0.0016, falha). Bucket 85+ avg cai
   (-4pp caixas, -2pp cápsulas) mas N sobe (+86 caixas) e hit +1pp.
   Trade-off, não piora pura.
3. **vintage v3 (containers-only multiplicativo ×1.05)** — Caixas
   +0.0053/+0.0057 (PASSOU), Cápsulas Spearman +0.0040 (OK) mas Pearson
   +0.0014 (abaixo do critério 0.002). 1/5 universos (precisa >=2).
   Melhor que v2 mas ainda não passa. Código mantido (flag False).
4. **pump_risk como score penalty** — piorou cápsulas (-0.0044), não
   pegou Clutch (rally +30%/14d estrito demais). Função pública
   `signals.pump_risk()` mantida. Memória: `pump-risk-score-vs-ui`.

## Infraestrutura empírica

**Engine:** `skinvault/backtest.py`
- `simulate_item(name, ph, horizon_days=90, step_days=14)` — gera samples
- `score_from_history(name, ph)` — score atual com case_status passado
- `aggregate_by_bucket(samples)` + `correlation(samples)` + `format_report(...)`

**Cache:** `skinvault/ssr_cache.py`
- `PriceHistoryCache` TTL 24h em `data/ssr_cache.json`
- `cached_price_history(name, cache=...)`

**CLI:** `python -m skinvault --backtest "<item>"` ou `--from-portfolio`
(default 90d/14d). Flag `--no-cache` força refresh.

## Módulos novos / atualizados nesta sessão

| Arquivo | O que tem |
|---|---|
| `skinvault/valve_events.py` (novo) | Catálogo de 3 eventos Valve (out/2025, dez/2025, mai/2026) + helpers `events_for_category()` / `latest_regime_change()` |
| `skinvault/cases.py` | `_CAPSULES` (58 cápsulas), `_AUTOGRAPH_CAPSULES` (30, 2021+), `_PREMIUM_STICKERS` (37, Majors 2014-2015), `case_status()` reconhece containers por nome, `is_container()` reconhece todos os 3 dicts, `list_capsules()`, `list_autograph_capsules()`, `list_premium_stickers()` |
| `skinvault/signals.py` | `pump_risk()` pública; flags gated `_VINTAGE_BONUS_ENABLED=False` (v3 multiplicativo ×1.05), `_PUMP_PENALTY_ENABLED=False` |
| `skinvault/backtest.py` | `simulate_item` e `score_from_history` agora passam `case_status` |
| `skinvault/ui/scanner_screen.py` | Categorias "Cápsulas" + "Autographs" + "Stickers" no `_SCAN_BY_CATEGORY`, banner amarelo quando categoria tem evento Valve <180d |
| `tests/test_cases.py` | 37 novos testes de Autograph Capsules + Premium Stickers (57 total) |

## UI completa (3 telas com Validar Score + Score column)

| Tela | Botão | Coluna Score | Persistência |
|---|---|---|---|
| Scanner | "Validar Score" | Score + Conf. + filtro | per-scan |
| Watchlist | "Validar Score" | Sim + schedule 30min | `current_score` em watchlist.json |
| Portfolio (AccountScreen) | "Validar Score do Portfolio" | Sim + schedule 30min | `current_score` em portfolio.json |

Tooltip mostra retorno empírico do bucket por tipo (skin vs container).

## Alertas score-based (end-to-end funcional)

- `alerts.evaluate_item(..., current_score=N)` aceita score
- Regra `score_above` no `_RulesDialog`
- Fluxo: `bridge.alert_fired` → `notification_requested` → router →
  MainWindow → `tray_icon.showMessage`

## Modo overlay (CS fullscreen)

- Toggle via tray menu "Modo overlay (CS fullscreen)"
- Flags: `WindowStaysOnTopHint` + `WA_ShowWithoutActivating`

## Arquivos chave

```
skinvault/
  signals.py           — enhanced_score + pump_risk (novo) + vintage gated
  backtest.py          — case_status agora passado
  ssr_cache.py         — cache 24h de price_history
  cases.py             — _CAPSULES (58), _AUTOGRAPH_CAPSULES (30), _CASES,
                         case_status, is_container
  valve_events.py      — catálogo updates Valve + helpers (NOVO)
  alerts.py            — engine de regras
  __main__.py          — CLI com --backtest, --no-cache
  gui.py               — MainWindow, tray, overlay
  ui/
    scanner_screen.py  — 5 categorias (Caixas/Cápsulas/Autographs/Stickers/Skins)
    watchlist_screen.py
    account_screen.py
    screen_router.py
memory/                — descobertas empíricas (5 novas nesta sessão)
```

## Methodology (validada nesta sessão também)

```
1. Observação: pattern X tem comportamento Y
2. Hipótese mecânica: explicação concreta com critério verificável
3. Implementar com gate fácil de reverter (flag de módulo + experiment block)
4. Backtest agregado em N universos diversos (caixas + cápsulas + skins)
5. Critério de sucesso pré-acordado (ex: Δ Pearson > +0.002 em >= 2 universos)
6. Decidir: keep se passa, revert se não, e DOCUMENTAR ambos
7. Negative findings também viram memória — guiam próxima iteração
```

Resultados de experimentos validados:
- z-score reversion → regrediu, reverted
- drawdown → +0.0017 marginal, kept
- rel_ath (containers) → +37% relativo, kept
- rel_ath (universal) → +7% adicional, kept
- vintage v1 (universal) → reprovado (skins -0.0033)
- vintage v2 (containers-only) → marginal, reprovado por critério estrito
- pump_risk penalty → reprovado (cápsulas -0.0044)

---

## Próximas direções priorizadas

Cada item tem hipótese, arquivos, critério de aceite, custo estimado e
pré-requisitos. Ordenadas por valor/custo.

### 1. Coluna "Risco" no Scanner — visual, sem afetar score

- **Hipótese:** `pump_risk()` é útil como info pro usuário mesmo sem
  ser score penalty. Avisar visualmente quando há sinais combinados de
  pump-and-dump / falling knife.
- **Arquivos:** `skinvault/ui/scanner_screen.py`
- **O quê fazer:**
  1. Adicionar coluna "Risco" (após "Conf.") com chip colorido
     (low=cinza, medium=amarelo, high=vermelho)
  2. Tooltip mostra `pr["reasons"]` joined
  3. Chamar `signals.pump_risk(price_history, volume_history)` em
     `_scan_item` e armazenar em result
  4. Renderizar na tabela
- **Custo:** 30min
- **Pré-requisitos:** nenhum (`pump_risk()` já existe)
- **Critério de aceite:** UI funcional, tooltip informativo, sem
  regressão nos testes
- **Memórias:** `pump-risk-score-vs-ui`

### 2. Vintage v3 — bonus menor ou multiplicativo

- **Hipótese:** v2 reprovou porque +3 movia borderlines demais pro 85+.
  Variantes: (a) bonus +1 ou +2 em vez de +3, (b) multiplicador
  (×1.05) em vez de aditivo, (c) gate negativo (penalizar vintage com
  score < 30 — clutch-style)
- **Arquivos:** `skinvault/signals.py` (ajustar `_VINTAGE_BONUS` e
  bloco gated)
- **Critério de aceite:** Δ Pearson > +0.002 em >= 2 dos 3 universos
  (caixas, cápsulas, skins) E bucket 85+ avg não cai > 2pp em nenhum
- **Custo:** 30min (mudança + backtest)
- **Pré-requisitos:** nenhum
- **Memórias:** `negative-finding-vintage-bonus`

### 3. pump_risk v2 refinado — pode resgatar o filtro

- **Hipótese:** v1 falhou porque "rally +30% em 14d" é estrito demais
  pra falling knife. Variantes:
  - Rally +20% em 30d (mais flexível)
  - `at_ath` sozinho conta como flag dupla (peso 2)
  - Exclusão por `valve_events.latest_regime_change(category) is not None`
    (suspende filtro quando há catalyst Valve recente)
- **Arquivos:** `skinvault/signals.py` (ajustar `pump_risk`)
- **Critério de aceite:** Δ Pearson > +0.002 em >= 2 universos E
  Clutch Case % no bucket 85+ cai pelo menos 50%
- **Custo:** 1h (refinar + backtest + memória)
- **Pré-requisitos:** nenhum
- **Memórias:** `pump-risk-score-vs-ui`,
  `clutch-case-falling-knife`

### 4. Pre-2020 Team Sticker Capsules sem dados — resolver os ~12 names

- **Hipótese:** Os ~12 nomes que retornam SEM DADOS (Cologne 2015/2016,
  Cluj-Napoca 2015, Atlanta 2017, Krakow 2017, Boston/London 2018,
  Katowice/Berlin 2019) podem estar com nome ligeiramente errado.
- **Arquivos:** `skinvault/cases.py` (`_CAPSULES`)
- **O quê fazer:**
  1. Para cada um dos 12, buscar manualmente no Steam Community Market
     o nome exato do market_hash_name
  2. Corrigir em `_CAPSULES` se necessário
  3. Verificar se o SSR retorna dados com o nome corrigido
- **Custo:** 30-45min
- **Pré-requisitos:** nenhum
- **Critério de aceite:** cobertura backtest de cápsulas sobe de 58/58
  para 70/70 (ou o máximo possível)

### 5. Autograph Capsules — backtest agregado (pós-fetch) — DONE (negative finding)

- **Hipótese:** Com 30 Autograph Capsules adicionadas (2021+), a
  cobertura e os sinais do backtest de cápsulas podem se alterar.
- **Resultado: NEGATIVE FINDING.** Spearman combinado caiu de +0.1034
  para +0.0874 (Δ = -0.0160), acima do critério de -0.005. Autograph
  capsules têm sinal mais fraco (Spearman +0.0633 standalone) e
  diluem o ranking de sticker capsules.
- **O quê fazer:** nada — estrutura atual já está correta. Autographs
  são categoria própria no Scanner, não mescladas com sticker capsules
  em análises. Apenas documentar a diluição. 30 autograph capsules
  agora têm dados SSR em cache (1594 samples).

### 6. Stickers premium curados — DONE

- **Hipótese:** mesma tese de escassez se aplica a stickers de Majors
  antigos (Holo/Foil/Gold). Titan Holo Katowice 2014 = $73k, IBP Holo
  = $75k. Mas universo grande e exposto a pump groups (M4A1 Nightmare
  pattern).
- **Feito:**
  1. `_PREMIUM_STICKERS` em `cases.py` com **37 stickers** Holo
  2. `list_premium_stickers()` helper + 20 testes
  3. Categoria "Stickers" no Scanner
  4. Backtest agregado: **PASSOU** todos os 3 critérios
- **Resultados:**
  - Spearman: +0.0710 (Pearson: +0.0478)
  - Cobertura: 97.3% (36/37 — só Virtus.Pro Kato 2015 sem SSR)
  - Bucket 85-100: N=27 (PASSA >=10), AvgRet=+75880.86% (outliers extremos)
  - Bucket 50-69: +29.13% avg, 67.6% hit — sticker é a classe de maior retorno
  - Outliers no 85+: Vox Eminor Katowice 2015 Holo (+2M%), VP DreamHack 2014 Holo (+23k%) — reais (equipes extintas)
  - Memória: `stickers-maior-retorno-empírico`

---

## Comandos úteis

```bash
# Rodar testes
python -m pytest

# Rodar app
python -m skinvault --ui

# Backtest CLI
python -m skinvault --backtest "AK-47 | Redline (Field-Tested)"
python -m skinvault --backtest "Chroma 2 Case"
python -m skinvault --backtest --from-portfolio
python -m skinvault --backtest "<item>" --no-cache

# Backtest agregado de uma categoria (script ad-hoc)
python -c "
from skinvault import cases, ssr_cache, backtest as bt
items = cases.list_capsules()  # ou _SCAN_BY_CATEGORY['Caixas']
cache = ssr_cache.PriceHistoryCache()
samples = []
for n in items:
    ph = cache.get(n) if cache.has(n) else ssr_cache.cached_price_history(n, cache=cache)
    if ph: samples.extend(bt.simulate_item(n, ph, horizon_days=90, step_days=14))
buckets = bt.aggregate_by_bucket(samples)
print(bt.format_report(buckets, correlation_value=bt.correlation(samples),
                       horizon_days=90, total_samples=len(samples)))
"

# Comparar flag ON vs OFF em score
python -c "
from skinvault import signals, ssr_cache, backtest as bt, cases
for flag in (True, False):
    signals._VINTAGE_BONUS_ENABLED = flag   # ou _PUMP_PENALTY_ENABLED
    # ... rodar e comparar
"
```

## Números chave (PÓS bug fix do case_status)

- **Pearson caixas:** +0.1243 (22 itens / 4301 amostras)
- **Pearson cápsulas:** +0.0383 (58 itens / 8518 amostras)
- **Spearman cápsulas:** +0.1034 (58 itens)
- **Pearson skins:** +0.0056 (63 itens / 7899 amostras)
- **Autograph capsules (2021+):** 30 itens / 1594 amostras (cache populado 08/06/2026)
- **Spearman autographs (standalone):** +0.0633
- **Pearson autographs (standalone):** +0.1412
- **Spearman cápsulas + autographs (combinado):** +0.0874 (Δ = -0.0160 vs só cápsulas — dilui)
- **Premium stickers (Majors 2014-2015):** 37 itens catalogados, 36/37 com dados SSR (só Virtus.Pro Kato 2015 sem SSR), 6320 samples
- **Spearman stickers:** +0.0710 (PASSOU — Pearson +0.0478, cobertura 97.3%, bucket 85+ N=27)
- **Bucket 70-84 caixas:** +31.0% / 64% hit (n=1107) — sweet spot
- **Bucket 70-84 cápsulas:** +21.3% / 64% hit (n=822) — sweet spot
- **Bucket 85-100 caixas:** +56.0% / 71% hit (n=312)
- **Bucket 85-100 cápsulas:** +68.9% / 58% hit (n=48)
- **Cache TTL:** 24h em `data/ssr_cache.json`
- **Horizon padrão:** 90d

## Para o próximo Claude/OpenCode

1. **Leia primeiro:** este arquivo + `MEMORY.md` em
   `~/.claude/projects/C--SkinVault/memory/`
2. **Confirme estado:** `python -m pytest` (1231 esperados) e
    `git log --oneline -10`
3. **Autograph Capsules** (2021+) estão em `_AUTOGRAPH_CAPSULES` em `cases.py`,
   30 itens. Pre-2020 autograph capsules excluídas (naming heterogêneo, drivers
   de demanda diferentes). Categoria "Autographs" no Scanner.
4. **Premium Stickers** (Majors 2014-2015) estão em `_PREMIUM_STICKERS` em
   `cases.py`, 37 itens Holo. Categoria "Stickers" no Scanner. Backtest
   **PASSOU** (Spearman +0.0710, Pearson +0.0478, cobertura 97.3%, bucket 85+ N=27).
   Virtus.Pro Katowice 2015 Holo é o único sticker sem SSR data (Steam SSR
   não retorna).
5. **Antes de qualquer experimento de score:** confirme que `backtest`
    passa `case_status` (já corrigido, mas vale verificar no diff dos
    últimos commits)
6. **Antes de adicionar nova categoria:** pesquise updates recentes da
   Valve nessa categoria via WebSearch
   ([[feedback-valve-updates-influenciam-mercado]])
7. **Sempre gate + backtest + memória.** Methodology funcionou — não
   pule passos
8. **Negative findings são tão valiosos quanto positivos** — documente
   sempre
