"""Janela nativa (pywebview) hospedando o front web.

Equivalente ao `MainWindow` de `gui.py`, mas so' o casco de janela --
sidebar/telas vivem no HTML servido por `server.py`.
"""
from __future__ import annotations

import logging
import sys

from skinvault.webapp import winapi

log = logging.getLogger(__name__)

_TITLE = "SkinVault"
_window = None  # type: ignore[var-annotated]


def create(url: str, overlay_mode: bool = False):
    """Cria a janela pywebview e aplica o modo overlay se pedido.

    Precisa ser chamado ANTES de `webview.start()`. A instancia fica
    guardada neste modulo pra `restore()`/`apply_overlay()`/`destroy()`
    conseguirem agir sobre ela sem o chamador carregar a referencia.
    """
    import webview

    global _window
    _window = webview.create_window(
        _TITLE, url=url, width=1280, height=800, min_size=(960, 600),
    )
    if overlay_mode:
        _window.events.loaded += lambda: apply_overlay(True)
    return _window


def _hwnd() -> int:
    """Tenta obter o HWND nativo da janela pywebview (so' Windows).

    A API interna do pywebview muda entre versoes/backends -- tentamos
    os caminhos conhecidos (`.native.Handle`) e caimos pro FindWindow
    por titulo se nenhum funcionar. Verificar empiricamente contra a
    versao instalada faz parte da Fase 1 (piloto); aqui o fallback
    garante que overlay vira no-op, nao crash, se a API mudou.
    """
    if _window is None or sys.platform != "win32":
        return 0
    native = getattr(_window, "native", None)
    handle = getattr(native, "Handle", None)
    if handle is not None:
        try:
            return int(handle.ToInt64())
        except Exception:
            try:
                return int(handle)
            except Exception:
                pass
    hwnd = winapi.get_hwnd_by_title(_TITLE)
    if not hwnd:
        log.warning("Nao consegui obter o HWND da janela; overlay desativado.")
    return hwnd


def apply_overlay(enabled: bool) -> None:
    hwnd = _hwnd()
    if hwnd:
        winapi.set_overlay(hwnd, enabled)


def restore() -> None:
    """Traz a janela pra frente -- equivalente a `MainWindow.activate()`."""
    if _window is None:
        return
    try:
        _window.restore()
    except Exception:
        pass
    try:
        _window.show()
    except Exception:
        log.exception("Falha ao restaurar a janela.")


def destroy() -> None:
    if _window is None:
        return
    try:
        _window.destroy()
    except Exception:
        log.exception("Falha ao destruir a janela.")


def get_window():
    return _window
