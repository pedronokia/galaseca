# SkinVault — Roadmap de UI Fase 4: polimento e consistência

> **Audience:** próximo agente (opencode/outro) que vai executar isto do zero.
> **Você NÃO vê imagens.** Esta fase é puramente **consistência** — não há
> nova linguagem visual pra trazer, é fechar arestas que ficaram da Fase 3.
>
> **Regra-mãe:** NÃO mexer na paleta, em tipografia ou na estrutura macro
> (sidebar, breadcrumb, strip de status). Mexer só nos pontos listados.
>
> **Antes de tocar em QUALQUER coisa**, leia:
> - `ROADMAP_UI.md` §1 (padrões: como criar tela/botão/label/tabela, tooltips)
> - `ROADMAP_UI.md` §3 (outliers conhecidos — não "consertar")
> - `ROADMAP_UI.md` §4 (workflow audit→edit→validate→commit)
> - `ROADMAP_UI_FASE3.md` §1 (regras inegociáveis) e §2 (tabela de tokens)
>
> Cada frente: **Contexto → Ação → Não fazer → Aceite → Auto-validação →
> Commit.** Ordem recomendada na §4. Ao concluir uma frente, marque-a com ✅
> + parágrafo **Resultado** (padrão das Fases 1-3).

---

## 0. Por que esta fase existe

A Fase 3 trouxe a **estrutura** do botcloud (sidebar-rail, PageHeader grande,
strip de status, StatCards à esquerda com ícone, row tinting, ToggleSwitch).
Mas no rodar com dados reais sobraram inconsistências que destoam: glifos
de empty state diferentes em cada tela, ações no canto superior direito sem
padrão (4 botões ghost em algumas, 1 primary + ⋯ em outras), typos de
acentos PT-BR em strings user-facing, painel "Atividade recente" virando
órfão quando não há atividade. Esta fase fecha isso.

---

## 1. Regras inegociáveis

Idênticas à Fase 3 (ver `ROADMAP_UI_FASE3.md` §1). Resumo:
- **Python 3.9 + PyQt6.** Nada de f-string com `=`, match-case, etc.
- **Gráficos e ícones só com QPainter** (nunca lib externa).
- **Cores SÓ via tokens de `theme.py`.** NUNCA hex novo inline.
- **NÃO ALTERAR A PALETA** nem tipografia.
- **Semântica de cor:** `POSITIVE` = bom; `DANGER` = ruim; `ACCENT` = marca/UI.
- **Tooltip em todo botão** (frase "o que acontece quando clico").
- **1 frente = 1 commit.** pt-BR, presente do indicativo, **sem
  `Co-Authored-By`**. Padrão: `ui: <verbo> <o que mudou>`.

---

## 2. Tokens disponíveis

Ver `ROADMAP_UI_FASE3.md` §2 — tabela completa de tokens YouTube
(BG/SURFACE/BORDER/TEXT/ACCENT/POSITIVE/DANGER/STEAM_BLUE/…) e helpers de
`theme.py` (`brl()`, `btn_primary()`/`btn_ghost()`/`btn_steam()`,
`label_caption()`, `row_tint()`, `configure_table()`).

`LineIcon` (`components.py:283`) já tem: `user, history, radar, chart,
swap, calc, eye, gear, info, archive, wallet, coins, trophy, percent,
calendar` (+ fallback círculo).

---

## 3. Frentes

### Frente AA — Acentos PT-BR em strings user-facing (impact: ALTO) [deps: nenhuma] ✅

**Contexto:** strings user-facing perderam acentos em vários lugares.
Aparecem no UI assim mesmo (não é bug de fonte — é typo no fonte). Lista
completa (grep "inventario|evolucao|sincronizacao" no projeto):

- `skinvault/gui.py:390` — `"Erro durante a sincronizacao:\n{msg}"`
- `skinvault/gui.py:399` — `"{added} novos / {total} no inventario"`
- `skinvault/gui.py:790` — `"Avaliacao de inventario CS2 sem login.<br>"`
- `skinvault/ui/account_screen.py:188` — `"Puxa seu inventario, market
   history, listings ativas e trade …"`
