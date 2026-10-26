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
  var texto = btn.getAttribute("data-copiar") || btn.getAttribute("data-copiar-link");
  if (!texto || !navigator.clipboard) return;
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

// Favoritos -- igual às notas acima, só neste navegador, nunca enviado
// pro servidor. "☆ Só favoritos" filtra as linhas da tabela na hora,
// sem recarregar a página (o filtro do servidor não sabe o que está
// no localStorage de cada visitante).
(function () {
  var CHAVE = "skinvault_favoritos";
  function lerTudo() {
    try {
      return JSON.parse(localStorage.getItem(CHAVE) || "{}");
    } catch (e) { return {}; }
  }
  function salvar(todos) {
    try { localStorage.setItem(CHAVE, JSON.stringify(todos)); } catch (e) {}
  }
  function pintarBotao(btn, favoritado) {
    btn.textContent = btn.textContent.replace(/^[☆★]/, favoritado ? "★" : "☆");
    btn.classList.toggle("favoritado", favoritado);
  }
  function aplicarEstadoInicial() {
    var favoritos = lerTudo();
    document.querySelectorAll(".botao-favorito").forEach(function (btn) {
      var item = btn.getAttribute("data-favorito");
      if (favoritos[item]) pintarBotao(btn, true);
    });
  }
  try { aplicarEstadoInicial(); } catch (e) {}

  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".botao-favorito");
    if (!btn) return;
    try {
      var favoritos = lerTudo();
      var item = btn.getAttribute("data-favorito");
      var novoEstado = !favoritos[item];
      if (novoEstado) { favoritos[item] = true; } else { delete favoritos[item]; }
      salvar(favoritos);
      pintarBotao(btn, novoEstado);
    } catch (e) {}
  });

  document.addEventListener("click", function (e) {
    var botao = e.target.closest("#botao-favoritos");
    if (!botao) return;
    try {
      var favoritos = lerTudo();
      var ativo = botao.classList.toggle("ativo");
      var algumVisivel = false;
      document.querySelectorAll("table.tabela-candidatos tbody tr").forEach(function (linha) {
        var botaoLinha = linha.querySelector(".botao-favorito");
        if (!botaoLinha) return;
        var item = botaoLinha.getAttribute("data-favorito");
        var escondida = ativo && !favoritos[item];
        linha.style.display = escondida ? "none" : "";
        if (!escondida) algumVisivel = true;
      });
      var textoBotao = document.getElementById("texto-botao-favoritos");
      if (textoBotao) textoBotao.textContent = ativo ? "★ Todos os itens" : "☆ Só favoritos";
      var msgVazio = document.getElementById("msg-sem-favoritos");
      if (msgVazio) msgVazio.hidden = !(ativo && !algumVisivel);
    } catch (e) {}
  });
})();

