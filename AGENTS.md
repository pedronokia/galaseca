# SkinVault — Notas para agentes de IA

Lido por OpenCode, Claude Code e similares. Resumo do que vale saber
antes de mexer.

## Stack

- Python **3.9** (compatibilidade obrigatória)
- PyQt6 (sem WebEngine — removido em commit anterior por crash do
  Qt6Core 6.10.2)
- pytest (`python -m pytest -q`)
- Sem dependências de rede nos testes (tudo mockado via monkeypatch)

## Regras do projeto

- **Steam-only.** Multi-marketplace (Buff/CSFloat/Skinport) está fora
  de escopo até reavaliação pós-uso real.
- **Dados factuais, nunca previsão.** Os sinais descrevem o passado;
  o usuário decide.
- **Login opt-in.** F1–F9 funcionam sem login (dados públicos); F10
  adiciona sync da conta Steam via cookies.
- **Tudo em `gui.py`** a menos que seja lógica pura. Lógica de
  análise vai em `signals.py`, `cases.py`, `alerts.py`, `ranking.py`.
- **Preferir QPainter custom widgets** a bibliotecas de charting
  (Matplotlib etc.).
- **Dark theme do Athenas** — quando o usuário cita inspiração de UI
  (Faceit, etc.), interpretar como **estrutura informacional /
  linguagem**, não cores/tema. Cores ficam.

## Arquitetura

```
skinvault/
├── steam_api.py    # priceoverview + SSR page data (público)
├── steam_session.py
├── steam_login_dialog.py
├── sync.py         # orquestrador F10
├── signals.py      # tendência, anomaly, multi_trend, enhanced_score
├── cases.py        # ~50 cases + ~100 skins mapeadas
├── alerts.py       # engine de regras (price_below, drop_pct, etc.)
├── ranking.py      # snapshots Top 20 com ΔPos
├── prices.py       # PriceCache TTL + persistência
├── portfolio.py    # fee-aware (15% Steam fee)
├── trades.py       # CRUD + stats
├── trade_matcher.py # FIFO BUY↔SELL (F12)
├── watchlist.py
├── settings.py
├── backup.py       # restore com whitelist contra Zip Slip
├── _paths.py       # DATA_DIR centralizado
├── gui.py          # MainWindow + dialogs grandes
└── ui/             # screens individuais (Athenas-style)
    ├── theme.py    # paleta + tipografia + helpers de stylesheet
    ├── components.py # Sidebar, Breadcrumb, Footer, Card, StatCard, SegmentedControl, Avatar
    ├── widgets.py  # MiniSparkline, DepthChart, MonthBarChart, ValueChart
    ├── screen_router.py
    ├── login_gate.py
    ├── account_screen.py
    ├── history_screen.py
    ├── scanner_screen.py
    ├── market_screen.py
    ├── trades_screen.py
    ├── simulador_screen.py
    └── watchlist_screen.py
```

## Padrão Athenas (UI)

Estabelecido na F11. Toda nova tela deve seguir:

- **Sidebar lateral esquerda** via `Sidebar` em `QDockWidget` (já
  feita).
- **Breadcrumb 40px no topo** (`Breadcrumb` em `components.py`) — UI
  router seta o path via `ScreenRouter.navigate`.
- **Cabeçalho explicativo** — não só "Scanner", mas "Scanner de
  Oportunidades — Análise multi-fator". Subtítulo verboso quando faz
  sentido.
- **Footer** com status/contexto (`Footer` em `components.py`).
- **Linguagem verbosa-explicativa** nos labels: "Mudança de posição
  vs scan anterior" em vez de "ΔPos".
- **Botões com verbo+objeto**: "Escanear itens selecionados", não
  "Escanear".
- **Tooltips extensos** explicando significado + como interpretar.

## CTA hierarchy (estilo Faceit, F11+)

**Um botão primário por tela.** Auxiliares ficam ghost ou secondary.
Exemplos consolidados:

- Account: `btn_steam` "Sincronizar com Steam" é o único destaque.
- Market: `btn_primary` "Consultar item"; auxiliares ghost.
- Trades: `btn_primary` "Adicionar trade"; overflow menu "⋯" pro
  resto.
- Scanner: `btn_primary` "Escanear"; "Ranking Top 20" é `btn_secondary`.
- History: leitura/navegação → todos os botões do toolbar são
  `btn_ghost`; o `SegmentedControl` é o protagonista.
