// Tela de Conta -- Fase 2. Pinta com o cache (instantaneo) e depois
// escuta o SSE pro resultado da avaliacao completa (com rede).
document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("account-status");
  const refreshBtn = document.getElementById("btn-refresh");

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);

  function setStat(name, value, opts) {
    opts = opts || {};
    const card = document.querySelector(`.stat-card[data-stat="${name}"]`);
    if (!card) return;
    const valueEl = card.querySelector(".stat-value");
    const deltaEl = card.querySelector(".stat-delta");
    valueEl.textContent = value;
    valueEl.classList.remove("positive", "negative", "accent-net");
    if (opts.accent) valueEl.classList.add(opts.accent);
    if (opts.delta !== undefined) deltaEl.textContent = opts.delta;
    // Mesmo texto do StatCard.setToolTip() do Qt (account_screen.py) --
    // so' nao existia aqui, os 4 cartoes do topo ficavam sem explicacao.
    if (opts.title) card.title = opts.title;
    else card.removeAttribute("title");
  }

  function render(payload) {
    const totals = payload.totals || {};
    setStat("gross", brl(totals.market),
      { title: "Valor de mercado da carteira (Steam Market)." });
    setStat("net", brl(totals.net_if_sold), {
      accent: "accent-net",
      title: "Valor bruto menos a taxa Steam de 15%.",
    });
    const pnl = totals.pnl;
    const total = (payload.rows || []).length;
    const semCusto = totals.unknown_cost || 0;
    const comCusto = total - semCusto;
    if (pnl == null) {
      // evaluate_portfolio so' devolve pnl=None quando NENHUM item tem
      // custo declarado (ver portfolio.py:evaluate_portfolio).
      setStat("pnl", "—", {
        delta: "nenhum item tem custo declarado",
        title: `Nenhum dos ${total} itens tem custo registrado.\n`
          + "Informe o custo na tela Inventário, coluna Custo.",
      });
    } else {
      setStat("pnl", brl(pnl), {
        accent: pnl >= 0 ? "positive" : "negative",
        delta: totals.pnl_pct != null
          ? `${pnl >= 0 ? "+" : ""}${totals.pnl_pct.toFixed(1)}%` : "",
        title: `Calculado sobre ${comCusto} de ${total} itens.\n`
          + `${semCusto} sem custo registrado ficaram de fora.`,
      });
    }
    setStat("items", String(total));

    const now = new Date().toLocaleTimeString("pt-BR",
      { hour: "2-digit", minute: "2-digit" });
    if (payload.rate_limited) {
      statusEl.textContent =
        `${payload.rows.length} item(ns) • a Steam limitou as ` +
        `consultas de preço (${now})`;
    } else {
      statusEl.textContent = `${payload.rows.length} item(ns) • atualizado ${now}`;
    }
  }

  // Se o usuario navegou pra fora da tela de Conta com um refresh em
  // andamento (a thread do servidor continua rodando, publica o SSE
  // "account_eval" pra QUALQUER conexao escutando, independente de
  // quem disparou) e voltou, esta pintura inicial (cache, rapida) e o
  // account_eval desse refresh antigo competem pelo mesmo render(). Se
  // o SSE (dado mais fresco, pos-avaliacao) chegar ANTES desta pintura
  // resolver, nao deixa o cache antigo sobrescrever por cima. Mesma
  // familia de bug ja' corrigida nesta sessao em varios outros pontos.
  let liveApplied = false;
  fetch("/api/account/summary")
    .then((r) => r.json())
    .then((payload) => { if (!liveApplied) render(payload); })
    .catch(() => { statusEl.textContent = "Não consegui carregar a carteira."; });

  refreshBtn.addEventListener("click", () => {
    refreshBtn.disabled = true;
    statusEl.classList.add("is-busy");
    statusEl.textContent = "Avaliando inventário...";
    fetch("/api/account/refresh", { method: "POST" }).then((r) => {
      if (r.status === 409) {
        statusEl.textContent = "Já há uma atualização em andamento.";
        refreshBtn.disabled = false;
        statusEl.classList.remove("is-busy");
      }
    });
  });

  const es = window.skinvaultEvents;
  if (es) {
    es.addEventListener("account_progress", (ev) => {
      const { done, total } = JSON.parse(ev.data);
      statusEl.textContent = `Avaliando inventário... ${done}/${total}`;
    });
    es.addEventListener("account_eval", (ev) => {
      refreshBtn.disabled = false;
      statusEl.classList.remove("is-busy");
      const payload = JSON.parse(ev.data);
      if (payload.error) {
        // Nao marca liveApplied aqui -- se a pintura inicial do cache
        // ainda estiver pendente, deixa ela aplicar normal (melhor
        // mostrar o ultimo dado bom conhecido do que deixar os cartoes
        // vazios pra sempre so' porque ESTE refresh falhou).
        statusEl.textContent = "Falha ao atualizar: " + payload.error;
        return;
      }
      liveApplied = true;
      render(payload);
    });
  }
});
