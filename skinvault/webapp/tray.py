"""Bandeja do sistema (pystray) + notificacao nativa (winotify).

Substitui `QSystemTrayIcon`/`QMenu` (`gui.py:_init_tray`) e
`tray_icon.showMessage()` (`gui.py:_on_notification`).
"""
from __future__ import annotations

import logging
import sys
import threading

try:
    import pystray
except ImportError:  # pragma: no cover - ambiente sem pystray instalado
    pystray = None

from skinvault import settings as settings_mod
from skinvault.webapp import window as window_mod

log = logging.getLogger(__name__)

_icon = None  # type: ignore[var-annotated]


def _make_icon_image():
    """Icone 64x64 provisorio (circulo verde) -- so' pra ter algo na bandeja.

    Trocar por um .ico real do projeto nao bloqueia o scaffolding.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover
        return None
    img = Image.new("RGB", (64, 64), (15, 15, 15))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill=(34, 197, 94))
    return img


def _on_abrir(icon, item) -> None:
    window_mod.restore()


def _on_overlay(icon, item) -> None:
    s = settings_mod.load_settings()
    novo = not s.get("overlay_mode", False)
    s["overlay_mode"] = novo
    settings_mod.save_settings(s)
    window_mod.apply_overlay(novo)


def _overlay_checked(item) -> bool:
    return bool(settings_mod.load_settings().get("overlay_mode", False))


def _on_sair(icon, item) -> None:
    icon.stop()
    window_mod.destroy()


def start() -> None:
    """Inicia o icone da bandeja numa thread daemon propria.

    `pystray.Icon.run()` bloqueia (roda seu proprio loop de mensagens),
    por isso precisa de thread dedicada -- igual o tray do Qt roda
    integrado ao loop do QApplication, so' que aqui nao ha' um loop
    central pra integrar.
    """
    global _icon
    if pystray is None:
        log.warning("pystray indisponivel; bandeja desativada.")
        return
    menu = pystray.Menu(
        pystray.MenuItem("Abrir SkinVault", _on_abrir, default=True),
        pystray.MenuItem("Modo overlay", _on_overlay, checked=_overlay_checked),
        pystray.MenuItem("Sair", _on_sair),
    )
    _icon = pystray.Icon("skinvault", _make_icon_image(), "SkinVault", menu)
    threading.Thread(target=_icon.run, daemon=True, name="skinvault-tray").start()


def stop() -> None:
    if _icon is not None:
        try:
            _icon.stop()
        except Exception:
            pass


def notify(title: str, body: str, severity: str = "info") -> None:
    """Dispara um toast nativo do Windows.

    `severity`: 'opportunity' | 'warning' | 'info' -- mesmo vocabulario
    de `alerts.py`; aqui so' influencia o log (winotify nao tem um
    icone por severidade equivalente ao `QSystemTrayIcon.MessageIcon`
    de hoje).
    """
    if sys.platform != "win32":
        log.info("Notificacao (sem toast nativo fora do Windows): %s - %s",
                  title, body)
        return
    try:
        from winotify import Notification
        toast = Notification(app_id="SkinVault", title=title, msg=body,
                              duration="short")
        toast.show()
    except Exception:
        log.exception("Falha ao exibir notificacao nativa (severidade=%s).",
                       severity)
