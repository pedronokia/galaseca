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
- **Sem login, sempre.** Só dado público da Steam — nunca senha, cookie
  de sessão ou API key privada. Um login opt-in (F10) chegou a ser
  implementado e foi **revertido** em 2026-08-07: o Steam Subscriber
  Agreement proíbe de forma ampla automação de conta logada, com risco
  de terminação sem aviso (ver ROADMAP.md, seção FASE 10, para o
  histórico). `sync.py` sobrevive só como leitor dos dados já
  sincronizados antes da reversão.
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
├── sync.py         # leitores do historico de sync F10 (revertida)
├── signals.py      # tendência, anomaly, multi_trend, enhanced_score
├── cases.py        # ~50 cases + ~100 skins mapeadas, 58 sticker capsules, 30 autograph capsules
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
├── single_instance.py # guarda de instancia unica (QLocalServer)
├── gui.py          # MainWindow + dialogs grandes
└── ui/             # screens individuais (Athenas-style)
    ├── theme.py    # paleta + tipografia + helpers de stylesheet
    ├── components.py # Sidebar, Breadcrumb, Footer, Card, StatCard, SegmentedControl, Avatar
    ├── widgets.py  # MiniSparkline, DepthChart, MonthBarChart, ValueChart
    ├── screen_router.py
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

### 1. Convenção de porcentagem — **unificada para 0–100**

Todas as funções retornam `*_pct` / `*_rate` como percentual **0–100**.
Não multiplique por 100.

| Função | Retorno |
|---|---|
| `portfolio.position_pnl` → `pnl_pct` | **0–100** ✅ |
| `portfolio.evaluate_portfolio` → `totals.pnl_pct` | **0–100** ✅ |
| `portfolio.simulate_trade` → `roi_pct` | **0–100** ✅ |
| `trades.record_trade` → `pnl_pct` | **0–100** ✅ |
| `trades.trade_stats` → `win_rate` | **0–100** ✅ |
| `trade_matcher.summarize` → `win_rate` | **0–100** ✅ |

Unificado em 2026-06-06. Se adicionar função nova de pct, mantenha
0–100.

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

### 4b. O que o backtest mediu (2026-07-28)

Corpus de 123 séries, 324 mil pontos diários, 24.306 amostras, horizonte
90d. Rodado com `simulate_item(with_factors=True)` +
`cross_sectional_ic` / `factor_ic` / `quintile_spread`.

**O score briga consigo mesmo.** IC por fator:

| fator | IC | datas positivas |
|---|---|---|
| mediana | **+0,195** | 82,9% |
| verdict | **+0,166** | 81,0% |
| momentum | **−0,192** | 14,3% |
| multi_period | **−0,140** | 18,7% |
| **score completo** | **+0,051** | 59,8% |

`momentum` e `multi_period` cancelam `mediana` e `verdict`. Não é ruído:
o sinal de todos os fatores é estável nas duas metades cronológicas.
Invertendo os dois, o IC vai a **+0,207** (+0,209 / +0,204 por metade).

**Testado em 7 horizontes (7d a 365d)** — e o resultado refutou a primeira
explicação, que era "momentum funciona em prazo curto e reverte em 90d":

| horizonte | mediana | momentum | multi_period | vintage | case |
|---|---|---|---|---|---|
| 7d | **+0,346** | **−0,327** | −0,238 | +0,028 | +0,016 |
| 90d | +0,194 | −0,190 | −0,140 | +0,098 | +0,065 |
| 365d | +0,072 | −0,094 | −0,051 | ~~+0,221~~ | **+0,117** |

> **As colunas `vintage` desta tabela estão contaminadas** (descoberto em
> 2026-07-29). `enhanced_score` calculava a idade do container como
> `date.today().year - year`, ignorando o instante simulado — então toda
> amostra de uma caixa de 2013 recebia o bônus, inclusive as de 2013,
> quando ela tinha 0 anos. O fator era constante por item e o IC media
> conhecimento do futuro. Corrigido via `now_ts`; ver 4c e o comentário do
> `_VINTAGE_BONUS_ENABLED`. A coluna `case` sofre de um problema parecido
> mas não corrigível hoje: `case_status` devolve o status de HOJE, então
> uma caixa aposentada em 2018 aparece como descontinuada também nas
> amostras de 2015 — falta data de aposentadoria no catálogo.

**Momentum é negativo em TODOS os horizontes, e mais forte no mais curto.**
Não há regime em que ele acerte. O mercado reverte à média em toda escala
medida — não existe janela de momentum pra preservar.

