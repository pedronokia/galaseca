# SkinVault — Handoff (2026-06-09, sessão 3: UI polish)

Documento auto-suficiente para continuar a sessão em outra ferramenta
(OpenCode/etc).

## Estado atual

- **1284 testes passando**
- Python 3.9 compat, PyQt6 GUI, Steam-only
- 5 telas com tabelas redesenhadas em **Win11 dark** (HistoryScreen na
  sessão anterior; Scanner/Watchlist/Account/Trades nesta sessão)
- **4 arquivos não commitados** (alinhamento por coluna):
  - `skinvault/ui/scanner_screen.py` (+35 linhas)
  - `skinvault/ui/watchlist_screen.py` (+28 linhas)
  - `skinvault/ui/account_screen.py` (+31 linhas)
  - `skinvault/ui/trades_screen.py` (+31 linhas)

## Filosofia (NÃO mudar)

- **Nunca prever futuro; apenas descrever dados factualmente**
- Tudo em `gui.py` salvo lógica pura; análise vai em `signals.py`/
  `cases.py`/`alerts.py`/`backtest.py`/`valve_events.py`
- Steam-only por enquanto
- **Updates da Valve são o maior catalyst E maior risco** — pesquisar
  updates recentes antes de recomendar investimento em uma categoria

## Padrão visual Win11 dark (estabelecido nas últimas 2 sessões)

Aplicado a `theme.py` + 5 telas com tabela:

### Em `theme.py` (commit `7cdb13e`)
- `table_style()`: `QTableWidget::item` padding `4px 12px`; header com
  `border-bottom: 1px solid BORDER`, padding `10px 12px`. Visual estilo
  Win11/Fluent.

### Em cada tela com tabela (5 arquivos)
1. **Stretch dinâmico** em coluna `Item`/`Itens` (HistoryScreen detecta
   pelo header; demais usam `COL_NAME` constante)
2. **`ResizeToContents`** em todas as outras colunas
3. **Alinhamento por coluna** no fim de `_populate`:
   - Dinheiro/quantidade/score → `AlignRight | AlignVCenter`
   - Status/categórico/origem → `AlignCenter`
   - Headers acompanham o alinhamento dos cells
4. **Cores side-aware** (HistoryScreen apenas): texto verde/vermelho
   sem background cheio — estilo Future/Bloomberg

### Alinhamento por tela

| Tela | Direita | Centralizado |
|---|---|---|
| HistoryScreen | Valor, Preço, P&L | Tipo, Operação |
| ScannerScreen | Preco, Preco justo, Score | Sinal, Veredito, Spread, Book, Tendencia, S/D, Risco, Conf. |
| WatchlistScreen | Preco alvo, Preco atual | Status, Score, Confiança |
| AccountScreen | Qtd, Preço, Subtotal, Recebido, P&L, Score | Origem |
| TradesScreen | Qtd, Compra, Venda, P&L, ROI | Data, Origem |

---

## Plano para a próxima sessão (OpenCode)

Ordenadas por valor/custo. **A FASE 1 é refactor obrigatório antes de
expandir o pattern** — caso contrário 4 cópias do mesmo bloco vão virar
5+.

### FASE 1 — Refactor do helper de alinhamento (1h, CRÍTICO)

**Por quê:** as 5 telas têm ~30 linhas idênticas de alinhamento por
coluna. Extrair pra `theme.py` antes de propagar mais.

**Onde:** `skinvault/ui/theme.py`

**O quê adicionar:**

```python
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget

def align_table_columns(
    table: QTableWidget,
    right: set[int] | None = None,
    center: set[int] | None = None,
) -> None:
    """Aplica alinhamento por coluna estilo trading-app (Win11 dark).

    - Colunas em `right`: AlignRight | AlignVCenter (dinheiro, números)
    - Colunas em `center`: AlignCenter (status, categóricos)
    - Demais colunas: padrão (esquerda)
    - Headers também alinham pra bater com cells

    Deve ser chamado no fim do _populate(), após inserir todos os rows.
    """
    right = right or set()
    center = center or set()
    for i in range(table.rowCount()):
        for c in range(table.columnCount()):
            cell = table.item(i, c)
            if cell is None:
                continue
            if c in right:
                cell.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter,
                )
            elif c in center:
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    for c in right:
        hi = table.horizontalHeaderItem(c)
        if hi is not None:
            hi.setTextAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
            )
    for c in center:
        hi = table.horizontalHeaderItem(c)
        if hi is not None:
            hi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
```

**Substituir nas 5 telas:**

