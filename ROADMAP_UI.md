# SkinVault — Roadmap de UI Polish

> Documento de continuidade. Resume o estado atual da UI, padrões estabelecidos, e próximas frentes de polish ordenadas por impacto/esforço.
>
> **Audience:** próximo agente (opencode/outro) que vai pegar este trabalho do zero.
> Cada item tem **arquivo:linha** e **ação concreta**, não vibe. Leia top-down.

---

## 0. Snapshot do estado atual

**Última sessão fechou em commit `7065198`.** 16 commits sequenciais (`f2668bd` → `7065198`) consolidam um sistema de design tokens + helpers visuais. Frente P (tabelas/headers/Watchlist) adicionada em sessão seguinte — ver §2.6.

### Arquivos chave da UI

```
skinvault/ui/
├── theme.py          (260 LOC)  ← tokens + style helpers
├── components.py     (1010 LOC) ← shared widgets (Card, Sidebar, Footer, FormRow, EmptyState, LoadingState, SectionHeader, StatCard, Toast, Toolbar, ActivityFeed, …)
├── widgets.py        (360 LOC)  ← QPainter custom widgets (MiniSparkline, DepthChart, MonthBarChart, ValueChart)
├── screen_router.py  (200 LOC)  ← navegação entre telas via QStackedWidget
├── login_gate.py     (120 LOC)  ← tela inicial sem sessão
├── welcome_dialog.py (100 LOC)  ← modal "primeira sessão"
├── account_screen.py     (660 LOC)
├── history_screen.py     (1100 LOC)
├── scanner_screen.py     (1580 LOC)
├── market_screen.py      (590 LOC)
├── trades_screen.py      (560 LOC)
├── simulador_screen.py   (335 LOC)
└── watchlist_screen.py   (720 LOC)
```

### Tokens definidos em `theme.py`

| Categoria | Tokens |
|---|---|
| Paleta | `BG`, `BG_ELEVATED`, `SURFACE`, `SURFACE_HOV`, `BORDER`, `TEXT`, `TEXT_MUTED`, `ACCENT`, `ACCENT_DIM`, `ACCENT_HOV`, `STEAM_BLUE`, `STEAM_DIM`, `STEAM_HOV`, `DANGER`, `DANGER_DIM`, `DANGER_HOV`, `WARN`, `WARN_BG`, `WARN_BORDER`, `WARN_TEXT`, `BG_OVERLAY`, `FOCUS_GREEN`, `FOCUS_STEAM`, `FOCUS_RED` |
| Charts | `CHART_YELLOW` (SR/spread), `CHART_INDIGO` (SMA) |
| Spacing | `SPACE_XS=4`, `SPACE_SM=8`, `SPACE_MD=12`, `SPACE_LG=16`, `SPACE_XL=24`, `SPACE_2XL=32` |
| Size | `SIZE_INPUT_H=32`, `SIZE_BTN_H=34`, `SIZE_ROW_H=32`, `SIZE_ICON_SM/MD/LG=14/18/22`, `SIZE_AVATAR=72`, `SIZE_PROGRESS_H=6`, `SIZE_SEPARATOR=1`, `SIZE_CHART_H=120`, `SIZE_SIDEBAR_W=220`, `SIZE_HEADER_H=40`, `SIZE_FOOTER_H=32` |
| Radius | `RADIUS_SM=6`, `RADIUS_MD=10`, `RADIUS_LG=14` |
| Card padding | `CARD_PAD_SM=(14,10,14,10)`, `CARD_PAD_MD=(16,14,16,14)`, `CARD_PAD_LG=(20,18,20,18)` |
| Font family | `FONT_FAMILY = '"Segoe UI Variable Display", "Segoe UI", system-ui'` |
| Font size | `FS_MUTED=9pt`, `FS_BODY=10pt`, `FS_INPUT=11pt`, `FS_TITLE_SM=13pt`, `FS_STAT=18pt`, `FS_TITLE=24pt`, `FS_HERO=28pt` |

### Style helpers em `theme.py`

| Helper | Output | Uso |
|---|---|---|
| `input_style()` | QLineEdit/QDoubleSpinBox/QSpinBox base + focus accent | Todos os inputs |
| `btn_primary(padding, fs, disabled)` | Verde accent, fundo translucent | CTAs principais |
| `btn_steam(padding, fs)` | Azul Steam, fundo translucent | Ações de sync/conta |
| `btn_secondary(padding, fs)` | Cinza outline | Secundárias |
| `btn_danger(padding, fs)` | Vermelho, fundo translucent | Ações destrutivas |
| `btn_ghost(padding, fs)` | Flat sem borda, hover preenche | Toolbar/icon buttons |
| `table_style()` | QTableWidget completo (rows 8px pad, alt zebra, header bg, hover SURFACE_HOV, selected ACCENT_DIM) | Todas as tabelas |
| `card_style(radius)` | `QWidget#Card` com top-highlight `#30303A` | Card base via `setStyleSheet` |
| `align_table_columns(table, right, center)` | Alinha cols por sentido | Final do `_populate()` |
| `configure_table(table)` | Boilerplate Win11: hideHeader, default row 32, NoEdit, SelectRows, alt rows, sort, table_style | Todas as 5 telas com tabela |
| `label_caption()` | `TEXT_MUTED + FS_MUTED + FONT_FAMILY` | Captions/hints (35+ sites) |
| `label_body_muted()` | `TEXT_MUTED + FS_BODY + FONT_FAMILY` | Subtitle/descrição (14 sites) |
| `label_section()` | `TEXT + FS_TITLE_SM + 600 + FONT_FAMILY` | Section title (7 sites) |
| `label_caption_bold()` | `TEXT_MUTED + FS_MUTED + 600 + FONT_FAMILY` | Eyebrows/chip headers (4 sites) |
| `label_hero()` | `TEXT + FS_HERO + 700 + FONT_FAMILY + letter-spacing -0.5` | Hero modals (1 site) |
| `brl(v)` | Formata BRL pt-BR com `R$ 1.234,56` | Todo valor monetário |

### Shared components em `components.py` (não exhaustivo)

`Card`, `StatCard`, `Sidebar`, `_SidebarItem`, `Breadcrumb`, `Footer`, `EmptyState`, `LoadingState`, `SectionHeader`, `Toolbar`, `FormRow`, `Toast`, `ActivityFeed`, `_ElideLabel`, `Avatar`, `_TradeChip`, `_TradeHistoryStrip`, `SegmentedControl`, `LockOverlay`, etc.

---

## 1. Padrões estabelecidos (use estes antes de inventar)

### 1.1 Criar uma nova tela

```python
# my_screen.py
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from skinvault.ui import theme as t
from skinvault.ui.components import Card, SectionHeader, FormRow, EmptyState

class MyScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(t.SPACE_XL, t.SPACE_LG, t.SPACE_XL, t.SPACE_LG)
        root.setSpacing(t.SPACE_LG)

        # 1. Header
        root.addWidget(SectionHeader(
            "Título da Tela",
            "Subtítulo explicativo curto.",
            title_fs=t.FS_TITLE,
        ))

        # 2. Card (padding default = CARD_PAD_LG)
        card = Card(self)
        # ... ou Card(self, padding=t.CARD_PAD_MD) para compacto

        # 3. Empty state quando sem dados
        empty = EmptyState(
            icon="◇",
            title="Nada aqui ainda",
            subtitle="Como adicionar…",
            cta_label="Adicionar",
            on_cta=self._on_add,
        )
```

Registrar a tela em `screen_router.py`:
1. Adicionar constante `SCREEN_FOO = "foo"`
2. Instanciar dentro de `_build()` e `_stack.addWidget(...)`
3. Adicionar caso em `navigate()` para `setCurrentWidget` + `breadcrumb.set_path(...)`
4. Adicionar item no sidebar em `gui.py::_create_sidebar_dock`

### 1.2 Adicionar um botão (template)

```python
self._foo_btn = QPushButton("Texto")
self._foo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
self._foo_btn.setStyleSheet(t.btn_primary())  # ou btn_steam/secondary/danger/ghost
self._foo_btn.setToolTip("Frase curta no estilo 'O que acontece quando clico'")
self._foo_btn.clicked.connect(self._on_foo)
```

