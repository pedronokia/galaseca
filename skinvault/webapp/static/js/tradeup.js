// Calculadora de Trade-up -- Fase 5. "Calcular" usa so' o que ja esta
// em cache (instantaneo); "Buscar precos na Steam" roda em background
// e acompanha pelo SSE (mesmo pipeline da Conta).
document.addEventListener("DOMContentLoaded", () => {
  const catalogStatus = document.getElementById("catalog-status");
  const refreshBtn = document.getElementById("btn-refresh-catalog");
  const input = document.getElementById("tradeup-input");
  const quickBtn = document.getElementById("btn-quick-plan");
  const evalBtn = document.getElementById("btn-evaluate");
  const statusEl = document.getElementById("tradeup-status");
  const errorsCard = document.getElementById("tradeup-errors");
  const warningsCard = document.getElementById("tradeup-warnings");
  const resultsRow = document.getElementById("tradeup-results");
  const outcomesCard = document.getElementById("tradeup-outcomes-card");
  const outcomesBody = document.getElementById("outcomes-body");

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);
  const pct = (v) => v == null ? "—" : `${(v * 100).toFixed(1)}%`;

  // "Calcular" (quickBtn, so' cache, rapido) e "Buscar precos na Steam"
  // (evalBtn, via SSE, pode levar segundos) escrevem no MESMO resultado
  // na tela, sem nenhuma guarda entre si -- clicar em "Buscar precos",
  // e antes dele voltar clicar em "Calcular" com a entrada mudada,
  // deixava o preview rapido na tela ate' o resultado antigo do
  // "Buscar precos" chegar via SSE e sobrescrever por cima, mostrando
  // dado de uma entrada que ja' nao e' mais a que esta' no campo. Mesma
  // familia de bug ja' corrigida nesta sessao em market_screen.py (Qt),
  // inventory.js e _price_worker.py.
  let resultGen = 0;
  let pendingEvalGen = 0;

  function fmtDate(ts) {
    if (!ts) return "nunca";
    return new Date(ts * 1000).toLocaleString("pt-BR");
  }

  function renderCatalogStatus(data) {
    if (data.status === "missing") {
      catalogStatus.textContent =
        "Catálogo ainda não foi baixado — clique em 'Atualizar catálogo'.";
      return;
    }
    catalogStatus.textContent =
      `Catálogo de ${fmtDate(data.updated_at)} • ${data.skins} skins em ` +
      `${data.collections} coleções`;
  }

  function loadCatalogStatus() {
    fetch("/api/tradeup/catalog").then((r) => r.json()).then(renderCatalogStatus);
  }
  loadCatalogStatus();

  refreshBtn.addEventListener("click", () => {
    refreshBtn.disabled = true;
    catalogStatus.classList.add("is-busy");
    catalogStatus.textContent = "Baixando catálogo (ByMykel/CSGO-API)…";
    fetch("/api/tradeup/catalog/refresh", { method: "POST" }).then((r) => {
      if (r.status === 409) {
        catalogStatus.textContent = "Já há uma atualização em andamento.";
        refreshBtn.disabled = false;
        catalogStatus.classList.remove("is-busy");
      }
    });
  });

  function setList(container, items, cls) {
    if (!items || !items.length) {
      container.hidden = true;
      container.innerHTML = "";
      return;
    }
    container.hidden = false;
    const ul = document.createElement("ul");
    for (const msg of items) {
      const li = document.createElement("li");
      li.textContent = msg;
      ul.appendChild(li);
    }
    container.innerHTML = "";
    container.appendChild(ul);
  }

  function setStat(name, value, delta) {
    const card = document.querySelector(`.stat-card[data-stat="${name}"]`);
    card.querySelector(".stat-value").textContent = value;
    card.querySelector(".stat-delta").textContent = delta || "";
  }

  function renderResult(res) {
    setList(errorsCard, res.errors, "error");
    setList(warningsCard, res.warnings, "warning");

    if (res.errors && res.errors.length) {
      resultsRow.hidden = true;
      outcomesCard.hidden = true;
      return;
    }

    resultsRow.hidden = false;
    setStat("cost", brl(res.cost));
    setStat("ev", brl(res.ev_net),
      res.coverage != null ? `cobertura: ${pct(res.coverage)}` : "");
    const profitTxt = res.profit == null ? "—" : brl(res.profit);
    setStat("profit", profitTxt,
      res.roi != null ? `retorno: ${pct(res.roi)}` : "");
    document.querySelector('.stat-card[data-stat="profit"] .stat-value')
      .classList.toggle("positive", res.profit != null && res.profit >= 0);
    document.querySelector('.stat-card[data-stat="profit"] .stat-value')
      .classList.toggle("negative", res.profit != null && res.profit < 0);
    setStat("chance", pct(res.prob_profit));

    const outcomes = res.outcomes || [];
    outcomesCard.hidden = outcomes.length === 0;
    outcomesBody.innerHTML = "";
    for (const o of outcomes) {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = o.name;
      const tdProb = document.createElement("td");
      tdProb.className = "num";
      tdProb.textContent = pct(o.prob);
      const tdPrice = document.createElement("td");
      tdPrice.className = "num";
      tdPrice.textContent = brl(o.price);
      const tdNet = document.createElement("td");
      tdNet.className = "num";
      tdNet.textContent = brl(o.net);
      tr.append(tdName, tdProb, tdPrice, tdNet);
      outcomesBody.appendChild(tr);
    }
  }

  quickBtn.addEventListener("click", () => {
    resultGen += 1;
    const gen = resultGen;
    statusEl.textContent = "Calculando…";
    fetch("/api/tradeup/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: input.value }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (gen !== resultGen) return;  // superado por um calculo mais novo
        statusEl.textContent = "Calculado com os preços já guardados.";
        renderResult(res);
      });
  });

  evalBtn.addEventListener("click", () => {
    resultGen += 1;
    pendingEvalGen = resultGen;
    evalBtn.disabled = true;
    statusEl.classList.add("is-busy");
    statusEl.textContent = "Buscando preços na Steam…";
    fetch("/api/tradeup/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: input.value }),
    }).then((r) => {
      if (r.status === 409) {
        statusEl.textContent = "Já há um cálculo em andamento.";
        evalBtn.disabled = false;
        statusEl.classList.remove("is-busy");
      }
    });
  });

  const es = window.skinvaultEvents;
  if (es) {
    es.addEventListener("tradeup_catalog", (ev) => {
      const data = JSON.parse(ev.data);
      refreshBtn.disabled = false;
      catalogStatus.classList.remove("is-busy");
      renderCatalogStatus(data);
    });
    es.addEventListener("tradeup_progress", (ev) => {
      const { done, total, fetches } = JSON.parse(ev.data);
      statusEl.textContent = total
        ? `Buscando preços… ${done}/${total} (${fetches} na Steam)`
        : "Buscando preços…";
    });
    es.addEventListener("tradeup_result", (ev) => {
      evalBtn.disabled = false;
      statusEl.classList.remove("is-busy");
      if (pendingEvalGen !== resultGen) return;  // superado por um "Calcular" mais novo
      const res = JSON.parse(ev.data);
      statusEl.textContent = "Pronto.";
      renderResult(res);
    });
  }
});