Mas existem **duas famílias com horizontes opostos**:

- **Curto prazo, reversão à média** — `mediana`, `verdict`, e
  `momentum`/`multi_period` invertidos. Mais fortes em 7d, decaem com o
  horizonte.
- **Longo prazo, estrutural** — `vintage` e `case`. Quase nulos em 7d,
  máximos em 365d. É oferta se ajustando ao longo de anos, o mesmo
  mecanismo do drop pool.

Somar as duas num número só dilui ambas. Separar o score por horizonte
continua fazendo sentido, mas por este motivo — não pelo que estava
escrito aqui antes.

**Nada disso vence a taxa.** Quintil superior do score corrigido:
+13,64% brutos em 90d. Com os 15% da Steam: **−1,18% líquidos**. A 2% de
taxa (mercado terceiro), os mesmos 13,64% viram +11,41%.

> **Correção de 2026-07-30 — o break-even é 15%, não 17,65%.** O texto
> anterior dizia 17,65% porque `backtest.net_after_fee` usava
> `preço × (1 − taxa)`, tratando a taxa como percentual do preço de
> compra. **Não é o que a Steam faz:** a taxa incide sobre o valor do
> *vendedor*. Você lista a R$ 115, o comprador paga 115, você recebe
> 115/1,15 = 100 — logo o break-even é exatamente a taxa.
> `portfolio.net_proceeds` sempre usou o modelo certo; os dois módulos
> discordavam em silêncio. Corrigido, com teste que trava os dois juntos
> (`test_backtest_e_portfolio_concordam`). A conclusão qualitativa não
> muda — 13,64% ainda não cobre 15% — mas a margem é bem menor do que o
> texto original sugeria.

**Drop pool, medido:** caixa aposentada rendeu +20,3%/ano de mediana nos
últimos 3 anos (8 de 8 positivas); caixa no pool ativo, −13,4%/ano.
Kilowatt −80,8%/ano. Sair do pool é quando a valorização começa, não
quando acaba. Ressalva: n=4 e n=8, e idade está confundida com
aposentadoria.

Ao mexer no score, meça antes e depois — a infraestrutura está pronta.

### 4c. Aposentadoria de caixa: o efeito é um SALTO que depois DECAI (2026-07-29)

41 caixas, séries diárias completas da listing page, retorno 365d em
janelas rolando (passo 30d) dentro dos **últimos 3 anos** — mesma janela
de calendário pra todas, então regime de mercado fica controlado. Unidade
de análise é a CAIXA (janelas sobrepostas na mesma série são
autocorrelacionadas; contar amostras daria precisão falsa).

| grupo | n | mediana | líquido (15%) | positivas | pior caixa |
|---|---|---|---|---|---|
| aposentadas | 35 | **+48,0%** | **+25,8%** | 35/35 | +7,8% |
| pool ativo | 5 | +18,9% | +1,0% | 3/5 | **−50,1%** |

**A ressalva de idade do 4b ("idade está confundida com aposentadoria")
foi resolvida — e o resultado inverteu a suspeita.** Por coorte:

| coorte | n | mediana | líquido |
|---|---|---|---|
| ativo 2022-25 | 5 | +18,9% | +1,0% |
| **aposent. recente 2019-21** | 7 | **+78,3%** | **+51,6%** |
| aposent. média 2015-18 | 16 | +49,2% | +26,8% |
| aposent. antiga 2013-14 | 12 | +32,4% | +12,5% |

Há um **salto de 4x exatamente na fronteira** ativo → recém-aposentada, e
daí em diante o retorno **cai** com a idade.
`Spearman(idade, retorno)` dentro das aposentadas = **−0,762**.

Ou seja: não é "velha rende mais". É a aposentadoria que dispara uma
re-precificação, que **se esgota** ao longo dos anos seguintes. O
mecanismo bate: sai do drop pool → oferta para de crescer → preço
re-precifica → efeito exaure.

Isso **vence a taxa com folga** (+25,8% líquidos), ao contrário do flip de
90d do 4b (−3,41% líquidos). É a única tese medida aqui que fecha a conta.

Limites que continuam de pé:

- **n=5 no pool ativo é o gargalo e não tem como crescer** — só existem 6
  caixas ativas. Gallery (2024) tem n=10 janelas; Fever (2025) nem entrou.
