// Tela de Inventario -- Fase 3. Tabela com filtro e custo editavel (clique
// na celula). So' Steam entra com item (2026-10-20, a pedido do usuario):
// "+ Adicionar item" e "Colar lista" saíram da tela. Reusa o mesmo payload
// da Conta (account_data.summary_payload) -- mesma avaliacao, mais colunas.
document.addEventListener("DOMContentLoaded", () => {
  const statusEl = document.getElementById("inventory-status");
  const tbody = document.getElementById("inventory-body");
  const emptyMsg = document.getElementById("inventory-empty");
  const filterInput = document.getElementById("filter-input");
  const importBtn = document.getElementById("btn-import-steam");
  const importForm = document.getElementById("import-steam-form");
  const importCancel = document.getElementById("import-cancel");
  const importProfile = document.getElementById("import-profile");
  const importStatus = document.getElementById("import-status");
  const refreshBtn = document.getElementById("btn-refresh-prices");

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
      // stopPropagation nos dois -- sem isto o keydown borbulhava pro
      // tdCost pai, que tem o PRÓPRIO listener de Enter/Space (celula
      // acessivel via teclado, tabIndex=0) pra ABRIR edicao. Resultado
      // real medido: Enter salvava (fetch com o valor novo) E reabria
      // a edicao na mesma cela com o `row.cost` ANTIGO (ainda nao
      // atualizado) -- essa segunda edicao, nunca tocada pelo usuario,
      // perdia o foco no proximo render() (disparado pelo proprio save
      // ou por um "account_eval" via SSE) e seu commit() disparava um
      // SEGUNDO fetch com o valor velho, sobrescrevendo o que acabou
      // de ser salvo. Achado ao vivo navegando a tela de verdade com
      // Playwright, 2026-10-27.
      if (ev.key === "Enter") { ev.preventDefault(); ev.stopPropagation(); input.blur(); }
      if (ev.key === "Escape") { ev.stopPropagation(); done = true; render(rows); }
    });
  }

  function placeholderIcon() {
    const div = document.createElement("div");
    div.className = "item-icon-placeholder";
    div.textContent = "◇";
    return div;
  }

  function iconElement(row) {
    if (!row.icon) return placeholderIcon();
    const img = document.createElement("img");
    img.className = "item-icon";
    img.src = `/api/icon/${encodeURIComponent(row.icon)}`;
    img.alt = "";
    img.loading = "lazy";
    // Hash sem imagem no CDN (raro, mas acontece) -- cai pro mesmo
    // marcador generico de quem nunca teve icone, em vez de um
    // quadradinho de imagem quebrada do navegador.
    img.addEventListener("error", () => img.replaceWith(placeholderIcon()), { once: true });
    return img;
  }

  function renderRow(row) {
    const tr = document.createElement("tr");
    const pnlTxt = row.has_cost ? brl(row.pnl) : "—";
    const pnlCls = row.pnl == null ? "" : (row.pnl >= 0 ? "positive" : "negative");

    const tdName = document.createElement("td");
    tdName.className = "item-cell";
    tdName.appendChild(iconElement(row));
    const nameSpan = document.createElement("span");
    const nomeCompleto = row.display_name || row.name;
    nameSpan.textContent = nomeCompleto;
    // Nome trunca com reticencias (CSS) pra caber numa linha so' --
    // title garante o nome inteiro ainda disponivel, no tooltip.
    nameSpan.title = nomeCompleto;
    tdName.appendChild(nameSpan);
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

    const tdActions = document.createElement("td");
    tdActions.className = "row-actions";
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "danger";
    delBtn.textContent = "Remover";
    delBtn.addEventListener("click", () => {
      // Item sincronizado da Steam some de novo na proxima importacao
      // (continua no inventario real) -- so' a posicao manual antiga
      // (de antes desta tela deixar de criar uma) e' definitiva. Nao
      // da' pra saber aqui sem reimportar, entao confirma sempre.
      //
      // window.skinvaultConfirm (app.js), não confirm() nativo -- o
      // próprio app.js documenta por quê: color-scheme não alcança
      // window.confirm, só controles de formulário, então o balão
      // nativo aparecia claro no meio do app inteiro em tema escuro.
      window.skinvaultConfirm(
        `Remover "${nomeCompleto}" da carteira?`,
        { title: "Remover item", confirmLabel: "Remover", danger: true },
      ).then((ok) => {
        if (!ok) return;
        fetch("/api/inventory/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: row.name }),
        })
          .then((r) => r.json())
          .then((payload) => {
            if (payload.error) {
              statusEl.textContent = "Erro: " + payload.error;
              return;
            }
            applyPayload(payload);
          });
      });
    });
    tdActions.appendChild(delBtn);

    tr.append(tdName, tdQty, tdPrice, tdNet, tdCost, tdPnl, tdActions);
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
  // importacao. cooldown_s > 0 avisa ANTES do clique (disjuntor de
  // steam_api.py ja' sabe que vai recusar) -- sem isso o usuario so'
  // descobria depois de tentar e levar o erro.
  fetch("/api/inventory/import/status").then((r) => r.json()).then((data) => {
    if (data.steam_profile) importProfile.value = data.steam_profile;
    if (data.cooldown_s > 0) {
      const min = Math.max(1, Math.round(data.cooldown_s / 60));
      importBtn.title = `A Steam ainda está limitando as consultas — faltam cerca de ${min} minuto(s).`;
    }
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
      // Sempre substitui: pedido do usuario -- toda sincronizacao com
      // a Steam reflete o inventario real atual, nunca acumula item
      // que ja' saiu de la' (vendido/trocado). Posicao manual antiga
      // (de antes desta tela deixar de criar uma) nunca e' tocada por
      // isto (merge_steam_inventory so' mexe em source=SOURCE_STEAM).
      body: JSON.stringify({ profile, remove_missing: true }),
    }).then((r) => {
      if (r.status === 409) {
        importStatus.classList.remove("is-busy");
        importStatus.textContent = "Já há uma importação em andamento.";
      }
    });
  });

  // Mesma rota/SSE da tela Conta (account_data.start_refresh) -- sem
  // isto, quem via' direto na aba Inventario nunca tinha como sair do
  // cache (Preco/Recebe/Lucro ficavam "—" pra sempre) sem navegar ate'
  // Conta so' pra apertar um botao e voltar.
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
