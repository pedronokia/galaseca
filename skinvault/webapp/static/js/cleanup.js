// Tela de Limpeza -- Fase 9. Medir é sempre seguro (so' leitura);
// "Limpar selecionados" e' destrutivo e pede confirmação explícita no
// navegador antes de mandar pro backend.
document.addEventListener("DOMContentLoaded", () => {
  const listEl = document.getElementById("targets-list");
  const statusEl = document.getElementById("cleanup-status");
  const adminStatus = document.getElementById("admin-status");
  const resultsCard = document.getElementById("results-card");
  const resultsBody = document.getElementById("results-body");

  let targets = [];

  function renderTarget(t) {
    const div = document.createElement("div");
    div.className = "cleanup-target" + (t.dangerous ? " dangerous" : "")
      + (t.available ? "" : " unavailable");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = !!t.selected;
    checkbox.disabled = !t.available;
    checkbox.dataset.key = t.key;
    checkbox.addEventListener("change", saveSelection);

    const body = document.createElement("div");
    body.className = "cleanup-target-body";

    const title = document.createElement("div");
    title.className = "cleanup-target-title";
    title.textContent = t.title;
    if (t.dangerous) {
      const b = document.createElement("span");
      b.className = "cleanup-badge danger";
      b.textContent = "Perigoso";
      title.appendChild(b);
    }
    if (t.needs_admin) {
      const b = document.createElement("span");
      b.className = "cleanup-badge admin";
      b.textContent = "Precisa de admin";
      title.appendChild(b);
    }
    body.appendChild(title);

    const desc = document.createElement("div");
    desc.className = "cleanup-target-desc";
    desc.textContent = t.available ? t.description
      : t.description + " (não disponível nesta máquina)";
    body.appendChild(desc);

    if (t.note) {
      const note = document.createElement("div");
      note.className = "cleanup-target-note";
      note.textContent = t.note;
      body.appendChild(note);
    }

    const sizeWrap = document.createElement("div");
    const size = document.createElement("div");
    size.className = "cleanup-target-size";
    size.textContent = t.bytes_human;
    const count = document.createElement("div");
    count.className = "cleanup-target-count";
    count.textContent = `${t.files} arquivo(s)`;
    sizeWrap.append(size, count);

    div.append(checkbox, body, sizeWrap);
    return div;
  }

  function render() {
    listEl.innerHTML = "";
    for (const t of targets) listEl.appendChild(renderTarget(t));
  }

  function selectedKeys() {
    return [...listEl.querySelectorAll("input[type=checkbox]:checked")]
      .map((el) => el.dataset.key);
  }

  function saveSelection() {
    fetch("/api/cleanup/selection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: selectedKeys() }),
    });
  }

  function load() {
    fetch("/api/cleanup/status").then((r) => r.json()).then((data) => {
      targets = data.targets || [];
      render();
      const precisaAdmin = targets.some((t) => t.needs_admin && t.available);
      adminStatus.textContent = (!data.is_admin && precisaAdmin)
        ? "Alguns alvos precisam do app rodando como administrador para limpar por completo."
        : "";
    });
  }
  load();

  document.getElementById("btn-rescan").addEventListener("click", () => {
    statusEl.textContent = "Medindo…";
    load();
    statusEl.textContent = "";
  });

  document.getElementById("btn-clean").addEventListener("click", () => {
    const keys = selectedKeys();
    if (!keys.length) {
      statusEl.textContent = "Selecione ao menos um alvo.";
      return;
    }
    const nomes = targets.filter((t) => keys.includes(t.key))
      .map((t) => t.title);
    const perigoso = targets.some((t) => keys.includes(t.key) && t.dangerous);
    const aviso = perigoso
      ? `ATENÇÃO: isso inclui "Esvaziar Lixeira" — não há como desfazer.\n\n`
      : "";
    if (!confirm(`${aviso}Limpar estes alvos agora?\n\n${nomes.join("\n")}`)) {
      return;
    }
    statusEl.textContent = "Limpando…";
    fetch("/api/cleanup/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys }),
    })
      .then((r) => r.json())
      .then((payload) => {
        if (payload.error) {
          statusEl.textContent = "Erro: " + payload.error;
          return;
        }
        statusEl.textContent = "Limpeza concluída.";
        renderResults(payload.results || {});
        load();
      });
  });

  function renderResults(results) {
    resultsBody.innerHTML = "";
    resultsCard.hidden = Object.keys(results).length === 0;
    for (const [key, r] of Object.entries(results)) {
      const t = targets.find((x) => x.key === key);
      const tr = document.createElement("tr");
      const tdName = document.createElement("td");
      tdName.textContent = t ? t.title : key;
      const tdRemoved = document.createElement("td");
      tdRemoved.className = "num";
      tdRemoved.textContent = String(r.removed);
      const tdFreed = document.createElement("td");
      tdFreed.className = "num";
      tdFreed.textContent = r.freed_human;
      const tdSkipped = document.createElement("td");
      tdSkipped.className = "num";
      tdSkipped.textContent = String(r.skipped);
      tr.append(tdName, tdRemoved, tdFreed, tdSkipped);
      resultsBody.appendChild(tr);
    }
  }
});