- mediana-a-mediana, ignora spread de compra/venda;
- 3 caixas faltando (Bloodhound, Operation Shattered Web, Snakebite);
- ~~`_CASES` parece ter entrada duplicada~~ — confirmado e corrigido em
  2026-07-29: `Operation Shattered Web Case` e
  `Operation Bloodhound Weapon Case` não existem no Market (ver #12 pro
  método do `<title>`). Removidas.

**A data de aposentadoria NÃO é recuperável do histórico do items_game.txt**
(tentado e descartado em 2026-07-29). O estudo mostrou que a variável que
importa é *anos desde a aposentadoria*, e `cases.py` só guarda ano de
lançamento + status atual. As duas barreiras:

1. **O histórico começa em 2016-12.** `GameTracking-CSGO` tem 133 commits
   de `items_game.txt` (2016-12 a 2023-08) e `GameTracking-CS2` tem 53
   (2023-12 a hoje). A coorte 2013-14 aposentou antes da janela.
2. **O config da era CS:GO não contém o drop pool.** Verificado no
   snapshot de 2019-07: `timed_drop` 0 ocorrências, `drop_pool` 0,
   `prime` 0, e nenhum atributo por caixa marcando "ativa". Os únicos
   arquivos no diretório são `items_game.txt`, `items_game_cdn.txt` (mapa
   de ícone, 238 KB) e `items_game_live.txt` (102 bytes). A informação de
   pool vivia no servidor da Valve, não no cliente.

`set_timed_drops_*`, que é o que `gamedata.py` extrai, **só existe na era
CS2** — o watcher funciona de 2023-12 pra frente e não retro-alimenta.
Consequência: um fator de "anos desde aposentadoria" não tem como ser
backtestado hoje, e por isso não entrou no score.

### 4d. O teto de valorização é o PREÇO ABSOLUTO (2026-07-30)

Pergunta do usuário: "os itens têm teto de valorização? não sei quando
vender". Medido em 84 itens com 500+ pontos diários (41 caixas, 43
skins), 7.541 amostras, horizonte 365d, passo 30d.

**Corte cross-sectional** — itens rankeados *entre si na mesma data*,
janelas de 90d. Sem isso o regime de mercado contamina tudo: numa alta
geral, todo item tem alta recente **e** retorno futuro alto.

| fator | IC | datas positivas |
|---|---|---|
| **preço absoluto** | **−0,2635** | 20% |
| — só caixas | **−0,3036** | 24% |
| — só skins | −0,0415 | 46% |
| **distância do topo histórico** | **−0,2033** | 22% |
| alta dos últimos 90d | +0,0500 | 61% |

**O teto existe e é o preço.** Quanto mais caro o item, menos ele
valoriza — negativo em 76-80% das janelas. Mediana do retorno 365d por
faixa:

| faixa | mediana | itens |
|---|---|---|
| R$ 0–1 | **+73,0%** | 43 |
| R$ 1–5 | +41,1% | 53 |
| R$ 5–20 | +44,0% | 48 |
| R$ 20–100 | +27,4% | 39 |
| R$ 100–500 | +18,7% | 21 |
| R$ 500+ | **+8,7%** | 17 |

Isso generaliza a memória `clutch-case-falling-knife`: não era um caso
isolado, é o padrão. E o efeito é **muito mais forte em caixas**
(−0,30) do que em skins (−0,04) — não é só "tipo de item".

**Sobre quando vender:** `distância do topo` tem IC −0,20. Perto da
máxima histórica, o retorno futuro cai. No corte simples por bucket esse
sinal aparecia **plano** — só surge controlando por data, o que é a
lição metodológica aqui.