1. `skinvault/ui/history_screen.py` — bloco no `_populate()` que
   detecta `money_cols` dinamicamente por nome do header. **Manter a
   detecção dinâmica** (HistoryScreen muda headers por segmento) — só
   chamar o helper depois de construir os sets.
2. `skinvault/ui/scanner_screen.py` — fim do `_populate()`,
   `right_cols = {COL_PRECO, COL_JUSTO, COL_SCORE}`,
   `center_cols = {COL_SINAL, COL_VEREDITO, COL_SPREAD, COL_BOOK,
   COL_TREND, COL_SD, COL_RISCO, COL_CONFIDENCE}`.
3. `skinvault/ui/watchlist_screen.py` — fim do `_populate()`,
   `right_cols = {COL_TARGET, COL_PRICE}`,
   `center_cols = {COL_STATUS, COL_SCORE, COL_CONFIDENCE}`.
4. `skinvault/ui/account_screen.py` — fim do `_populate_table()`,
   `right_cols = {COL_QTY, COL_PRICE, COL_SUBTOTAL, COL_RECEIVED,
   COL_PNL, COL_SCORE}`, `center_cols = {COL_ORIGIN}`.
5. `skinvault/ui/trades_screen.py` — fim do `_populate()`,
   `right_cols = {COL_QTY, COL_COST, COL_SELL, COL_PNL, COL_ROI}`,
   `center_cols = {COL_DATE, COL_SOURCE}`.

**Critério de aceite:**
- `python -m pytest` → 1284 testes
- 5 telas continuam visualmente idênticas após refactor (rodar
  `python -m skinvault --ui` e abrir cada tela)
- Cada chamada do helper substitui ~30 linhas → redução de ~125 linhas
  totais

---

### FASE 2 — Auditoria de dialogs (1h)

**Por quê:** o pattern Win11 está nos 5 screens principais, mas
dialogs (popups) podem estar com visual inconsistente.

**Dialogs a auditar:**

| Arquivo | Classe | O que checar |
|---|---|---|
| `history_screen.py` | `SimulateTradeDialog` | bg, padding, button styles |
| `watchlist_screen.py` | `_RulesDialog` | form layout, spacing |
| `scanner_screen.py` | `_ScoreBreakdownDialog` | já tem `BG_ELEVATED` ✓ |
| `scanner_screen.py` | `_BacktestResultDialog` | tabela interna usa `table_style()` ✓ |
| `trades_screen.py` | `_TradeDialog` | form layout, spacing |
| `welcome_dialog.py` | (welcome wizard) | typography vs theme |
| `login_gate.py` | login flow | typography vs theme |

**Checklist por dialog:**
- [ ] `setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")`
- [ ] `setContentsMargins(20, 18, 20, 18)` no root layout
- [ ] `setSpacing(14)` no root layout
- [ ] Botões via `t.btn_primary()` / `t.btn_secondary()` / `t.btn_ghost()`
- [ ] Labels com `font-family: {t.FONT_FAMILY}`
- [ ] Inputs via `t.input_style()`
- [ ] Tamanho mínimo (`setMinimumWidth(420)` ou similar)

**Critério de aceite:** lista escrita de inconsistências (sem
necessariamente corrigir tudo — priorizar pelos visíveis com mais
frequência: `_TradeDialog`, `_RulesDialog`).

---

### FASE 3 — Polish Market & Simulador (30min)

**Por quê:** essas 2 telas **não têm tabelas** (`market_screen.py`,
`simulador_screen.py`) — usam `StatCard`, `DepthChart`,
`MiniSparkline`. Mesmo assim, verificar:

- [ ] Typography consistente (`FS_TITLE`, `FS_BODY`, `FS_MUTED`)
- [ ] Padding/margins consistentes (`24, 20, 24, 20`)
- [ ] Cards com `Card` widget de `components.py`
- [ ] Cores via constantes de `theme.py` (não hardcoded)

**Critério de aceite:** lista de issues; aplicar fixes triviais
(typos, hardcoded colors).

---

### FASE 4 — Verificação visual + commit (15min)

**Comandos:**

```powershell
python -m pytest                          # esperado: 1284 passing
python -m skinvault --ui                  # rodar app
# Visitar cada tela: History, Scanner, Watchlist, Account, Trades,
# Market, Simulador
```

**Commit sugerido (após FASE 1):**

```
refactor: extract align_table_columns helper to theme.py

DRY pass nas 5 telas com tabelas após o Win11 dark redesign.
Move o bloco de alinhamento por coluna (~30 linhas) pra theme.py.

Comportamento idêntico, ~125 linhas a menos no total.
```

---

