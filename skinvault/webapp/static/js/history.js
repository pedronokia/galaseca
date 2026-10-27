// Tela de Historico -- Fase 7. Dois segmentos (evolucao do valor +
// trades, este ultimo lendo o mesmo /api/trades da tela de Trades) e
// o simulador de lucro.
document.addEventListener("DOMContentLoaded", () => {
  const brl = (v) => v == null ? "—" : new Intl.NumberFormat(
    "pt-BR", { style: "currency", currency: "BRL" }).format(v);
  const dateTime = (ts) => ts ? new Date(ts * 1000).toLocaleString("pt-BR") : "—";
  const date = (ts) => ts ? new Date(ts * 1000).toLocaleDateString("pt-BR") : "—";

  // ── segmentos ──────────────────────────────────────────
  const segButtons = document.querySelectorAll("#history-segmented .segment");
  const segments = {
    value: document.getElementById("value-segment"),
    trades: document.getElementById("trades-segment"),
  };
  segButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      segButtons.forEach((b) => b.classList.toggle("active", b === btn));
      const key = btn.dataset.segment;
      for (const [k, el] of Object.entries(segments)) {
        el.hidden = k !== key;
      }
    });
  });

  // ── evolucao do valor ──────────────────────────────────
  const valueBody = document.getElementById("value-body");
  const valueEmpty = document.getElementById("value-empty");
  fetch("/api/history/value").then((r) => r.json()).then((data) => {
    const series = data.series || [];
    valueEmpty.hidden = series.length > 0;
    valueBody.innerHTML = "";
    for (const p of series) {
      const tr = document.createElement("tr");
      const tdDate = document.createElement("td");
      tdDate.textContent = dateTime(p.ts);
      const tdValue = document.createElement("td");
      tdValue.className = "num";
      tdValue.textContent = brl(p.total);
      tr.append(tdDate, tdValue);
      valueBody.appendChild(tr);
    }
  });

  // ── trades (leitura) ───────────────────────────────────
  const tradesBody = document.getElementById("trades-body");
  const tradesEmpty = document.getElementById("trades-empty");
  fetch("/api/trades").then((r) => r.json()).then((data) => {
    const items = data.trades || [];
    tradesEmpty.hidden = items.length > 0;
    tradesBody.innerHTML = "";
    for (const t of items) {
      const tr = document.createElement("tr");
      const pnlCls = t.pnl >= 0 ? "positive" : "negative";
      const cells = [
        [t.name, ""],
        [brl(t.buy_cost), "num"],
        [brl(t.sell_price), "num"],
        [String(t.quantity), "num"],
        [brl(t.pnl), `num ${pnlCls}`],
        [date(t.sell_ts), ""],
      ];
      for (const [text, cls] of cells) {
        const td = document.createElement("td");
        if (cls) td.className = cls;
        td.textContent = text;
        tr.appendChild(td);
      }
      tradesBody.appendChild(tr);
    }
  });

  // ── simulador ───────────────────────────────────────────
  const simCard = document.getElementById("sim-card");
  document.getElementById("btn-simulate").addEventListener("click", () => {
    simCard.hidden = !simCard.hidden;
  });

  function parseMoney(raw) {
    let s = String(raw || "").trim();
    if (!s) return null;
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
    const v = parseFloat(s);
    return Number.isNaN(v) ? NaN : v;
  }

  const simError = document.getElementById("sim-error");
  const simResult = document.getElementById("sim-result");

  // "Calcular" nao desabilita nada durante o fetch -- clicar de novo
  // com valores diferentes antes da primeira resposta voltar disparava
  // uma segunda chamada concorrente escrevendo no MESMO simResult.
  // Se a primeira (mais lenta) chegasse depois da segunda, o resultado
  // da entrada ANTIGA sobrescrevia o da entrada atual nos campos.
  // Mesma familia de bug ja' corrigida nesta sessao em market.js/
  // tradeup.js/watchlist.js (web) e varios pontos do Qt.
  let simGen = 0;

  document.getElementById("sim-calc").addEventListener("click", () => {
    const buy = parseMoney(document.getElementById("sim-buy").value);
    const sell = parseMoney(document.getElementById("sim-sell").value);
    const qtyRaw = document.getElementById("sim-qty").value;
    simError.hidden = true;
    if (buy === null || Number.isNaN(buy) || buy < 0) {
      simError.textContent = "Preço de compra inválido.";
      simError.hidden = false;
      return;
    }
    if (sell === null || Number.isNaN(sell) || sell < 0) {
      simError.textContent = "Preço de venda inválido.";
      simError.hidden = false;
      return;
    }
    simGen += 1;
    const gen = simGen;
    fetch("/api/history/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        buy_price: buy, sell_price: sell,
        quantity: qtyRaw.trim() === "" ? 1 : Number(qtyRaw),
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (gen !== simGen) return;  // superado por um calculo mais novo
        if (res.error) {
          simError.textContent = res.error;
          simError.hidden = false;
          return;
        }
        simResult.hidden = false;
        simResult.classList.toggle("positive", res.is_profit);
        simResult.classList.toggle("negative", res.is_loss);
        simResult.innerHTML = `
          <div class="sim-pnl">${brl(res.pnl)} (${res.roi_pct}%)</div>
          <div class="sim-detail">
            Recebido líquido: ${brl(res.net_received)} · Taxa Steam:
            ${brl(res.steam_fee)} · Equilíbrio: venda a partir de
            ${brl(res.break_even_price)}
          </div>`;
      });
  });
});
