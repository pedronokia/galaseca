# HANDOFF — estado em 2026-08-08

Ponto de partida pra quem continuar (opencode ou outro agente). Substitui
o handoff de 2026-08-04.

**Mudança maior desde 04/08: F10 (login/sync via cookies de sessão Steam)
foi revertida por completo em 2026-08-07.** O Steam Subscriber Agreement
proíbe de forma ampla automação de conta logada, com terminação sem aviso
prévio — risco diferente do scan público anônimo. O usuário decidiu
remover a capacidade inteira; os dados já sincronizados
(`steam_market_events.json`, `active_listings.json`, `trade_history.json`)
foram mantidos, só a capacidade de logar de novo saiu. Detalhes completos
em `ROADMAP.md` (seção FASE 10) e memória `f10-login-sync-revertida`. O
app voltou a abrir direto na tela Conta, sem tela de login, sidebar
sempre visível — validado com screenshot e navegação manual real.

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

- Branch: `main`, working tree limpo. Todos os commits do F10 (revert) já
  feitos localmente; nenhum push pendente (repo não tem remote).
- Suíte: **2121 testes**, ~75s. `cd C:\SkinVault && python -m pytest -q`
  (caiu de 2360 pra 2121 por causa da remoção de ~290 testes de
  login/sync do F10 — não é regressão).
- App: `pythonw -m skinvault --ui` (rodar de `C:\SkinVault`)
- **F1-F9, F11, F12 concluídas. F10 implementada e revertida** (ver nota
  acima e ROADMAP.md). Nenhuma fase formal do ROADMAP pendente.
- **Fase 3/4 de UI e sprints de Microinterações/Layout concluídas** — UI e
  fluxo de dados local em estado maduro (sem mudança desde 04/08 aqui).
- **Rate limit centralizado**: `steam_api.RATE_LIMIT_DELAY_S = 4.0`
  (subiu de 1-2s), referenciado ao vivo em todo call site — nunca copiado
  pra constante de módulo nem usado como default de parâmetro (os dois
  congelam o valor e ficam un-monkeypatchable; `tests/conftest.py` zera
  a constante via fixture autouse pra suíte não dormir de verdade).
- **Pacote de liquidez/z-score (05-08/08)**: liquidez sob demanda no
  Inventário (grid + tabela) e Watchlist, Oferta/Demanda no Market,
  `price_zscore` exposto no Scanner/Market, filtro de preço e termômetro
  de mercado no Scanner, aviso honesto de rate limit quando o scan falha.

**Sondagem de rate limit em 08/08/2026:** `search_market` **sem facetas**
(query de texto simples) voltou a responder normalmente. `priceoverview`
e `search_market` **com facetas** (o que `discovery.py` usa pra
categorias) continuam em **rate_limited** — são orçamentos separados no
lado da Steam, confirmado com 2 chamadas isoladas. Detalhes em
"Fila, em ordem".

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

## Sprint de Microinterações & UX (01-02/08)

**Fase 1 — `dc6dc23`: Toast clicável, estados de botão, atalhos**
- `Toast` (`components.py`) já existia (fade in/out, variants, auto-stack);
  ganhou fechar ao clicar (`mousePressEvent` + guarda `_dismissing` contra
  disparo duplo com o timer de auto-dismiss).
- QSS: estado `:pressed` em todo `btn_*` (tokens `*_PRESSED`, um degrau
  além do `:hover`) e hover/pressed no cabeçalho de coluna da tabela
  (clicável pra ordenar, mas sem feedback nenhum antes).
- Watchlist ganhou toast em adicionar (sucesso/duplicado) e remover
  (linha única/seleção múltipla) — único fluxo do app sem feedback
  transiente até então.
- Conta ganhou botão "Copiar ID" ao lado do SteamID (clipboard + toast) —
  não existia nenhuma ação de copiar em lugar nenhum do app.

**Fase 2 — `8f3ad24`: Loading states e bug crítico de thread**
- `set_button_loading(btn, bool, texto)` (`components.py`): desabilita,
  troca o texto e esmaece a opacidade via `QPropertyAnimation`.