**Regra**: todo botão precisa de tooltip. Audit de cobertura ficou 100% em `b28aa73` — não regredir.

### 1.3 Criar um label (use helper, não inline)

```python
# Caption muted pequeno (hint, timestamp, metadata)
lbl.setStyleSheet(t.label_caption())

# Body muted (parágrafo descritivo)
lbl.setStyleSheet(t.label_body_muted())

# Section title (header de card/grupo)
lbl.setStyleSheet(t.label_section())

# Caption bold (eyebrow, chip header, label de form)
lbl.setStyleSheet(t.label_caption_bold())

# Hero (modal de boas-vindas)
lbl.setStyleSheet(t.label_hero())
```

Se a variante não existir, **decida**:
- Outlier verdadeiro (font-style italic, padding-top, text-decoration)? Fica inline.
- Vai aparecer 3+ vezes no codebase? Extrai helper novo em `theme.py`.

### 1.4 Adicionar um token

1. Define em `theme.py` na seção apropriada (Paleta / Spacing / Size / Radius / Font / Card padding).
2. Documenta com comentário inline (`# usado em …`).
3. Migra usos existentes que batem exato.

### 1.5 Criar uma tabela

```python
self._table = QTableWidget(0, N_COLS)
self._table.setHorizontalHeaderLabels([...])
t.configure_table(self._table)  # boilerplate Win11 (row height, selection, alt rows, sort, stylesheet)

# Específicos da tela:
hh = self._table.horizontalHeader()
hh.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
# … outras colunas
```

No fim do `_populate()`:
```python
t.align_table_columns(
    self._table,
    right={COL_PRICE, COL_PNL, COL_QTD},
    center={COL_STATUS, COL_OP},
)
```

### 1.6 Tooltips: regras de redação

- **Foque no "O que acontece quando clico"**, não no "o que é". `"Calcula P&L líquido após taxa Steam de 15%"` > `"Botão de simulação"`.
- 1–2 frases curtas. Use `\n` para multi-linha se precisar de contexto extra.
- Mencione atalhos relevantes (`"Esc também limpa o filtro"`).
- Pt-BR com terminologia consistente: "carteira" (não "portfolio"), "P&L líquido" (sempre com "líquido" se for pós-taxa), "Steam" (cap S).

---

## 2. Frentes priorizadas (impact × effort)

> Ordenação: ~~**A** > B > C > D > E > F > G > H > I~~ > **K** > **L** (restantes)
>
> **Fase 2 (jun/2026)**: **M** primeiro (sozinha — muda o baseline visual global), depois **N / O / P / Q / R / S** em paralelo, **T / U** depois de N, **V** por último. Specs na seção 2.6.

### Frente A — Migração final de label outliers (esforço: ~30min, impact: baixo, polish: alto)

Restam ~15 sites com captions outliers em `scanner_screen.py` e `components.py`. Cada um tem CSS extra (`font-style: italic`, `padding-top: 4px/6px`, `letter-spacing: 1px`).

**Decisão sugerida**: NÃO extrair helpers — extrair `label_caption_italic()`, `label_caption_pad_top_sm`, etc. seria piorar (1 callsite por helper). **Deixar inline com comentário explicando o porquê do outlier**.

**Arquivos & linhas** (estado pós `7065198`):

```
scanner_screen.py:340  font-style: italic       (hist_src, fonte do dado vintage)
scanner_screen.py:574  padding-top: 4px         (scatter_lbl, separação de header)
scanner_screen.py:646  padding-top: 6px         (baseline, separação parágrafo)
scanner_screen.py:872  QCheckBox{}              (esconder baixa confiança)
components.py:668      letter-spacing: 1px      (_TradeHistoryStrip eyebrow)
watchlist_screen.py:283 QCheckBox{}             (esconder baixa confiança)
```

**Ação**: passar adicionando `# Outlier: <razão> — não migrar p/ helper` acima de cada um. Documentação > extração.

~~### Frente B — Empty state coverage para Simulador (esforço: 30min, impact: médio)~~ ✅ `90c6c92`

~~Simulador (`skinvault/ui/simulador_screen.py`) tem 2 "empty states" ainda em prosa, fora do padrão `EmptyState`:~~

~~1. **Result card antes do primeiro Simular**: linha 142–148. Texto `"Preencha os valores e clique em Simular."` + 4 StatCards mostrando `—`. Visualmente OK mas inconsistente.~~

~~2. **Simulações recentes vazias**: linhas 178–186 e 271–275 (em `_rebuild_history`). Mostra `"As últimas 5 simulações desta sessão aparecem aqui."` como caption muted abaixo do label.~~

~~**Sugestões concretas**:~~
~~- (1) Trocar a `QLabel` de result_detail por um inline mini-`EmptyState` (sem hero icon) — só title + subtitle. Ou manter mas migrar texto pra `t.label_body_muted()` (já está? confirmar).~~
~~- (2) **Esconder a seção "Simulações recentes" inteira até a primeira simulação**. Quando `len(self._history) == 0`, `hist_lbl.setVisible(False)` + `self._hist_row` collapsed. Reaparece com a primeira simulação. Mais limpo que mostrar placeholder.~~

**Resultado**: item (1) já estava resolvido (`t.label_body_muted()` desde sessão anterior). Item (2) implementado: `hist_lbl` → `self._hist_lbl`, inicia oculto, `_rebuild_history` vazio só esconde label e retorna, populado mostra label + chips. Placeholder `"As últimas 5 simulações..."` removido. `90c6c92`.

~~### Frente C — Focus rings / acessibilidade keyboard (esforço: 1h, impact: alto)~~ ✅

~~Atualmente os widgets têm pouco indicador visual de focus além do `:focus` do `input_style()` (border ACCENT). Botões e segments NÃO mostram foco.~~

~~**Ação**:~~
~~- Adicionar `:focus` selector em `btn_primary/steam/secondary/danger/ghost` em `theme.py` com `outline: 2px solid {ACCENT_HOV}; outline-offset: 2px;` (Qt 6 não suporta `outline` direto em QSS — usar `border` ou `QGraphicsDropShadowEffect`, validar).~~
~~- Verificar tab order em cada screen (ordem de criação dos widgets). Documentar order em screens críticas (Scanner, Watchlist).~~
~~- Validar com `Tab` + `Enter` no inventário e simulador.~~

**Resultado**: implementado via mudança de cor da borda 1px já reservada (zero layout shift) + bg igual ao hover — `outline` descartado (Qt6 QSS não suporta). 3 tokens novos: `FOCUS_GREEN/STEAM/RED` (versão -400 da cor base de cada família). Cobertura: 5 btn helpers, `SegmentedControl`, chips do `ActivityFeed`, `_SidebarItem` (com `:checked:focus` reassertando cor pra não apagar o estado ativo), QComboBox do scanner (ACCENT, igual inputs) e 3 QCheckBox (label clareia pra TEXT).

**Tab order auditado** (focus chain programática, sem show): Scanner = combo categoria → Escanear → Ranking → Validar → Limpar cache → 2 checkboxes (Exportar CSV inicia disabled, tabela inicia oculta — entram no fim quando ativos); Watchlist = Adicionar → Validar → Atualizar → checkbox → tabela. Ambos batem com a ordem visual; `setTabOrder` manual não foi necessário.

**Validação**: QSS parse sem warnings (handler de mensagens Qt em todos os styles tocados), 1287 tests, screenshots sem regressão no estado default. **Pendente humano**: um passe manual de `Tab`/`Enter` no app real — o ring usa o mesmo mecanismo `:focus` do `input_style()` (comprovado em produção), mas estado focado não é capturável via `grab()` sem janela ativa.

~~### Frente D — DepthChart RGB → tokens (esforço: 15min, impact: baixo)~~ ✅ `fb38216`

~~`widgets.py:298-319` usa `QColor(34, 197, 94, 40)` e `QColor(239, 68, 68, 40)` em `paintEvent`. São ACCENT e DANGER hardcoded como RGB tuples.~~