- `skinvault/ui/account_screen.py:435` — `"Avaliando inventario..."`
- `skinvault/ui/account_screen.py:465` — `f"Avaliando inventario… {done}/{total}"`
- `skinvault/ui/widgets.py:201` — `"Avalie 2x+ pra ver a evolucao do valor"`

**Ação:** substituir literalmente (são todas strings literais Python):
- `inventario` → `inventário`
- `evolucao` → `evolução`
- `sincronizacao` → `sincronização`
- `Avaliacao` → `Avaliação`
- `grafico` (account_screen.py:449, comentário — ignorar) — não é
  user-facing, pular.
- `historico` (widgets.py:183, docstring — ignorar) — não é user-facing.

Ou seja: **só strings exibidas no UI** (entre `"…"` que viram label/tooltip/
status/mensagem). Docstrings e comentários de código ficam.

**Não fazer:** NÃO mexer em CLI (`__main__.py`, `gui.py` partes de CLI) —
fora de escopo desta fase (pode quebrar grep dos usuários). NÃO renomear
identificadores/variáveis (`_grafico`, `_historico`, etc.).

**Aceite:** rodando o app, nenhuma label/tooltip/status exibe palavra PT-BR
sem acento. Empty state da Conta diz "Avaliando inventário…", widget de
gráfico vazio diz "Avalie 2x+ pra ver a evolução do valor", erro de sync
diz "Erro durante a sincronização".

**Auto-validação (sem imagem):**
- `grep -rE '"[^"]*inventario[^"]*"' skinvault/ui skinvault/gui.py` deve
  retornar vazio.
- Idem `"[^"]*evolucao[^"]*"`, `"[^"]*sincronizacao[^"]*"`,
  `"[^"]*Avaliacao[^"]*"`.
- Suíte cheia verde.

**Commit:** `ui: corrige acentos PT-BR em strings user-facing (Conta, sync, widgets)`

✅ **Resultado:** 7 strings literais corrigidas em 3 arquivos (`gui.py` 3×, `ui/account_screen.py` 3×, `ui/widgets.py` 1×): `inventario→inventário`, `evolucao→evolução`, `sincronizacao→sincronização`, `Avaliacao→Avaliação`. Docstring de `_reload_value_series` (account_screen.py:449) e comentários intocados (não user-facing). Os 4 greps do aceite retornam vazio. 1296 testes passam; o único `test_launch_start_minimized` que falha já estava quebrado em HEAD (`7d5c5b3`) por bug pré-existente de `FakeApp.setWindowIcon` no test double, sem relação com esta frente. Commit `cc30e70`.

---

### Frente BB — EmptyState: unificar glifos canônicos (impact: ALTO) [deps: nenhuma] ✅

**Contexto:** componente `EmptyState` (`components.py:67`) recebe glifo
livre. Hoje cada tela escolhe o que quer:
- Account (`account_screen.py:352`): `"○"` (círculo vazio)
- Market (`market_screen.py:297`): a confirmar — provavelmente `"◇"`
- History (`history_screen.py:535`): `"◇"` (diamante)
- Scanner (`scanner_screen.py:338`): `"◎"` (alvo)
- Trades (`trades_screen.py:319`): `"◇"` (diamante)
- Watchlist (`watchlist_screen.py:315`): a confirmar

Sem regra → cada tela parece de uma família visual diferente.

**Ação:** definir **2 glifos canônicos** baseados em semântica e aplicar:

| Glifo | Semântica | Telas |
|---|---|---|
| `"◇"` (U+25C7) | **"Ainda sem dados"** — esperando o usuário popular | Account (inventário vazio), History, Trades, Watchlist, Market (sem busca) |
| `"◎"` (U+25CE) | **"Pronto pra agir"** — empty state com ação imediata | Scanner (pronto pra escanear), e qualquer outra "call to action" |

