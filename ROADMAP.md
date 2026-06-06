# SkinVault Roadmap

## Filosofia
- **Login opt-in** — F1-F9 funcionam sem login (dados públicos); F10 adiciona sync da conta Steam via cookies de sessão (opt-in, sob risco do usuário)
- **Dados factuais** — descrevemos, não prevemos
- **Valor real** — após taxa Steam (15%)
- **Steam-only** por enquanto — multi-market (Buff/CSFloat/Skinport) é decisão futura

---

## Mapa: os 13 indicadores → as fases

| # | Indicador | Status | Fase |
|---|---|---|---|
| 1 | Variação multi-período (24h/7d/30d/90d/1y) | ✅ | F2 |
| 2 | Volume de negociações + média móvel | ✅ | F3 |
| 3 | Detecção de volume anormal | ✅ | F4 |
| 4 | Supply (oferta disponível) | ✅ | F3 |
| 5 | Relação Oferta x Demanda (S/D ratio) | ✅ | F5 |
| 6 | Float Analysis | ⚪ fora de escopo | — |
| 7 | Pattern Scanner | ⚪ fora de escopo | — |
| 8 | Popularidade pro players | ⚪ fora de escopo | — |
| 9 | Cases de origem + status | ✅ | F7 |
| 10 | Taxa de unboxing | ⚪ fora de escopo | — |
| 11 | Alertas de oportunidade | ✅ | F8 |
| 12 | Score de Investimento (multi-fator) | ✅ | F6 |
| 13 | Multi-marketplace (arbitragem) | ⚪ fora de escopo | — |

---

## FASE 1 — Fundação ✅
- [x] Priceoverview API (lowest, median, volume)
- [x] SSR page parsing (price history + order book)
- [x] Fair value verdict (abaixo/justo/acima da mediana)
- [x] Order book depth chart
- [x] SMA overlay no sparkline
- [x] Suporte/resistência no histórico
- [x] Scanner com score (0-100)
- [x] Categorias automáticas (Rifles, Pistolas, Facas, Luvas...)

## FASE 2 — Multi-period Trends ✅
- [x] `multi_trend(price_history)` em `signals.py`
- [x] Retorna `{24h, 7d, 30d, 90d, 1y}` com change_pct/direction
- [x] Exibição no ScannerTab (coluna Tendência)
- [x] Exibição no MarketTab
- [x] Usado no `scan_score()` (concordância multi-período)

## FASE 3 — Volume + Supply Tracker ✅
- [x] `record_item_volume(name, volume)` / `load_item_volume(name)`
- [x] `record_item_supply(name, cSellOrders)` / `load_item_supply(name)`
- [x] Cap em 200 entradas (volume e supply)
- [x] Coleta automática no MarketTab + ScannerTab
- [x] Persistência em `data/volume_history.json` e `supply_history.json`

## FASE 4 — Anomaly Detection ✅
- [x] `volume_anomaly(history, factor=2.0)` — desvio vs média móvel
- [x] Reutilizado para supply anomaly
- [x] Retorna `{is_anomaly, ratio, current, avg, direction, label}`
- [x] Flag visual no MarketTab (label amarelo)
- [x] Flag visual no ScannerTab (background amarelo + contador "ANOMALIA: N")

## FASE 5 — Supply/Demand Score ✅
- [x] `supply_demand_ratio(volume, supply)` → ratio + label
- [x] Integrado no `scan_score()` com pesos: ≥5 (+15), ≥3 (+10), <0.5 (-10)
- [x] Coluna "S/D" no ScannerTab
- [x] Label no MarketTab e no Top Pick

---

## FASE 6 — Investment Score Aprimorado ✅
- [x] `enhanced_score()` retorna `(score, breakdown)` com contribuição por fator
- [x] `format_breakdown()` serializa para tooltip
- [x] Tooltip no ScannerTab na coluna Score mostrando todos os fatores
- [x] `scan_score()` mantido como wrapper retrocompatível
- [x] Bonus de caixa: descontinuada +5, rara +3 (preparado para F7)

Fatores e pesos atuais:
| Fator | Peso | Fonte |
|---|---|---|
| Diff vs mediana | ±35 | diff_pct |
| Spread | ±25 | order book |
| Book ratio | ±20 | order book |
| Tendência (verdict) | ±15 | trend |
| Supply/Demand | ±15 | volume/supply |
| Momentum (SMA) | ±5 | price_history |
| Concordância multi-período | ±10 | multi_trend |
| Liquidez (volume>2000) | +5 | volume |
| Caixa descontinuada | +5 | cases.case_status |
| Caixa rara | +3 | cases.case_status |

## FASE 7 — Case Database ✅
- [x] `skinvault/cases.py` — 50+ cases + 100+ skins populares mapeadas
- [x] `case_status(name)` com normalizacao (StatTrak/Souvenir/wear)
- [x] Match exato + fallback substring (luvas variantes)
- [x] MarketTab: substitui `discontinued_flag` pelo case_status (cor por status)
- [x] ScannerTab: tooltip de case na coluna nome + chip no Top Pick
- [x] Integrado no Investment Score (F6)

## FASE 8 — Alertas Avançados ✅
- [x] `skinvault/alerts.py` engine de regras: price_below, price_drop_pct,
       volume_spike, supply_drop