## Score: fatores integrados (signals.enhanced_score) — referência

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
| **vintage v4** | +2 | descontinuado >= 8 anos, containers-only | **enabled** |
| **pump_risk v3** | -5 | level=='high' (combinação >= 2 flags) | **enabled** |

## Descobertas empíricas chave (memória persistida)

Ver `~/.claude/projects/C--SkinVault/memory/`:
- **caixas-amplificam-bucket-alto** — 22 caixas, Pearson +0.1243;
  bucket 85+ a +56.0% / 71% hit (n=312)
- **capsulas-amplificam-mais-que-caixas** — 58 cápsulas, Pearson +0.0383;
  bucket 70-84 é sweet spot (+22% / 64% hit, n=872)
- **score-90d-horizon** — score é sinal de 60-90d
- **bucket-85-outliers** — bucket 85+ dominado por cases descontinuadas
- **clutch-case-falling-knife** — anti-padrão; squeeze tardio
- **feedback-valve-updates-influenciam-mercado** — pesquisar updates
  Valve antes de qualquer recomendação

## Arquivos chave

```
skinvault/
  signals.py           — enhanced_score + pump_risk + vintage gated
  backtest.py          — case_status passado
  ssr_cache.py         — cache 24h de price_history
  cases.py             — _CAPSULES (58), _AUTOGRAPH_CAPSULES (30),
                         _CASES, case_status, is_container
  valve_events.py      — catálogo updates Valve + helpers
  alerts.py            — engine de regras
  __main__.py          — CLI com --backtest, --no-cache
  gui.py               — MainWindow, tray, overlay
  ui/
    theme.py           — Win11 dark + helpers de stylesheet
    history_screen.py  — segmented control + 7 segmentos
    scanner_screen.py  — 7 categorias + score breakdown
    watchlist_screen.py
    account_screen.py
    trades_screen.py
    market_screen.py   — sem tabela
    simulador_screen.py — sem tabela
    components.py      — Card, StatCard, SegmentedControl,
                         ActivityFeed, RecentMatchesStrip, EmptyState
    widgets.py         — DepthChart, MiniSparkline, MonthBarChart,
                         ValueChart
    screen_router.py
memory/                — descobertas empíricas
```

## Methodology (preservar — funcionou em 2 sessões)

```
1. Observação: pattern X tem comportamento Y
2. Hipótese mecânica: explicação concreta com critério verificável
3. Implementar com gate fácil de reverter
4. Backtest agregado em N universos diversos
5. Critério de sucesso pré-acordado
6. Decidir: keep se passa, revert se não, e DOCUMENTAR ambos
7. Negative findings também viram memória
```

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
```

## Para o próximo Claude/OpenCode

1. **Leia primeiro:** este arquivo + `MEMORY.md` em
   `~/.claude/projects/C--SkinVault/memory/`
2. **Confirme estado:** `python -m pytest` (1284 esperados) e
   `git log --oneline -10`
3. **Antes de qualquer experimento de score:** confirme que
   `backtest.simulate_item` / `score_from_history` passam `case_status`
   pra `enhanced_score` (corrigido em sessão anterior, mas vale
   verificar)
4. **Antes de adicionar nova categoria:** pesquise updates recentes da
   Valve nessa categoria via WebSearch
5. **Sempre gate + backtest + memória.** Methodology funcionou — não
   pule passos
6. **Negative findings são tão valiosos quanto positivos** — documente
   sempre

## Próximas direções de score (suspensas para FASE 1-4 de UI)

Estes itens vão pro próximo ciclo, após terminar o polish UI:

### S1. Pre-2020 capsule names — resolver os ~12 sem dados SSR

- **Arquivos:** `skinvault/cases.py` (`_CAPSULES`)
- **O quê fazer:** buscar nome exato do `market_hash_name` no Steam
  Community Market para Cologne 2015/2016, Cluj-Napoca 2015, Atlanta
  2017, Krakow 2017, Boston/London 2018, Katowice/Berlin 2019
- **Custo:** 30-45min
- **Critério:** cobertura backtest cápsulas sobe de 58/58 para 70/70

### S2. pump_risk v4 refinements

- **Hipótese:** v3 (penalty -5 em 'high') passou critério mas é
  conservador. Variantes a testar:
  - Exclusão por `valve_events.latest_regime_change(category)`
    (suspende filtro quando há catalyst Valve recente <30d)
  - Rally +20% em 30d (em vez de +30% em 14d) — mais sensível
- **Critério:** Δ Spearman > +0.002 em ≥ 2 universos E bucket 85+ avg
  intacto E pega Clutch
- **Custo:** 1h
