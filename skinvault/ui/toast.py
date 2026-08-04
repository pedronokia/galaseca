"""ToastManager — gestão global de toasts.

Envolve o `Toast` de `components.py` (fade/slide/auto-dismiss/clique já
provados e cobertos por teste). O manager centraliza o disparo pra telas
novas sem duplicar o widget, e emite `toast_finished` quando um toast
conclui o ciclo de vida — feedback reativo sem acoplar a tela ao widget.

Uso:

    ToastManager.instance().show_success(self, "Salvo!")
    ToastManager.instance().show_error(self, "Falhou.", duration_ms=4000)

`show` aceita parent, texto, variant e duração; os atalhos
`show_success/show_error/show_info/show_warning` fixam a variant.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from skinvault.ui.components import Toast


class ToastWidget(Toast):
    """Toast que avisa o manager quando encerra o ciclo (fade-out fim)."""

    finished = pyqtSignal()

    def _on_faded_out(self) -> None:
        super()._on_faded_out()
        self.finished.emit()


class ToastManager(QObject):
    """Singleton global: exibe toast e emite `toast_finished` ao fechar."""

    toast_finished = pyqtSignal()

    _instance: "ToastManager | None" = None

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @classmethod
    def instance(cls) -> "ToastManager":
        inst = cls._instance
        if inst is None:
            inst = cls._instance = cls()
            return inst
        try:
            # Acesso ao sinal valida o objeto C++ por baixo: se a
            # QApplication (wrapper) morreu e levou o singleton junto
            # (cenário de teste, onde o app é recriado entre casos),
            # RuntimeError aqui — aí recria. No app real isso nunca
            # dispara: a QApplication vive a sessão inteira.
            _ = inst.toast_finished
        except RuntimeError:
            inst = cls._instance = cls()
        return inst

    def show(self, parent: "object | None", text: str,
             variant: str = "info", duration_ms: int = 3000) -> ToastWidget:
        """Exibe um toast e liga `toast_finished` quando ele fechar."""
        toast = ToastWidget.show_toast(parent, text, variant, duration_ms)
        toast.finished.connect(self.toast_finished.emit)
        return toast

    def show_success(self, parent: "object | None", text: str,
                     duration_ms: int = 3000) -> ToastWidget:
        return self.show(parent, text, "success", duration_ms)

    def show_error(self, parent: "object | None", text: str,
                   duration_ms: int = 3000) -> ToastWidget:
        return self.show(parent, text, "error", duration_ms)

    def show_info(self, parent: "object | None", text: str,
                  duration_ms: int = 3000) -> ToastWidget:
        return self.show(parent, text, "info", duration_ms)

    def show_warning(self, parent: "object | None", text: str,
                     duration_ms: int = 3000) -> ToastWidget:
        return self.show(parent, text, "warning", duration_ms)
