# HANDOFF — estado em 2026-08-02

Ponto de partida pra quem continuar (opencode ou outro agente). Substitui
o handoff de 2026-07-30.

**Leia primeiro:** [AGENTS.md](AGENTS.md). As armadilhas **#10, #11, #12**
e as seções **4b/4c/4d** foram escritas em 30/07 e resumem o que custou
caro descobrir.

**Decisão de produto em 02/08: escopo 100% Mercado da Comunidade Steam.**
Não haverá integração com mercados externos/paralelos daqui pra frente
(Buff163 e similares). Análises, fair value, sinais e histórico dependem
exclusivamente de dado Steam. Isso reafirma a regra original do
`AGENTS.md` ("Steam-only... até reavaliação pós-uso real") — a
reavaliação aconteceu (branch `feat/multi-market-e-inventario`, 51
commits mergeados), e a conclusão foi recuar. **CSGOTM e Skinport
continuam integrados** (comparação "Melhor fora"/"Onde" no inventário já
é funcionalidade real e usada); só o Buff163 — que nunca funcionou — saiu
do código. Se a intenção for descontinuar CSGOTM/Skinport também, isso é
uma tarefa maior e separada (remove o card "Melhor fora", a composição
"vendendo fora" da Conta e o painel de venda do inventário) — avisar
antes de tocar nisso.

---

## Estado

- Branch: `main` (a `feat/multi-market-e-inventario` foi mergeada em
  `dc349c7`).
- Suíte: **2127 testes**, ~65s. `cd C:\SkinVault && python -m pytest -q`
- App: `pythonw -m skinvault --ui` (rodar de `C:\SkinVault`)
- Working tree limpo.
- **Fase 3 (UI botcloud, `ROADMAP_UI_FASE3.md`) e Fase 4 (UI
  consistência, `ROADMAP_UI_FASE4.md`) 100% concluídas** — todas as
  frentes ✅, nada pendente nesses dois documentos.

