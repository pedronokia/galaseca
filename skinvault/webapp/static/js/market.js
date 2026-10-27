// Tela de Consulta de Mercado -- Fase 10. Unica tela que bate na
// Steam ao vivo por acao do usuario (sem auto-busca ao carregar).
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("market-input");
  const searchBtn = document.getElementById("market-search-btn");
  const statusEl = document.getElementById("market-status");
  const emptyCard = document.getElementById("market-empty");
  const contentEl = document.getElementById("market-content");
  const chipsEl = document.getElementById("recent-chips");
  const verdictMsg = document.getElementById("verdict-message");
  const bookLine = document.getElementById("book-line");
  const caseLine = document.getElementById("case-line");
  const sparkWrap = document.getElementById("sparkline-wrap");
  const sparkEmpty = document.getElementById("sparkline-empty");

  // Incrementado em toda runSearch() -- so' aplica a resposta se ainda
  // for a mais recente. Sem isto, buscar um item lento e, antes dele
  // voltar, buscar outro rapido (clique + Enter nao tem nenhuma guarda
  // entre si -- searchBtn.disabled nao desabilita o campo de texto)
  // podia deixar a tela mostrando o preco do item ERRADO, se a resposta
  // da busca antiga chegasse depois da nova. Mesma familia de bug ja'
  // corrigida nesta sessao em market_screen.py (Qt, _search_seq),
  // inventory.js e _price_worker.py -- achado aqui revisando o fluxo de
  // runSearch(), 2026-10-27.
  let searchGen = 0;

  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);

  function renderChips(recent) {
    chipsEl.innerHTML = "";
    for (const name of recent) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "recent-chip";
      chip.textContent = name;
      chip.addEventListener("click", () => {
        input.value = name;
        runSearch();
      });
      chipsEl.appendChild(chip);
    }
  }

  function loadRecent() {
    fetch("/api/market/recent").then((r) => r.json())
      .then((data) => renderChips(data.recent || []));
  }
  loadRecent();

  function setStat(name, value, cls) {
    const card = document.querySelector(`.stat-card[data-stat="${name}"]`);
    const valueEl = card.querySelector(".stat-value");
    valueEl.textContent = value;
    valueEl.className = "stat-value" + (cls ? ` ${cls}` : "");
  }

  function renderSparkline(points) {
    sparkWrap.innerHTML = "";
    const values = points.map((p) => p.price_median).filter((v) => v != null);
    if (values.length < 2) {
      sparkEmpty.hidden = false;
      return;
    }
    sparkEmpty.hidden = true;
    const w = 600, h = 120, pad = 6;
    const min = Math.min(...values), max = Math.max(...values);
    const range = max - min || 1;
    const stepX = (w - pad * 2) / (values.length - 1);
    const coords = values.map((v, i) => {
      const x = pad + i * stepX;
      const y = pad + (h - pad * 2) * (1 - (v - min) / range);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", coords.join(" "));
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", "var(--accent)");
    line.setAttribute("stroke-width", "2");
    svg.appendChild(line);
    sparkWrap.appendChild(svg);
  }

  function runSearch() {
    const name = input.value.trim();
    if (!name) return;
    searchGen += 1;
    const gen = searchGen;
    statusEl.textContent = `Consultando ${name}…`;
    statusEl.classList.add("is-busy");
    searchBtn.disabled = true;
    fetch("/api/market/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    })
      .then((r) => r.json())
      .then((data) => {
        // Resposta de uma busca ja' superada por outra mais recente --
        // a mais nova ainda esta' em voo e vai aplicar o proprio
        // resultado quando voltar; mexer no estado aqui so' desfaria
        // isso fora de ordem.
        if (gen !== searchGen) return;
        searchBtn.disabled = false;
        statusEl.classList.remove("is-busy");
        if (data.error) {
          statusEl.textContent = "Erro: " + data.error;
          return;
        }
        if (!data.found) {
          emptyCard.hidden = false;
          contentEl.hidden = true;
          statusEl.textContent =
            `Não foi possível obter dados de "${name}". Verifique o ` +
            "nome (desgaste, StatTrak, espaços) ou tente de novo.";
          return;
        }
        emptyCard.hidden = true;
        contentEl.hidden = false;
        render(data);
        loadRecent();
        statusEl.textContent = data.throttled
          ? "A Steam limitou as consultas de preço agora — mostrando o " +
            "que veio da página do item."
          : "Pronto.";
      })
      .catch(() => {
        if (gen !== searchGen) return;
        searchBtn.disabled = false;
        statusEl.classList.remove("is-busy");
        statusEl.textContent = "Falha ao consultar — tente de novo.";
      });
  }

  function render(data) {
    const overview = data.overview || {};
    const verdict = data.verdict || {};
    setStat("lowest", brl(overview.lowest));
    setStat("median", brl(overview.median));
    setStat("volume", overview.volume != null ? String(overview.volume) : "—");
    setStat("verdict", verdict.label || "—", verdict.verdict);

    verdictMsg.textContent = verdict.message || "Dados insuficientes para avaliar.";

    const ob = data.order_book;
    if (ob && (ob.buy_count != null || ob.sell_count != null)) {
      bookLine.textContent =
        `Fila de ofertas: ${ob.buy_count ?? "—"} compradores, ` +
        `${ob.sell_count ?? "—"} vendedores` +
        (data.order_book_approx ? " (aproximado — outro desgaste)" : "");
    } else {
      bookLine.textContent = "";
    }

    const cs = data.case_status;
    if (cs && cs.case) {
      caseLine.hidden = false;
      caseLine.textContent = `${cs.case} — ${cs.label}`;
    } else {
      caseLine.hidden = true;
    }

    renderSparkline(data.price_history_tail || []);
  }

  searchBtn.addEventListener("click", runSearch);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") runSearch();
  });
});
