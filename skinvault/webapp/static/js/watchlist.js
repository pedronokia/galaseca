// Tela de Watchlist -- Fase 8. "Verificar agora" so' confere o que ja
// esta' guardado (cache-only); alerta disparado usa o mesmo pipeline
// de notificacao (tray + toast) que a Fase 0/1 provou.
document.addEventListener("DOMContentLoaded", () => {
  const body = document.getElementById("watchlist-body");
  const emptyMsg = document.getElementById("watchlist-empty");
  const statusEl = document.getElementById("watchlist-status");
  const addBtn = document.getElementById("btn-add");
  const addForm = document.getElementById("add-form");
  const addCancel = document.getElementById("w-cancel");
  const addError = document.getElementById("add-error");
  const checkBtn = document.getElementById("btn-check");
  const logBody = document.getElementById("log-body");
  const logEmpty = document.getElementById("log-empty");

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);
  const dateTime = (ts) => ts ? new Date(ts * 1000).toLocaleString("pt-BR") : "—";

  function parseMoney(raw) {
    let s = String(raw || "").trim();
    if (!s) return null;
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
    const v = parseFloat(s);
    return Number.isNaN(v) ? NaN : v;
  }

  // ── lista ──────────────────────────────────────────────
  function renderRow(item) {
    const tr = document.createElement("tr");

    const tdName = document.createElement("td");
    tdName.textContent = item.name;

    const tdPrice = document.createElement("td");
    tdPrice.className = "num";
    tdPrice.textContent = brl(item.price);

    const tdRules = document.createElement("td");
    tdRules.textContent = item.rules_summary || "nenhuma regra";

    const tdState = document.createElement("td");
    if (item.muted) {
      tdState.textContent = "Silenciado";
      tdState.className = "state-muted";
    } else if (item.triggered) {
      tdState.textContent = "Disparado";
      tdState.className = "state-triggered";
    } else {
      tdState.textContent = "Monitorando";
    }

    const tdActions = document.createElement("td");
    tdActions.className = "row-actions";
    const rulesBtn = document.createElement("button");
    rulesBtn.type = "button";
    rulesBtn.textContent = "Regras";
    rulesBtn.addEventListener("click", () => openRulesModal(item));
    const muteBtn = document.createElement("button");
    muteBtn.type = "button";
    muteBtn.textContent = item.muted ? "Reativar" : "Silenciar 24h";
    muteBtn.addEventListener("click", () => {
      fetch(`/api/watchlist/${item.index}/mute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hours: item.muted ? null : 24 }),
      }).then((r) => r.json()).then(applyPayload);
    });
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "danger";
    delBtn.textContent = "Remover";
    delBtn.addEventListener("click", () => {
      window.skinvaultConfirm(`Remover "${item.name}" da watchlist?`, {
        title: "Remover item", confirmLabel: "Remover", danger: true,
      }).then((ok) => {
        if (!ok) return;
        fetch(`/api/watchlist/${item.index}`, { method: "DELETE" })
          .then((r) => r.json()).then(applyPayload);
      });
    });
    tdActions.append(rulesBtn, muteBtn, delBtn);

    tr.append(tdName, tdPrice, tdRules, tdState, tdActions);
    return tr;
  }

  function applyPayload(payload) {
    statusEl.classList.remove("is-busy");
    if (payload.error) {
      statusEl.textContent = "Erro: " + payload.error;
      return;
    }
    const items = payload.items || [];
    emptyMsg.hidden = items.length > 0;
    body.innerHTML = "";
    for (const item of items) body.appendChild(renderRow(item));
    if (payload.fired !== undefined) {
      statusEl.textContent = payload.fired.length
        ? `${payload.fired.length} alerta(s) novo(s).`
        : "Verificado — nenhum alerta novo.";
      loadLog();
    }
  }

  function loadWatchlist() {
    fetch("/api/watchlist").then((r) => r.json()).then(applyPayload);
  }
  loadWatchlist();

  checkBtn.addEventListener("click", () => {
    statusEl.classList.add("is-busy");
    statusEl.textContent = "Verificando…";
    fetch("/api/watchlist/check", { method: "POST" })
      .then((r) => r.json()).then(applyPayload);
  });

  // ── adicionar ──────────────────────────────────────────
  addBtn.addEventListener("click", () => { addForm.hidden = !addForm.hidden; });
  addCancel.addEventListener("click", () => {
    addForm.hidden = true;
    addForm.reset();
    addError.hidden = true;
  });
  addForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const name = document.getElementById("w-name").value.trim();
    if (!name) return;
    // NAO usar `parseMoney(...) || 0`: parseMoney devolve NaN pra texto
    // invalido, e NaN e' falsy em JS -- o `or` escondia o erro de
    // digitacao como "sem alvo" (mesma armadilha ja corrigida em
    // inventory.js e trades.js).
    const parsedTarget = parseMoney(document.getElementById("w-target").value);
    const target = parsedTarget === null ? 0 : parsedTarget;
    if (Number.isNaN(target) || target < 0) {
      addError.textContent = "Preço alvo inválido.";
      addError.hidden = false;
      return;
    }
    fetch("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, target }),
    }).then((r) => r.json()).then((payload) => {
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

  // ── regras ─────────────────────────────────────────────
  const modal = document.getElementById("rules-modal");
  const rulesError = document.getElementById("rules-error");
  let rulesIndex = null;

  function openRulesModal(item) {
    rulesIndex = item.index;
    document.getElementById("rules-item-name").textContent = item.name;
    const r = item.rules || {};
    document.getElementById("r-price-below").value = r.price_below ?? "";
    document.getElementById("r-price-drop").value = r.price_drop_pct ?? "";
    document.getElementById("r-baseline").value = item.baseline_price ?? "";
    document.getElementById("r-volume").value = r.volume_spike ?? "";
    document.getElementById("r-supply").value = r.supply_drop ?? "";
    document.getElementById("r-score").value = r.score_above ?? "";
    rulesError.hidden = true;
    modal.hidden = false;
  }
  document.getElementById("rules-cancel").addEventListener("click", () => {
    modal.hidden = true;
  });
  // Mesma saida de "clique fora"/Esc que o confirm() novo (app.js) --
  // sem isso este era o unico modal da tela que so fechava pelo botao.
  modal.addEventListener("mousedown", (ev) => {
    if (ev.target === modal) modal.hidden = true;
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !modal.hidden) modal.hidden = true;
  });
  document.getElementById("rules-save").addEventListener("click", () => {
    // O backend espera numero (`float(data[key])`, que nao aceita
    // virgula); os campos aqui sao em pt-BR ("45,00"), entao precisam
    // passar por parseMoney antes de ir pro JSON -- sem isso TODO envio
    // com virgula virava "price_below inválido".
    const raw = {
      price_below: document.getElementById("r-price-below").value,
      price_drop_pct: document.getElementById("r-price-drop").value,
      baseline_price: document.getElementById("r-baseline").value,
      volume_spike: document.getElementById("r-volume").value,
      supply_drop: document.getElementById("r-supply").value,
      score_above: document.getElementById("r-score").value,
    };
    const vals = {};
    let invalid = false;
    for (const [key, text] of Object.entries(raw)) {
      const parsed = parseMoney(text);
      if (parsed !== null) {
        if (Number.isNaN(parsed)) invalid = key;
        vals[key] = parsed;
      }
    }
    if (invalid) {
      rulesError.textContent = `${invalid}: use números, ex.: 45,00.`;
      rulesError.hidden = false;
      return;
    }
    fetch(`/api/watchlist/${rulesIndex}/rules`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(vals),
    }).then((r) => r.json()).then((payload) => {
      if (payload.error) {
        rulesError.textContent = payload.error;
        rulesError.hidden = false;
        return;
      }
      modal.hidden = true;
      applyPayload(payload);
    });
  });

  // ── log ────────────────────────────────────────────────
  function loadLog() {
    fetch("/api/watchlist/log").then((r) => r.json()).then((data) => {
      const entries = data.entries || [];
      logEmpty.hidden = entries.length > 0;
      logBody.innerHTML = "";
      for (const e of entries) {
        const tr = document.createElement("tr");
        const tdWhen = document.createElement("td");
        tdWhen.textContent = dateTime(e.ts);
        const tdName = document.createElement("td");
        tdName.textContent = e.name;
        const tdLabel = document.createElement("td");
        tdLabel.textContent = e.label;
        tr.append(tdWhen, tdName, tdLabel);
        logBody.appendChild(tr);
      }
    });
  }
  loadLog();
});