- Simulador: `btn_primary` "Simular"; "Limpar" ghost.

## Gotchas — leia antes de mudar coisa relacionada

### 1. Convenção de porcentagem é **inconsistente** entre módulos

Antes de multiplicar `*_pct` por 100 ou formatar como `%`, **abra a
função fonte** e confirme:

| Função | Retorno |
|---|---|
| `portfolio.position_pnl` → `pnl_pct` | **fração 0–1** (multiplique por 100) |
| `portfolio.evaluate_portfolio` → `totals.pnl_pct` | **fração 0–1** |
| `portfolio.simulate_trade` → `roi_pct` | **0–100** (não multiplique) |
| `trades.record_trade` → `pnl_pct` | **0–100** |
| `trades.trade_stats` → `win_rate` | **0–100** |
| `trade_matcher.summarize` → `win_rate` | **fração 0–1** |

Já causou bugs em Trades, Simulador e foi quase causado de novo em
outras telas nesta sessão. Tem testes de regressão mas a convenção
não foi unificada.

### 2. `time.mktime` é permissivo

Aceita "31 Apr" como 1 Mai, "29 Feb" fora de bissexto como 1 Mar.
Use `datetime.datetime(...).timestamp()` quando precisar de validação
estrita (ver `trade_matcher.parse_steam_date`).

### 3. Steam removeu `item_nameid` do SSR

O endpoint `itemordershistogram` (orderbook XHR) **ainda funciona**,
mas o `item_nameid` necessário não está mais publicamente acessível
na listing page (nem em `Market_LoadOrderSpread(...)`, nem em
`/render`, nem no body raw). A solução adotada em `_find_query` é
**loose_match**: aceita orderbook de outro wear do mesmo skin via
`_skin_root_name`. Resultado marca `order_book_approx=True`; a UI
sinaliza visualmente.

Se algum dia descobrir o `item_nameid` pelo body, dá pra ir direto ao
endpoint — orderbook seria preciso.

### 4. Steam omite ano para datas do ano corrente

"5 Jan" sem ano (ano corrente) vs "5 Jan, 2024" (ano antigo). O mesmo
evento gera strings diferentes em syncs feitos em anos diferentes.
`sync.market_event_key` normaliza via `parse_steam_date` → ISO antes
de hashear.

### 5. `_find_query` faz substring match

`item_name in cached_name` — não match exato. "AK-47 | Redline" pega
"AK-47 | Redline (Field-Tested)" também. Em geral OK, mas cuidado
com nomes que são prefixos uns dos outros.

### 6. `restore_backup` faz whitelist

Aceita só entries em `_DATA_FILES`. Se for adicionar arquivo novo a
`data/`, lembra de incluir aqui também — caso contrário não é
restaurado.

### 7. Workers em threads daemon

Scanner usa `threading.Thread(target=_worker, daemon=True)`. **Exceções
propagam silenciosamente** — daí o try/except no início do `_scan_item`.
Não confie no traceback aparecer em algum lugar. Quando depurar
scan, registre via `print` ou bridge signal.

### 8. PyQt6 `QShortcut`

Padrão no codebase é
`QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(handler)`.
**Não** use kwarg `activated=...` no construtor — não funciona em
todas as versões.

## Persistência (arquivos em `data/`)

- `prices.json`, `portfolio.json`, `history.json`, `item_history.json`
- `volume_history.json`, `supply_history.json`
- `watchlist.json`, `trades.json`, `steamids.json`, `settings.json`
- `alerts_log.json`, `rankings.json`
- `steam_session.json` (cookies — não commitar; coberto por
  `.gitignore`)
- `steam_market_events.json`, `active_listings.json`, `trade_history.json`

Backup cobre todos. `backup._DATA_FILES` é a lista canônica.

## Como rodar

```bash
# GUI (Windows relança em pythonw, exit code 0 esperado)
python -m skinvault --ui

# CLI
python -m skinvault --portfolio
python -m skinvault --add "<nome>" <custo> [qtd]

# Testes
python -m pytest -q
```

## Veja também

- [HANDOFF.md](HANDOFF.md) — estado da sessão Claude Code de
  2026-06-06, com commits e frentes em aberto.
- [ROADMAP.md](ROADMAP.md) — F1–F12 concluídas; itens fora de escopo
  documentados.
