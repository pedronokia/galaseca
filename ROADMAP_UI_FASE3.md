# SkinVault — Roadmap de UI Fase 3: linguagem visual "botcloud" (tokens YouTube)

> **Audience:** próximo agente (opencode/outro) que vai executar isto do zero.
> **Você NÃO vê imagens.** Toda a referência visual do botcloud.app está
> descrita em texto na §0. Implemente a partir da descrição + specs.
>
> **Regra-mãe:** NÃO mexer na paleta. As cores já foram decididas (tons do
> YouTube — ver §2). Esta fase é **só estrutura/layout/componentes**, no
> espírito do dashboard botcloud.app, reusando nossos tokens.
>
> **Antes de tocar em QUALQUER coisa**, leia no `ROADMAP_UI.md`:
> - §1 (padrões: como criar tela/botão/label/tabela, tooltips)
> - §3 (outliers conhecidos — não "consertar")
> - §4 (workflow audit→edit→validate→commit, como rodar prints e testes)
>
> Cada frente é autocontida: **Contexto → Ação → Não fazer → Aceite →
> Auto-validação → Commit**. Ordem recomendada na §4. Ao concluir uma
> frente, marque-a com ✅ + um parágrafo de **Resultado** aqui (padrão das
> Fases 1-2).

---

## 0. Referência visual — o que é o "look botcloud" (descrito em texto)

Fonte: `botcloud.app`, tela "Operações" (dashboard de trading bot). Pedro
quer trazer a **estrutura/linguagem** dela, mantendo nossas cores. Elementos
que definem o visual, em ordem de protagonismo:

1. **Sidebar = rail só de ícones (~64px de largura).** Sem rótulos de texto;
   só glifos de linha, centralizados verticalmente. Logo no topo. Item ativo
   = "pílula" de fundo arredondada atrás do ícone (não uma borda lateral).
   Tooltip mostra o nome ao passar o mouse. *(Hoje a nossa é 220px COM
   rótulos — isto é um conflito, ver Frente FF.)*

2. **Barra superior com duas zonas:** à esquerda o breadcrumb
   ("Dashboard › Operações"); à direita um cluster de utilidades em botões
   quadrados arredondados: idioma (globo), **toggle de tema (☀/🌙)**, avatar
   de perfil. *(Hoje só temos o breadcrumb à esquerda.)*

3. **Título de página grande e bold** (~32px), com subtítulo muted logo
   abaixo. *(Hoje usamos 16px compacto — conflito, ver Frente GG.)*

4. **Strip de controle largo**: um card horizontal de largura total com uma
   ação primária à esquerda (botão pílula "PARAR") e um status centralizado
   ("BOTCLOUD EM EXECUÇÃO" com ícone de info).

