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
| 365d | +0,072 | −0,094 | −0,051 | **+0,221** | **+0,117** |

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
+13,64% brutos em 90d. Com os 15% da Steam: **−3,41% líquidos**. O bruto
mínimo pra empatar é **17,65%**, não 15% — a taxa incide sobre a venda,
não sobre o lucro (`net_after_fee` / `breakeven_gross`). A 2% de taxa
(mercado terceiro), os mesmos 13,64% viram +11,37%.

**Drop pool, medido:** caixa aposentada rendeu +20,3%/ano de mediana nos
últimos 3 anos (8 de 8 positivas); caixa no pool ativo, −13,4%/ano.
Kilowatt −80,8%/ano. Sair do pool é quando a valorização começa, não
quando acaba. Ressalva: n=4 e n=8, e idade está confundida com
aposentadoria.

Ao mexer no score, meça antes e depois — a infraestrutura está pronta.

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
