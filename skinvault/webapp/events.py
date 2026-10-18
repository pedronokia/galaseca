"""Pub/sub simples que alimenta os endpoints SSE.

Substitui o `pyqtSignal.emit()` -> `slot()` de hoje: uma thread de
trabalho (scheduler de alertas, worker de uma rota) chama `publish()`;
cada aba/janela conectada em /api/events tem sua propria Queue e recebe
uma copia do evento.
"""
from __future__ import annotations

import json
import queue
import threading
from typing import Any, Iterator

_lock = threading.Lock()
_subscribers: "set[queue.Queue[str]]" = set()


def _format_sse(event: str, payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def publish(event: str, payload: Any) -> None:
    """Envia `payload` (serializavel em JSON) pra todo assinante vivo."""
    message = _format_sse(event, payload)
    with _lock:
        subscribers = list(_subscribers)
    for q in subscribers:
        try:
            q.put_nowait(message)
        except queue.Full:
            pass  # assinante lento: perde o evento em vez de travar o publisher


def subscribe() -> "queue.Queue[str]":
    q: "queue.Queue[str]" = queue.Queue(maxsize=100)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: "queue.Queue[str]") -> None:
    with _lock:
        _subscribers.discard(q)


def stream(q: "queue.Queue[str]") -> Iterator[str]:
    """Generator pro Response(mimetype='text/event-stream').

    Um comentario SSE (`: ping`) a cada 20s mantem a conexao viva -- o
    EventSource do navegador usa isso pra perceber conexao morta e
    reconectar, mesmo sem proxy no meio do caminho (e' tudo loopback).
    """
    try:
        while True:
            try:
                msg = q.get(timeout=20)
                yield msg
            except queue.Empty:
                yield ": ping\n\n"
    finally:
        unsubscribe(q)
