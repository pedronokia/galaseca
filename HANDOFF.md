# HANDOFF — estado em 2026-07-30

Ponto de partida pra quem continuar (opencode ou outro agente). Substitui
o handoff de 2026-06-09.

**Leia primeiro:** [AGENTS.md](AGENTS.md). As armadilhas **#10, #11, #12**
e as seções **4b/4c/4d** foram escritas nesta sessão e resumem o que
custou caro descobrir.

---

## Estado

- Branch: `feat/multi-market-e-inventario`
- **30 commits**. **Não há remote configurado** — não é decisão pendente,
  não existe pra onde enviar.
- Suíte: **1923 testes**, ~65s. `cd C:\SkinVault && python -m pytest -q`
- App: `pythonw -m skinvault --ui` (rodar de `C:\SkinVault`)
- Working tree limpo.

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

## Fila, em ordem

### 1. Cartão "Itens no lucro 0 de 2" na tela de Conta — enganoso
Só 2 das 31 posições têm custo registrado, então o P&L agrega 2. O cartão
diz "0 de 2" e parece que o usuário tem 2 itens. Precisa dizer que são 2
**com custo conhecido** de 31 — `portfolio.evaluate_portfolio` já devolve
`totals.unknown_cost` justamente pra isso, e ninguém usa.

### 2. Coluna "Origem" do inventário
100% "Steam" nas 31 linhas. Ocupa espaço sem informar. Ou some, ou só
aparece quando há mistura com posições manuais.

### 3. Grade do inventário
Cada tile mostra "—" embaixo. O valor de fora já existe (`market_net` no
dict do tile) e podia aparecer ali.

### 4. `scanner_discovery` (bloqueado por fora)
`discovery.py` escrito e testado, flag `scanner_discovery = False`. Nunca
completou uma chamada real. Quando a Steam liberar: rodar `search_market`
uma vez; se vier `ok`, ligar a flag.

### 5. Buff163 fora do ar
`markets.fetch_market("buff163")` retorna erro, 0 itens. É a menor taxa
(2,5%). Não investigado.

### 6. Ponto ruim no `history.json`
Os deltas já foram corrigidos, mas sobrou o ponto de 11/06 (R$ 200,00,
avaliação parcial). Remover muda o gráfico de valor — decisão do dono.

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