Trocar `"○"` da Account por `"◇"` (cabe na 1ª linha). Confirmar
Market/Watchlist e ajustar se diferentes.

**Documentar** a regra na docstring do `EmptyState`:
```python
"""
Glifos canônicos:
- "◇" para "ainda sem dados" (esperando o usuário popular)
- "◎" para "pronto pra agir" (empty state com CTA)
"""
```

**Não fazer:** NÃO inventar glifo novo; NÃO trocar `◇`/`◎` por LineIcon
nem por Unicode mais "elegante" (mantém leveza e consistência ASCII-art).
NÃO mexer no resto do componente.

**Aceite:** todas as 7+ telas usam `◇` ou `◎` conforme a tabela; docstring
do `EmptyState` documenta a regra.

**Auto-validação:**
- `grep -rE 'EmptyState\(\s*icon\s*=\s*"[^◇◎]' skinvault/ui` deve retornar
  vazio (todo `icon=` é `◇` ou `◎`).
- `EmptyState("◇", "X").grab()` non-null; idem `◎`.

**Commit:** `ui: unifica glifos de empty state (◇ sem dados, ◎ pronto pra agir)`

✅ **Resultado:** Account troca `"○"` por `"◇"` (`account_screen.py:352`) e Watchlist troca `"☆"` por `"◇"` (`watchlist_screen.py:316`) — ambas se encaixam em "ainda sem dados". Docstring do `EmptyState` (`components.py:67`) passa a documentar a regra dos 2 glifos canônicos com mapeamento explícito de telas. Demais telas (History, Trades, Market `◇` + Scanner `◎`) já estavam no padrão. Greps de aceite (`EmptyState(\s*icon\s*=\s*"[^◇◎]` e variante posicional) retornam vazio. 1376 testes verdes (o `test_launch_start_minimized` deselected ficou destravado pelo commit paralelo `e2e4d90`). Commit `e14be60`.

---

### Frente CC — PageHeader actions: limite de 2 botões + ⋯ menu (impact: ALTO) [deps: nenhuma]

**Contexto:** no canto superior direito de cada tela hoje:

| Tela | Ações no header |
|---|---|
| Account | "Validar Score do Portfolio" + "Atualizar scores" (2 ghost) |
| History | "Recarregar" + "Exportar CSV" + "Buscar ícones" + "Simular trade" (4 ghost) |
| Scanner | Categoria + "Escanear" + "Ranking Top 20" + "Validar Score" (3 botões + dropdown) |
| Trades | "Adicionar trade" (primary) + "⋯" (ghost menu — bom!) |
| Market | Search + "Consultar item" (1 primary) |
| Watchlist | "Atualizar scores+alertas" (1 ghost gigante) |

O padrão do Trades (1 primary + 1 ⋯ menu) é o limpo. Aplicar nas demais.

**Ação:** padronizar a regra em todo PageHeader:

> **Máximo 1 botão primary + máximo 1 botão ghost + (opcional) menu ⋯
> pra ações secundárias.**

Migrações concretas:
1. **History** — manter "Recarregar" + "Simular trade" (primary?) no
   header. Mover "Exportar CSV" e "Buscar ícones" pra dentro do menu ⋯
   (padrão do Trades, ver `trades_screen.py:174-187`).
2. **Account** — "Validar Score do Portfolio" → "Validar score" (frente
   FF cuida do encurtamento) como primary; "Atualizar scores" continua
   ghost. Já são só 2, mantém.
3. **Scanner** — Categoria continua à esquerda; "Escanear" primary;
   "Ranking Top 20" + "Validar Score" + (futuro) "Limpar cache SSR" vão
   pro menu ⋯. (Hoje "Limpar cache SSR" + "Exportar CSV" estão acima da
   tabela em `scanner_screen.py:238-251` — mover também pro ⋯.)
4. **Trades** — já está no padrão. Não mexer.

**Não fazer:** NÃO criar PageHeader novo; NÃO mexer no breadcrumb ou nas
utilidades à direita (☀/perfil — Fase 3 Frente CC). Tooltips obrigatórios
em TODA ação movida.

