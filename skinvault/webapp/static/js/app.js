document.addEventListener("DOMContentLoaded", () => {
  const toastArea = document.getElementById("toast-area");

  function showToast(payload) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = `${payload.title}: ${payload.body}`;
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