- `sync_bar()`: barra fina indeterminada pra refresh em segundo plano sem
  esconder dado já carregado (diferente do `LoadingState`, que substitui
  o conteúdo); aplicada acima da tabela do Scanner.
- **Bug crítico corrigido**: os workers em background thread do Mercado
  (`_on_search`), do Scanner (`_on_scan`) e da Conta (`_reload_profile`)
  não tinham `try/except` ao redor da chamada de rede — uma exceção
  inesperada matava a thread ANTES de emitir o sinal de conclusão, e o
  botão (mais o spinner) ficava travado desabilitado pra sempre. No
  Mercado era o pior caso: tela em branco, sem conteúdo nem empty-state.
  Corrigido com `try/except/finally` garantindo que o sinal de conclusão
  sempre dispara, sucesso ou erro.

**Fase 3 — `a4553b8`: Empty states e transições**
- Scanner ganhou CTA "Escanear agora" no empty state — o glifo `◎` é
  documentado em `EmptyState` como "pronto pra agir, com CTA imediato",
  mas a tela só tinha passos em texto, quebrando o próprio contrato do
  componente.
- Label `_sem_match` no Scanner e na Watchlist quando a busca não acha
  nada (mesmo padrão já corrigido no Inventário — sem isso a tabela
  ficava em branco, indistinguível de "sem dados" ou falha silenciosa).
- Orçamento de `fade_in()` travado em teste: 150-200ms (o default já
  cumpria, 150ms).

## Sprint de Layout & Ergonomia (02/08)

**Densidade de tabelas — `fba4af0`**
- 3 níveis (Compacta 24px / Padrão 32px / Confortável 44px), cada um com
  padding de célula próprio; "Padrão" preserva exatamente os valores
  históricos (32px, `9px 14px`).
- `configure_table(table, density=...)` aplica na construção;
  `set_table_density(table, density)` reaplica ao vivo numa tabela já
  construída.
- Persistido em `settings["table_density"]`; seção nova em Configurações
  (Compacta/Padrão/Confortável) aplica na hora nas 5 telas com tabela
  (Inventário, Histórico, Scanner, Trades, Watchlist).

**ViewModeSwitcher + P&L no grid — `fba4af0`**
- Componente `ViewModeSwitcher` formaliza o alternador Grade/Tabela que
  o Inventário já montava na mão (par de `SegmentedControl` repetido).
- Card do inventário ganhou P&L colorido (verde/vermelho, "P&L —" sem
  custo conhecido) — era o único dado que faltava; ícone, nome e preço
  já estavam lá.

**Sidebar animada + ItemDetailDrawer — `926866f`**
- Sidebar recolhível (rail ↔ rótulos) já existia madura e testada;
  ganhou transição animada (`QVariantAnimation`, 180ms) ao trocar de
  modo — antes era salto instantâneo de largura.
- `ItemDetailDrawer` novo: painel lateral que desliza da direita ao
  clicar numa linha da TABELA do Inventário (a Grade já tinha painel de
  detalhe próprio, sem mudança ali). Mostra thumbnail, Preço, P&L,
  Condição (wear extraído do nome — Float fica de fora de propósito: é
  Steam-only e a Steam pública não expõe float sem ferramenta de
  terceiro, ver `AGENTS.md`/ROADMAP), tags (StatTrak™/Souvenir) e atalho
  "Abrir no Mercado Steam". Fechar só esconde — seleção da lista e dado
  do item continuam intactos.
- **2 bugs achados na validação manual com o app rodando de verdade**
  (não pegos pelos testes automatizados, que coincidentemente também
  assumiam a mesma ordem): clique na linha indexava a posição VISUAL em
  vez do dado real — a tabela é sortable, e ordenar por qualquer coluna
  desalinha visual de inserção, então o drawer abria com o item errado.
  Corrigido guardando o nome cru no `UserRole` da própria célula clicada.
  Achado também: a Condição lia do nome em inglês (`raw_name`) enquanto o
  resto da tela já é pt-BR — corrigido pra ler do nome localizado. Os
  dois com teste de regressão.

## Refinamento Grid & ItemDetailDrawer (02-03/08) — `8459d65`

Referência Steam/SIH, aplicada nos dois lugares que a sessão anterior
tinha acabado de criar.

