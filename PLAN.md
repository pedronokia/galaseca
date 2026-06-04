# SkinVault — Plano de Execução (handoff completo)

> Documento autossuficiente pra continuar o projeto em **outra IA/sessão** (OpenCode)
> que NÃO tem a memória de como ele nasceu. Leia da seção 0 à 3 antes de codar.

---

## 0. Prompt pronto pra colar no OpenCode (bootstrap de contexto)

```
Estou continuando um projeto Python chamado SkinVault, em C:\SkinVault.
É um app DESKTOP local-first (PyQt6) para quem compra/vende skins de CS2 no
Steam. Princípio inegociável: ele lê APENAS dados PÚBLICOS do Steam (SteamID +
preços do Market) e NUNCA pede login/senha/cookie — esse "sem login" é o
diferencial de confiança contra extensões tipo SIH. Já existe um MVP funcional
com testes. Leia PLAN.md e README.md inteiros antes de qualquer coisa. Rode os
testes (python -m pytest tests/ -q) e me diga o que entendeu do estado atual e
qual é a próxima tarefa do roadmap (seção 3 do PLAN.md). Não quebre os princípios
da seção 6. Trabalhe uma tarefa por vez, com testes, e me mostre antes de commitar.
```

---

## 1. O que JÁ existe (estado atual)

**4 commits, 21 testes passando.** Roda sem instalar nada (usa stdlib `urllib`);
PyQt6 só é necessário pra UI (`--ui`).

### Estrutura
```
C:\SkinVault\
  README.md            visão/posicionamento/monetização
  PLAN.md              este arquivo
  VALIDATION_POST.md   post pronto pra validar demanda (fazer CEDO)
  requirements.txt     PyQt6, httpx (httpx ainda não usado; stdlib por ora)
  .gitignore           (data/ é ignorado, exceto data/.gitkeep)
  skinvault/
    __init__.py        __version__ = "0.0.1"
    __main__.py        CLI: <steamid> | --ui | --portfolio | --add
    steam_api.py       dados públicos do Steam (inventário + preço)
    prices.py          PriceCache (TTL 6h, persiste) + backoff + value_inventory + cached_price
    history.py         snapshots {ts,total} -> série do gráfico
    portfolio.py       fee-aware: net_proceeds, break_even, position_pnl, evaluate_portfolio + persistência
    gui.py             janela PyQt6 (SÓ a aba de Inventário por enquanto)
  tests/
    test_steam_api.py  parse BRL, join/agrega, status (private/rate/empty/ok/error)
    test_prices.py     cache hit/miss/TTL/persistência, value_inventory
    test_history.py    snapshot roundtrip + cap
    test_portfolio.py  matemática da taxa, totais, sem-preço, roundtrip
  data/                (LOCAL, gitignored) prices.json, history.json, portfolio.json
```

### O que funciona (provado ao vivo)
- `get_market_price("AK-47 | Redline (Field-Tested)")` -> R$ real do Steam Market.
- `value_inventory(steamid)` -> avalia inventário público inteiro (com cache+backoff).
- `--portfolio` -> lucro REAL pós-taxa + break-even (matemática honesta).
- `--ui` -> janela abre, avalia inventário, gráfico de valor no tempo, erro inteligente.

### O que está parcial / pendente
- `gui.py` só tem a aba **Inventário**. NÃO tem aba **Portfólio** ainda (Tarefa 1).
- Sem watchlist/alertas, sem fair-value de compra, sem empacotamento .exe.
- `requirements.txt` lista httpx mas o código usa `urllib` (stdlib). Manter ou migrar.

### Como rodar / testar
```
cd C:\SkinVault
python -m pytest tests/ -q                 # 21 testes
python -m skinvault                         # ajuda
python -m skinvault <SteamID64>             # avalia inventário (CLI)
python -m skinvault --portfolio             # portfólio fee-aware
python -m skinvault --add "AWP | Asiimov (Field-Tested)" 650 1
python -m skinvault --ui                    # janela
```

---

