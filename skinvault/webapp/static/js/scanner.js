// Tela de Scanner -- Fase 11. Escaneia uma categoria em background e
// acompanha item a item pelo SSE (mesmo pipeline de Conta/Trade-up).
document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("category-select");
  const scanBtn = document.getElementById("btn-scan");
  const statusEl = document.getElementById("scanner-status");
  const body = document.getElementById("scanner-body");
  const emptyMsg = document.getElementById("scanner-empty");

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);

  let results = [];
  let scanning = false;

  function setScanning(value) {
    scanning = value;
    select.disabled = value;
    scanBtn.textContent = value ? "Cancelar scan" : "Escanear";
    scanBtn.classList.toggle("btn-secondary", value);
    scanBtn.classList.toggle("btn-primary", !value);
    statusEl.classList.toggle("is-busy", value);
  }

  fetch("/api/scanner/categories").then((r) => r.json()).then((data) => {
    select.innerHTML = "";
    for (const cat of data.categories || []) {
      const opt = document.createElement("option");
      opt.value = cat;
      opt.textContent = cat;
      select.appendChild(opt);
    }
  });

  fetch("/api/scanner/status").then((r) => r.json()).then((data) => {
    setScanning(!!data.scanning);
  });

  function scoreClass(score) {
    if (score >= 70) return "score-high";
    if (score <= 30) return "score-low";
    return "";
  }

  function renderRows() {
    const sorted = [...results].sort((a, b) => b.score - a.score);
    body.innerHTML = "";
    emptyMsg.hidden = sorted.length > 0;
    for (const r of sorted) {
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = r.name;
      tdName.title = r.score_tooltip || "";
      const tdScore = document.createElement("td");
      tdScore.className = `num score-cell ${scoreClass(r.score)}`;
      tdScore.textContent = String(r.score);
      tdScore.title = r.score_tooltip || "";
      const tdPrice = document.createElement("td");
      tdPrice.className = "num";
      tdPrice.textContent = brl(r.price) + (r.derived_price ? " *" : "");
      const tdVerdict = document.createElement("td");
      tdVerdict.textContent = r.verdict_label;
      const tdSpread = document.createElement("td");
      tdSpread.textContent = r.spread || "—";
      const tdBook = document.createElement("td");
      tdBook.textContent = r.book || "—";
      const tdTrend = document.createElement("td");
      tdTrend.textContent = r.trend || "—";
      const tdSd = document.createElement("td");
      tdSd.textContent = r.sd_label || "—";
      const tdCase = document.createElement("td");
      tdCase.textContent = r.case_label || "—";
      tr.append(tdName, tdScore, tdPrice, tdVerdict, tdSpread, tdBook,
        tdTrend, tdSd, tdCase);
      body.appendChild(tr);
    }
  }

  scanBtn.addEventListener("click", () => {
    if (scanning) {
      statusEl.textContent = "Cancelando…";
      fetch("/api/scanner/cancel", { method: "POST" });
      return;
    }
    results = [];
    renderRows();
    const category = select.value;
    statusEl.textContent = `Escaneando ${category}…`;
    fetch("/api/scanner/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category }),
    }).then((r) => r.json()).then((data) => {
      if (data.error) {
        statusEl.textContent = "Erro: " + data.error;
        return;
      }
      setScanning(true);
    });
  });

  const es = window.skinvaultEvents;
  if (es) {
    es.addEventListener("scanner_progress", (ev) => {
      const { done, total, name } = JSON.parse(ev.data);
      statusEl.textContent = `[${done}/${total}] ${name}`;
    });
    es.addEventListener("scanner_item", (ev) => {
      results.push(JSON.parse(ev.data));
      renderRows();
    });
    es.addEventListener("scanner_done", (ev) => {
      const { cancelled } = JSON.parse(ev.data);
      setScanning(false);
      statusEl.textContent = cancelled
        ? `Scan cancelado — ${results.length} item(ns) coletado(s).`
        : `Pronto — ${results.length} item(ns) avaliado(s).`;
    });
  }
});