- **Badge "No Mercado" no Grid**: canto superior direito do card, só
  quando o item TEM anúncio ativo de verdade — não cotação de
  referência. Novo `_carregar_listados()` no Inventário passou a
  consumir `active_listings.json` (já existia via `sync.py`, nunca
  tinha sido lido pela tela). Aproximação por nome, não por asset:
  `sync.py` não guarda asset_id nas listagens, então 3 unidades do mesmo
  item com só 1 anunciada aparecem como "No Mercado" as três — mesma
  granularidade que o resto da tela já usa (P&L e preço também são por
  nome agrupado).
- **Seleção reforçada no Grid**: fundo próprio (`ACCENT_DIM`) em vez de
  reaproveitar o `SURFACE_HOV` do hover, e borda mais grossa (2/3px →
  3/4px). Antes um card selecionado-mas-não-sob-o-mouse ficava
  visualmente idêntico a um card só de passagem.
- **Drawer reestruturado**: cotações agrupadas num card próprio —
  "Vendendo na Steam (saldo)" (anuncie por + você recebe) separado por
  linha fina de "Vendendo fora (dinheiro real)" (plataforma + líquido).
  As duas moedas não são comparáveis, e antes viviam soltas na mesma
  lista de campos sem nada dizendo isso.
- **Ações rápidas novas**: "Copiar nome" (clipboard + Toast) e "Ver no
  Mercado" (renomeado de "Abrir no Mercado Steam").
- **Decisão de escopo registrada**: "Inspecionar no Jogo"
  (`steam://rungame/...`) NÃO foi implementado. O link exige asset_id +
  inspect ticket por unidade que nenhum lugar do sync capta hoje, e
  inspecionar no jogo é o próprio mecanismo de ver float/pattern —
  mantém a trava Steam-only do `AGENTS.md`/ROADMAP. Documentado na
  docstring do `ItemDetailDrawer` pra não reabrir a discussão.
- Validado com o app rodando de verdade: badge ausente com
  `active_listings.json` vazio (conta real sem anúncio ativo agora),
  cotações Steam/Fora corretas no drawer, clipboard conferido via
  `read_clipboard` após "Copiar nome".

## Gráficos & Visualização Financeira (03/08) — `14ed8d7`

Refinamento dos dois gráficos principais (Conta e Mercado), fechado com
16 testes novos e um fix de hermeticidade que destravou a suíte inteira.

- **ValueChart (Conta)** — "Evolução do valor" ganhou:
  - **Gradiente linear** na cor da tendência (`POSITIVE`/`DANGER`) sob a
    curva, esmaecendo até transparente na base (widgets.py:344-359). O
    traço continua sólido — é o que os testes de cor leem.
  - **Crosshair + tooltip rich-text** no hover: data em negrito, valor
    em `t.brl()` e variação % vs o **primeiro ponto do período visível**
    (não do histórico todo), colorida pela direção.
  - **Seletor 1D/7D/1M/1A/Tudo** (`SegmentedControl` no topo do cartão):
    recorta a MESMA série já carregada em memória por timestamp, sem
    re-ler o disco. `ValueChart.set_range()` com timestamps opcionais —
    sem timestamp o widget continua funcionando como antes.
- **PriceHistoryChart (Mercado)** — gradiente confinado à **área de
  preço** (não invade as barras de volume, widgets.py:764-784) e tooltip
  rich-text interativo com data + variação + volume de vendas. Fatiamento
  de período continua por índice (`_points[-7:]`/`[-30:]`), determinístico.
- **Hermeticidade de testes**: os `test_screen_router_*` que chamam
  `_check_session`/`_on_session` com sessão válida liam o `settings.json`
  **real do usuário** (anti-padrão documentado em "Não repita"). Com
  `welcome_seen: False`, `_maybe_show_welcome` abria um `WelcomeDialog`
  **modal real** — `exec()` vira event loop que nunca fecha no offscreen
  e a suíte travava no primeiro router test (estava assim no HEAD
  anterior, não foi a etapa de gráficos que introduziu). Corrigido com o
  mesmo padrão já estabelecido em `test_router_shows_welcome_first_time`
  (`_hermetic_welcome`/`_FakeWelcome`).