**Aceite:** nenhuma tela tem mais de 2 botões diretos no header; ações
secundárias vivem em ⋯. Tooltip em todas. Atalhos de teclado preservados.

**Auto-validação:**
- `grep -c "tb.add_right" skinvault/ui/history_screen.py` retorna ≤ 3
  (incluindo o `_update_prices_btn` invisível).
- Click no ⋯ do History abre menu com "Exportar CSV" e "Buscar ícones".
- Suíte cheia verde (cuidar de testes que clicam diretamente em botões
  movidos — passar a chamar `act_export_csv.trigger()` etc.).

**Commit:** `ui: padroniza header actions (1 primary + 1 ghost + menu ⋯)`

---

### Frente DD — ActivityFeed: encolher quando vazio (impact: médio) [deps: nenhuma]

**Contexto:** `ActivityFeed` (`components.py:647`) tem
`setMinimumWidth(280)` e `setMaximumWidth(380)`. Na Account
(`account_screen.py:370`) é adicionado com `split.addWidget(self._activity_feed, 0)`.
Quando o usuário **não tem atividade** (caso `_empty` em
`components.py:687`), o painel mostra só uma label "Nenhuma atividade
ainda." num espaço de 280-380px, parecendo órfão.

**Ação:** quando `_all_events` está vazio:
1. Esconder os chips de filtro (`chips_row` — `components.py:664-679`).
2. Setar `setMinimumWidth(200)` enquanto vazio (compactar).
3. Restaurar 280/chips quando voltar a ter eventos.

Método novo: `_apply_empty_layout(is_empty: bool)`, chamado no fim de
`set_events()` (público) e no `__init__`.

**Não fazer:** NÃO esconder o painel inteiro (perde discoverability —
usuário não saberia que existe); NÃO mexer no max width; NÃO criar
componente novo.

**Aceite:** com 0 eventos, o painel encolhe pra ~200px com só
título + empty message; com ≥1 evento, expande pra 280px+ com chips.

**Auto-validação:**
- `ActivityFeed(); af.set_events([])` → `af.minimumWidth() == 200`.
- `af.set_events([{...evento mock...}])` → `af.minimumWidth() == 280`.
- Chips visíveis só quando há eventos.

**Commit:** `ui: ActivityFeed encolhe e esconde chips quando vazio`

---

### Frente EE — Tooltips em botões sem tooltip (impact: médio) [deps: nenhuma]

**Contexto:** regra do projeto: tooltip em todo botão. Hoje há botões sem
tooltip (vide regra-mãe + `ROADMAP_UI.md`). Auditoria rápida:

**Ação:** rodar varredura — `grep -nE "QPushButton\(" skinvault/ui/*.py`
e checar pra cada um se há `setToolTip(...)` em até 5 linhas depois.
Pra cada faltante, adicionar tooltip explicando o que acontece ao clicar
("Recarrega os dados do segmento atual do disco." é o padrão a seguir,
visto em `history_screen.py:476`).

Botões a verificar (lista NÃO exaustiva — varredura completa é
obrigatória):
- BackupDialog (`gui.py:157`) — todos os botões internos
- SteamSyncDialog (`gui.py:279`)
- AccountScreen — `_validate_btn`, `_refresh_btn` (já têm? confirmar)
- Diálogos de adicionar trade (`trades_screen.py:113-117`)
- `_more_btn` do Trades (`trades_screen.py:178`) — já tem "Mais ações."
- Botões dos dialogs em `scanner_dialogs.py`

**Não fazer:** NÃO adicionar tooltip a botão que JÁ tem; NÃO mexer em
`setStatusTip` (é outra coisa); NÃO sobrescrever tooltip por mensagem
genérica ("Clique aqui").

**Aceite:** após a varredura, **zero** `QPushButton(...)` no projeto sem
`setToolTip(...)` em até 5 linhas.

**Auto-validação:** script de check em `scripts/check_tooltips.py` que faz
o grep e reporta. Suíte cheia verde.