~~**Ação**:~~
~~```python
# Antes:
p.fillPath(bid_path, QColor(34, 197, 94, 40))
bid_pen = QPen(QColor(34, 197, 94))

# Depois:
bid_fill = QColor(t.ACCENT)
bid_fill.setAlpha(40)
p.fillPath(bid_path, bid_fill)
bid_pen = QPen(QColor(t.ACCENT))
```~~

~~Idem para `ask_path` com `t.DANGER`. 4 locais ao total. Visual idêntico, intent explícito.~~

**Resultado**: 4 locais migrados. `fb38216`.

~~### Frente E — FS_ICON tokens (esforço: 30min, impact: baixo, polish: médio)~~ ✅ `649a132`

~~12 sites com `font-size: NN pt` hardcoded para glifos de ícone. Listagem em `git log` rodando audit. Distribuição:~~

~~| Valor | Sites | Onde |
|---|---|---|
~~| 64pt | 1 | `components.py:54` (EmptyState icon hero) |~~
~~| 48pt | 2 | `login_gate.py:57` (hero text "SkinVault"), `components.py:402` (LockOverlay 🔒) |~~
~~| 36pt | 1 | `scanner_screen.py:173` (score number display) |~~
~~| 32pt | 1 | `welcome_dialog.py:26` (feature card icon) |~~
~~| 28pt | 1 | `components.py:857` (LoadingState spinner glyph) |~~
~~| 22pt | 1 | `components.py:358` (Avatar fallback `?`) |~~
~~| 16pt | 2 | `history_screen.py:97,131` (P&L number display) |~~
~~| 14pt | 2 | `components.py:219` (Sidebar brand "SkinVault"), `login_gate.py:65` (tagline) |~~
~~| 12pt | 1 | `components.py:458` (badge "Premium") |~~

~~**Sugestão** (introduzir 4 tokens semanticamente nomeados):~~
~~```python
FS_ICON_HERO = "64pt"   # EmptyState glyph
FS_ICON_LG   = "48pt"   # Avatar / OverlayLock
FS_ICON_MD   = "32pt"   # Welcome feature
FS_ICON_SM   = "22pt"   # Avatar fallback
FS_DISPLAY   = "36pt"   # Big number (score)
```~~

~~Os outros (28, 16, 14, 12pt) ficam inline com comentário — single-use ou contexto muito específico.~~

**Resultado**: 5 tokens adicionados (`FS_ICON_HERO`, `FS_ICON_LG`, `FS_DISPLAY`, `FS_ICON_MD`, `FS_ICON_SM`), 6 sites migrados. 28/16/14/12pt mantidos inline. `649a132`.

~~### Frente F — Tabela polish avançado (esforço: 1–2h, impact: alto)~~ ✅ parcial `05a7512`

~~Várias melhorias possíveis em `table_style()`:~~