- **Flake eliminado**: o teste de range do ValueChart colocava um ponto
  exatamente na fronteira da janela "7d" — passava ou falhava conforme
  microssegundos entre `agora` e o cutoff interno. Congelado `time.time`
  no teste (padrão já usado no arquivo).
- Validado: 34 testes de gráfico + suíte completa **2212 passed** (2x).

## Accent Colors & Personalização de Tema (03/08) — `4d30bcf`

Etapa 2 da personalização de tema: o destaque da UI saiu do verde fixo e
virou paleta reativa, persistida e trocável ao vivo.

- **Sistema de tokens (`theme.py`)**: cinco paletas de destaque — verde
  (SkinVault, `#22C55E`), azul neon (`#3B82F6`), laranja cyberpunk
  (`#F97316`), roxo/magenta (`#A855F7`) e neutro clássico (`#F1F1F1`).
  Os tokens derivados (`ACCENT`, `ACCENT_DIM`, `ACCENT_HOV`,
  `ACCENT_PRESSED`, `FOCUS_GREEN`) são recalculados dinamicamente por
  `_apply_accent()`, que cai no default se a chave for inválida.
  `_reload_palette(theme, accent=None)` preserva o accent corrente quando
  não vem — a chamada legada de 1 argumento continua funcionando.
- **Seletor nas Configurações (`settings_screen.py`)**: pills customizadas
  (`_SwatchButton`) pintadas via QPainter com a **própria cor da paleta**
  na bolinha (não o `ACCENT` corrente), no FormRow "Cor de destaque".
  Persistido em `settings["accent_color"]` (`settings.json`), aplicado na
  hora ao clicar e restaurado pro verde no reset.
- **Aplicação reativa sem restart (`gui.py`, `sidebar.py`,
  `components.py`)**: `set_theme(theme, accent=None)` e
  `_on_theme_changed` reaplicam o QSS e chamam `restyle()` nos widgets
  que travavam a cor antiga — `_SidebarItem`/`Sidebar` (ícones + chip de
  sessão) e `SegmentedControl` (todos os botões re-estilizados).
- **`POSITIVE`/`DANGER` continuam semânticos**: P&L de alta/queda não
  muda com a paleta — só o destaque estético (o verde voltou a ser o
  histórico `#22C55E` pré-F11 como default).
- Validado: **20 testes novos** (17 em `tests/test_accent.py` + 3 hooks de
  MainWindow em `test_ui_smoke.py`) + suíte completa **2232 passed**.

## Shimmer & Microinterações de UI (03/08) — `1f39952`

Frente C do plano de polish: esqueletos de carregamento com brilho e
feedback visual-tátil de clique em toda a UI.

- **ShimmerController (`ui/shimmer.py`)**: singleton com **UM QTimer de
  80ms** animando a fase de brilho de todos os esqueletos sincronizados
  (dezenas de tiles + gráficos); o timer só roda enquanto há widget
  registrado e desliga sozinho quando o último sai. O controller é objeto
  Python puro (não-QObject) e recria o QTimer se o C++ dele morrer junto
  do QApplication — resiliência que o pytest exige (os testes destroem o
  app entre rodadas, e um QObject de módulo perdia o C++ sem aviso).
- **Skeletons em QPainter (`inventory_grid.py`, `widgets.py`)**:
  `SkeletonTile` no grid do inventário e estados de carregamento no
  `ValueChart`/`PriceHistoryChart` (linha + fill e barras de volume),
  desenhados com os tokens de superfície e a faixa de brilho na **Accent
  Color** da paleta configurável. O Mercado liga o loading na consulta/
  limpeza; a Conta liga enquanto não há série de valor carregada.
- **Microinterações visual-tátil**: estados `:pressed` com cor/feedback
  dedicados (diferentes do `:hover`, tokens `*_PRESSED`) em
  SegmentedControl, chips de filtro (Histórico e ActivityFeed), itens da
  Sidebar, `_SwatchButton` das Configurações e botão de categoria do
  Inventário.
- **Testes**: 27 novos em `tests/test_shimmer.py` — controller
  (registro/parada/limpeza/tick com widget destruído), visibilidade dos
  tiles (mostrado anima, escondido desregistra), transição esqueleto→
  dados, cor da faixa e troca de accent, e `:pressed` de cada componente.
  Suíte completa **2259 passed**.