## 2. Convenções e GOTCHAS (não repetir erros já descobertos)

1. **Console Windows é cp1252** — `print()` com emoji/★/™ QUEBRA (UnicodeEncodeError).
   Em saída de terminal use ASCII; `__main__.main()` já faz `sys.stdout.reconfigure(errors="replace")`.
   Na UI (Qt) pode UTF-8 à vontade.
2. **Steam inventário 400 é AMBÍGUO.** Pode ser privado, VAZIO (conta sem skins),
   ou rate-limit disfarçado. NÃO afirme "privado" com certeza. (Descoberto: settings
   em "Público" e mesmo assim 400 — porque a conta de teste não tem skins.)
3. **Taxa do Steam ~15%** cobrada sobre o que o VENDEDOR recebe:
   - `net_proceeds(price) = price / 1.15` (o que você recebe de fato)
   - `break_even_price(cost) = cost * 1.15` (preço de listagem pra empatar)
   - "Vale mais que paguei" NÃO é lucro até passar por essa conta.
4. **Rate-limit do Market** (~20 req/min no priceoverview). Por isso `PriceCache`
   (TTL 6h, persiste) + backoff. Só bater na rede em cache MISS.
5. **`_http_get(url) -> (status, body)` é a ÚNICA camada de rede** — é o ponto de
   MOCK nos testes. Não chame `urllib` direto em outras funções.
6. **Testes não podem importar `gui.py`** (puxa PyQt6). Mantenha a lógica
   (steam_api/prices/history/portfolio) livre de PyQt6.
7. **Windows: evitar here-string `@'...'@` em `git commit -m`** no PowerShell —
   quebrou com `/`. Use `git commit -F arquivo_msg.txt`.
8. **Nomes de item** devem ser EXATOS como no Market (ex.: "AK-47 | Redline (Field-Tested)").
   Variações/wear sem listagem -> preço None (tratar).

---

## 3. ROADMAP (tarefas executáveis, em ordem)

> Cada tarefa: objetivo, arquivos, e "pronto quando" (critério de aceite).
> Trabalhar UMA por vez, com testes, commit pequeno.

### Tarefa 1 — Aba "Meu Portfólio" na UI  ⭐ (próxima)
- **Objetivo:** levar o `--portfolio` (já pronto na lógica) pra janela.
- **Arquivos:** `skinvault/gui.py`.
- **Como:** transformar `MainWindow` em `QTabWidget` com 2 abas: "Inventário"
  (a atual) e "Meu Portfólio". Na aba portfólio: tabela
  [Item, Custo, Vale, Recebe, Lucro Real, Break-even] com lucro colorido
  (verde/vermelho), linha de totais, um formulário (nome + custo + qtd +
  botão "Adicionar" -> `portfolio.add_position`) e botão remover. Avaliar em
  thread com `portfolio.evaluate_portfolio(positions, lambda n: prices.cached_price(n, cache))`.
- **Pronto quando:** `python -m skinvault --ui` -> aba Portfólio -> adiciono
  posição -> vejo lucro real pós-taxa colorido + totais. (Render = smoke test manual.)

### Tarefa 2 — Anti-ripoff do comprador (fair-value de compra)
- **Objetivo:** "essa listagem está X% acima/abaixo da mediana de vendas".
- **Arquivos:** `steam_api.py` (+ UI campo de consulta).
- **Como:** `get_market_overview(name) -> {lowest, median, volume}` (o endpoint
  priceoverview já traz lowest_price, median_price, volume — parsear os 3).
  Veredito: comparar lowest vs median.
- **Pronto quando:** consulto um item e vejo "menor listagem R$X, mediana R$Y,
  você pagaria Z% acima da mediana". Teste do cálculo do veredito.

### Tarefa 3 — Sinais de valorização (versão HONESTA, não bola de cristal)
- **Objetivo:** ajudar a decisão SEM prometer previsão.
- **Como:** (a) tendência factual sobre a série que NÓS observamos (snapshot de
  preço por item ao longo do tempo, tipo o history do inventário);
  (b) flag de "caixa descontinuada" (oferta encolhe -> tende a subir; é sinal
  explicável, não mágica); (c) flag de volatilidade/liquidez (volume baixo).
