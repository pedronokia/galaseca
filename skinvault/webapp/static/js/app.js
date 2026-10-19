document.addEventListener("DOMContentLoaded", () => {
  const toastArea = document.getElementById("toast-area");

  // severidades que passam por aqui: "info"/"opportunity" (alerts.py,
  // via watchlist), "success"/"warning"/"error" (telas que notificam
  // resultado de uma acao). Desconhecida cai no estilo neutro de "info".
  const SEVERITY_CLASS = {
    success: "toast-success", opportunity: "toast-success",
    warning: "toast-warning", error: "toast-error", info: "toast-info",
  };
  const AUTO_DISMISS_MS = 6000;

  function showToast(payload) {
    const el = document.createElement("div");
    el.className = `toast ${SEVERITY_CLASS[payload.severity] || "toast-info"}`;

    const title = document.createElement("div");
    title.className = "toast-title";
    title.textContent = payload.title;
    const body = document.createElement("div");
    body.className = "toast-body";
    body.textContent = payload.body;
    el.append(title, body);

    // Sem isto os toasts empilhavam pra sempre (nenhum codigo tirava
    // da tela) -- clique tambem fecha, pra quem quer ler com calma e
    // dispensar na hora.
    const dismiss = () => {
      el.classList.add("toast-leaving");
      el.addEventListener("transitionend", () => el.remove(), { once: true });
    };
    el.addEventListener("click", dismiss);
    el.style.pointerEvents = "auto";
    setTimeout(dismiss, AUTO_DISMISS_MS);

    toastArea.prepend(el);
  }

  // Guardado em window pra outras telas (account.js) escutarem outros
  // eventos na MESMA conexao, em vez de abrir uma segunda EventSource.
  window.skinvaultEvents = connectEvents(showToast);

  const btn = document.getElementById("btn-debug-notify");
  if (btn) {
    btn.addEventListener("click", () => {
      fetch("/api/debug/notify", { method: "POST" });
    });
  }

  // Tooltip customizado (tema escuro) no lugar do balao nativo do
  // navegador (branco, serrilhado, sem respeitar o tema). Preguicoso
  // de proposito: converte `title` -> `data-tooltip` so' no primeiro
  // hover/foco de CADA elemento, nao uma vez so' no carregamento --
  // varias telas setam `.title` depois do DOMContentLoaded (linha de
  // tabela do Scanner, item renderizado do Inventario...), e uma
  // conversao unica no load nunca pegaria essas. Remover o `title`
  // cancela o balao nativo agendado (confirmado: funciona em todo
  // motor testado) antes dele aparecer.
  // Reposiciona o balao quando o elemento esta perto da borda da area
  // de conteudo -- centralizado (regra default) ele estourava a
  // direita em colunas do fim de uma tabela larga (Scanner) ou botoes
  // no canto do page-header, e a esquerda em colunas logo apos o
  // sidebar (overflow:auto do .app-content corta, nao so' a borda da
  // janela -- vazado contra window.innerWidth cortava mesmo quando a
  // conta "cabia" na janela, por nao contar o sidebar). Roda a cada
  // hover (nao so' na 1a vez) pra acompanhar resize/scroll. Sidebar
  // fica de fora: tem posicionamento proprio (lado do icone) que ja
  // nao estoura.
  function posicionarTooltip(el) {
    const container = el.closest(".app-content") || document.body;
    const bounds = container.getBoundingClientRect();
    const rect = el.getBoundingClientRect();
    const margin = 12;
    const maxLargura = 280;
    const centro = rect.left + rect.width / 2;
    if (centro + maxLargura / 2 > bounds.right - margin) {
      el.setAttribute("data-tooltip-align", "right");
    } else if (centro - maxLargura / 2 < bounds.left + margin) {
      el.setAttribute("data-tooltip-align", "left");
    } else {
      el.removeAttribute("data-tooltip-align");
    }
  }

  function adotarTooltip(ev) {
    const el = ev.target.closest
      ? ev.target.closest("[title], [data-tooltip]") : null;
    if (!el) return;
    if (el.getAttribute("title")) {
      el.setAttribute("data-tooltip", el.getAttribute("title"));
      el.removeAttribute("title");
    }
    if (el.hasAttribute("data-tooltip") && !el.classList.contains("sidebar-item")) {
      posicionarTooltip(el);
    }
  }
  document.addEventListener("mouseover", adotarTooltip, true);
  document.addEventListener("focusin", adotarTooltip, true);

  // Confirmação no tema escuro, no lugar do confirm() nativo (balão
  // claro do navegador — color-scheme não alcança window.confirm,
  // só controles de formulário). Promise<boolean>: true = confirmou.
  const confirmModal = document.getElementById("confirm-modal");
  const confirmTitle = document.getElementById("confirm-title");
  const confirmMessage = document.getElementById("confirm-message");
  const confirmCancelBtn = document.getElementById("confirm-cancel");
  const confirmOkBtn = document.getElementById("confirm-ok");

  window.skinvaultConfirm = function (message, opts) {
    opts = opts || {};
    confirmTitle.textContent = opts.title || "Confirmar";
    confirmMessage.textContent = message;
    confirmOkBtn.textContent = opts.confirmLabel || "Confirmar";
    confirmOkBtn.className = opts.danger ? "btn-danger" : "btn-primary";
    confirmModal.hidden = false;
    confirmOkBtn.focus();
    return new Promise((resolve) => {
      function cleanup(result) {
        confirmModal.hidden = true;
        confirmOkBtn.removeEventListener("click", onOk);
        confirmCancelBtn.removeEventListener("click", onCancel);
        confirmModal.removeEventListener("mousedown", onBackdrop);
        document.removeEventListener("keydown", onKey);
        resolve(result);
      }
      function onOk() { cleanup(true); }
      function onCancel() { cleanup(false); }
      function onBackdrop(ev) { if (ev.target === confirmModal) cleanup(false); }
      function onKey(ev) { if (ev.key === "Escape") cleanup(false); }
      confirmOkBtn.addEventListener("click", onOk);
      confirmCancelBtn.addEventListener("click", onCancel);
      confirmModal.addEventListener("mousedown", onBackdrop);
      document.addEventListener("keydown", onKey);
    });
  };
});