## Refinamento do Inventário & Ordenação (04/08) — `7b3b646`

Segunda passada de polish no grid de inventário, fechada com 14 testes
novos e suíte completa **2273 passed**.

- **Badge de Wear/Desgaste no card**: pill semi-transparente (alpha=30,
  `fundo = QColor(TEXT) + setAlpha(30)`) no canto direito do topo, colado
  ao badge "No Mercado". A categoria é elidida pelo espaço que sobra em
  vez de passar por baixo dos pills. `_desgaste()` reconhece o wear nos
  DOIS idiomas (nome localizado pt-BR e `market_hash_name` cru em
  inglês); parênteses que não são condição — `(FT)`, `(Souvenir)`,
  `(Holo-Foil)`, nomes de evento — ficam de fora de propósito (um pill
  falso é pior que nenhum).
- **Iconografia ampliada**: `TILE_ICON_H` 108 → 120 e área de scale
  generosa (`TILE_W-12 × TILE_ICON_H-8`) — armas longas e facas crescem
  com a altura da faixa, aspecto sempre preservado (o ícone da Steam é
  quadrado; o vão lateral dos ícones quadrados é o preço do KeepAspect).
- **Tipografia do preço em destaque**: número primário do card subiu pra
  10pt bold com `PreferFullHinting` (o texto pequeno borrava sem hinting
  no Windows); a origem (saldo/fora) fica num corpo menor e muted ao lado.
- **P&L semântico**: verde `POSITIVE` lucro, vermelho `DANGER` prejuízo,
  `TEXT_MUTED` quando não há custo cadastrado (mesma regra da coluna da
  tabela — sync grava `cost=0.0` pra "não sei", então pnl vem `None` em
  vez de inventar zero). Helpers `_pnl_cor`/`_pnl_texto`.
- **Ordenação bidirecional (Asc/Desc)**: clicar no segmento já ativo
  alterna a direção, com seta `▲/▼` no segmento ativo e as demais
  limpas. Direção natural por chave (valor e qtd do maior pro menor,
  nome alfabético) e reset ao trocar de chave. `InventoryGrid` ganhou
  `_reverse`, `set_direction()`, `order()`/`reverse()` e
  `_aplicar_ordem()` (reordena sem recriar os tiles — recriar perderia a
  seleção e o ícone carregado); `SegmentedControl.set_label()` atualiza o
  rótulo sem trocar seleção; `_on_ordem`/`_atualizar_ordem_labels` na
  tela sincronizam as setas. Tooltip explica o gesto.
- **Testes (14 novos)**: `_desgaste` nos dois idiomas, container sem
  wear, parêntese não-wear ignorado; `_pnl_cor`/`_pnl_texto` (semântica
  das três faixas, "P&L —" sem custo); direção padrão por chave, toggle
  no clique repetido, `set_direction` repetida sem efeito, reset ao
  trocar de chave; setas dos segmentos na tela (nasce em Valor ▼, move ao
  trocar, inverte no clique repetido, alternar Grade/Tabela não toca a
  ordenação). Renderização do paintEvent conferida offscreen com todas as
  combinações (wear + listado, prejuízo, sem custo, nome cru).
- Validado com o app rodando de verdade: badges, preço e P&L visíveis no
  grid; alternância Asc/Desc pelos segmentos.

## Pacote de Funcionalidades Internas & Relatórios (04/08) — `93ceac3`

Pacote de funcionalidades internas & relatórios, fechado com 7 suítes de
testes novas (72 testes) e suíte completa **2345 passed** (100% verdes).

- **Metas Financeiras (`skinvault/goals.py` / `ui/goals_card.py`)**: metas
  de valor líquido/mercado/P&L/itens com barras de progresso reativas no
  AccountScreen, pintadas com a Accent Color da paleta configurável.
  `parse_target` entende os dois formatos numéricos — "5.000" = milhar
  pt-BR, "1234.56" = decimal — e `upsert_goal`/`remove_goal` devolvem a
  lista já normalizada com ids determinísticos (`g1…`). Metas persistem em
  `settings["goals"]`: sem arquivo novo em `data/`, o `backup.py` cobre de
  graça.