- **IMPORTANTE:** NUNCA rotular como "vai valorizar / previsão". Só "subiu X% em
  N dias" (descritivo) + sinais de oferta. Ver seção 6.
- **Pronto quando:** vejo tendência factual + flags, sem nenhuma promessa de futuro.

### Tarefa 4 — Watchlist + alertas de preço
- **Objetivo:** "me avisa quando a skin X cair abaixo de R$Y".
- **Arquivos:** novo `watchlist.py` (persistência `data/watchlist.json`) + UI +
  notificação desktop.
- **Como:** lista [{name, target}]; loop em background respeitando rate-limit
  (reusar `cached_price`); quando preço <= target -> notificação (Qt
  QSystemTrayIcon.showMessage).
- **Pronto quando:** adiciono item+alvo, e quando o preço cruza, recebo notificação.

### Tarefa 5 — Empacotar .exe (PyInstaller)
- **Objetivo:** distribuir sem o usuário ter Python.
- **Como:** spec do PyInstaller (incluir PyQt6). Entry = `python -m skinvault --ui`
  (criar um `run.py` ou `__main__` que abra a UI por padrão no .exe).
- **Pronto quando:** `dist/SkinVault/SkinVault.exe` abre a janela.

### Tarefa 6 — VALIDAÇÃO (fazer CEDO, em paralelo — não é a última!)
- **Objetivo:** confirmar que o público paga ANTES de muito código.
- **Como:** postar o conteúdo de `VALIDATION_POST.md` (r/csgomarketforum,
  r/SideProject, Discords de trade — ler regras de self-promo). Medir interesse.
- **Critério de decisão:** se em ~3 comunidades ninguém quiser testar nem pagar,
  repensar o ângulo (ou focar em renda de freela, que paga rápido).

---

## 4. Monetização (quando validar)
- App desktop vendido como **licença via Gumroad/Lemon Squeezy** (eles cuidam do
  pagamento; você gera a chave). **Freemium:** grátis o básico (valor do
  inventário), pago o pro (portfólio fee-aware, alertas, histórico longo).
- O cliente paga VOCÊ em vez do tool web grátis porque confia: dados no PC dele.

---

## 5. Roadmap visual (resumo)
```
[v0 feito] inventário + preço + portfólio fee-aware (CLI) + UI inventário
   |
Tarefa 1  aba Portfólio na UI          <- PRÓXIMA
Tarefa 2  fair-value de compra (anti-ripoff)
Tarefa 6  VALIDAÇÃO (paralelo, cedo!)
Tarefa 3  sinais de valorização (honestos)
Tarefa 4  watchlist + alertas
Tarefa 5  empacotar .exe + distribuir
   |
[se validar] monetizar (Gumroad freemium)
```

## 6. PRINCÍPIOS que NÃO podem quebrar
1. **Nunca** pedir login/senha/cookie/sessão. Só dado público. (É o moat.)
2. **Matemática honesta:** sempre mostrar o lucro REAL pós-taxa, não a aparência.
3. **Nada de "prever vencedores"/"vai valorizar"** — é a armadilha da bola de
   cristal (mesmo erro de trading bot). Mostre dados/sinais; a pessoa decide.
4. **Lógica testada** e livre de PyQt6 (UI separada).
5. Público-alvo = **comprador/colecionador** (não flipador — flip esbarra na
   taxa 15% + Wallet que não saca).

## 7. Contexto humano (por que este projeto existe)
Nasceu como pivô saudável: trocar "ganhar dinheiro automático/apostando" por
"criar valor com a skill que já tenho". É aposta de **portfólio EM CIMA** de renda
ativa (freela), não no lugar dela. O objetivo realista não é "ficar rico" — é um
produto honesto que cria valor e compõe. Mantenha esse norte.
```
```
