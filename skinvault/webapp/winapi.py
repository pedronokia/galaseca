"""Helpers ctypes Win32 que o pywebview nao expõe.

Overlay mode (stays-on-top + nao rouba foco) hoje e' feito via flags Qt
(`WindowStaysOnTopHint` + `WA_ShowWithoutActivating`, gui.py:390-394).
pywebview nao tem equivalente cross-platform pra "nao roubar foco" --
aqui chamamos SetWindowPos direto no HWND nativo da janela.
"""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)

_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010


def set_overlay(hwnd: int, enabled: bool) -> bool:
    """Aplica/remove stays-on-top sem roubar foco. True se aplicou."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        flag = _HWND_TOPMOST if enabled else _HWND_NOTOPMOST
        ctypes.windll.user32.SetWindowPos(
            hwnd, flag, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE,
        )
        return True
    except Exception:
        log.exception("Falha ao aplicar modo overlay via SetWindowPos.")
        return False


def get_hwnd_by_title(title: str) -> int:
    """Fallback: acha o HWND pelo titulo exato da janela (so' Windows)."""
    if sys.platform != "win32":
        return 0
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        return int(hwnd) if hwnd else 0
    except Exception:
        return 0