**O que NÃO se sustentou:** o corte simples sugeria que comprar *depois*
de alta forte funcionava (+40,2% de mediana no bucket "subiu 50-100% em
90d"). Controlando por data, o IC vai a +0,05, e a +0,003 em caixas.
Era regime de mercado, não sinal.

Limites: os 84 itens são os que estavam no `ssr_cache`, não uma amostra
aleatória — há viés de sobrevivência (a série existe porque o item ainda
negocia). E o score **não vê preço absoluto**, que por esta medição é o
fator mais forte a 365d que já medimos.

### 4e. Reversão à média aplicada ao score — só em skins (2026-10-17)

O 4b mediu `momentum` e `multi_period` com IC negativo em todos os
horizontes, mas o score continuou pró-tendência por quase 3 meses. Agora
o sinal é `_MOMENTUM_SIGN`/`_MULTI_PERIOD_SIGN = -1`. Re-medido em corpus
maior: 373 séries com 500+ pontos do `ssr_cache`, passo 14d, ~50-58 mil
amostras por horizonte, IC transversal (`cross_sectional_ic`).

| universo | horizonte | IC antes | IC depois | mediana quintil sup. antes → depois |
|---|---|---|---|---|
| skins | 7d | 0,055 | **0,301** | +0,12% → +4,39% |
| skins | 90d | 0,035 | **0,160** | +3,94% → +9,35% |
| skins | 365d | 0,001 | **0,052** | +19,4% → +25,0% |
| caixas | 7d | 0,036 | 0,150 | +0,56% → +1,79% |
| caixas | 90d | 0,024 | 0,070 | +9,13% → +10,17% |
| caixas | 365d | 0,065 | 0,064 | **+66,8% → +59,9%** |

Em caixas a 365d a reversão **piora** (Spearman agregado −0,068, quintil
superior perde 7 p.p.) — e é o horizonte da tese de aposentadoria (4c),
a única que vence a taxa. Por isso a inversão vale **só fora de
container** (`_REVERSAL_IN_CONTAINERS = False`). É a confirmação das "duas
famílias" do 4b: reversão no curto prazo; em caixa, o longo prazo é
estrutural.

**Ainda não vence a taxa no curto prazo.** Skins 90d com o score novo:
quintil superior +9,35% bruto, abaixo dos 15% da Steam. O ganho é de
**ranking** (escolher melhor entre itens), não licença pra flipar.

**Achado negativo:** desligar o bônus de drawdown "no topo + subindo"
(`_DRAWDOWN_AT_HIGH_ENABLED`) não passou no critério — ΔSp +0,007 / +0,0002
/ −0,003 em 7d/90d/365d. Ficou ligado.

Outros ICs de fator no corpus novo, para a próxima rodada: `price_level`
+0,155 e `liquidity` +0,141 em 365d (os dois maiores do longo prazo);
`trend` ≈ 0 em 90d.

### 5. `_find_query` prioriza match exato (corrigido em 2026-07-28)

Ordem de preferência, independente da ordem de iteração do SSR:

1. igualdade exata do nome
2. substring (`item_name in cached_name`, para nome parcial do chamador)
3. skin root, só com `loose_match=True`
4. queryKey sem slot de nome

**Por que a ordem importa.** Antes era substring puro, pegando o
primeiro que casasse. Mas `"Souvenir X"` e `"StatTrak™ X"` **contêm**
`"X"` — e uma listing page traz até 10 variantes do mesmo skin. Medido
numa página real: pedindo `AK-47 | Redline (Field-Tested)` voltava a
série da **Souvenir**, com 1 ponto de histórico, enquanto a correta
estava na mesma resposta com **5188**.

Falhava em silêncio, e contaminava tudo que deriva de `price_history`:
tendência, momentum, multi-período, SMA, suporte/resistência — até 30
dos 100 pontos do score, calculados sobre 1 ponto do item errado.

Ao mexer aqui, não volte a retornar no primeiro match do laço.

### 5a. Naming `(Holo-Foil)` com hífen é o correto

Verificado em 2026-06-09 contra SSR real: o Steam Market **preserva
o formato** que você passa na URL. `(Holo-Foil)` com hífen retorna
pricehistory + orderbook + description com dados completos.
`(Holo/Foil)` com barra retorna apenas description sem dados.
Portanto:

- `_CAPSULES` mantém hífen (já está correto desde F1).
- **Não "corrija"** para barra — quebra SSR data.
- Search page exibe `/` mas listing page preserva `-`.

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

### 9. Instância única — o sinal é a conexão, não uma mensagem

`minimize_to_tray_on_close` faz o X esconder na bandeja. Quem não percebe
reabre pelo atalho e empilha processos: **29 vivos ao mesmo tempo**, todos
gravando nos mesmos JSON de `data/` sem lock nenhum. `save_portfolio` e os
caches reescrevem o arquivo inteiro, então a última gravação apaga o que as
outras fizeram. `single_instance.py` fecha isso com um `QLocalServer` cujo
nome é um sha1 do `DATA_DIR` (case-folded — `C:\SkinVault\data` e
`c:/skinvault/data` precisam colidir).

**Não tente mandar payload no ping.** Medido no Windows: o cliente conecta,
escreve, dá `flush()` e `disconnectFromServer()`; o servidor recebe
`newConnection` com `bytesAvailable() == 0` e depois `disconnected`, sem
nunca disparar `readyRead`. O payload some. Testadas e todas falharam:
`waitForBytesWritten`, `waitForDisconnected` no cliente,
`waitForReadyRead` no servidor. Só entrega se o cliente mantiver o socket
vivo — e o cliente aqui é um processo que existe para morrer em seguida.

Por isso a **conexão em si** é a mensagem. Consequência aceita: qualquer
processo que abra o pipe faz a janela subir.

Duas outras decisões que parecem bugs e não são:

- Falha ao criar o servidor devolve `True` (abre sem proteção). Um app que
  se recusa a abrir sem ninguém concorrendo é pior que um app sem guarda.
- `listen()` falhando **não** chama `removeServer()` direto: primeiro tenta
  conectar de novo. Remover às cegas mataria o servidor da instância viva
  que acabou de ganhar a corrida.

### 10. Persistência: nunca use `write_text` direto em `data/`

Use `_paths.atomic_write_text` / `atomic_write_bytes`. Eles gravam num
temporário no **mesmo diretório** e trocam com `os.replace`.

`Path.write_text` **trunca** o destino antes de escrever. Morrer no meio
deixa JSON cortado — e as workers do app são threads daemon, mortas de
supetão no fim do interpretador (gotcha #7). O agravante é o par com o
load: todo loader tratava JSON inválido como "vazio", então o **próximo
save gravava o vazio por cima**. Perda definitiva, sem uma linha de log.

Do lado da leitura, `_paths.load_json_record(path, default)`:

- ausente ou ilegível → `default`, sem drama;
- presente mas não parseia → vai pra `<nome>.corrupt` e devolve `default`;
- parseia com tipo errado → **não** vai pra quarentena. Isso é bug de
  código ou arquivo de outra versão, não truncamento; mover esconderia.

Use em arquivo de **registro** (portfolio, trades, watchlist, histórico,
`ssr_cache`). Em cache barato, virar vazio em silêncio é o certo — encher
`data/` de `.corrupt` de cache é só ruído. `ssr_cache` conta como registro
apesar de ser cache: são ~265 séries acumuladas contra um endpoint
agressivamente rate-limited, e refazer custa dias.

Detalhes que parecem excesso e não são:

- **`fsync` antes do replace.** Medido em 2026-07-29 no `ssr_cache.json`
  real (43 MB): +10ms, 27% sobre um write de 35ms. Barato pelo que
  compra. Em arquivo de 1 KB o custo total sai de 0,3ms pra 2,6ms — a
  suíte inteira ficou ~10s mais lenta, e vale.
- **`except BaseException`** ao limpar o temporário: `KeyboardInterrupt`
  não herda de `Exception`, e o `.tmp` não pode sobreviver a nenhum
  aborto.
- **`newline` default** (não `""`): mantém a tradução pra CRLF que o
  `write_text` fazia. Validado: os 17 JSON do `data/` real fazem
  round-trip byte-a-byte idêntico.
- **`ensure_data_dir()` varre `*.tmp`** no startup — um `kill -9` no meio
  da escrita não roda `except` nenhum, e sem a varredura eles acumulam.

### 11. Render offscreen mente sobre duas coisas

Renderizar o `ScreenRouter` com `QT_QPA_PLATFORM=offscreen` e amostrar
luminância é o jeito certo de validar **layout, tema e hierarquia** sem
pedir print pro usuário. Mas ele erra em dois pontos, os dois medidos em
2026-07-29 depois de quase virarem "correções" de bugs inexistentes:

**1. Animação não avança com `processEvents()`.** `LoadingState.showEvent`
chama `fade_in()`, que instala um `QGraphicsOpacityEffect` em 0.0 e anima
até 1.0 em 150ms. `processEvents()` não faz o relógio andar, então o
widget renderiza **totalmente invisível** e parece que o estado não
funciona. Bombeie com tempo real antes do `render()`:

```python
fim = time.time() + 0.5
while time.time() < fim:
    app.processEvents(); time.sleep(0.01)
```

(O `fade_in` só dispara com a janela visível — é por isso que os testes,
que nunca dão `show()`, ficam determinísticos. O guard está lá de
propósito.)

**2. O fallback de fonte é mais pobre que o do app real.** Offscreen,
`◴◷◶◵` (spinner do `LoadingState`) e `◇` (ícone do `EmptyState`) saem
como **tofu** — retângulo vazio. Na plataforma `windows` os mesmos
codepoints renderizam normalmente. `QFontMetrics.inFontUcs4()` também
diz que faltam, porque só olha a família primária e ignora o fallback.

Antes de "consertar" um glifo, repita o teste com a plataforma nativa
(`QPixmap` + `QPainter`, sem `show()`, não rouba foco) e compare a
assinatura de tinta com um codepoint da área de uso privado (``),
que é tofu garantido.

### 12. A listing page também é racionada — e falha em SILÊNCIO

O gotcha #3 e as notas antigas diziam que a listing page continua
respondendo quando `priceoverview`/`search` estão em 429. **É verdade só
até certo volume.** Medido em 2026-07-29 buscando as séries das caixas:

- as 17 primeiras páginas voltaram completas (~5000 pontos cada);
- a partir daí, **HTTP 200, corpo de 210 KB, e nenhum dado**: sem
  `Market_LoadOrderSpread`, sem `var line1`, sem `g_rgAssets`.

A Steam serve a casca da página em vez de recusar. Isso é pior que um 429
para quem consome:

- o status diz sucesso, então nenhum retry/backoff dispara;
- o corpo é grande, então checar tamanho não detecta;
- `get_market_page_data` devolve None, e o chamador lê isso como
  **"este item não tem histórico"** — que é uma afirmação falsa sobre o
  item, não sobre a rede.

Ao varrer muitos itens, trate `page sem price_history` como **suspeita de
throttle**, não como fato: se vários itens seguidos vierem vazios, pare a
varredura. Um item real sem histórico é raro; dez seguidos é bloqueio.

`ssr_cache.cached_price_history` não cacheia o None, então não há
envenenamento (ao contrário do que acontecia com `prices` — ver #10). Mas
o scanner e a watchlist exibem esses itens como "sem dado".

**Erro de método a não repetir:** o script que descobriu isso sondava
`_http_get` antes de chamar `get_market_page_data`, pra detectar 429 —
e com isso fazia **duas requisições por item**, dobrando o consumo
justamente no endpoint que queria poupar. Se precisar do status, use o
retorno de `get_market_page_data` e não uma sonda separada.

### 13. Cadência segura entre requisições ao Market (2026-08-07)

Um scan de "Todas as categorias" (centenas de itens, 2 chamadas cada)
estourou 429 de verdade na sessão real. Pesquisado depois: os throttles
espalhados pelo projeto usavam 1.0–2.0s entre chamadas (30–60 req/min).
Fontes públicas (discussões da comunidade Steam + ArchiSteamFarm — ver
`skinvault/steam_api.py:RATE_LIMIT_DELAY_S`) citam limite prático de
~20 req/min no endpoint de mercado/inventário, com ~4s como margem
segura recomendada. **Todos os pontos que dormiam entre chamadas foram
migrados pra usar `steam_api.RATE_LIMIT_DELAY_S`** (Scanner, Watchlist,
Account, `PriceWorker`, `value_inventory`, `sync.py`) em vez de número
mágico duplicado — mudar o valor uma vez ajusta o app inteiro.

**429 não é ban.** A Valve não bane por IP (só por conta, e só por
fraude/trapaça/chargeback — não por tráfego de leitura pública). O
bloqueio observado dura minutos a poucas horas segundo relatos da
comunidade, nunca é permanente, e não afeta a conta de forma alguma.

**Armadilha de teste:** `steam_api.RATE_LIMIT_DELAY_S` referenciado
direto em cada call site (nunca copiado pra uma constante de módulo tipo
`_X = steam_api.RATE_LIMIT_DELAY_S` nem usado como default de parâmetro
tipo `def f(throttle=steam_api.RATE_LIMIT_DELAY_S)`) — os dois congelam
o valor na hora da importação/definição, e um monkeypatch depois nunca
alcança quem já capturou o número antigo (`value_inventory` e
`sync._HISTORY_THROTTLE_S` caíram nisso, corrigidos pra resolver em
tempo de chamada). `tests/conftest.py` zera a constante via fixture
`autouse` pra suíte inteira não dormir de verdade.

## Persistência (arquivos em `data/`)

- `prices.json`, `portfolio.json`, `history.json`, `item_history.json`
- `volume_history.json`, `supply_history.json`
- `watchlist.json`, `trades.json`, `steamids.json`, `settings.json`
- `alerts_log.json`, `rankings.json`
- `steam_market_events.json`, `active_listings.json`, `trade_history.json`
  (histórico da sync F10, revertida — mantidos por decisão do usuário,
  só lidos hoje via `sync.py`, nunca mais escritos)

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