- **Calculadora de Taxas & Arbitragem (`skinvault/fee_calculator.py` /
  `ui/fee_calculator_dialog.py`)**: dado custo + margem desejada, mostra por
  quanto listar e quanto sobra em cada plataforma — Steam (`seller_added`,
  taxa sobre o que o vendedor RECEBE) + Skinport/CS.MONEY/DMarket
  (`percent_off`), ordenado por capital preso. O líquido da Steam é saldo,
  não dinheiro: a linha vem marcada e a UI nunca soma as duas moedas.
- **Exportação & Relatórios (`skinvault/reports.py` / `ui/exporter.py`)**:
  CSV com BOM UTF-8 (abre certo no Excel pt-BR), JSON estruturado e
  relatório HTML print-friendly (fundo branco, tinta escura, sparkline SVG
  inline, sem JS/asset externo). Botões no Inventário ("Exportar") e na
  Conta ("Exportar histórico").
- **Correções & Estabilidade**: o `FeeCalculatorDialog` preenchia cada
  célula com o NOME da coluna em vez do valor (`QTableWidgetItem(txt)` →
  `str(chave)`) — achado pelo teste, corrigido em `fee_calculator_dialog.py`.
  Fixture de `QApplication` dos testes de exportação marcada `autouse=True`:
  sem isso o `InventoryScreen()` era construído sem app e o PyQt6 abortava o
  processo com `0xC0000409` (mesma assinatura do AGENTS.md #8).
- **Testes**: 7 arquivos novos herméticos — `test_goals.py`,
  `test_fee_calculator.py`, `test_reports.py`, `test_goals_card.py`,
  `test_fee_calculator_dialog.py`, `test_inventory_export.py` — todos com
  `settings` mockado, sem tocar `data/` nem a rede.

## Pacote de UX, Sistema de Toasts & Custo Retroativo (04/08) — `fc276cc`

Pacote de UX de uma passada, fechado com 15 testes novos e suíte completa
**2360 passed** (100% verdes).

- **ToastManager (`ui/toast.py`)** — singleton QObject que centraliza o
  disparo de toasts sem duplicar o widget provado de `components.py`
  (`ToastWidget` subclasse emite `finished`). `toast_finished` dá feedback
  reativo sem acoplar a tela ao widget; atalhos `show_success`/`show_error`/
  `show_info`/`show_warning`. Resiliência ao ciclo C++ do Qt/pytest: se a
  `QApplication` (wrapper) morre e leva o singleton junto, `instance()`
  recria — no app real a `QApplication` vive a sessão inteira e o caminho
  nunca dispara.
- **GoalsCard CTA (`goals_card.py`)** — empty state interativo com botão
  "Criar primeira meta" que abre o `GoalsEditDialog` direto; a CTA some
  quando há metas cadastradas. Salvar avisa via toast "Metas atualizadas!".
- **Custo Retroativo no Histórico (`history_screen.py`)** — `RetroCostDialog`
  lista posições sem custo (sync Steam grava `cost=0.0` = "não sei") e grava
  via `portfolio.update_position_cost` (zero = drop). Sinal `costs_updated`
  ligado no `ScreenRouter` à reavaliação do `AccountScreen` — os KPIs da
  conta recalcularam reativamente, sem restart.
- **Toasts integrados** — exportações (Inventário e "Exportar histórico" da
  Conta) avisam "Relatório exportado com sucesso!"; copiar SteamID e o novo
  "Copiar link" do perfil avisam "Copiado para a área de transferência!".
- **Testes & Estabilidade** — 15 novos em `tests/test_ux_package.py` (ciclo
  de vida do toast, CTA de metas, reatividade do custo retroativo); assertiva
  do smoke test de copiar SteamID atualizada para o texto novo.

## Fila, em ordem

A interface gráfica e o fluxo de dados local estão em estado maduro.
Resta só a verificação externa abaixo, condicionada à Steam sair do
rate limit — não é trabalho pendente do lado do app.

### 1. `scanner_discovery` (bloqueado por fora, achado mais preciso em 08/08)
`discovery.py` escrito e testado, flag `scanner_discovery = False`. Nunca
completou uma chamada real.

**Verificado em 08/08/2026:** o bloqueio não é mais uniforme. Sondagem
pontual (script fora da suíte, `discovery.discover_category()` nas 6
categorias mapeadas):

- `search_market()` **sem facetas** (query de texto simples,
  ex. `"AK-47"`) responde normalmente — 3 resultados reais.
- `search_market()` **com facetas** (o parâmetro que toda categoria do
  discovery usa, ex. `{"type": "CSGO_Type_Rifle"}`) segue devolvendo
  `rate_limited`, count=10 ou count=100, tanto faz — confirmado em 2
  chamadas isoladas. As 6 categorias caíram todas no fallback.

**Conclusão:** são dois orçamentos de rate limit separados do lado da
Steam — texto simples recuperou, busca por faceta não. `scanner_discovery`
continua `False`. Uma próxima sondagem deve testar uma chamada **com
facetas** diretamente (não só uma busca de texto simples), senão o sinal
de "recuperou" é falso positivo.

A resiliência do fallback continua garantida na suíte:
- `discover_category` retorna `(None, SOURCE_FALLBACK)` em 429
  (`test_rate_limit_devolve_none`);
- `resolve_scan_items(enabled=True)` devolve a lista fixa intacta mesmo se
  a busca explodir em exceção;
- `scanner_discovery` permanece `False` no `settings.py` (default).

### 2. Fator de score "recência de aposentadoria" — não é viável hoje
Tentativa de virar a tese `caixa-aposentadoria-salto-e-decai` (+25,8%
líquidos, única que bate a taxa) em fator de `enhanced_score()`.
Planejada, aprovada, e abandonada no primeiro passo (curadoria de dado)
em 08/08/2026: **não existe fonte confiável de data de aposentadoria**
pras 36 caixas discontinued em `cases.py` (que só guarda ano de
lançamento). `items_game.txt` não cobre a era pré-2016 nem tem drop pool
na era CS:GO (achado já documentado em 29/07); pesquisa web num caminho
diferente hoje também não achou fonte única confiável, e a mecânica real
parece ter sido aposentadoria em lote (quebra a aproximação por ordem de
lançamento — a mesma que o vintage bonus já reprovou 4 vezes). Registrado
como achado negativo, comentário deixado em `signals.py` perto do bônus
de caixa (F7). Retomar só quando `gamedata.py` acumular eventos reais de
retirada (2023-12+) com retorno 365d já observado — hoje a amostra seria
zero ou quase. Detalhes: memória `negative-finding-retirement-recency-2026-08`.

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
  e só passava enquanto o arquivo estava vazio; os `test_screen_router_*`
  liam `settings.json` real e, com `welcome_seen` False, abriam um
  `WelcomeDialog` modal que travava a suíte (consertado em `14ed8d7` via
  `_hermetic_welcome`). Teste de UI que depende de `data/` do usuário é
  teste que passa ou trava conforme o estado da máquina de quem roda.
- **Não deixe `dlg.exec()`/`exec_()` de dialog modal alcançar teste
  offscreen.** O event loop modal nunca fecha sem interação — o teste não
  passa nem falha, trava. Se o fluxo sob teste pode abrir dialog, patch no
  `WelcomeDialog`/classe do dialog (padrão `_FakeWelcome`).
- **Não deixe teste de filtro temporal com ponto na fronteira da janela.**
  Um ponto exatamente no cutoff (`>=`) faz o assert virar loteria de
  microssegundos. Congele `time.time` ou afaste o ponto da fronteira.
- **Não rode a suíte com `--ui` em subprocess.** Vazava uma instância do
  app por rodada.
- **Não indexe `self._rows[row]`/`self._positions[row]` pelo índice
  VISUAL de uma `QTableWidget` com `setSortingEnabled`.** Ordenar por
  qualquer coluna desalinha a ordem visual da ordem de inserção — pegou
  o `ItemDetailDrawer` do Inventário (linha clicada ≠ item mostrado) e já
  tinha pegado a coluna Score/Origem antes. Guarde o dado real no
  `UserRole` da célula e busque por ele, nunca pela posição.

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
