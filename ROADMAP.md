# SkinVault Roadmap

## Filosofia
- **Zero login/sessão/cookie** — tudo com dados públicos da Steam
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
| 9 | Cases de origem + status | ⏳ | F7 |
| 10 | Taxa de unboxing | ⚪ fora de escopo | — |
| 11 | Alertas de oportunidade | ⏳ | F8 |
| 12 | Score de Investimento (multi-fator) | 🟡 parcial | F6 |
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

## FASE 6 — Investment Score Aprimorado (em curso) 🟡
Objetivo: score multi-fator com pesos configuráveis + breakdown visível.

Fatores e pesos atuais (no `scan_score()`):
| Fator | Peso | Fonte | Status |
|---|---|---|---|
| Diff vs mediana | ±35 | diff_pct | ✅ |
| Spread | ±25 | order book | ✅ |
| Book ratio | ±20 | order book | ✅ |
| Tendência (verdict) | ±15 | trend | ✅ |
| Supply/Demand | ±15 | volume/supply | ✅ |
| Momentum (SMA) | ±5 | price_history | ✅ |
| Concordância multi-período | ±10 | multi_trend | ✅ |
| Liquidez (volume>2000) | +5 | volume | ✅ |
| Caixa descontinuada | — | case_database | ⏳ F7 |

- [ ] `enhanced_score()` retorna `(score, breakdown)` com contribuição por fator
- [ ] Tooltip no ScannerTab mostrando breakdown ao hover na coluna Score
- [ ] Pesos configuráveis em `settings.py` (opcional, depois)

## FASE 7 — Case Database
Objetivo: mapear skin → caixa de origem + status.

- [ ] `skinvault/cases.py` — database de ~80 cases/coleções principais
- [ ] `case_status(name)` retorna `{case, collection, is_discontinued, is_rare, dropped_since}`
- [ ] Exibir no MarketTab (linha com caixa + status)
- [ ] Exibir no ScannerTab (tooltip ou coluna compacta)
- [ ] Bonus no Investment Score: +5 para descontinuada, +3 para rare

## FASE 8 — Alertas Avançados
Objetivo: notificar oportunidades no tray.

- [ ] `skinvault/alerts.py` — define regras (preço cai X%, volume sobe Y%, anomaly)
- [ ] WatchlistTab expandida com regras por item
- [ ] QSystemTrayIcon com notificações nativas
- [ ] Log de alertas disparados em `data/alerts_log.json`
- [ ] Click no tray abre ScannerTab focado no item

## FASE 9 — Top 20 Ranking
Objetivo: ranking automático para descobrir oportunidades.

- [ ] Botão "Ranking Top 20" no ScannerTab
- [ ] Escaneia lista predefinida de itens populares (top por categoria)
- [ ] Salva snapshot em `data/rankings.json`
- [ ] Comparativo: "semana passada estava em 5º, agora 2º"
- [ ] Filtrável por categoria

---

## 🔴 Fora do Escopo (requerem fonte externa / autenticação)

**Decisão arquitetural Steam-only:** evitar dependência de scraping frágil e sessões privadas.

- **Float Analysis / Pattern Scanner (#6, #7)** — Steam não expõe via API pública; precisaria CSFloat API
- **Multi-market arbitragem (#13)** — Buff (login chinês), Skinport (API ok), SkinBaron (scraping), CSFloat (API ok). Decisão para depois das Fases 6-9.
- **Pro player / streamer tracking (#8)** — HLTV/Liquipedia scraping frágil
- **Unboxing rate (#10)** — só Valve tem
- **Histórico de compras/vendas Steam pessoal** — requer sessão privada

---

## Ordem de Implementação

```
✅ F1 → ✅ F2 → ✅ F3 → ✅ F4 → ✅ F5 → 🟡 F6 → ⏳ F7 → ⏳ F8 → ⏳ F9
```

Cada fase é autossuficiente e testável. Fases 6-9 são independentes entre si.
