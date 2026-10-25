// JS do dashboard público -- extraído de index.html pra ficar fora da
// página (permite um Content-Security-Policy sem 'unsafe-inline' em
// script-src no Caddyfile). Vanilla, sem dependência, sem build step.

// Copiar nome do item (clipboard) e atalho "/" pra focar a busca -- os
// únicos dois recursos desta página que genuinamente não dão pra fazer
// sem JS. Delegação de evento (um listener só, cobre linhas criadas por
// qualquer um dos modos: lista, agrupado).
document.addEventListener("click", function (e) {
  var btn = e.target.closest(".botao-copiar");
  if (!btn) return;
  var texto = btn.getAttribute("data-copiar");
  if (!navigator.clipboard) return;
  navigator.clipboard.writeText(texto).then(function () {
    var original = btn.textContent;
    btn.textContent = "✓";
    setTimeout(function () { btn.textContent = original; }, 1200);
  }).catch(function () {});
});

document.addEventListener("keydown", function (e) {
  if (e.key !== "/") return;
  var ativo = document.activeElement;
  var campoAberto = ativo && (ativo.tagName === "INPUT"
    || ativo.tagName === "TEXTAREA" || ativo.tagName === "SELECT");
  if (campoAberto) return;
  var campo = document.getElementById("campo-busca");
  if (!campo) return;
  e.preventDefault();
  campo.focus();
});

// Notas pessoais por item -- só neste navegador (localStorage), nunca
// enviadas pro servidor. Tenta ler/escrever; se o navegador bloquear
// (aba anônima, storage desligado), a página continua funcionando
// normal, só sem salvar a nota.
(function () {
  var CHAVE = "skinvault_notas";
  function lerTudo() {
    try {
      return JSON.parse(localStorage.getItem(CHAVE) || "{}");
    } catch (e) { return {}; }
  }
  try {
    var notas = lerTudo();
    document.querySelectorAll(".input-tag-local").forEach(function (campo) {
      var item = campo.getAttribute("data-item");
      if (notas[item]) campo.value = notas[item];
    });
  } catch (e) {}

  document.addEventListener("change", function (e) {
    if (!e.target.classList || !e.target.classList.contains("input-tag-local")) return;
    try {
      var todas = lerTudo();
      var item = e.target.getAttribute("data-item");
      if (e.target.value) {
        todas[item] = e.target.value;
      } else {
        delete todas[item];
      }
      localStorage.setItem(CHAVE, JSON.stringify(todas));
    } catch (e) {}
  });
})();
