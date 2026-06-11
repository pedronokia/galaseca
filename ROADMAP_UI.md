# SkinVault — Roadmap de UI Polish

> Documento de continuidade. Resume o estado atual da UI, padrões estabelecidos, e próximas frentes de polish ordenadas por impacto/esforço.
>
> **Audience:** próximo agente (opencode/outro) que vai pegar este trabalho do zero.
> Cada item tem **arquivo:linha** e **ação concreta**, não vibe. Leia top-down.

---

## 0. Snapshot do estado atual

**Última sessão fechou em commit `7065198`.** 16 commits sequenciais (`f2668bd` → `7065198`) consolidam um sistema de design tokens + helpers visuais.

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

> Ordenação: ~~**A** > B > C > D > E > F > G > H > I~~ > **H** > **J** > **K** > **L** (restantes)

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

### Frente H — Charts polish (esforço: 2h, impact: alto)

`widgets.py` tem 4 charts custom (`MiniSparkline`, `DepthChart`, `MonthBarChart`, `ValueChart`). Todos QPainter raw, sem tooltips ou hover interactivity.

**Sugestões**:
- **Hover tooltip** em MiniSparkline mostrando preço + data no ponto.
- **DepthChart**: mostrar best_bid/best_ask como labels nas pontas, não só linha dashed.
- **MonthBarChart**: clicar numa barra abre filter da History naquele mês.
- **ValueChart**: animação de transição quando série atualiza (interpolate paths).

Cada um é um sub-feature. Mapear cada `paintEvent` e adicionar `mouseMoveEvent` para hover, `mousePressEvent` para click. **Não usar bibliotecas de chart** (PyQtGraph etc.) — viola a regra `Preferir QPainter custom widgets a bibliotecas de charting` em CLAUDE.md.

~~### Frente I — Inputs polish (esforço: 30min, impact: médio)~~ ✅ `fa05e94`

~~- **Placeholder mais descritivo** em vários `QLineEdit`. Audit nas screens: `setPlaceholderText(...)` em cada input importante.~~
~~- **Validation feedback inline** — atualmente erros aparecem como `QLabel(DANGER)` separado. Ideia: `_input_style_error()` que pinta borda em DANGER quando validação falha. Reset on focus.~~
~~- **Clear button** (X) dentro de QLineEdit pra resetar busca. `QLineEdit.addAction(QIcon, TrailingPosition)`.~~

**Resultado**: history_screen placeholders melhorados ('0,00' → descritivo), `input_style_error()` helper em theme.py com :focus reset, validation aplicada em history_screen _calc (inputs ficam com borda DANGER até foco), market_screen ganhou clear button (os outros 3 inputs já tinham via `setClearButtonEnabled` de sessão anterior). `fa05e94`.

### Frente J — Animations / transitions (esforço: 2–3h, impact: médio)

App é estático demais. Pequenas animações dariam vida:
- **Screen transitions**: fade entre QStackedWidget pages. Já existe `QGraphicsOpacityEffect` import em `components.py` — usar.
- **Loading state crossfade**: ao terminar load, fade out spinner + fade in conteúdo (em vez de hide/show abrupto).
- **Toast slide-in** (atual `Toast` já tem? Verificar).
- **Sidebar item ripple** on click. Subtle.

**Cuidado**: animação demais distrai. Manter sub-200ms e prefer linear/ease-out.

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

Suíte completa: ~196s, 1284 testes (estado em `7065198`). Após mudanças de UI, sempre rodar antes de commit — mesmo polishes "puro CSS" porque podem mexer em imports.

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