- ~~**Sort indicator** mais visível. Atualmente Qt usa default ↑↓ no header — quase invisível no tema dark. Customizar via `::up-arrow` e `::down-arrow` selectors com SVG inline ou unicode.~~ ✅
- ~~**Hover row** (não só cell). Atualmente `::item:hover` ilumina só a cell hovered. UX trading-app: hover ilumina a row inteira. Precisa override em `mouseMoveEvent` ou stylesheet com `QTableView::item:hover { background: SURFACE_HOV; }` + atenção ao bug Qt6 com :hover em rows.~~ ✅
- **Frozen first column** (item name) ao scroll horizontal. Útil em Scanner e Account (muitas colunas, items grandes). Requer container com 2× QTableWidget sincronizadas — foge de CSS polish. **Adiado**.
- ~~**Striped rows mais visíveis**. Alt color atual é `SURFACE` (#1C1C24) vs base `BG_ELEVATED` (#16161C) — delta 6/canal, quase imperceptível. Subido para `#21212B` (delta 11/canal).~~ ✅

**Resultado**: `table_style()` ganhou `::up-arrow`/`::down-arrow` (8px, subcontrol-position), `::item:selected:hover` com `ACCENT_HOV`, e alt-color `#21212B`. `05a7512`.

~~### Frente G — Welcome dialog redesign (esforço: 1h, impact: médio)~~ ✅ `0b1417f`

~~Atual (`welcome_dialog.py`): hero + subtitle + 3 feature cards horizontais + CTA. Funcional mas visualmente plano.~~

~~**Ideias** (escolher 1):~~
~~- **Background gradient** sutil (`qlineargradient` de BG_ELEVATED → BG) no QDialog para hierarquia.~~
~~- **Animated counter** no CTA "Vamos lá" mostrando "começar em 5… 4…" se usuário não interagir (UX questionável, mas curioso).~~
~~- **Feature cards com hover lift**: QGraphicsDropShadowEffect on hover (cuidado com perf, vide histórico — descartado em cards normais por baixo ROI no dark theme; talvez OK aqui pq é evento de hover, não permanente).~~
~~- **Replace ícones glifo (◐ ◎ ★)** por **SVG do projeto** ou **emojis nativos** mais bonitos. Glifos atuais são abstratos demais.~~

**Resultado**: 3 ideias implementadas (bg gradient, hover lift via WA_Hover + border-color, emojis nativos). O animated counter foi descartado — poluição visual desnecessária. `0b1417f`.

~~### Frente H — Charts polish (esforço: 2h, impact: alto)~~ ✅ (charts vivos) — `30e7617`

~~`widgets.py` tem 4 charts custom (`MiniSparkline`, `DepthChart`, `MonthBarChart`, `ValueChart`). Todos QPainter raw, sem tooltips ou hover interactivity.~~

~~**Sugestões**:~~
~~- **Hover tooltip** em MiniSparkline mostrando preço + data no ponto.~~ ✅
~~- **DepthChart**: mostrar best_bid/best_ask como labels nas pontas, não só linha dashed.~~ ✅
~~- **MonthBarChart**: clicar numa barra abre filter da History naquele mês.~~ ✅ (montado na History — vide decisão abaixo)
- **ValueChart**: animação de transição quando série atualiza. (Desbloqueado — widget montado na Account; animação segue como ideia futura.)

**Resultado**:
- **Bug encontrado e corrigido**: `market_screen` lia `x["price"]` do price_history, mas o formato SSR é `{time, price_median, purchases}` — o sparkline do Market **nunca renderizou dados** (sempre "Sem historico" com meta dizendo "5000 pontos"). O mock do teste usava o formato errado e mascarava o bug. Fix + regression test.
- **MiniSparkline**: `set_series(values, timestamps=None)`, mouse tracking, `_hover_index_at()` (inverso da geometria de `_x`), guia vertical dashed + dot no ponto, `QToolTip` com `brl(preço) — dd/mm/aaaa`. Tooltip estático de ajuda migrou pro label "Histórico de preços" do header (senão brigaria com o dinâmico).
- **DepthChart**: preços best bid/ask em `brl()` colorido (ACCENT/DANGER) ancorados nas pontas dos ticks dashed, com clamp na área útil; legendas "Bids"/"Asks" coloridas nos cantos; spread agora em `brl()`.
- **Caps de altura removidos** (sparkline max 50, depth max 160): Market é o único consumidor real e os caps empurravam o espaço sobrando pro header do card — era isso que centralizava o label no meio do card nos prints antigos.
- 5 tests novos; suíte 1292.

**⚠️ Descoberta — MonthBarChart e ValueChart eram órfãos**: nenhuma tela montava os dois desde a migração tabs→screens (F11); só os smoke tests os referenciavam. O import de MiniSparkline no account_screen também era morto (removido). **Decisão (Pedro, jun/2026): MONTAR os dois.** Resultado:
- **MonthBarChart** montado na History: card "P&L mensal" visível só no segmento Trades, alimentado por `trades.monthly_pnl()` (agregação mensal extraída de `trade_stats()` — a tela não exige as chaves de fees/days que o stats completo requer). Clique numa barra filtra a tabela naquele mês via `month_clicked` (pyqtSignal; toggle — clicar de novo ou trocar de segmento limpa); hover tooltip com mês completo + P&L + nº de trades; barra do filtro destacada, demais esmaecidas.
- **Bugs herdados corrigidos na montagem** (nunca vistos porque era código morto): labels dos meses eram pintados em `y=h-1` (clipados pra fora do widget) e barras negativas desciam de `h-12` com só 12px de espaço (amputadas). Paint refeito com baseline dinâmica + linha de zero; label `[:3]` renderizava "202" para keys `%Y-%m` — agora `month_label()` pt-BR (Jan...Dez).
- **ValueChart** montado na Account, no card "Desempenho da carteira": a GUI agora grava `history.record_snapshot(valor bruto)` a cada avaliação (mesmo `history.json` do CLI), com dedup vs último ponto pra não poluir com o schedule de 30min.
- +8 tests (click emite key, click fora não emite, selected destaca/reseta, labels, filtro toggle na History, segmento limpa filtro, snapshot com dedup, inventário vazio não grava).

~~### Frente I — Inputs polish (esforço: 30min, impact: médio)~~ ✅ `fa05e94`

~~- **Placeholder mais descritivo** em vários `QLineEdit`. Audit nas screens: `setPlaceholderText(...)` em cada input importante.~~
~~- **Validation feedback inline** — atualmente erros aparecem como `QLabel(DANGER)` separado. Ideia: `_input_style_error()` que pinta borda em DANGER quando validação falha. Reset on focus.~~
~~- **Clear button** (X) dentro de QLineEdit pra resetar busca. `QLineEdit.addAction(QIcon, TrailingPosition)`.~~

**Resultado**: history_screen placeholders melhorados ('0,00' → descritivo), `input_style_error()` helper em theme.py com :focus reset, validation aplicada em history_screen _calc (inputs ficam com borda DANGER até foco), market_screen ganhou clear button (os outros 3 inputs já tinham via `setClearButtonEnabled` de sessão anterior). `fa05e94`.

~~### Frente J — Animations / transitions (esforço: 2–3h, impact: médio)~~ ✅ `1b75bac`

~~App é estático demais. Pequenas animações dariam vida:~~
~~- **Screen transitions**: fade entre QStackedWidget pages. Já existe `QGraphicsOpacityEffect` import em `components.py` — usar.~~ ✅
~~- **Loading state crossfade**: ao terminar load, fade out spinner + fade in conteúdo (em vez de hide/show abrupto).~~ ✅ (via fade do spinner)
~~- **Toast slide-in** (atual `Toast` já tem? Verificar).~~ ✅ (tinha só fade; slide 8px adicionado)
- **Sidebar item ripple** on click. **Descartado** — anti-distração (vide Cuidado abaixo); hover/checked/focus já dão feedback.

**Cuidado**: animação demais distrai. Manter sub-200ms e prefer linear/ease-out.

**Resultado**: helper central `fade_in(widget, duration_ms=150)` em `components.py` (OutCubic; effect removido ao final com `singleShot(0)` — deletar dentro do `finished` mata a anim filha durante a emissão). Router faz fade na tela entrante apenas em troca real e com stack visível — **guard crítico**: `_screenshot.py` e tests navegam sem `show()` e precisam de render determinístico. LoadingState faz fade de si mesmo no `showEvent` (mesmo guard), cobrindo os 26 sites de `setVisible` sem tocar as telas — o "crossfade" do roadmap virou fade só do spinner: atrasar o conteúdo com fade-in seria anti-UX (usuário quer o dado na hora). Toast ganhou slide-in de 8px paralelo ao fade existente. 6 tests novos.

### Frente K — Settings / preferências (esforço: 2h, impact: médio)

Atualmente settings ficam em modal opaco (`gui.py::SettingsDialog`). Polish:
- Migrar para uma **Settings screen** acessível pelo sidebar (item "Configurações" inferior).
- Sections claras com `SectionHeader`: "Aparência", "Comportamento", "Avançado".
- Live preview ao mudar tema (já existe `_reload_palette` em `theme.py`).
- Reset to defaults button.

### Frente L — Documentação visual interna (esforço: 2h, impact: dev-only)

Criar `docs/STYLEGUIDE.md` com:
- Screenshot de cada componente em `components.py`.
- Tabela tokens → cor visual.
- Decision log: por que ACCENT é verde, por que rows são 32px, por que descartamos shadows.

Ajuda futuro agente / contribuidor a entender o design system rapidamente.

---

## 2.6 Fase 2 — Refinamento fino (análise jun/2026)

> Análise feita sobre `prints/*.png` de 12/06/2026 (1920×1200, estado default) + auditoria de `theme.py`, `components.py`, `gui.py`. Objetivo: tirar o app de "Qt bem-arrumado" e levar a "produto fino" — menos ruído visual, hierarquia mais clara, microdetalhes Win11, dados que se explicam sozinhos.
>
> **Diagnóstico resumido (top ofensores, em ordem de dano):**
> 1. **QSS global sem seletor** (`gui.py::_apply_stylesheet`) propaga `background` pra todo QLabel → "tarjas" escuras atrás de cada texto em cada card de cada tela. Um fix, app inteiro muda. → Frente M
> 2. **H1 de 24pt + chrome vertical** consome ~90px antes do primeiro dado; Account nem tem header; combo dentro do título no Scanner. → Frentes N, T
> 3. **Chrome Qt nativo claro** (spinbox, checkbox, popup de combo, scrollbar) gritando no dark theme. → Frente R
> 4. **Estados vazios = deserto** (Scanner/Trades/Market 70% viewport vazio; Market com 2 charts-oceano de 600px). → Frente Q
> 5. **Cor semântica errada em estado neutro** ("0% (0W/0L)" VERMELHO com zero trades — vermelho é perda, não ausência) + KPI esticado sem contexto. → Frente O
> 6. ~~Tabelas sem zebra/hover, headers truncando ("'reco alvo" na Watchlist), Watchlist com "OK" verde pra item sem regra e sem distância ao alvo.~~ → **Frente P ✅**
> 7. **Sidebar com glifos abstratos** (∴ ◈ ○ ⇄) de pesos inconsistentes + sessão ("Conectado como…") ocupando barra full-width. → Frente S
> 8. Busca do Market coadjuvante (placeholder truncado, recentes no canto oposto, detalhes em prosa). → Frente U
> 9. Sem atalho de poder: 7 telas + ~10 ações e nenhum acesso rápido global. → Frente V (Ctrl+K)
>
> **Para agentes executando estas frentes**: cada frente é autocontida (contexto → ação → não-fazer → aceite). Antes de QUALQUER edição, leia §1 (padrões), §3 (outliers — não tocar), §4 (workflow/validação/commit). Regras inegociáveis: Python 3.9, PyQt6, gráficos/ícones só com QPainter custom (nunca lib externa), cores/tamanhos via tokens `t.*` de `theme.py` (nunca hex inline novo — se precisar, adicione token), tooltip em todo botão, commit pt-BR sem Co-Authored-By, **1 frente = 1 commit**, e ao concluir marcar a frente com ✅ + parágrafo de resultado aqui no roadmap (padrão das frentes A-J).
>
 > **Ordem**: M primeiro e sozinha (invalida screenshots anteriores — todas as outras frentes validam visual contra o baseline pós-M). Depois N/O/P/Q/R/S em paralelo. T e U dependem de N. V por último.
 >
 > Concluídas: ✅**M**, ✅**N**, ✅**O**, ✅**P**, ✅**Q**, ✅**U**. Próximas: R, S, T, V.

 ~~### Frente M — Matar a propagação de QSS global: as "tarjas" atrás de todo label (esforço: 1-2h, impact: ALTÍSSIMO) [deps: nenhuma — RODAR PRIMEIRO]~~ ✅

**Problema**: `gui.py::MainWindow._apply_stylesheet` (grep `def _apply_stylesheet`) aplica `self.setStyleSheet(f"background: {_BG}; color: {_TEXT}; font-family: ...")` **sem seletor**. QSS sem seletor propaga a TODOS os descendentes: cada `QLabel` da aplicação herda `background: #0E0E12` e pinta uma tarja escura atrás do texto — sobre cards `#16161C` isso cria as faixas visíveis em TODOS os StatCards, títulos de seção e captions de TODAS as telas (qualquer print em `prints/` mostra). É o maior ofensor visual do app. Mesmo bug em `SettingsDialog.__init__` e `BackupsDialog.__init__` (grep `setStyleSheet(f"background: {_BG}` em `gui.py` — 3 sites no total).

**Ação**:
1. Nos 3 sites, restringir o background ao container e manter cor/fonte como herança intencional:
   ```python
   # MainWindow:
   self.setStyleSheet(
       f"QMainWindow {{ background: {_BG}; }}"
       f"* {{ color: {_TEXT}; font-family: 'Segoe UI Variable Display',"
       f" 'Segoe UI', system-ui; }}"
   )
   # Dialogs: QDialog {{ background: {_BG}; }} + mesmo bloco *
   ```
   `* {{ color/font }}` é propagação desejada (texto padrão do app); widgets com setStyleSheet próprio (label_caption etc.) vencem por especificidade — comportamento atual preservado. `background` NÃO pode estar no `*`.
2. Auditar band-aids que só existiam pra anular a herança: `grep -n "background: transparent" skinvault/ skinvault/ui/` — remover um a um validando por screenshot (alguns são legítimos, ex. btn_ghost idle).
3. Bônus de janela (mesma frente): titlebar escura no Windows via DWM, em `MainWindow.__init__` (e nos QDialogs de Settings/Backups):
   ```python
   try:  # Win11/10 1809+; falha silenciosa em SOs antigos
       import ctypes
       hwnd = int(self.winId())
       for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (20; 19 em builds antigos)
           if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                   hwnd, attr, ctypes.byref(ctypes.c_int(1)),
                   ctypes.sizeof(ctypes.c_int)) == 0:
               break
   except Exception:
       pass
   ```
4. Conferir `theme._reload_palette` / `gui.set_theme`: o stylesheet novo precisa ser reaplicado no live-reload de tema (grep `set_theme` em gui.py).

**Não fazer**: não trocar nenhum token/cor; não "consertar" labels individualmente (o fix é na raiz); não usar QPalette pra background (QSS é o mecanismo da casa).

**Aceite**: screenshots novos das 7 telas sem NENHUMA tarja atrás de label (comparar 01/05/06 antes/depois — os mais afetados); botões/inputs/tabelas visualmente idênticos ao estado anterior; titlebar escura; suíte 100% verde.

**Validação**: §4.3 completo + regenerar TODOS os prints (novo baseline). Commit: `ui: QSS com seletor no root — fim das tarjas atras de labels + titlebar dark`.

**Resultado**: 7 sites total (3 gui.py + 2 components.py + screen_router.py + login_gate.py) migrados para QSS com seletor. Toast band-aid removido. Titlebar escura nas 3 janelas, adiada para `showEvent` (chamar `winId()` + DWM no `__init__` causava crash SIGSEGV em modo grab). Lição: **QSS sem seletor em QUALQUER ancestral reintroduz a propagação — mesmo que a raiz tenha seletor, filhos podem propagar de volta**. Audit completo dos 7 sites: MainWindow `_apply_stylesheet`, SettingsDialog, BackupDialog, ScreenRouter, Sidebar, LockOverlay, LoginGate. `background: transparent` auditado: 1 band-aid removido (Toast label), 7 legítimos. 1309 tests verdes. Screenshots regenerados como novo baseline — tamanhos reduzidos (especialmente 02-history: -2480B, consistente com menos ruído de tarja).

**Hotfix pós-M (a0db650)**: a remoção das tarjas revelou um overlap latente no `ActivityFeed` — o título "Atividade recente" colidia com o primeiro item da lista porque o rótulo vazio usava `AlignCenter` (vertical + horizontal), centralizando o texto na vertical e sobrepondo-o ao título quando o layout do Card não dava altura suficiente ao `_list_lay`. Fix: `AlignCenter` → `AlignHCenter` (vertical centering removido) + `title.setWordWrap(False)` no título. O bug sempre existiu, mas o background opaco herdado do QSS global escondia a colisão.

~~### Frente N — PageHeader compacto e consistente nas 7 telas (esforço: 2-3h, impact: alto) [deps: M]~~

~~**Problema**: H1 avulso de 24pt (`FS_TITLE`) consome ~90px verticais antes do primeiro dado (prints 03-07). Account é a ÚNICA tela sem título de página — quebra o padrão de cabeçalho explicativo (Athenas). No Scanner o QComboBox de categoria está montado NA LINHA do H1. Na Account, 3 botões empilhados à direita do card de perfil com larguras desalinhadas.~~

~~**Ação**:~~
~~1. Novo componente `PageHeader(title, subtitle="", actions: list[QWidget] | None = None)` em `components.py`: HBox = VBox(título 16pt semibold + subtítulo `label_caption()`) + stretch + actions à direita; altura total ≤ 56px. Adicionar token `FS_TITLE_MD = "16pt"` em theme.py (entre FS_TITLE_SM 13pt e FS_TITLE 24pt).~~
~~2. Migrar as 7 telas: título/subtítulo existentes entram no PageHeader; ações primárias da tela (ex.: combo categoria + "Escanear categoria" no Scanner; "Consultar item" no Market; "Adicionar trade" no Trades) viram `actions`.~~
~~3. Account ganha header: "Minha Conta" / "Inventário, desempenho da carteira e sincronização Steam." — Sincronizar/Validar/Atualizar scores saem do card de perfil e viram actions (corrige o desalinhamento).~~
~~4. Padronizar root das telas: `setContentsMargins(24, 16, 24, 16)`, `setSpacing(12)`.~~

~~**Não fazer**: não tocar no breadcrumb; não mudar `label_section()` (títulos DENTRO de cards ficam).~~

~~**Aceite**: 7 telas com PageHeader; `grep -n "FS_TITLE\b" skinvault/ui/*_screen.py` → 0 hits; Account com header e ações alinhadas; ~40px verticais recuperados por tela.~~

**Resultado**: `PageHeader` implementado em `components.py` (52px, HBox=VBox(title+subtitle) + stretch + actions). Token `FS_TITLE_MD = "16pt"` adicionado. Todas as 7 telas migradas: Account (header "Minha Conta" + sync/validate/refresh viram actions no PageHeader — saíram do card de perfil), History ("Histórico" + subtitle), Scanner (title + combo + Escanear/Ranking/Validar como actions), Market ("Consulta de Mercado" + Consultar item como action), Trades ("Histórico de Trades" + Adicionar trade + "⋯" como actions), Simulador, Watchlist. Root margins padronizados para `(24, 16, 24, 16)` com spacing 12. `FS_TITLE` eliminado das screens (`grep` 0 hits). 1309 tests verdes. Screenshots regenerados.

~~### Frente O — StatCards inteligentes: delta, contexto, estado neutro (esforço: 2h, impact: médio-alto) [deps: M]~~

~~**Problema**: (1) KPIs mostram número seco sem variação nem contexto. (2) Cor semântica errada em estado neutro: Trades exibe "0% (0W / 0L)" em DANGER com zero trades (print 05) — vermelho significa perda, não ausência de dado. (3) Em 1920px os StatCards esticam igualmente (~450px pra um número de 8 chars — prints 03/05).~~

~~**Ação**:~~
~~1. `StatCard.set_delta(pct: float | None, label: str = "")` em components.py: linha FS_MUTED sob o valor — `▲ +2,4% {label}` (ACCENT), `▼ -1,1%` (DANGER), `— {label}` (TEXT_MUTED); `None` esconde. Setas unicode ▲▼, nunca emoji.~~
~~2. Ligar onde já há dado: Account "Valor bruto" → % vs penúltimo ponto de `history.load_history()` (a tela já carrega a série — grep `_reload_value_series` em account_screen.py); Trades "P&L líquido" → vs mês anterior via `trades.monthly_pnl()`; Watchlist "Alertas em 24h" → label "último: HH:MM" do alerts_log (sem %).~~
~~3. Estado neutro: auditar `grep -n "set_value" skinvault/ui/*_screen.py` — valor zero-sem-dados usa `t.TEXT`/`t.TEXT_MUTED`, NUNCA DANGER/ACCENT. Pior ofensor: taxa de acerto do trades_screen.~~
~~4. Proporção: `setMaximumWidth(300)` no StatCard + `addStretch(1)` no fim das KPI rows (Scanner, Trades, Watchlist, Market, Account) — cards alinham à esquerda em monitor largo.~~

~~**Não fazer**: NÃO animar números (animated counter descartado na Frente F); sem sparkline dentro de StatCard (escopo).~~

**Resultado**: `StatCard.set_delta()` implementado em components.py com 3 estados (▲ ACCENT, ▼ DANGER, — TEXT_MUTED) + `pct=None` para texto contextual. Dados ligados: Account "Valor bruto" → % vs penúltimo ponto do history; Trades "P&L líquido" → vs mês anterior via `monthly_pnl()`; Watchlist "Alertas em 24h" → timestamp do último alerta. Estado neutro fixado: `_stat_winrate` de trades usa `TEXT_MUTED` quando total=0 (antes DANGER). `setMaximumWidth(300)` + `addStretch(1)` aplicados nas 5 telas com KPI rows (Account: 2 rows, Scanner, Trades, Market, Watchlist). Smoke tests de `set_delta` (3 estados) adicionados. 1309 tests verdes. Screenshots regenerados.

~~### Frente P — Tabelas: zebra sutil, hover, headers íntegros, Watchlist legível (esforço: 2-3h, impact: alto) [deps: M]~~ ✅

~~**Problema**: (1) Headers truncam — print 07 mostra "Preco alvo"→"'reco alvo" (sort indicator + padding comem o texto em ResizeToContents). (2) Sem zebra nem hover — History com 416 rows cansa. (3) Watchlist: "OK" verde pra item SEM regra (sem regra ≠ saudável); Regras/Score/Confiança cheios de "—"; falta o dado mais útil: distância ao preço-alvo (AWP R$898 vs alvo R$700 = +28%).~~

~~**Ação**:
1. Em `theme.py::configure_table`: `table.setAlternatingRowColors(True)` + QSS `alternate-background-color: rgba(255,255,255,0.018)`; hover `QTableWidget::item:hover {{ background: {SURFACE_HOV}; }}` (hover é por célula — se ficar "quadriculado" no uso real, descartar e registrar no §3); `hh.setMinimumSectionSize(96)` + revisar padding da `QHeaderView::section` até o print da Watchlist mostrar os headers completos.
2. `watchlist_screen.py`: Status com 3 estados — "Sem regras" (TEXT_MUTED) / "Monitorando" (STEAM_BLUE) / "Disparado" (WARN); grep `"OK"` pra achar o site. Nova coluna "Distância ao alvo": `(atual-alvo)/alvo` como `+28,3%` — ACCENT quando atual ≤ alvo (favorável pra compra), DANGER quando acima; tooltip explicando a leitura (§1.6). Colunas Score/Confiança 100% "—" → `setColumnHidden(True)` até existir dado (aparecem pós "Validar Score").
3. Zebra/hover valem automaticamente pra todas as telas com tabela (1 helper).~~

~~**Não fazer**: não mexer em larguras por tela (Stretch do Item é o padrão §1.5); sem paginação.~~

~~**Aceite**: print 07 com headers completos, status 3-estados e coluna de distância; zebra sutil (alpha ≤0.02 — não pode "listrar"); History com 416 rows fluida.~~

**Resultado**: `configure_table` ganhou `hh.setMinimumSectionSize(96)` para headers íntegros. Watchlist: 3 estados de status (Sem regras/Monitorando/Disparado) com cores TEXT_MUTED/STEAM_BLUE/WARN e tooltips descritivos; nova coluna "Distância ao alvo" após o preço-alvo com cor ACCENT (favorável) ou DANGER (acima do alvo) e tooltip explicativa; colunas Score e Confiança ocultas inicialmente (reveladas após "Validar Score"). 1309 tests verdes. Screenshots regenerados.

**Hotfix 2** (`ecfba84..HEAD`): headers AINDA truncavam no print real — causa raiz: padding de `QHeaderView::section` (28px horizontal) não contabilizado no sizeHint do `ResizeToContents`/`Interactive`. Corrigido via (a) redução do padding QSS de `10px 16px 10px 12px` para `8px 10px 8px 10px`; (b) `setMinimumSectionSize(120)`; (c) nova função `_ensure_header_width()` que força `resizeSection` com folga de 50px; (d) Watchlist migrou de `ResizeToContents` para `Interactive` (evita que Qt sobrescreva o resize). Smoke test `test_table_headers_nao_truncam` valida que colunas com texto longo (> que cabe no mínimo) recebem espaço extra. 1310 tests verdes.

~~### Frente Q — Empty states acionáveis + fim dos charts-oceano (esforço: 2-3h, impact: alto) [deps: M]~~ ✅

~~**Problema**: estado vazio = 70% viewport deserto (prints 03/04/05). Market é o pior: 2 cards de chart com stretch infinito (~600px) pra exibir "Sem historico" no centro.~~

~~**Ação**:
1. `EmptyState` (components.py) ganha param opcional `steps: list[str]`: lista numerada compacta (círculo 20px ACCENT_DIM com o número + `label_body_muted`) renderizada sob o subtítulo — onboarding no lugar do vazio.
2. Aplicar: Scanner (1. Escolha uma categoria 2. Clique em Escanear 3. Duplo-clique numa linha explica o score), Trades (1. Adicione manualmente ou sincronize 2. Acompanhe P&L e taxa de acerto 3. Clique numa barra do P&L mensal pra filtrar), Watchlist vazia (1. Adicionar item 2. Editar regras 3. Receber alertas nativos).
3. Market: charts Histórico/Livro com `setFixedHeight(300)` em vez de stretch (grep `Histórico de preços` em market_screen.py); o espaço liberado vai pro card "Detalhes do item".
4. Revisar consistência dos EmptyState existentes (glifo geométrico, título curto, CTA quando há ação óbvia).~~

~~**Não fazer**: sem ilustrações/imagens externas; sem cards fake; manter os glifos hero atuais (◇ ○ ◎ — assinatura).~~

**Resultado**: EmptyState ganhou param `steps` (círculo 20px ACCENT_DIM + número + `label_body_muted`), aplicado em Scanner, Trades e Watchlist com onboarding de 3 passos cada. Market: chart cards trocaram stretch por `setFixedHeight(300)`, liberando espaço pro card "Detalhes do item". Market EmptyState ganhou CTA "Tentar novamente" conectado a `_on_search`. Consistência revisada: todos os 6 EmptyStates usam glifo geométrico, título curto e CTA onde há ação óbvia (Account sync, Watchlist add, Trades add, Market retry; Scanner e History sem CTA porque a ação primária está no PageHeader/toolbar). Extra: P&L líquido em trades_screen.py mostra `t.TEXT` (neutro) quando não há trades no filtro (antes ACCENT verde para R$ 0,00). 1313 tests verdes. Screenshots regenerados.

### Frente R — Despir o Qt cru: spinbox, checkbox, combo popup, scrollbar (esforço: 2-3h, impact: médio-alto) [deps: M]

**Problema**: 4 controles ainda com chrome nativo claro no dark theme: QDoubleSpinBox do Simulador (setas nativas, print 06); QCheckBox indicator branco (Scanner/Watchlist, prints 03/07); popup do QComboBox do Scanner (QAbstractItemView nativo); QScrollBar nativo (History/Activity feed).

**Ação** (helpers novos em theme.py + aplicar nos sites):
1. `spin_style()`: bg SURFACE, border BORDER radius 6, `::up-button/::down-button` 18px com border-left BORDER, setas via `::up-arrow/::down-arrow` (triângulo CSS, sem imagem). Aplicar no Simulador (grep `SpinBox` em simulador_screen.py). Alternativa aceitável: migrar pra QLineEdit + QDoubleValidator se o spin não agrega (documentar a escolha).
2. `checkbox_style()`: `QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER}; border-radius: 4px; background: {SURFACE}; }}` + `::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}` + `:focus` consistente com Frente C. NOTA: o outlier da §3 sobre esses QCheckBox é do styling de LABEL — o indicator é novo escopo; helper centraliza.
3. Popup de combo: `QComboBox QAbstractItemView {{ background: {BG_ELEVATED}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_HOV}; color: {TEXT}; }}` — integrar ao estilo existente do combo do Scanner.
4. Scrollbar global fina no stylesheet do MainWindow (coordenar com M — mesmo bloco QSS): track transparente 10px, handle radius 5 min-height 32, sem add/sub-line. Tokens novos `SCROLL_THUMB = "#2E2E38"` / `SCROLL_THUMB_HOV = "#3A3A46"` em theme.py.

**Não fazer**: não trocar QComboBox por widget custom; não esconder scrollbar quando há overflow.

**Aceite**: varredura visual dos prints novos sem nenhum chrome nativo claro; helpers listados no §0; smoke test de instanciação por helper.

**Validação**: §4.3. Commit: `ui: estiliza spinbox/checkbox/combo-popup/scrollbar — fim do chrome Qt nativo`.

### Frente S — Sidebar: ícones de linha QPainter + sessão no rodapé (esforço: 3-4h, impact: alto — assinatura visual) [deps: M]

**Problema**: (1) `_SidebarItem` embute glifos unicode no texto (`setText(f"  {icon}    {label}")` em components.py) — ∴ ◈ ○ ★ ⇄ ▭ ≡ têm pesos/larguras inconsistentes e não comunicam. (2) "Conectado como {nome}" ocupa barra full-width na base da janela inteira.

**Ação**:
1. `class LineIcon(QWidget)` (em components.py): ícone 18×18 desenhado com QPainter, stroke 1.5px, `QPen.setCapStyle(RoundCap)`, SEM fill (linguagem Fluent/Lucide). `set_color(str)` pra acompanhar estado. Ícones por nome: `user` (círculo + arco ombros), `history` (relógio: círculo + 2 ponteiros), `radar` (2 arcos concêntricos + dot), `chart` (polyline 3 segmentos), `swap` (2 setas opostas), `calc` (rect + grid 2×2 de dots), `eye` (2 arcos + pupila), `gear` (círculo + 6 ticks radiais), `info` (círculo + i), `archive` (rect + tampa). Nome inválido → círculo (fallback).
2. `_SidebarItem` muda de texto-com-glifo pra HBox: LineIcon + QLabel, preservando os estados QSS atuais (:hover/:checked/:focus — Frente C); checked pinta o ícone com `set_color(t.ACCENT)` (conectar no toggled).
3. Chip de sessão no rodapé da SIDEBAR substituindo a barra global: dot 8px ACCENT + nome TEXT + "Steam" caption; tooltip com SteamID; clique navega pra Minha Conta. Localizar a barra atual com grep `Conectado como` (gui.py) — remover ou reduzir o footer global ao que sobrar de responsabilidade (avaliar e documentar).
4. Smoke tests: LineIcon paint por nome (grab não-nulo) + fallback.

**Não fazer**: NUNCA emoji/PNG/SVG (regra: QPainter); não mudar SIZE_SIDEBAR_W; sem collapse de sidebar nesta frente.

**Aceite**: sidebar com 7 itens + 3 inferiores usando ícones de linha consistentes (mesmo stroke/peso óptico); checked em ACCENT; sessão no rodapé da sidebar; barra inferior global removida/reduzida; prints das 7 telas ok.

**Validação**: §4.3. Commit: `ui: sidebar com icones de linha QPainter + chip de sessao no rodape`.

### Frente T — Scanner: cada controle no seu lugar (esforço: 2h, impact: médio) [deps: N]

**Problema** (print 03): combo de categoria dentro do título; checkboxes de filtro soltos entre header e KPIs; a dica mais importante ("duplo-clique explica o score") enterrada em caption de rodapé; "Limpar cache SSR"/"Exportar CSV" desalinhados dos botões.

**Ação**:
1. Com o PageHeader (N): combo + "Escanear categoria" (primário) + "Ranking Top 20" + "Validar Score" como actions; "Limpar cache SSR"/"Exportar CSV" descem pra toolbar ghost acima da tabela (tooltips §1.2).
2. Checkboxes "Esconder baixa confiança"/"Esconder order book aproximado" → linha de filtros imediatamente acima da tabela (visual da _FilterBar da History).
3. Dica do duplo-clique → tooltip do header da coluna Score (`horizontalHeaderItem(col).setToolTip(...)`) + consolidar o rodapé em UMA linha de caption (hoje 2-3 empilhadas).
4. Conferir tab order pós-reorganização (Frente C documentou a ordem — manter coerência com a visual).

**Não fazer**: não tocar na lógica de scan/ranking/score; não esconder KPIs.

**Aceite**: print do Scanner com header limpo, filtros junto da tabela, rodapé com ≤1 caption; tab order coerente.

**Validação**: §4.3. Commit: `ui: scanner — controles agrupados por contexto, dica de score na coluna`.

### Frente U — Market: busca protagonista + detalhes em grid (esforço: 2-3h, impact: médio) [deps: N, Q] ✅

**Problema** (print 04): input de busca pequeno (placeholder trunca: "Ex: AK-47 | Redli..."); botão "Consultar item" no extremo oposto do input; "Buscas recentes" como dropdown deslocado; "Detalhes do item" em prosa espremida na base.

**Ação**:
1. Linha de busca protagonista: input `setMinimumWidth(420)` + "Consultar item" (primário) COLADO à direita do input; garantir `returnPressed` → consultar.
2. "Buscas recentes" vira popup do próprio input: ao focar (ou ao digitar), menu flutuante com as últimas N — os dados já existem (grep `Buscas recentes` em market_screen.py); remover o dropdown solto.
3. "Detalhes do item" vira QGridLayout 2 colunas chave→valor (`label_caption_bold` + valor TEXT; Veredito com cor semântica ACCENT/WARN/DANGER) — usar os campos que a tela já calcula.
4. Conferir charts a 300px fixos (se Q já rodou; senão aplicar a spec da Q item 3 aqui).

**Não fazer**: não tocar em SSR/parse/rate-limit; sem autocomplete remoto.

**Aceite**: print do Market com busca em destaque + CTA junto, recentes acessíveis pelo input, detalhes em grid; charts 300px.

**Validação**: §4.3. Commit: `ui: market — busca protagonista, recentes no input, detalhes em grid`.

**Resultado**: (1) Input `setMinimumWidth(420)` + botão "Consultar item" colado à direita numa HBox dedicada — saiu do PageHeader e do Toolbar; `returnPressed` continua consultando. (2) "Buscas recentes" removido como botão solto; vira `QAction("▾")` no trailing do input, exibe o mesmo `_recent_menu` via `_show_recent_menu()` que executa o menu ancorado no bottomLeft do input. (3) Detalhes migraram de `QFormLayout` + `label_caption()` para `QGridLayout` 2 colunas com labels em `label_caption_bold()` e valores em `FS_BODY` semibold; `_add_detail` → `_add_detail_row`, `_clear_detail_form` → `_clear_detail_grid`. (4) Charts mantêm `setFixedHeight(300)` da Frente Q. `Toolbar` removido dos imports. 1316 tests verdes.

### Frente V — Command palette Ctrl+K (esforço: 4-6h, impact: alto; AMBICIOSA — por último) [deps: M-U]

**Oportunidade**: 7 telas + ~10 ações frequentes e nenhum acesso rápido global. Command palette (padrão VS Code/Raycast/Linear) é o selo de produto moderno — e o usuário é power user.

**Ação**:
1. Novo `skinvault/ui/palette.py`: função pura `palette_rank(query: str, items: list[dict]) -> list[dict]` — fuzzy por subsequência case-insensitive com score (match no início > contíguo > espalhado). SEM dependência de GUI (testável com pytest puro).
2. `CommandPalette(QDialog)`: frameless, 560px, top 20%, bg BG_ELEVATED border BORDER radius 12; QLineEdit FS_INPUT + lista de resultados (LineIcon da Frente S se disponível + label + categoria muted). Sombra permitida AQUI (modal único, perf não-recorrente — exceção documentada à regra anti-shadow).
3. Registro estático no MainWindow: 7 navegações ("Ir: Scanner"…) + ações ("Consultar item no Market", "Adicionar trade", "Adicionar à watchlist", "Sincronizar com Steam", "Backup agora", "Exportar CSV da tela atual"). Ações com input navegam e focam o campo (grep `def focus_` em skinvault/ui/ — vários já existem).
4. `QShortcut(Ctrl+K)` global; Esc fecha, Enter executa, ↑↓ navegam.
5. Tests: `palette_rank` puro (≥5 casos: prefixo vence, case-insensitive, sem match → vazio, ordenação estável) + smoke de abrir/executar navegação.

**Não fazer**: não indexar dados dinâmicos (inventário/preços) nesta versão; se uma ação não tiver foco programático, degradar pra navegação simples.

**Aceite**: Ctrl+K abre em qualquer tela; "scan"+Enter navega pro Scanner; "trade" lista ≥2 ações; visual 100% tokens; testes verdes.

**Validação**: §4.3. Commit: `ui: command palette Ctrl+K — navegacao e acoes globais com fuzzy match`.

---

## 3. Outliers conhecidos (decisão consciente, não tocar)

Lista de inline styles que **deliberadamente ficam inline** — extrair helpers para essas variantes piora o codebase.

| Arquivo:linha | O quê | Por quê |
|---|---|---|
| `theme.py:148` `color: #DCFFE6` | btn_primary text | Tint específico de ACCENT para contraste; vive dentro do helper |
| `theme.py:156-157` `#777, #333, #1a1a20` | btn_primary disabled | States específicos do disabled |
| `theme.py:164` `color: #DDF4FF` | btn_steam text | Idem, tint de STEAM_BLUE |
| `theme.py:176` `border #3A3A44` | btn_secondary border | Border mais claro que BORDER padrão (separator strong) |
| `theme.py:185` `color: #FFE6E6` | btn_danger text | Tint de DANGER |
| `theme.py:230` `border-top #30303A` | card_style top highlight | Hierarquia visual sutil (commit `f2668bd`) |
| `components.py:146` `padding=(20,16,20,16)` | StatCard | Único padding LG horizontal + MD vertical; intencional pra display compacto |
| `components.py:668` `letter-spacing: 1px` | _TradeHistoryStrip eyebrow | Spacing visual único |
| `components.py:357-359` Avatar `?` styling | Fallback quando sem imagem | Composição com setStyleSheet existente |
| `scanner_screen.py:220-223` `DANGER bold` | Mensagem de erro do simulador | Validation feedback, contexto único |
| `scanner_screen.py:340-341` `font-style: italic` | hist_src vintage label | Tipográfico único |
| `scanner_screen.py:574-575` `padding-top: 4px` | scatter_lbl | Spacing local |
| `scanner_screen.py:646-647` `padding-top: 6px` | baseline | Spacing local |
| `scanner_screen.py:871-873` `QCheckBox{}` | hide_low_conf | QCheckBox selector, não QLabel |
| `watchlist_screen.py:282-284` `QCheckBox{}` | hide_low_conf | Idem |
| `widgets.py:298-319` `QColor(34,197,94,40)` etc. | DepthChart bid/ask | RGB tuples para alpha; tokenizar em Frente D acima |
| `widgets.py:145,173,330` chart pens | Agora usa CHART_YELLOW/INDIGO ✓ | Já migrado em `35d8974` |

**Regra de bolso**: se você está prestes a extrair um helper que só será chamado 1 vez no codebase, **não extrai**. Documenta com comentário inline.

---

## 4. Notas operacionais

### 4.1 Rodar screenshots

```bash
# Normal (com guard CS2):
python _screenshot.py

# Bypass guard (quando CS2 está em background não-fullscreen):
SKIP_GAME_GUARD=1 python _screenshot.py
```

O script NÃO chama `win.show()` — usa `WA_DontShowOnScreen` evitado, `resize() + processEvents() + grab()`. Zero janela aparece. Zero risco de roubar foco do CS2. Commit `4017654` documenta a história.

Output em `prints/`:
```
01-account, 02-history, 03-scanner, 04-market, 05-trades, 06-simulador, 07-watchlist
```

### 4.2 Rodar testes

```bash
python -m pytest tests/ -x -q
```

Suíte completa: ~185s, 1309 testes (estado atual). Após mudanças de UI, sempre rodar antes de commit — mesmo polishes "puro CSS" porque podem mexer em imports.

Para subset rápido (sem GUI):
```bash
python -m pytest tests/ -x -q -k "not ui and not gui"
```

### 4.3 Workflow de polish (audit → edit → validate → commit)

1. **Audit**: `grep -rnA1 "<pattern>" skinvault/ui/*.py` para listar candidatos.
2. **Classify**: clean (canonical) vs outlier (extra CSS) — outlier fica inline.
3. **Edit**: substituir bloco inline por helper.
4. **Import check**: `python -c "import skinvault.ui.foo"`.
5. **Visual check**: `SKIP_GAME_GUARD=1 python _screenshot.py` + abrir um print.
6. **Tests**: subset rápido `pytest -x -q`.
7. **Commit**: mensagem descritiva no padrão pt-BR (vide histórico). NÃO usar Co-Authored-By (projeto não usa).
8. **Cleanup**: `git checkout prints/` para descartar pixel-diff não-significativo em PNGs.

### 4.4 Convenção de commit (pt-BR)

```
ui: <verbo no presente> <o que mudou>

<corpo: o que/por que, não como. Listas com - se mais de 1 item>

<menção a commits anteriores se relevante: 'continua a23659a'>
```

Exemplos da sessão:
- `ui: simulador migra para FormRow + FormRow ganha tooltip opcional`
- `ui: extract t.configure_table() helper, consolida boilerplate de 5 telas`
- `ui: 3 helpers de label inline (caption/body_muted/section), -19 LOC`

### 4.5 Pre-commit checklist

- [ ] `git diff` revisado linha-a-linha
- [ ] Imports sem QAbstractItemView/QColor mortos após refactor
- [ ] `python -c "import skinvault.ui.<arquivo_tocado>"` passa
- [ ] `pytest -x -q` passa (ou pelo menos subset não-UI)
- [ ] Screenshot mostra zero regressão visual onde aplicável
- [ ] `git status` limpo após `git checkout prints/` se prints foram só re-gerados

---

## 5. Bug tracker / débito conhecido

Não detectado nesta sessão, mas potencial:

- **history_screen scrollbar custom** linha 511. Pode ter inconsistência de cor com tema. Validar quando houver muitas rows.
- **Toast positioning** em multi-monitor. Não testado.
- **High-DPI**: fonts em pt podem renderizar diferente em 4K. Testar `scaleFactor` setting.
- **Light theme** existe (`_reload_palette` em `theme.py`) mas não foi polido nesta sessão — dark recebeu todo o foco. Light pode ter regressões.

---

## 6. Apêndice: comandos úteis

```bash
# Auditoria de patterns inline
grep -rnA1 "color: {t\.TEXT_MUTED}; font-size: {t\.FS_MUTED}" skinvault/ui/*.py

# Listar tokens disponíveis em theme.py
grep -E "^[A-Z_]+ +=" skinvault/ui/theme.py

# Listar helpers em theme.py
grep -E "^def " skinvault/ui/theme.py

# LOC por screen
wc -l skinvault/ui/*.py | sort -n

# Tooltip coverage
for f in skinvault/ui/*.py; do
  b=$(grep -c "QPushButton(" "$f")
  t=$(grep -c "setToolTip" "$f")
  [ "$b" -gt 0 ] && echo "$f: $b btn / $t tt"
done

# Buttons inline (que NÃO usam helpers)
grep -rn "QPushButton.*setStyleSheet" skinvault/ui/*.py | grep -v "t\.btn_"

# Hex hardcoded fora de theme.py
grep -rEn "#[0-9A-Fa-f]{6}" skinvault/ui/ | grep -v theme.py
```

---

## 7. Onde parar este roadmap

Este documento descreve o estado **pós-commit `7065198`** (sessão de 16 commits de polish).

Próxima sessão começa com:
1. Ler este arquivo top-down.
2. Confirmar `git log --oneline -1` mostra `7065198` ou descendente.
3. Escolher uma frente (A–L) baseado em apetite de tempo e energia.
4. Seguir workflow da §4.3.

Boa polish.

— Pedro / agente Claude (10 jun 2026)