// Exportar CSV -- lê as linhas visíveis da(s) tabela(s) de candidatos e
// gera um arquivo client-side (sem rota nova no servidor, sem reenviar
// nada que já está na página).
(function () {
  function textoCelula(td) {
    var clone = td.cloneNode(true);
    clone.querySelectorAll("button, .botao-copiar, .botao-favorito, svg").forEach(
      function (el) { el.remove(); });
    return clone.textContent.replace(/\s+/g, " ").trim();
  }
  function paraCsv(valor) {
    if (/[",\n;]/.test(valor)) return '"' + valor.replace(/"/g, '""') + '"';
    return valor;
  }
  document.addEventListener("click", function (e) {
    if (e.target.id !== "botao-exportar-csv") return;
    var linhas = [];
    var cabecalho = document.querySelector("table.tabela-candidatos thead tr");
    if (cabecalho) {
      linhas.push(Array.from(cabecalho.querySelectorAll("th")).map(
        function (th) { return paraCsv(th.textContent.trim()); }).join(";"));
    }
    document.querySelectorAll("table.tabela-candidatos tbody tr").forEach(function (tr) {
      if (tr.style.display === "none") return;
      linhas.push(Array.from(tr.querySelectorAll("td")).map(
        function (td) { return paraCsv(textoCelula(td)); }).join(";"));
    });
    var blob = new Blob(["﻿" + linhas.join("\n")], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = "skinvault.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });
})();

// Comparador -- marca até 3 itens (sessionStorage, por aba/sessão: não
// faz sentido sobreviver semanas como os favoritos) e mostra uma barra
// flutuante com link pra /comparar?nomes=A,B,C.
(function () {
  var CHAVE = "skinvault_comparar";
  var MAX = 3;
  function ler() {
    try { return JSON.parse(sessionStorage.getItem(CHAVE) || "[]"); } catch (e) { return []; }
  }
  function salvar(lista) {
    try { sessionStorage.setItem(CHAVE, JSON.stringify(lista)); } catch (e) {}
  }
  function atualizarBarra() {
    var lista = ler();
    var barra = document.getElementById("barra-comparar");
    if (!barra) return;
    if (lista.length < 2) { barra.hidden = true; return; }
    barra.hidden = false;
    var contagem = barra.querySelector(".contagem-comparar");
    if (contagem) contagem.textContent = lista.length;
    var link = barra.querySelector(".link-comparar");
    if (link) link.href = "/comparar?nomes=" + lista.map(encodeURIComponent).join(",");
  }
  try {
    var selecionados = ler();
    document.querySelectorAll(".checkbox-comparar").forEach(function (cb) {
      cb.checked = selecionados.indexOf(cb.getAttribute("data-comparar")) !== -1;
    });
    atualizarBarra();
  } catch (e) {}

  document.addEventListener("change", function (e) {
    if (!e.target.classList || !e.target.classList.contains("checkbox-comparar")) return;
    var lista = ler();
    var nome = e.target.getAttribute("data-comparar");
    if (e.target.checked) {
      if (lista.length >= MAX) { e.target.checked = false; return; }
      lista.push(nome);
    } else {
      lista = lista.filter(function (n) { return n !== nome; });
    }
    salvar(lista);
    atualizarBarra();
  });

  document.addEventListener("click", function (e) {
    if (e.target.id !== "botao-limpar-comparar") return;
    salvar([]);
    document.querySelectorAll(".checkbox-comparar").forEach(function (cb) { cb.checked = false; });
    atualizarBarra();
  });
})();

// "O que mudou desde sua última visita" -- compara a nota de cada item
// na tabela com a última vez que ESTE navegador viu a página, destaca
// quem mudou, e atualiza o snapshot pra próxima visita.
(function () {
  var CHAVE = "skinvault_ultima_visita";
  function lerAnterior() {
    try { return JSON.parse(localStorage.getItem(CHAVE) || "{}"); } catch (e) { return {}; }
  }
  try {
    var anterior = lerAnterior();
    var atual = {};
    document.querySelectorAll("table.tabela-candidatos tbody tr[data-nome]").forEach(function (tr) {
      var nome = tr.getAttribute("data-nome");
      var nota = parseInt(tr.getAttribute("data-nota"), 10);
      if (!nome || isNaN(nota)) return;
      atual[nome] = nota;
      var antes = anterior[nome];
      if (antes === undefined || antes === nota) return;
      var celulaNota = tr.querySelector(".nota");
      if (!celulaNota) return;
      var subiu = nota > antes;
      var selo = document.createElement("span");
      selo.className = "selo-mudou-nota " + (subiu ? "tendencia-alta" : "tendencia-baixa");
      selo.title = "Nota " + (subiu ? "subiu" : "caiu") + " de " + antes + " pra " + nota + " desde sua última visita";
      selo.textContent = (subiu ? " ▲" : " ▼") + Math.abs(nota - antes);
      celulaNota.appendChild(selo);
    });
    if (Object.keys(atual).length) localStorage.setItem(CHAVE, JSON.stringify(atual));
  } catch (e) {}
})();

// Atalhos de teclado pra paginação (seta esquerda/direita) -- só quando
// nenhum campo de formulário está focado, pra não roubar a seta de
// dentro de um <input>.
document.addEventListener("keydown", function (e) {
  if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
  var ativo = document.activeElement;
  var campoAberto = ativo && (ativo.tagName === "INPUT"
    || ativo.tagName === "TEXTAREA" || ativo.tagName === "SELECT");
  if (campoAberto) return;
  var id = e.key === "ArrowLeft" ? "link-pagina-anterior" : "link-pagina-seguinte";
  var link = document.getElementById(id);
  if (!link) return;
  e.preventDefault();
  window.location.href = link.href;
});

// Buscas salvas -- guarda a querystring atual com um nome escolhido
// pelo visitante (só neste navegador), pra voltar rápido depois sem
// reconfigurar os filtros.
(function () {
  var CHAVE = "skinvault_buscas_salvas";
  function ler() {
    try { return JSON.parse(localStorage.getItem(CHAVE) || "[]"); } catch (e) { return []; }
  }
  function salvar(lista) {
    try { localStorage.setItem(CHAVE, JSON.stringify(lista)); } catch (e) {}
  }
  function renderizar() {
    var ul = document.getElementById("lista-buscas-salvas");
    if (!ul) return;
    var lista = ler();
    ul.innerHTML = "";
    if (!lista.length) { ul.hidden = true; return; }
    ul.hidden = false;
    lista.forEach(function (item, i) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = item.query;
      a.textContent = item.nome;
      li.appendChild(a);
      var remover = document.createElement("button");
      remover.type = "button";
      remover.className = "botao-link botao-remover botao-remover-busca";
      remover.textContent = "remover";
      remover.setAttribute("data-indice", i);
      li.appendChild(remover);
      ul.appendChild(li);
    });
  }
  try { renderizar(); } catch (e) {}

  document.addEventListener("click", function (e) {
    if (e.target.id === "botao-salvar-busca") {
      var nome = window.prompt("Nome pra esta busca:");
      if (!nome) return;
      try {
        var lista = ler();
        lista.push({ nome: nome, query: window.location.pathname + window.location.search });
        salvar(lista);
        renderizar();
        mostrarToast("Busca \"" + nome + "\" salva.");
      } catch (err) {}
      return;
    }
    if (e.target.classList && e.target.classList.contains("botao-remover-busca")) {
      try {
        var lista2 = ler();
        lista2.splice(parseInt(e.target.getAttribute("data-indice"), 10), 1);
        salvar(lista2);
        renderizar();
      } catch (err) {}
    }
  });
})();

// PWA: registra o service worker (ver /sw.js + manifest.json) -- só
// pra instalabilidade ("Adicionar à tela inicial"); a lógica de cache
// de verdade vive no próprio sw.js, não aqui.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(function () {});
}

// Toast -- confirmação visual curta (salvar busca, exportar CSV). Um
// elemento só, reaproveitado -- não empilha vários se clicar rápido.
function mostrarToast(mensagem) {
  try {
    var area = document.getElementById("area-toast");
    if (!area) return;
    area.textContent = mensagem;
    area.classList.add("visivel");
    clearTimeout(area._timeout);
    area._timeout = setTimeout(function () {
      area.classList.remove("visivel");
    }, 2200);
  } catch (e) {}
}

// Botão "voltar ao topo" -- aparece só depois de rolar um pouco.
(function () {
  var botao = document.getElementById("botao-topo");
  if (!botao) return;
  function atualizar() {
    botao.hidden = window.scrollY < 600;
  }
  document.addEventListener("scroll", atualizar, { passive: true });
  botao.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  try { atualizar(); } catch (e) {}
})();

// Contagem de favoritos no botão de filtro + atalho de teclado "f".
(function () {
  function contarFavoritos() {
    try {
      var favoritos = JSON.parse(localStorage.getItem("skinvault_favoritos") || "{}");
      return Object.keys(favoritos).length;
    } catch (e) { return 0; }
  }
  function atualizarBadge() {
    var badge = document.getElementById("contagem-favoritos");
    if (!badge) return;
    var n = contarFavoritos();
    badge.textContent = n;
    badge.hidden = n === 0;
  }
  try { atualizarBadge(); } catch (e) {}
  document.addEventListener("click", function (e) {
    if (e.target.closest(".botao-favorito") || e.target.id === "botao-favoritos") {
      setTimeout(atualizarBadge, 0);
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "f" && e.key !== "F") return;
    var ativo = document.activeElement;
    var campoAberto = ativo && (ativo.tagName === "INPUT"
      || ativo.tagName === "TEXTAREA" || ativo.tagName === "SELECT");
    if (campoAberto) return;
    var botao = document.getElementById("botao-favoritos");
    if (botao) botao.click();
  });
})();

// Conecta os toasts nas ações que já existiam (salvar busca / exportar
// CSV) -- os handlers originais continuam noutro listener; este só
// escuta o mesmo clique pra mostrar a confirmação visual.
document.addEventListener("click", function (e) {
  if (e.target.id === "botao-exportar-csv") {
    mostrarToast("CSV baixado.");
  }
});

// Prefetch da página de detalhes ao passar o mouse no link "Detalhes" --
// quando o visitante de fato clica, a página já está no cache do
// navegador. `rel="prefetch"` é uma dica (o navegador pode ignorar sob
// dados limitados/economia de bateria); nunca prefetch em toque (mobile
// não tem hover de verdade, e isso dispararia prefetch em todo scroll).
(function () {
  var jaPrefetchado = {};
  document.addEventListener("mouseover", function (e) {
    var link = e.target.closest('a.link-secundario[href^="/item/"]');
    if (!link || jaPrefetchado[link.href]) return;
    jaPrefetchado[link.href] = true;
    var tag = document.createElement("link");
    tag.rel = "prefetch";
    tag.href = link.href;
    document.head.appendChild(tag);
  });
})();
