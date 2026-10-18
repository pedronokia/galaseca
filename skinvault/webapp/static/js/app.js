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
});
