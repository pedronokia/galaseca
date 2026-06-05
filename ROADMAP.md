# SkinVault Roadmap

## Filosofia
- **Zero login/sessão/cookie** — tudo com dados públicos da Steam
- **Dados factuais** — descrevemos, não prevemos
- **Valor real** — após taxa Steam (15%)

---

## FASE 1 — Fundação ✅ (concluído)
- [x] Priceoverview API (lowest, median, volume)
- [x] SSR page parsing (price history + order book)
- [x] Fair value verdict (abaixo/justo/acima da mediana)
- [x] Order book depth chart
- [x] SMA overlay no sparkline
- [x] Suporte/resistência no histórico
- [x] Scanner com score (0-100)
- [x] Categorias automáticas (Rifles, Pistolas, Facas, Luvas...)

---

## FASE 2 — Multi-period Trends (dados já temos)
Objetivo: extrair tendências de 24h, 7d, 30d, 90d, 1y do `price_history` SSR.

- [ ] Função `multi_trend(price_history)` em `signals.py`
  - Retorna `{change_24h, change_7d, change_30d, change_90d, change_1y}`
- [ ] Exibir no ScannerTab como colunas ou tooltip
- [ ] Usar nos alertas: "subiu 30% em 7 dias"
- [ ] Adicionar ao Investment Score

## FASE 3 — Volume + Supply Tracker
Objetivo: persistir volume e supply ao longo do tempo (igual fazemos com preço).

- [ ] `record_item_volume(name, volume)` em `signals.py`
- [ ] `record_item_supply(name, cSellOrders)` em `signals.py`
- [ ] `load_item_volume_history(name)` / `load_item_supply_history(name)`
- [ ] Cap em 100 entradas (igual price history)
- [ ] Coletar automaticamente no MarketTab + ScannerTab
- [ ] Sparkline de volume no MarketTab

## FASE 4 — Anomaly Detection
Objetivo: detectar quando volume ou supply fogem da média.

- [ ] `volume_anomaly(history)` — compara último valor com média móvel
- [ ] `supply_anomaly(history)` — mesma lógica
- [ ] Retorna `{is_anomaly, ratio, direction, label}`
- [ ] Flag no ScannerTab: "Volume 3x maior que a média!"
- [ ] Flag no ScannerTab: "Supply caiu 20%"

## FASE 5 — Supply/Demand Score
Objetivo: criar métrica de relação oferta x demanda.

- [ ] `supply_demand_score(volume, supply)` → ratio 0-1
- [ ] Adicionar ao `scan_score()` com peso 20%
- [ ] Exibir no ScannerTab como coluna "S/D"

## FASE 6 — Investment Score Aprimorado
Objetivo: score multi-fator com pesos configuráveis.

Fatores e pesos:
| Fator | Peso | Fonte |
|---|---|---|
| Liquidez (volume) | 20% | volume 24h |
| Preço vs Mediana | 20% | diff_pct |
| Spread | 10% | order book |
| Book ratio (buy/sell) | 10% | order book |
| Supply/Demand | 15% | volume / cSellOrders |
| Tendência 30d | 15% | multi_period_trends |
| Caixa descontinuada | 10% | case_database |

- [ ] `enhanced_score(verdict, volume, supply, trends, case_status)` em `signals.py`
- [ ] Pesos salvos em `settings.py` (customizáveis)
- [ ] Exibir breakdown no ScannerTab (score por fator)
- [ ] Substituir `scan_score()` atual

## FASE 7 — Case Database
Objetivo: mapear skin → caixa de origem + status (active/rare/discontinued).

- [ ] `skinvault/cases.py` — database de ~50-100 cases e coleções
- [ ] `case_status(name)` retorna `{case, is_discontinued, is_rare, collection}`
- [ ] Exibir no MarketTab + ScannerTab
- [ ] Peso no Investment Score

## FASE 8 — Alertas Avançados
Objetivo: notificar oportunidades no tray.

- [ ] Configurar limites em Settings: preço cai X%, volume explode Y%, supply cai Z%
- [ ] WatchlistTab expandida com regras por item
- [ ] Notificação no QSystemTrayIcon com ação "Abrir Scanner"
- [ ] Log de alertas disparados

## FASE 9 — Top 20 Ranking
Objetivo: ranking automático diário.

- [ ] Botão "Ranking Top 20" no ScannerTab
- [ ] Escaneia itens pré-definidos (top por categoria)
- [ ] Salva snapshot do ranking em `data/rankings.json`
- [ ] Exibe evolução: "semana passada estava em 5o, agora 2o"

---

## 🔴 Fora do Escopo (requerem sessão Steam)

- **Float Analysis / Pattern Scanner** — Steam não expõe via API pública
- **Multi-market (Buff, CSFloat, Skinport)** — cada um tem suas regras
- **Histórico de compras/vendas Steam + Saldo** — requer autenticação
- **Unboxing rate** — só Valve tem esses dados
- **Pro player / streamer tracking** — sem API pública

---

## Ordem de Implementação Sugerida

```
FASE 2 → FASE 3 → FASE 4 → FASE 5 → FASE 6 → FASE 7 → FASE 8 → FASE 9
```

Cada fase é autossuficiente e testável. Fases 2-3 são pré-requisito para 4-6.
