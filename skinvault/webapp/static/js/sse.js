// Wrapper fino sobre EventSource -- substitui o pyqtSignal de hoje.
// EventSource reconecta automaticamente sozinho; nao precisamos de
// logica de retry aqui.
function connectEvents(onNotification) {
  const es = new EventSource("/api/events");
  es.addEventListener("notification", (ev) => {
    onNotification(JSON.parse(ev.data));
  });
  return es;
}
