// Tela de Trades -- Fase 4. CRUD local (sem rede): adicionar, editar
// (reabre o form preenchido) e excluir. O indice de cada trade so' vale
// pro payload atual -- toda acao re-renderiza a partir da resposta do
// servidor, nunca reusa um indice de uma resposta anterior.
document.addEventListener("DOMContentLoaded", () => {
  const tbody = document.getElementById("trades-body");
  const emptyMsg = document.getElementById("trades-empty");
  const addBtn = document.getElementById("btn-add-trade");
  const form = document.getElementById("add-trade-form");
  const cancelBtn = document.getElementById("t-cancel");
  const errorEl = document.getElementById("add-trade-error");
  const fName = document.getElementById("t-name");
  const fBuy = document.getElementById("t-buy");
  const fSell = document.getElementById("t-sell");
  const fQty = document.getElementById("t-qty");
  const fNotes = document.getElementById("t-notes");

  let editingIndex = null;

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);
  const dateFmt = (ts) => ts ? new Date(ts * 1000).toLocaleDateString("pt-BR") : "—";

  function parseMoney(raw) {
    if (raw == null) return null;
    let s = String(raw).trim();
    if (!s) return null;
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
    const v = parseFloat(s);
    return Number.isNaN(v) ? NaN : v;
  }

  function openForm(trade, index) {
    form.hidden = false;
    errorEl.hidden = true;
    editingIndex = index == null ? null : index;
    fName.value = trade ? trade.name : "";
    fBuy.value = trade ? String(trade.buy_cost).replace(".", ",") : "";
    fSell.value = trade ? String(trade.sell_price).replace(".", ",") : "";
    fQty.value = trade ? trade.quantity : 1;
    fQty.disabled = index != null;
    fName.disabled = index != null; // nome tambem e' so' na criacao
    fNotes.value = trade ? (trade.notes || "") : "";
    (index != null ? fBuy : fName).focus();
  }

  function closeForm() {
    form.hidden = true;
    form.reset();
    editingIndex = null;
    errorEl.hidden = true;
  }

  function renderStats(stats) {
    document.querySelector('.stat-card[data-stat="total"] .stat-value')
      .textContent = String(stats.total || 0);
    const pnlEl = document.querySelector('.stat-card[data-stat="pnl"] .stat-value');
    pnlEl.textContent = brl(stats.pnl_total);
    pnlEl.classList.remove("positive", "negative");
    if (stats.total) {
      pnlEl.classList.add((stats.pnl_total || 0) >= 0 ? "positive" : "negative");
    }
    document.querySelector('.stat-card[data-stat="winrate"] .stat-value')
      .textContent = stats.total ? `${stats.win_rate.toFixed(1)}%` : "—";
    document.querySelector('.stat-card[data-stat="winrate"] .stat-delta')
      .textContent = stats.total ? `${stats.win_count} de ${stats.total} no lucro` : "";
  }

  function renderRow(trade) {
    const tr = document.createElement("tr");
    const pnlCls = trade.pnl >= 0 ? "positive" : "negative";

    const cells = [
      trade.name,
      brl(trade.buy_cost),
      brl(trade.sell_price),
      String(trade.quantity),
      brl(trade.net_received),
    ];
    cells.forEach((text, i) => {
      const td = document.createElement("td");
      if (i > 0) td.className = "num";
      td.textContent = text;
      tr.appendChild(td);
    });

    const tdPnl = document.createElement("td");
    tdPnl.className = `num ${pnlCls}`;
    tdPnl.textContent = brl(trade.pnl);
    tr.appendChild(tdPnl);

    const tdNotes = document.createElement("td");
    tdNotes.textContent = trade.notes || "—";
    tr.appendChild(tdNotes);

    const tdActions = document.createElement("td");
    tdActions.className = "row-actions";
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.textContent = "Editar";
    editBtn.addEventListener("click", () => openForm(trade, trade.index));
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "danger";
    delBtn.textContent = "Excluir";
    delBtn.addEventListener("click", () => {
      fetch(`/api/trades/${trade.index}`, { method: "DELETE" })
        .then((r) => r.json())
        .then(applyPayload);
    });
    tdActions.append(editBtn, delBtn);
    tr.appendChild(tdActions);

    return tr;
  }

  function applyPayload(payload) {
    if (payload.error) return;
    tbody.innerHTML = "";
    const items = payload.trades || [];
    emptyMsg.hidden = items.length > 0;
    for (const t of items) tbody.appendChild(renderRow(t));
    renderStats(payload.stats || {});
  }

  fetch("/api/trades").then((r) => r.json()).then(applyPayload);

  addBtn.addEventListener("click", () => {
    if (form.hidden) openForm(null, null);
    else closeForm();
  });
  cancelBtn.addEventListener("click", closeForm);

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const name = fName.value.trim();
    if (!name) return;
    const buy = parseMoney(fBuy.value);
    const sell = parseMoney(fSell.value);
    if (buy === null || Number.isNaN(buy) || buy < 0) {
      errorEl.textContent = "Preço de compra inválido.";
      errorEl.hidden = false;
      return;
    }
    if (sell === null || Number.isNaN(sell) || sell < 0) {
      errorEl.textContent = "Preço de venda inválido.";
      errorEl.hidden = false;
      return;
    }
    // Quantidade so' entra na CRIACAO: `update_trade` nao recalcula
    // cost_total/pnl quando so' ela muda (ver routes/trades.py), entao
    // editar quantidade de um trade existente fica fora deste MVP.
    const body = editingIndex == null
      ? {
          name, buy_cost: buy, sell_price: sell,
          quantity: fQty.value.trim() === "" ? 1 : Number(fQty.value),
          notes: fNotes.value.trim(),
        }
      : { buy_cost: buy, sell_price: sell, notes: fNotes.value.trim() };
    const req = editingIndex == null
      ? fetch("/api/trades", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
      : fetch(`/api/trades/${editingIndex}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
    req.then((r) => r.json()).then((payload) => {
      if (payload.error) {
        errorEl.textContent = payload.error;
        errorEl.hidden = false;
        return;
      }
      closeForm();
      applyPayload(payload);
    });
  });
});
