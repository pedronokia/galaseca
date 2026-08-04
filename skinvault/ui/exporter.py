"""Helper de exportação — menu "Exportar" + QFileDialog + gravação atômica.

Toda tela que exporta segue o mesmo fluxo: um menu com CSV/JSON/HTML,
QFileDialog pra escolher o destino e `reports.write_export` (BOM UTF-8 no
CSV, escrita atômica — AGENTS.md #10). Retorna (caminho, erro) pra tela
poder dar feedback no status sem depender de exceção não tratada.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QFileDialog, QMenu, QWidget

from skinvault import reports
from skinvault.ui import theme as t

#: kind -> (filtro do QFileDialog, extensão/sufixo do default_name).
EXPORT_FILTERS = {
    "csv": ("CSV (*.csv)", "csv"),
    "json": ("JSON (*.json)", "json"),
    "html": ("Relatório HTML (*.html)", "html"),
}


def build_export_menu(parent: QWidget,
                      itens: "list[tuple[str, Callable[[], None]]]") -> QMenu:
    """Menu de exportação com os rótulos dados.

    `itens`: [(rótulo, handler)]. Cada item é btn_ghost estilo, com
    tooltip padrão. O menu herda o tema da janela (menu_style no QSS
    global da MainWindow — ver gui._apply_stylesheet).
    """
    menu = QMenu(parent)
    for rotulo, handler in itens:
        act = menu.addAction(rotulo)
        act.setToolTip(
            "Salva um arquivo com o conteúdo atual — usa a mesma fonte "
            "de dados da tela, sem re-buscar nada na rede.")
        act.triggered.connect(lambda _=False, h=handler: h())
    return menu


def save_export(parent: QWidget, default_name: str, kind: str,
                content: str) -> "tuple[str | None, str | None]":
    """Salva `content` via QFileDialog. Devolve (path, erro).

    path None = cancelado. erro preenchido = falha de gravação (a tela
    mostra no status, sem dialog bloqueante pra falha trivial de disco).
    """
    filtro, ext = EXPORT_FILTERS.get(kind, ("CSV (*.csv)", "csv"))
    if not default_name.endswith("." + ext):
        default_name = f"{default_name}.{ext}"
    path, _ = QFileDialog.getSaveFileName(
        parent, "Salvar exportação", default_name, filtro)
    if not path:
        return None, None
    try:
        reports.write_export(path, content, kind)
    except OSError as exc:
        return None, str(exc)
    return path, None


def export_menu_for(parent: QWidget, kind_labels: "list[str]",
                    make: Callable[[str], str],
                    default_name: str,
                    on_result: Callable[["str | None", "str | None"], None]
                    ) -> QMenu:
    """Atalho: menu pronto onde cada kind gera o conteúdo.

    `kind_labels`: subconjunto de EXPORT_FILTERS, ex. ["csv", "json"].
    `make(kind)` devolve o conteúdo (ou "" pra pular — ex.: sem dados).
    `on_result(path, erro)` recebe o resultado pro status da tela.
    """
    def handler(kind: str):
        conteudo = make(kind)
        if not conteudo:
            on_result(None, "nada para exportar")
            return
        path, erro = save_export(parent, default_name, kind, conteudo)
        on_result(path, erro)
    itens = [(f"Exportar {kind.upper()}", lambda k=kind: handler(k))
             for kind in kind_labels]
    return build_export_menu(parent, itens)