**A Steam está com rate limit há mais de 24h** em `priceoverview`,
`search/render`, `pricehistory` e `/inventory/`. A listing page e o CDN de
ícone respondem — mas a listing page tem orçamento próprio e falha em
silêncio (AGENTS.md #12).

## Filosofia (NÃO mudar)

- **Nunca prever futuro; apenas descrever dados factualmente.**
- Análise vai em `signals.py` / `cases.py` / `alerts.py` / `backtest.py`.
- UI modular em `skinvault/ui/`, uma tela por arquivo.
- Cores só via tokens de `theme.py`.
- **Ao mexer no score, meça antes e depois.** A infraestrutura existe
  (`simulate_item` + `correlation` + `factor_ic`).

---

## O que ficou pronto nesta sessão

**Infraestrutura**
- Instância única (`single_instance.py`).
- Escrita atômica em todo `data/` + quarentena de arquivo corrompido
  (`_paths.atomic_write_text` / `load_json_record`).
- 429 deixou de virar "sem preço" no cache; o lote corta na primeira
  recusa — 1 chamada em vez de 31, 7s em vez de 434s.

**Produto**
- Importação de trades do Steam Market (25 trades reais, P&L −R$ 14,56,
  32% de acerto). Idempotente.
- Sync de trocas: separa entregue de recebido; dedupe por hash composto
  (a página não expõe `tradeofferid`).
- Inventário mostra o item em **todas as plataformas** no tooltip,
  ordenado pelo líquido. CSGOTM (5%) costuma pagar mais que Skinport (12%).
- `portfolio.sell_guidance()` e `portfolio.max_buy_price()` — a lógica de
  "por quanto vender" e "quanto pagar". **Ainda não aparece na UI.**
- Ordenação de tabela por valor (era por texto: P&L decrescente mostrava
  o maior prejuízo no topo).

**Pesquisa** — detalhes em AGENTS.md 4b/4c/4d
- Aposentadoria de caixa é um **salto de 4x** que depois decai com a idade.
- **O teto de valorização é o preço absoluto** (IC −0,26; −0,30 em caixas).
- Vintage v4 **desligado**: a aprovação media lookahead.
- Fator de nível de preço **aprovado e ligado** (containers-only).
- Break-even da Steam é **15%**, não 17,65% — o backtest estava errado.

---

## Já entregue depois do handoff original (30/07, tarde)

- **Painel do inventário** diz por quanto anunciar, o que sobra em saldo,
  o cenário de venda rápida, as plataformas de fora ordenadas pelo
  líquido, e o piso pra empatar quando há custo.
- **Scanner** ganhou a coluna "Compre até" (verde quando o preço cabe no
  teto de 20% de margem).
- **Tabela do inventário**: "Melhor fora" + "Onde" no lugar da parede de
  travessões; rodapé soma R$ 1.510,86; rótulo "-15%" corrigido.
- **Histórico**: data unificada em DD/MM/YY (havia duas grafias, e uma
  não ordenava como data); rodapé avisa quando um filtro esconde
  registros.
- Removido do `history.json` o snapshot parcial que gerava "-79,6%"
  (backup em `history.json.bak-parcial`).

## Entregue em 30/07 à noite (sessão Claude Code)

- **Cartão "0 de 2"** (era fila #1): os três cartões de desempenho ganharam
  a legenda do denominador. No caminho apareceu número ERRADO, não só sem
  contexto: `evaluate_portfolio` contabilizava custo dentro do ramo que só
  roda com preço, então com a Steam em 429 o "Total investido" exibia
  R$ 0,00 pra quem tem R$ 850,00 declarados, e `unknown_cost` vinha 0 com
  29 posições sem custo. Agora há `cost_known` (desembolso) separado de
  `cost` (custo que lastreia o P&L).
- **Grade do inventário** (era fila #3): tile cai pro melhor líquido de
  fora quando falta o saldo, com a **origem** impressa junto — saldo
  travado e dinheiro não são a mesma moeda. Ordenação passou a usar o
  valor exibido (era `steam_net`, None em tudo). "?" virou o primeiro
  trecho do nome.
- **Tela Minha Conta**: a metade vazia recebeu "Evolução do valor" (o
  gráfico saiu dos 90px pra cartão próprio) e "Composição da carteira"
  (barras por categoria; mede valor com preço, contagem sem). "Valor
  bruto R$ 0,00" com "+1,5%" ao lado virou "—" + tooltip.
- **Barra lateral** alterna rail ↔ rótulos (`sidebar_collapsed`). A
  preferência "largura da barra" já existia mas só esticava o rail.
- **Acentuação** das strings visíveis + `palette_rank` ignorando acento
  dos dois lados. Camada de análise ficou de fora de propósito (os
  rótulos de breakdown vão pro rankings.json).

Suíte: **1967 testes**.

## Entregue em 01-02/08 (sessão Claude Code)

- **Commits ad-hoc pós Fase 4** (fora de roadmap formal): gráfico de
  histórico completo no Market (eixo, volume, intervalo 7d/30d/tudo,
  crosshair — `3fc3bc7`), busca por nome no Scanner (`1ef3950`),
  tooltips nos cabeçalhos de tabela em trades/watchlist/history/scanner
  ("front #4" — `b393325`), inventário no layout do Mercado da
  Comunidade Steam (`9bae27e`), fix de alinhamento dos filtros do
  inventário + procedência que negava caixa conhecida (`c559480`).
- **Fila #1 resolvida** — coluna "Origem" do inventário agora usa
  `setColumnHidden`: some quando todas as posições têm a mesma origem,
  só aparece com mistura Steam/Manual de verdade (`a69800e`).
- **Fila #2 resolvida** — acentuação de `signals.py`/`steam_api.py`/
  `alerts.py` (labels, messages, flags de breakdown/alerta/veredito).
  Levantamento confirmou que `rankings.json` não persiste esse texto
  (schema real é só `{name, score, position}`) e nenhuma lógica compara
  contra ele (comparações usam token em inglês: `verdict`, `level`,
  `factor`) — sem migração de dado necessária. `alerts_log.json`
  persiste `label` livre; registros antigos mantêm a grafia sem acento
  até rolarem do cap de 500, inofensivo (`f8fcbe7`).
- **Fila #4 resolvida** — Buff163 removido de `MARKET_FEES`
  (`markets.py`) e de `_NOME_MERCADO` (`inventory_grid.py`); nunca
  respondeu (sempre `ERROR`, 0 itens), então a remoção não tira nenhuma
  cotação que estivesse aparecendo de verdade. Decisão de produto: sem
  reintegração de mercado externo novo daqui pra frente.

## Fila, em ordem

### 1. `scanner_discovery` (bloqueado por fora)
`discovery.py` escrito e testado, flag `scanner_discovery = False`. Nunca
completou uma chamada real. Quando a Steam liberar: rodar `search_market`
uma vez; se vier `ok`, ligar a flag.

---

## Item fechado em 02/08: ponto ruim no `history.json`

**Já estava resolvido** — a fila só não tinha sido atualizada. Conferido
no dado real (`data/history.json` vs o backup
`data/history.json.bak-parcial`):

- Backup tem 3 pontos: 04/06 (R$ 964,93), 05/06 (R$ 979,42) e **11/06
  10:37 (R$ 200,00)** — o ponto de avaliação parcial.
- `history.json` **ao vivo** hoje só tem os 2 primeiros. O ponto de
  200 já foi removido (entrada "Removido do `history.json` o snapshot
  parcial que gerava -79,6%" na seção de 30/07 acima, feita na mesma
  sessão que criou o backup).
- Conferi a matemática: `(200 − 979,42) / 979,42 = −79,6%`, bate exato
  com o que já estava documentado. É o mesmo ponto.

**Nada a fazer nos dados** — não toquei em `history.json` nem no backup.
O `.bak-parcial` fica onde está como registro de segurança (não é
arquivo canônico, não entra na whitelist do `backup.py`). Só os 2 pontos
limpos aparecem no gráfico hoje.

O gráfico de valor está com poucos pontos (2, ambos de 04-05/06) porque
`record_snapshot` só roda quando uma avaliação completa com sucesso, e a
Steam andou em rate limit prolongado (ver topo do documento) — isso é
consequência do bloqueio externo, não um bug de dado.

---

## Não repita

- **Não use `Path.write_text` em `data/`.** Use `_paths.atomic_write_text`.
- **Não cacheie resultado de 429** como se fosse fato sobre o item.
- **Não confie em `page` sem `price_history`** numa varredura: pode ser
  throttle silencioso (200 com corpo grande e vazio de dado). Três vazios
  seguidos = pare.
- **Não meça fator de score sem controlar por data.** O regime de mercado
  produz correlação onde não há sinal — quase virou "comprar depois de
  alta funciona", que o corte cross-sectional dissolveu.
- **Não confie em render offscreen pra julgar glifo ou animação** (#11).
- **Não escreva teste que leia `data/` do usuário.** Um lia `trades.json`
  e só passava enquanto o arquivo estava vazio.
- **Não rode a suíte com `--ui` em subprocess.** Vazava uma instância do
  app por rodada.

---

## Contexto do dono

Quer o app pra **revenda de skins**. As três prioridades que ele nomeou:

1. entender a lógica da revenda **dentro da Steam**
2. saber analisar preço de skins
3. analisar o inventário e **apontar por quanto vender** e se vale a pena
   comprar pelo scan

Ele também troca skins por saldo em sites externos — esse caminho não
passa pelo Market, e por isso não aparece no P&L dos 25 trades.

Números que condicionam tudo: a Steam pede ~36% a mais que mercados com
dinheiro real, e o break-even da taxa é 15%. O quintil superior do score
rende +13,64% brutos em 90d → **−1,18% líquidos**. Flip de curto prazo
dentro da Steam não fecha. A tese que fecha é container recém-aposentado
em horizonte de ano (+25,8% líquidos).