- [x] `evaluate_item()`, `diff_new_alerts()` (auto-rearm), `record_alert()`,
       `load_alerts_log()` (cap 500)
- [x] WatchlistTab: coluna "Regras", botão "Editar regras" com dialog
       (drop %, volume spike, supply drop, baseline)
- [x] QSystemTrayIcon com notificações por regra
- [x] Tooltip na coluna Status mostra alertas ativos
- [x] Log persistido em `data/alerts_log.json`

## FASE 9 — Top 20 Ranking ✅
- [x] `skinvault/ranking.py` com save_snapshot / position_delta
- [x] Botão "Ranking Top 20" no ScannerTab (escaneia todas as categorias)
- [x] Snapshot persistido em `data/rankings.json` (cap 50)
- [x] Coluna "ΔPos" mostra +N (verde) / -N (vermelho) / = / NOVO (roxo)
- [x] Tooltip na ΔPos mostra posição anterior

---

## FASE 10 — Steam Account Sync ✅
**Filosofia revisada:** login passa de "zero" para "opt-in". F1-F9 continuam funcionando sem login; F10 adiciona sync de dados privados sob consentimento.

- [x] `skinvault/steam_session.py` — `SteamSession` (cookies + steamid), persist/load, validate via /my/ redirect
- [x] `skinvault/steam_login_dialog.py` — Chrome DevTools Protocol via WebSocket. Lança `chrome.exe` com `--remote-debugging-port`, faz polling em `/json` até detectar `/profiles/` ou `/id/` na URL, conecta WS e extrai cookies (HTTP-only inclusive) via `Network.getAllCookies`. Sem QtWebEngine (removido por crash do Qt6Core 6.10.2); fallback manual (colar cookies JSON) permanece.
- [x] `skinvault/steam_api.py` — funções autenticadas `fetch_market_history`, `fetch_my_listings`, `fetch_trade_history_html` + parsers HTML (regex, sem bs4)
- [x] `skinvault/sync.py` — orquestrador `sync_all`: inventario → portfolio; market history → `steam_market_events.json`; listings → `active_listings.json`; trade offers → `trade_history.json`
- [x] Dedupe via `listing_id`/`tradeofferid` ou composite hash; idempotente em runs sucessivos
- [x] `portfolio.py` + `trades.py` — campo `source` (manual | steam_sync | steam). Sync nunca sobrescreve manual.
- [x] `backup.py` — cobre os 4 novos JSONs (incluindo `steam_session.json` com aviso de credenciais)
- [x] `gui.py` — botão "Conectar Steam" no canto superior, `SteamSyncDialog` com 4 steps em thread, menu de status/desconectar
- [x] `requirements.txt` — `httpx>=0.28`, `websocket-client>=1.6` (sem PyQt6-WebEngine)
- [x] Testes: `test_steam_session.py`, `test_steam_api_auth.py`, `test_sync.py`

**Riscos conhecidos** (documentados na UI):
- Cookies em texto plano em `data/steam_session.json` — coberto por `.gitignore` da pasta data/
- Steam pode mudar fluxo de login → re-login manual resolve

---

## FASE 11 — Redesign UI estilo Athenas ✅
Sidebar hierárquica (7 telas) substituindo QTabWidget, LoginGate opcional, ScreenRouter com navegação por constantes, PyQt6-WebEngine como dependência fixa, janela maximizada+centralizada sem console (pythonw.exe). Telas implementadas: Account (carteira), History (histórico), Scanner (real com rate-limit), Market (busca + depth chart), Trades (CRUD), Simulador (compra/venda), Watchlist (regras + alertas).

## FASE 12 — Pareamento BUY↔SELL ✅
- [x] `skinvault/trade_matcher.py` — `parse_steam_date` (ano implícito Steam), `match_events` (FIFO por nome), `load_closed_trades`, `summarize`
- [x] Novo segmento "Pareados" no HistoryScreen com colunas Vendido em / Item / Compra / Venda / P&L líquido / ROI
- [x] Status bar com agregados (count, total P&L, W/L, win rate) respeitando filtro de período
- [x] 15 testes cobrindo parsing, FIFO, isolamento por nome, sell antes de buy, summarize

---

## 🔴 Fora do Escopo (decididos)

- **Float Analysis / Pattern Scanner (#6, #7)** — Steam não expõe via API pública; precisaria CSFloat API
- **Multi-market arbitragem (#13)** — Buff (login chinês), Skinport (API ok), SkinBaron (scraping), CSFloat (API ok). Reavaliar após uso real do scanner.
- **Pro player / streamer tracking (#8)** — HLTV/Liquipedia scraping frágil
- **Unboxing rate (#10)** — só Valve tem

---

## Ordem de Implementação

```
✅ F1 → ✅ F2 → ✅ F3 → ✅ F4 → ✅ F5 → ✅ F6 → ✅ F7 → ✅ F8 → ✅ F9 → ✅ F10 → ✅ F11 → ✅ F12
```

F10 introduz 3 novos módulos (`steam_session`, `steam_login_dialog`, `sync`)
e ~60 testes adicionais. F1-F9 seguem intactas e funcionam sem login.
