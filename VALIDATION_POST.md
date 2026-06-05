# Post de validação — atualizado (Tarefas 1-5 entregues)

**Objetivo:** descobrir se o ângulo *"desktop local-first, sem login"* importa de
verdade pro comprador/colecionador — ou se é só ideia bonita na minha cabeça.

> ⚠️ **Regras de self-promo:** a maioria dos subs grandes de CS (r/GlobalOffensive,
> r/GlobalOffensiveTrade) **banem divulgação direta**. Estratégias que funcionam:
> - Postar como **pedido de feedback/pesquisa** (não "baixa meu app"), sem link.
> - Subs mais amigáveis a isso: **r/csgomarketforum**, **r/SideProject**,
>   **r/IndieDev**, **r/cs2**. Ler as regras de cada um antes.
> - Responder DM/comentário com o link só se pedirem.
> - Alternativa: um Discord de trade onde você já participa.

---

## Estado atual do app (Jun 2026)

Todas as 5 tarefas de código entregues. **Zero dependência de login Steam.**

### O que cada aba faz

| Aba | Função |
|---|---|
| **Inventário** | Cola teu SteamID64 → vê valor total + tabela de itens + gráfico de valor no tempo |
| **Meu Portfólio** | Adiciona skins que você comprou (nome + custo + qtd) → mostra **lucro REAL pós-taxa 15%** + break-even. A matemática honesta que SIH não mostra |
| **Market Browser** | Digita o nome de um item → vê menor listagem, mediana, volume 24h e **veredito "tá caro/barato"** (anti-ripoff) |
| **Watchlist** | Adiciona item + preço alvo → app monitora em background e **notifica** quando o preço cai |

### Stack
- Python 3.9+ / PyQt6 (desktop)
- `.exe` portátil (PyInstaller, ~1.3 MB + runtime)
- Dados ficam `%APPDATA%/SkinVault/data/` (local, sem nuvem)
- Cache de preços com TTL 6h (não estoura rate-limit do Steam)

### Prints
`prints/` na raiz do repositório.

---

## Versão A — pergunta de pesquisa (mais segura, sem link)

**Título:** Would a *local* (desktop) skin inventory tracker that never touches your Steam login be useful, or do you not care?

**Corpo:**

> I keep seeing people nervous about browser extensions that need access to their
> Steam session (the recurring "is X safe?" threads). So I built a small
> **desktop app** that values your CS2 inventory and tracks its worth over time,
> plus a portfolio tracker with real post-fee P&L, market browser with fair-value
> check, and a price watchlist with desktop alerts.
>
> It only reads **public data** (your SteamID + public Market prices). It never
> asks for your login, never acts on your account, so it literally can't get your
> stuff stolen or your account banned.
>
> Before I go further, I want a reality check from people who actually trade:
>
> 1. Do you currently track your inventory value? With what (SIH, a spreadsheet,
>    a website, nothing)?
> 2. Does "runs locally, no login, your data stays on your PC" actually matter to
>    you — or is it a non-issue?
> 3. What's the one thing existing tools (SIH, Pricempire, etc.) do *badly* that
>    annoys you most?
> 4. Would you pay a few bucks (one-time) for a clean local tool, or only use free?
>
> Not selling anything — genuinely trying to figure out if this is worth building.
> Brutal honesty welcome.

---

## Versão B — post de lançamento (se/quando validar)

**Título:** SkinVault — inventory tracker that lives on your desktop, not in your browser session. No login needed.

**Corpo:**

> Tired of wondering if that browser extension is safe? Me too.
>
> [print here]
>
> **SkinVault** is a free desktop app that:
> - Reads your **public** Steam inventory (just your SteamID, no login)
> - Values everything using live Market prices
> - Shows your **real** P&L after Steam's 15% fee (most tools skip this)
> - Has a **Market Browser**: paste any item name, see lowest price vs median + "fair or overpriced?" verdict
> - **Watchlist**: set a target price, get a desktop notification when it hits
>
> No login. No browser session. No "can this extension steal my knife?" anxiety.
> Your data stays on your PC.
>
> Built with Python/PyQt6, packed as a portable `.exe`.
>
> Free during validation. Would love your feedback.

---

## O que medir (a validação de verdade)

- **Sinal forte:** gente pedindo o link / "quero testar" / descrevendo a dor 3 (fair-value)
  ou a 2 (trust) sem você induzir.
- **Sinal de morte:** "já tenho SIH e tô feliz", "não pagaria nada", silêncio.
- **Regra de decisão:** se em ~3 posts/comunidades não aparecer gente querendo
  testar nem disposta a pagar, **não invista as semanas** — o ângulo trust/local
  não move a agulha, e a gente repensa (ou foca no freela, que paga já).

## Checklist antes de postar
- [ ] Inventário liberado + app rodando no meu próprio SteamID (prova social: print do app)
- [ ] Print bonito do app (a UI vendendo sozinha)
- [ ] Ler as regras do sub
- [ ] Postar como pesquisa, responder rápido os comentários