5. **KPI cards ricos** (4 em linha). Cada card:
   - cantos bem arredondados, bastante respiro interno;
   - **linha de cabeçalho**: rótulo pequeno/muted à esquerda + **ícone no
     canto superior direito**;
   - **valor grande** abaixo (alinhado à esquerda);
   - às vezes um **pill badge** colado ao valor (ex.: "$ 24,72" num pill
     verde no card "Saldo atual");
   - **sub-linha** com micro-ícone + texto de contexto (ex.: "↗ 1.4% de
     lucro", "✓ 100% de assertividade").
   - Layout **alinhado à esquerda** (não centralizado).

6. **Tabela com a LINHA INTEIRA tingida** conforme o resultado: linhas de
   "WIN" têm fundo verde bem sutil (não só o texto). Ícones inline: bandeira
   do ativo, seta ▲ (verde) / ▼ (vermelho) na direção, ✓ no status.

7. **Toggle pílula** (switch) para filtros booleanos (ex.: "Sinais
   cancelados"), em vez de checkbox quadrado.

8. **Densidade arejada + cantos ~16px** em tudo.

**Tradução pro SkinVault:** o que dá pra trazer sem conflito são os KPI cards
ricos (#5), o tinte de linha (#6), a barra superior (#2) e o strip de status
(#4) — frentes AA-EE. A sidebar-rail (#1) e o título grande (#3) **revertem
decisões anteriores do Pedro** e ficam como frentes opcionais FF/GG, só
executar com aval dele. O toggle-pílula (#7) é cosmético (HH).

---

## 1. Regras inegociáveis

- **Python 3.9 + PyQt6.** Nada de f-string com `=`, match-case, etc.
- **Gráficos e ícones só com QPainter custom** (nunca lib externa). Ícones
  novos = novos métodos `_draw_<nome>` em `LineIcon` (ver §3 Frente AA).
- **Cores SÓ via tokens de `theme.py`.** NUNCA hex novo inline. Se precisar
  de uma cor que não existe, **adicione um token** em `theme.py` — mas nesta
  fase você quase nunca deve precisar (a paleta está completa).
- **NÃO ALTERAR A PALETA.** Não toque em `BG/BG_ELEVATED/SURFACE/BORDER/
  TEXT/TEXT_MUTED/ACCENT/POSITIVE/DANGER/...`. Os valores YouTube estão
  setados e aprovados. Mexeu na cor = quebrou a regra-mãe.
- **Semântica de cor (não recoplar):** `POSITIVE` (verde) = lucro/alta/bom;
  `DANGER` (vermelho) = prejuízo/queda/ruim; `ACCENT` (branco) = marca/UI
  (item ativo, foco, botão, número neutro). Nunca use ACCENT pra "lucro".
- **Tooltip em todo botão** (frase "o que acontece quando clico").
- **1 frente = 1 commit.** Mensagem em pt-BR, presente do indicativo, **sem
  `Co-Authored-By`** (o projeto não usa). Padrão: `ui: <verbo> <o que mudou>`.
- Ao concluir: marque ✅ + parágrafo **Resultado** nesta frente, aqui.

---

## 2. Tokens disponíveis (use estes — não invente hex)

Paleta YouTube já em `theme.py` (não alterar):

| Token | Valor | Uso |
|---|---|---|
| `BG` | `#0F0F0F` | fundo principal |
| `BG_ELEVATED` | `#212121` | cards, sidebar |
| `SURFACE` | `#272727` | input/hover/chip |
| `SURFACE_HOV` | `#3F3F3F` | hover forte |
| `BORDER` | `#303030` | bordas finas |
| `TEXT` | `#F1F1F1` | texto primário |
| `TEXT_MUTED` | `#AAAAAA` | secundário/labels |
| `ACCENT` | `#F1F1F1` | marca/UI (ativo, foco, botão, nº neutro) |
| `ACCENT_DIM` / `ACCENT_HOV` | `rgba(241,241,241,.13/.22)` | bg translúcido de ativo/hover |
| `POSITIVE` | `#3FB950` | **lucro/alta/bom** |
| `POSITIVE_DIM` / `POSITIVE_HOV` | `rgba(63,185,80,.16/.26)` | bg translúcido de lucro |
| `DANGER` | `#EF4444` | **prejuízo/queda/ruim** |
| `DANGER_DIM` / `DANGER_HOV` | `rgba(239,68,68,.16/.26)` | bg translúcido de prejuízo |
| `WARN` | `#F59E0B` | atenção/médio |
| `STEAM_BLUE` | `#66C0F4` | ações de Steam (sync/conta) |
| `FOCUS_GREEN` | `#FFFFFF` | focus ring do ACCENT (nome legado) |
| Radius | `RADIUS_SM=6` `RADIUS_MD=10` `RADIUS_LG=14` | cantos |
| Spacing | `SPACE_XS..2XL = 4/8/12/16/24/32` | margens/spacing |

**LineIcon** (`components.py:283`) já tem: `user, history, radar, chart,
swap, calc, eye, gear, info, archive` (+ fallback círculo). Despacho por
`getattr(self, f"_draw_{name}")` (linha ~319). Cada `_draw_*` pinta num
viewBox 18×18, stroke 1.5 RoundCap, sem fill. Adicionar ícone = novo
`_draw_<nome>` no mesmo padrão.

---

## 3. Frentes

### Frente AA — StatCard "botcloud": ícone de canto + pill badge + alinhamento à esquerda (impact: ALTO) [deps: nenhuma]

**Contexto:** os KPI cards do botcloud têm rótulo+ícone no topo, valor grande
à esquerda, pill badge opcional colado ao valor, e sub-linha de contexto. O
nosso `StatCard` (`components.py:205`) hoje é **centralizado** e só tem
label + value + `set_delta` (sub-linha já existe via `set_delta`, ver
`components.py` método `set_delta`). Faltam: ícone de canto, pill badge, e o
alinhamento à esquerda do botcloud.

**Ação:**
1. `LineIcon`: adicionar glifos úteis pra KPI (novos `_draw_*`, QPainter,
    mesmo padrão dos existentes): `wallet` (retângulo + aba), `coins`
    (2 elipses empilhadas), `trophy` (taça), `percent` (% com 2 círculos +
    barra), `calendar` (retângulo + 2 ticks no topo + linha). Nome inválido
    continua caindo no fallback.
2. `StatCard.__init__`: aceitar `icon: str = ""`. Reestruturar o layout pra
    **alinhado à esquerda** (botcloud):
    - **header row** = `QHBoxLayout`: `QLabel(label)` (`label_caption()`,
      AlignLeft) + `addStretch(1)` + (se `icon`) `LineIcon(icon, TEXT_MUTED)`
      16×18px no canto direito.
    - **value row** = `QHBoxLayout`: `self._value` (AlignLeft) + `self._badge`
      (pill, oculto por padrão) + `addStretch(1)`.
    - `self._delta` abaixo (AlignLeft).
    - Trocar os `AlignCenter` atuais (label/value) por AlignLeft. *(Sim, isto
      muda TODOS os StatCards de centralizado→esquerda; é intencional, é o
      look botcloud.)*
    - Preservar `_value_color` (placeholder "—" continua neutro — ver
      ROADMAP_UI.md / commit `39a6dc5`).
3. `StatCard.set_badge(text: str, kind: str = "neutral")`: mostra um pill
    colado ao valor. `kind` → cor:
    - `positive` → bg `POSITIVE_DIM`, texto `POSITIVE`
    - `danger` → bg `DANGER_DIM`, texto `DANGER`
    - `neutral` → bg `SURFACE`, texto `TEXT_MUTED`
    QSS do pill: `padding: 2px 8px; border-radius: 10px; font-size: FS_MUTED;
    font-weight: 600; font-family: FONT_FAMILY;`. `clear_badge()` esconde.
4. `StatCard.set_icon(name)` (opcional, troca o ícone em runtime).
5. **Aplicar** ícones + badges onde agrega (sem exagerar):
    - Account (`account_screen.py`): "Valor bruto" → `icon="wallet"`; "Valor
      líquido" → `icon="coins"`; "P&L total" → `icon="chart"`; "Total de
      itens" → `icon="archive"`. No card de P&L total, usar `set_badge` com a
      % de lucro (kind positive/danger conforme sinal).
    - Trades (`trades_screen.py`): "P&L líquido" → `icon="chart"` + badge com
      a taxa de acerto; "Taxa de acerto" → `icon="percent"`; "Taxas pagas" →
      `icon="coins"`.
    - Scanner/Watchlist/Market/Simulador: pelo menos o ícone de canto nos
      StatCards principais (escolha glifo coerente: radar/eye/chart/calc).

**Não fazer:** não remover `set_delta` (a sub-linha continua sendo ele); não
colorir badge fora de POSITIVE/DANGER/neutral; não deixar `icon` obrigatório
(default `""` = sem ícone, back-compat). Não inflar a altura do card além de
~110px (o teste `test_statcard_height` exige ≤130 após resize 1920×1200 —
grep em test_ui_smoke.py).

**Aceite:** StatCards alinhados à esquerda, com ícone de linha no canto
superior direito, valor grande à esquerda, pill badge onde aplicável,
sub-linha do delta preservada. Tudo via tokens. Tooltips preservados.

**Auto-validação (sem imagem):**
- `StatCard("x","R$ 1", icon="wallet")` instancia sem erro e tem o LineIcon
  como filho.
- `sc.set_badge("+2%", "positive")` → `POSITIVE` aparece no styleSheet do
  badge e o badge fica visível; `clear_badge()` esconde.
- `LineIcon("wallet").grab()` não-nulo (idem coins/trophy/percent/calendar).
- Suíte verde; `test_statcard_height` continua passando.

**Commit:** `ui: StatCard estilo botcloud — icone de canto, pill badge, alinhamento a esquerda`

✅ **Resultado:** LineIcon ganhou 5 novos glifos (wallet, coins, trophy, percent, calendar) via QPainter no padrão existente. StatCard reestruturado para layout alinhado à esquerda (botcloud): header row com label + ícone de canto, value row com valor + pill badge + stretch, delta preservado abaixo. `set_badge()`/`clear_badge()`/`set_icon()` adicionados. Aplicado nas 7 telas: Account (wallet/coins/chart/archive + badge pnl_pct), Trades (chart/percent/coins + badge win_rate), Scanner (radar/trophy/chart), Market (eye/chart/archive/radar), Watchlist (eye/gear/info/history), Simulador (chart/percent/coins/calc). 1377 testes verdes. Commit `241cebd`.

---

### Frente BB — Tabelas: tinte de linha semântico (lucro/prejuízo) (impact: ALTO) [deps: nenhuma]

**Contexto:** no botcloud a linha INTEIRA de win é tingida de verde sutil.
Hoje a gente só colore o texto da P&L (ver `history_screen.py` ~1008-1025 e
`trades_screen.py` ~383-411). Queremos o fundo da linha tingido conforme o
resultado, mantendo a zebra pras linhas neutras.

**Ação:**
1. Helper em `theme.py`: `row_tint(pnl: float | None) -> QColor | None` —
   retorna `QColor(POSITIVE_DIM)` se `pnl > 0`, `QColor(DANGER_DIM)` se
   `pnl < 0`, `None` se 0/None (mantém zebra). Alpha já baixo nos *_DIM.
   *(ou monte o QColor no screen; mas centralizar é melhor.)*
2. **Trades** (`trades_screen.py`, no loop de `_populate`/`insertRow`): para
   cada linha com pnl, setar `item.setBackground(tint)` em TODAS as células
   da linha (quando tint não-None). Ver onde hoje só faz `setForeground`.
3. **History** (`history_screen.py`): nas linhas do segmento Trades/Steam
   Market que têm P&L, mesmo tratamento. Linhas sem P&L (eventos neutros)
   ficam na zebra.

**Não fazer:** não tingir tabelas sem semântica boa/ruim de linha (Scanner,
Watchlist, Market — lá o sinal é por célula, não por linha); alpha tem que
ficar ≤ ~0.16 (não pode "gritar" nem matar a legibilidade do texto
verde/vermelho por cima); não quebrar a seleção (selected continua
`ACCENT_DIM`) nem o `configure_table` (theme.py:470).

**Aceite:** linhas de lucro com fundo verde translúcido, prejuízo vermelho
translúcido, neutras na zebra; texto ainda legível; seleção/hover intactos.

**Auto-validação (sem imagem):**
- `theme.row_tint(5)` → cor com componente verde; `row_tint(-5)` → vermelha;
  `row_tint(0)`/`row_tint(None)` → `None`.
- Após popular a tabela de Trades com 1 win e 1 loss, o `background()` das
  células bate (verde/vermelho); linha neutra sem background custom.

**Commit:** `ui: tabelas tingem a linha por resultado (lucro verde / prejuizo vermelho)`

---

### Frente CC — Barra superior: utilidades à direita (tema + perfil) (impact: médio) [deps: nenhuma]

**Contexto:** o botcloud tem, no topo, breadcrumb à esquerda e um cluster à
direita (idioma, toggle de tema, perfil). Hoje só temos o `Breadcrumb`
(`components.py:575`), à esquerda, montado no topo do `ScreenRouter`
(grep `_breadcrumb` em screen_router.py).

**Ação:**
1. `Breadcrumb`: aceitar widgets trailing — método `set_actions(widgets)` ou
   um `QHBoxLayout` com `addStretch(1)` + os botões à direita.
2. Adicionar 2 botões `btn_ghost` (icon-only, `LineIcon`):
   - **Toggle de tema** (`gear`→não; criar glifo `sun`/`moon` ou usar texto
     ☀/🌙 via QPainter — preferir LineIcon `sun` (círculo + raios) e `moon`
     (crescente)). Ao clicar: lê settings, alterna `theme` dark↔light, salva
     (`skinvault.settings.save_settings`) e reaplica via o mesmo caminho do
     `_on_theme_changed` do MainWindow (grep em gui.py). Tooltip: "Alternar
     tema claro/escuro".
   - **Perfil** (`user`): navega pra Account (`ScreenRouter.navigate
     (SCREEN_ACCOUNT)`). Tooltip: "Minha Conta".
3. Idioma: **pular** (app é pt-BR only; não inventar i18n).

**Não fazer:** não duplicar a tela de Configurações (o toggle é só
dark↔light rápido); não criar i18n; não mexer no gating de sessão do router.
Lembrar do pitfall da Frente M: QSS de fundo só com seletor (`#objectName`),
senão volta a "tarja" atrás dos labels.

**Aceite:** cluster à direita no topo em todas as telas; toggle de tema
alterna ao vivo; perfil navega pra Conta; tokens only; tooltips.

**Auto-validação (sem imagem):** clicar no toggle troca `settings["theme"]`
entre "dark"/"light" e chama o reaplicador; clicar no perfil emite
`navigate("account")`. Smoke: Breadcrumb com actions instancia.

**Commit:** `ui: barra superior com toggle de tema e atalho de perfil a direita`

---

### Frente DD — Strip de status/controle na Conta (impact: médio) [deps: nenhuma]

**Contexto:** o botcloud tem um card-strip largo de status/controle ("PARAR
/ EM EXECUÇÃO"). No SkinVault o equivalente honesto é um **strip de sessão**
na Account: estado da conexão + última sync + ação de sincronizar. Hoje as
ações de sync vivem no PageHeader da Account.

**Ação:** em `account_screen.py`, adicionar um `Card`
(`padding=CARD_PAD_MD`, largura total) logo abaixo do PageHeader e acima dos
StatCards: `QHBoxLayout` = [dot 8px (`POSITIVE` se conectado, `TEXT_MUTED` se
não) + label "Conectado como {nome}" / "Não conectado"] + `addStretch(1)` +
[caption "Última sync HH:MM"] + [botão `btn_steam` "Sincronizar com Steam"].
Reusar o estado de sessão que a Account já recebe (`set_session`).

**Não fazer:** não duplicar lógica de sync — chamar o mesmo sinal/método que
o botão de sync atual usa (grep `request_sync` em account_screen.py); decidir
e documentar se o botão de sync do PageHeader sai (pra não ficar duplicado).

**Aceite:** strip reflete o estado real da sessão; sync funciona; sem botão
de sync duplicado.

**Auto-validação:** com sessão setada, o strip mostra o nome e o dot
`POSITIVE`; sem sessão, "Não conectado" + dot `TEXT_MUTED`. Clique no botão
emite o sinal de sync.

**Commit:** `ui: strip de status da sessao na Conta (conectado / ultima sync / sincronizar)`

---

### Frente EE — Roundness + respiro (densidade botcloud) (impact: baixo) [deps: AA]

**Contexto:** o botcloud é mais arredondado (~16px) e arejado. Hoje
`RADIUS_LG=14` (`theme.py:93`).

**Ação:** subir `RADIUS_LG` 14→16 (pega Card/StatCard/etc. que usam
`RADIUS_LG`). Revisar o padding do StatCard pós-Frente AA pra ~1px a mais de
respiro se necessário. Conferir que nada estoura (cards menores ficam ok com
16px).

**Não fazer:** não mexer em `RADIUS_SM`/`RADIUS_MD`; não inflar margens
globais; mudança mínima, só o token.

**Aceite:** cards visivelmente mais arredondados, sem quebra de layout.

**Auto-validação:** suíte verde; prints sem corte/overflow.

**Commit:** `ui: cantos de card mais arredondados (RADIUS_LG 16) no espirito botcloud`

---

### Frente FF — Sidebar como rail de ícones (CONFLITO — só com aval do Pedro) [opcional]

**⚠️ Reverte decisão anterior:** a sidebar larga COM rótulos é o estilo
Athenas que o Pedro pediu (ver memória `redesign-athenas-style`). O botcloud
usa rail só de ícones. **Não execute sem o Pedro confirmar que quer trocar.**

**Contexto:** `Sidebar`/`_SidebarItem` em `components.py` (~395-563);
montagem em `gui.py:537` (`_create_sidebar_dock`); largura `SIZE_SIDEBAR_W`
(220) e `settings["sidebar_width"]`.

**Ação (se aprovado):**
- Largura do dock/sidebar → ~64px (novo token `SIZE_SIDEBAR_RAIL=64`).
- `_SidebarItem` em modo icon-only: esconder o texto (ou não setá-lo),
  centralizar o `LineIcon`, **mover o rótulo pra tooltip** (discoverability).
- Ativo = pílula de fundo arredondada (`ACCENT_DIM`, `border-radius`) atrás
  do ícone, em vez da borda-esquerda atual; ícone ativo em `ACCENT`.
- Chip de sessão → vira avatar compacto (dot/inicial) no rodapé.
- Brand no topo → versão compacta (só o glifo).

**Não fazer:** não perder navegação nem tooltips (rótulos viram tooltip);
manter `item_selected`/`select()`; preservar foco por teclado (Frente C).

**Aceite:** rail 64px, ícones centrados, ativo com pílula, tooltips com os
nomes, sessão como avatar; navegação e foco intactos.

**Auto-validação:** `select("scanner")` marca o item; tooltip de cada item =
o rótulo; smoke das 7 telas com a sidebar nova.

**Commit:** `ui: sidebar vira rail de icones (estilo botcloud) com rotulos no tooltip`

---

### Frente GG — Título de página grande/bold (CONFLITO — só com aval do Pedro) [opcional]

**⚠️ Reverte a Frente N** (que reduziu o H1 de 24pt→16pt de propósito, pra
ganhar ~40px verticais por tela). O botcloud usa título grande.

**Ação (se aprovado):** no `PageHeader` (`components.py:1244`), subir o
`title_fs` do título pra `FS_TITLE` (24pt) — ou criar `FS_TITLE_LG=22pt` se
24 ficar demais — e ajustar a altura fixa do PageHeader (hoje ~52px) pra
caber. Subtítulo continua `label_caption()`.

**Não fazer:** não tocar no breadcrumb; aceitar o trade-off de espaço
vertical (é o ponto).

**Aceite:** títulos grandes/bold nas 7 telas; sem corte.

**Auto-validação:** `grep FS_TITLE_MD` nas screens deve sumir (ou PageHeader
passa a usar o size grande); suíte verde.

**Commit:** `ui: titulo de pagina grande/bold (estilo botcloud) — reverte compactacao da Frente N`

---

### Frente HH — Toggle-pílula no lugar de checkbox (cosmético) [opcional]

**Contexto:** o botcloud usa switch pílula pra flags. A gente usa `QCheckBox`
("Esconder baixa confiança" no Scanner/Watchlist). 

**Ação:** criar um `ToggleSwitch(QWidget)` em `components.py` desenhado com
**QPainter** (trilho arredondado + bolinha que desliza; ON = `ACCENT`, OFF =
`SURFACE`/`BORDER`), API tipo checkbox (`isChecked`/`toggled`/`setChecked`).
Aplicar nos checkboxes de filtro do Scanner e Watchlist.

**Não fazer:** lib externa; não trocar checkboxes de formulário/settings
(só os de filtro on/off de tela); manter o sinal `toggled` pra não quebrar a
lógica que escuta.

**Aceite:** switch animado/clean no lugar dos checkboxes de filtro, mesmo
comportamento.

**Auto-validação:** `ToggleSwitch().grab()` non-null; `setChecked(True)`
emite `toggled(True)`; filtros do Scanner/Watchlist continuam funcionando.

**Commit:** `ui: ToggleSwitch (QPainter) substitui checkbox nos filtros de tela`

---

## 4. Ordem, validação e fechamento

**Ordem recomendada:** **AA → BB → CC → DD → EE** (todas seguras, sem
conflito, ordem de impacto). Depois, só com aval do Pedro: **FF** e/ou
**GG**; **HH** quando der.

**Validação de cada frente** (detalhe no `ROADMAP_UI.md` §4.3):
1. `python -c "import skinvault.ui.<arquivo>"` (import ok).
2. `python -m pytest tests/ -x -q` (ou subset `-k "not gui and not ui"` pra
   rodar rápido durante dev; a suíte cheia antes do commit).
3. Auto-validação da frente (asserts acima) — você NÃO vê imagem, então
   transforme o aceite visual em teste sempre que possível.
4. Regenerar prints: `python _screenshot.py` (o guard aborta sozinho se o
   cs2.exe estiver rodando; `SKIP_GAME_GUARD=1` só com CS2 fechado). Commitar
   os PNGs junto se mudaram de forma significativa; senão `git checkout
   prints/`.
5. Commit no padrão pt-BR (sem Co-Authored-By), 1 frente = 1 commit.
6. Marque ✅ + **Resultado** na frente, aqui neste arquivo.

**Pitfalls herdados (não repita):**
- QSS de `background` sem seletor propaga e cria "tarjas" atrás dos labels —
  sempre `QWidget#objectName { background: ... }` (Frente M).
- Em QSS de checkbox/spin, **subcontrol primeiro, estado depois**
  (`::indicator:focus`, nunca `:focus::indicator`) (Frente R).
- `drawLine` com float gera DeprecationWarning no Qt6 → use `QPointF`.
- `winId()`/DWM no `__init__` crasha no modo grab → fazer no `showEvent`.
- StatCard placeholder "—" tem que continuar neutro (commit `39a6dc5`).

**Estado da paleta (não regredir):** tons do YouTube, `POSITIVE`/`DANGER`
desacoplados do `ACCENT` (commit `d28b9cc`). Se algum verde/vermelho de P&L
virar branco/cinza, você recoplou errado — use `POSITIVE`/`DANGER`.

— Plano escrito por Pedro / agente Claude (15 jun 2026). Base: `botcloud.app`.
