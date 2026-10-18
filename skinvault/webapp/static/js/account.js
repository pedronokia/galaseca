// Tela de Conta -- Fase 2. Pinta com o cache (instantaneo) e depois
// escuta o SSE pro resultado da avaliacao completa (com rede).
document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("account-status");
  const refreshBtn = document.getElementById("btn-refresh");
  const tbody = document.getElementById("inventory-body");
  const emptyMsg = document.getElementById("inventory-empty");

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
  }

  function renderRows(rows) {
    tbody.innerHTML = "";
    emptyMsg.hidden = rows.length > 0;
    for (const r of rows) {
      const tr = document.createElement("tr");
      const pnlTxt = r.has_cost ? brl(r.pnl) : "—";
      const pnlCls = r.pnl == null ? "" : (r.pnl >= 0 ? "positive" : "negative");
      tr.innerHTML = `
        <td>${r.display_name || r.name}</td>
        <td class="num">${r.quantity}</td>
        <td class="num">${brl(r.price)}</td>
        <td class="num ${pnlCls}">${pnlTxt}</td>`;
      tbody.appendChild(tr);
    }
  }

  function render(payload) {
    const totals = payload.totals || {};
    renderRows(payload.rows || []);
    setStat("gross", brl(totals.market));
    setStat("net", brl(totals.net_if_sold), { accent: "accent-net" });
    const pnl = totals.pnl;
    if (pnl == null) {
      // evaluate_portfolio so' devolve pnl=None quando NENHUM item tem
      // custo declarado (ver portfolio.py:evaluate_portfolio).
      setStat("pnl", "—", { delta: "nenhum item tem custo declarado" });
    } else {
      setStat("pnl", brl(pnl), {
        accent: pnl >= 0 ? "positive" : "negative",
        delta: totals.pnl_pct != null
          ? `${pnl >= 0 ? "+" : ""}${totals.pnl_pct.toFixed(1)}%` : "",
      });
    }
    setStat("items", String((payload.rows || []).length));

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

  fetch("/api/account/summary")
    .then((r) => r.json())
    .then(render)
    .catch(() => { statusEl.textContent = "Não consegui carregar a carteira."; });

  refreshBtn.addEventListener("click", () => {
    refreshBtn.disabled = true;
    statusEl.textContent = "Avaliando inventário...";
    fetch("/api/account/refresh", { method: "POST" }).then((r) => {
      if (r.status === 409) {
        statusEl.textContent = "Já há uma atualização em andamento.";
        refreshBtn.disabled = false;
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
      const payload = JSON.parse(ev.data);
      if (payload.error) {
        statusEl.textContent = "Falha ao atualizar: " + payload.error;
        return;
      }
      render(payload);
    });
  }
});
