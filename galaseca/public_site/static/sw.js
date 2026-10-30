// Service worker mínimo, só pra cumprir o requisito de instalabilidade
// (Chrome exige um SW com handler de "fetch" pra contar como PWA
// "installable"). Nunca cacheia HTML/API -- o scan muda, e uma página
// em cache mostraria preço velho como se fosse de agora. Só os
// estáticos versionados (?v=<build>, ver server.py:static_v) entram no
// cache: o próprio nome da URL já muda a cada deploy, então cachear
// agressivo aqui não tem risco de servir versão errada.
const CACHE = "galaseca-static-v1";

self.addEventListener("install", function (event) {
  self.skipWaiting();
});

// Apaga caches com outro nome (ex. "skinvault-static-v1", de antes da troca
// de nome do projeto): sem isso ficariam no navegador do visitante pra sempre.
self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(nomes.filter(function (n) { return n !== CACHE; })
        .map(function (n) { return caches.delete(n); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (url.pathname.indexOf("/static/") !== 0 || !url.searchParams.has("v")) {
    return; // HTML/API/sem versão -- sempre rede, nunca cache.
  }
  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      return cache.match(event.request).then(function (cached) {
        if (cached) return cached;
        return fetch(event.request).then(function (resp) {
          cache.put(event.request, resp.clone());
          return resp;
        });
      });
    })
  );
});