**Commit:** `ui: tooltip em todos os QPushButton (regra do projeto)`

---

### Frente FF — Nomenclatura uniforme de ações (impact: baixo) [deps: CC]

**Contexto:** mesma operação semântica aparece com nomes diferentes:
- Account: "Atualizar scores"
- Watchlist: "Atualizar scores+alertas"
- Account: "Validar Score do Portfolio"
- Scanner: "Validar Score"

E há excesso de palavras: "do Portfolio" é redundante na Conta.

**Ação:**
1. "Atualizar scores" e "Atualizar scores+alertas" — manter o sufixo
   "+alertas" só na Watchlist (faz sentido: lá há regras de alerta de
   verdade). Confirmar tooltip da Watchlist explica o "+alertas".
2. "Validar Score do Portfolio" → **"Validar score"** (Account). Tooltip
   atual continua bom.
3. "Validar Score" → **"Validar score"** (Scanner). Padronizar
   capitalização: só primeira palavra maiúscula. Aplicar a TODOS os
   botões secundários do app.

Regra do projeto: **"sentence case" pra botões secundários, "Title Case"
só pro botão primário** (já é prática na Fase 3, formalizar aqui).

**Não fazer:** NÃO mexer em texto de CTA gigante do EmptyState
("Sincronizar com Steam" continua title case porque é primary CTA);
NÃO renomear strings ID/chaves (`SCREEN_ACCOUNT` etc.).

**Aceite:** todos os botões secundários do app são sentence case;
"Portfolio" não aparece em label da Conta (continua no tooltip).

**Auto-validação:**
- `grep "Validar Score" skinvault/ui/*.py` retorna 0.
- `grep "Validar score" skinvault/ui/*.py` retorna ≥ 2 (Account + Scanner).
- Suíte cheia verde (cuidar de testes que clicam por texto exato — passar
  a usar object names ou `clicked.emit()`).

**Commit:** `ui: nomenclatura uniforme — sentence case nos botoes secundarios`

---

## 4. Ordem, validação e fechamento

**Ordem recomendada:** **AA → BB → DD → EE → CC → FF.**
- AA e BB são correções simples e isoladas (baixo risco).
- DD e EE são polimentos médios.
- CC mexe em PageHeader de várias telas (risco médio — exige cuidado com
  testes que clicam em botões pelo texto).
- FF depende de CC (move ações pro menu antes de renomear).

**Validação de cada frente** (detalhe no `ROADMAP_UI.md` §4.3):
1. `python -c "import skinvault.ui.<arquivo>"` (import ok).
2. `python -m pytest tests/ -x -q` rápido durante dev; suíte cheia antes
   do commit.
3. Auto-validação da frente (asserts acima).
4. Regenerar prints: `python _screenshot.py` (guard aborta se cs2 estiver
   rodando). Commitar PNGs junto se mudaram de forma significativa.
5. Commit pt-BR (sem Co-Authored-By), 1 frente = 1 commit.
6. Marque ✅ + **Resultado** na frente.

**Pitfalls herdados (não repita):**
- QSS de `background` sem seletor propaga e cria "tarjas" — sempre
  `QWidget#objectName { background: …; }` (Frente M da Fase 3).
- Em QSS de checkbox/spin, **subcontrol primeiro, estado depois**.
- `drawLine` com float gera DeprecationWarning no Qt6 → use `QPointF`.
- StatCard placeholder "—" tem que continuar neutro.
- Testes que clicam botões pelo texto QUEBRAM se você mover o botão pra
  menu ou renomear — varrer `tests/test_ui_smoke.py` por
  `findChild.*QPushButton` antes de mover/renomear.

**Estado da paleta (não regredir):** tons do YouTube; `POSITIVE`/`DANGER`
desacoplados do `ACCENT`. Se algum verde/vermelho de P&L virar
branco/cinza, você recoplou errado.

— Plano escrito por Pedro / agente Claude (16 jun 2026). Base: estado
da UI pós Fase 3 + screenshots da app rodando com sessão Steam ativa.
