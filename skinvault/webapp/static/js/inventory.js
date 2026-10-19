// Tela de Inventario -- Fase 3. Tabela com filtro, custo editavel (clique
// na celula) e "+ Adicionar item". Reusa o mesmo payload da Conta
// (account_data.summary_payload) -- mesma avaliacao, mais colunas.
document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("inventory-status");
  const tbody = document.getElementById("inventory-body");
  const emptyMsg = document.getElementById("inventory-empty");
  const filterInput = document.getElementById("filter-input");
  const addBtn = document.getElementById("btn-add-item");
  const addForm = document.getElementById("add-item-form");
  const addCancel = document.getElementById("add-cancel");
  const addError = document.getElementById("add-item-error");
  const importBtn = document.getElementById("btn-import-steam");
  const importForm = document.getElementById("import-steam-form");
  const importCancel = document.getElementById("import-cancel");
  const importProfile = document.getElementById("import-profile");
  const importRemoveMissing = document.getElementById("import-remove-missing");
  const importStatus = document.getElementById("import-status");

  let rows = [];

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);

  function parseCostInput(raw) {
    if (raw == null) return null;
    let s = String(raw).trim();
    if (!s) return null;
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
    const v = parseFloat(s);
    return Number.isNaN(v) ? NaN : v;
  }

  function costCellContent(row) {
    const span = document.createElement("span");
    span.textContent = row.has_cost ? brl(row.cost) : "— (definir)";
    return span;
  }

  function startCostEdit(td, row) {
    td.innerHTML = "";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "cost-edit-input";
    input.value = row.has_cost ? String(row.cost).replace(".", ",") : "";
    input.placeholder = "ex.: 199,90";
    td.appendChild(input);
    input.focus();
    input.select();

    let done = false;
    const commit = () => {
      if (done) return;
      done = true;
      const parsed = parseCostInput(input.value);
      if (parsed === null) {
        render(rows); // cancelou (campo vazio) -- so' redesenha a celula
        return;
      }
      if (Number.isNaN(parsed) || parsed < 0) {
        statusEl.textContent = "Custo inválido — use números, ex.: 199,90.";
        render(rows);
        return;
      }
      fetch("/api/inventory/cost", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: row.name, cost: parsed }),
      })
        .then((r) => r.json())
        .then((payload) => {
          if (payload.error) {
            statusEl.textContent = "Erro: " + payload.error;
            return;
          }
          applyPayload(payload);
        });
    };
    input.addEventListener("blur", commit);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); input.blur(); }
      if (ev.key === "Escape") { done = true; render(rows); }
    });
  }

  function renderRow(row) {
    const tr = document.createElement("tr");
    const pnlTxt = row.has_cost ? brl(row.pnl) : "—";
    const pnlCls = row.pnl == null ? "" : (row.pnl >= 0 ? "positive" : "negative");

    const tdName = document.createElement("td");
    tdName.textContent = row.display_name || row.name;
    const tdQty = document.createElement("td");
    tdQty.className = "num";
    tdQty.textContent = row.quantity;
    const tdPrice = document.createElement("td");
    tdPrice.className = "num";
    tdPrice.textContent = brl(row.price);
    const tdNet = document.createElement("td");
    tdNet.className = "num";
    tdNet.textContent = brl(row.net_if_sold);
    const tdCost = document.createElement("td");
    tdCost.className = "num cost-cell";
    tdCost.title = "Clique para definir o custo";
    tdCost.tabIndex = 0;
    tdCost.setAttribute("role", "button");
    tdCost.appendChild(costCellContent(row));
    tdCost.addEventListener("click", () => startCostEdit(tdCost, row));
    tdCost.addEventListener("keydown", (ev) => {
      // Celula clicavel sem isto nao tinha jeito nenhum de chegar nela
      // via teclado (td nao e' focavel por padrao, sem tabindex).
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        startCostEdit(tdCost, row);
      }
    });
    const tdPnl = document.createElement("td");
    tdPnl.className = `num ${pnlCls}`;
    tdPnl.textContent = pnlTxt;

    tr.append(tdName, tdQty, tdPrice, tdNet, tdCost, tdPnl);
    return tr;
  }

  function render(items) {
    tbody.innerHTML = "";
    emptyMsg.hidden = items.length > 0;
    for (const row of items) {
      tbody.appendChild(renderRow(row));
    }
    applyFilter();
  }

  function applyFilter() {
    const alvo = (filterInput.value || "").trim().toLowerCase();
    let visiveis = 0;
    for (const tr of tbody.children) {
      const nome = tr.firstChild.textContent.toLowerCase();
      const esconde = alvo.length > 0 && !nome.includes(alvo);
      tr.hidden = esconde;
      if (!esconde) visiveis += 1;
    }
    if (!alvo) {
      statusEl.textContent = `${rows.length} item(ns)`;
    } else {
      statusEl.textContent = visiveis
        ? `Mostrando ${visiveis} de ${rows.length} itens`
        : `Nenhum dos ${rows.length} itens casa com "${filterInput.value.trim()}"`;
    }
  }

  function applyPayload(payload) {
    rows = payload.rows || [];
    render(rows);
  }

  fetch("/api/inventory")
    .then((r) => r.json())
    .then(applyPayload)
    .catch(() => { statusEl.textContent = "Não consegui carregar o inventário."; });

  // Prepreenche com o perfil usado da ultima vez (Qt e web compartilham
  // a mesma chave em settings.json), pra nao pedir o link de novo toda
  // importacao.
  fetch("/api/inventory/import/status").then((r) => r.json()).then((data) => {
    if (data.steam_profile) importProfile.value = data.steam_profile;
  });

  filterInput.addEventListener("input", applyFilter);

  importBtn.addEventListener("click", () => {
    importForm.hidden = !importForm.hidden;
    if (!importForm.hidden) importProfile.focus();
  });
  importCancel.addEventListener("click", () => {
    importForm.hidden = true;
  });
  importForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const profile = importProfile.value.trim();
    if (!profile) return;
    importStatus.hidden = false;
    importStatus.classList.add("is-busy");
    importStatus.textContent = "Buscando seu inventário na Steam…";
    fetch("/api/inventory/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile, remove_missing: importRemoveMissing.checked,
      }),
    }).then((r) => {
      if (r.status === 409) {
        importStatus.classList.remove("is-busy");
        importStatus.textContent = "Já há uma importação em andamento.";
      }
    });
  });

  addBtn.addEventListener("click", () => {
    addForm.hidden = !addForm.hidden;
    addError.hidden = true;
    if (!addForm.hidden) document.getElementById("add-name").focus();
  });
  addCancel.addEventListener("click", () => {
    addForm.hidden = true;
    addForm.reset();
    addError.hidden = true;
  });
  addForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const name = document.getElementById("add-name").value.trim();
    const costRaw = document.getElementById("add-cost").value;
    const qty = document.getElementById("add-qty").value;
    if (!name) return;
    const cost = parseCostInput(costRaw);
    if (Number.isNaN(cost) || (cost !== null && cost < 0)) {
      addError.textContent = "Custo inválido — use números, ex.: 199,90.";
      addError.hidden = false;
      return;
    }
    fetch("/api/inventory/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // NAO usar `Number(qty) || 1`: 0 e' falsy em JS e o `or` escondia
      // um valor invalido (ex.: "0") em vez de deixar o servidor recusar.
      body: JSON.stringify({
        name, cost, quantity: qty.trim() === "" ? 1 : Number(qty),
      }),
    })
      .then((r) => r.json())
      .then((payload) => {
        if (payload.error) {
          addError.textContent = payload.error;
          addError.hidden = false;
          return;
        }
        addForm.hidden = true;
        addForm.reset();
        addError.hidden = true;
        applyPayload(payload);
      });
  });

  const es = window.skinvaultEvents;
  if (es) {
    es.addEventListener("account_eval", (ev) => {
      const payload = JSON.parse(ev.data);
      if (payload.error) return;
      applyPayload(payload);
    });
    es.addEventListener("inventory_import_done", (ev) => {
      const payload = JSON.parse(ev.data);
      importStatus.classList.remove("is-busy");
      if (payload.error) {
        importStatus.textContent = payload.error;
        return;
      }
      importStatus.textContent = payload.mensagem;
      importForm.hidden = true;
      applyPayload(payload);
    });
  }
});
