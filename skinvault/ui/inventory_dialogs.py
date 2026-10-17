"""Dialogos do Inventario: importar da Steam pelo link do perfil e
adicionar item a' mao.

Por que existem: desde que o login/sincronizacao saiu (F10, revertida em
2026-08-07), a interface nao tinha NENHUM jeito de colocar itens na
carteira -- so' a linha de comando. Um usuario novo abria o Inventario
vazio, com a tela mandando "sincronizar" com algo que nao existia mais.

A importacao usa so' dado publico, como o resto do app: o inventario
publico da Steam (/inventory/<steamid64>/730/2) e a pagina XML publica do
perfil pra traduzir o link personalizado em SteamID64. Sem login, sem
cookie, sem chave de API.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from skinvault import portfolio, steam_api
from skinvault.settings import load_settings, save_settings
from skinvault.ui import theme as t
from skinvault.ui._price_worker import _safe_emit
from skinvault.ui.components import FormRow

#: Status de falha -> o que dizer ao usuario (e o que ele pode fazer).
MENSAGENS = {
    steam_api.RESOLVE_INVALID: (
        "Isso não parece um perfil da Steam. Cole o link do seu perfil, "
        "por exemplo: https://steamcommunity.com/id/seu-apelido"),
    steam_api.RESOLVE_NOT_FOUND: (
        "Não achamos esse perfil na Steam. Confira o link ou o apelido."),
    steam_api.INV_PRIVATE: (
        "Esse inventário está privado. Na Steam, abra Editar perfil → "
        "Configurações de privacidade e deixe o Inventário como Público. "
        "Depois tente de novo."),
    steam_api.INV_EMPTY: (
        "Não encontramos itens de CS2 que possam ser vendidos nesse "
        "inventário."),
    steam_api.INV_RATE_LIMITED: (
        "A Steam limitou as consultas agora. Espere alguns minutos e "
        "tente de novo."),
    steam_api.INV_ERROR: (
        "Não deu para falar com a Steam. Verifique a internet e tente de "
        "novo."),
}


def mensagem_de_erro(status: str) -> str:
    return MENSAGENS.get(status, MENSAGENS[steam_api.INV_ERROR])


def resumo_importacao(r: dict) -> str:
    """Resumo em linguagem comum do que a importacao fez."""
    linhas = [f"{r['itens_no_inventario']} item(ns) encontrados no "
              "inventário."]
    if r["adicionados"]:
        linhas.append(f"• {r['adicionados']} novo(s) na carteira.")
    if r["atualizados"]:
        linhas.append(f"• {r['atualizados']} já estavam e foram atualizados.")
    if r["manuais_mantidos"]:
        linhas.append(f"• {r['manuais_mantidos']} você já acompanhava à mão "
                      "e ficaram como estavam.")
    if r["removidos"]:
        linhas.append(f"• {r['removidos']} não estavam mais no inventário "
                      "e saíram da carteira.")
    if r["adicionados"]:
        # Duas linhas explicitas: o QLabel com quebra automatica errava a
        # altura dentro do dialogo e cortava o fim da frase.
        linhas.append("\nA Steam não informa quanto você pagou:\n"
                      "defina o custo de cada item para ver o lucro.")
    return "\n".join(linhas)


class _ImportBridge(QObject):
    # (status, itens) -- status de steam_api (RESOLVE_* ou INV_*)
    terminou = pyqtSignal(str, object)


def buscar_inventario(texto: str) -> "tuple[str, list]":
    """Link/apelido/ID -> (status, itens). Roda na thread do worker."""
    st, steam_id = steam_api.resolve_steam_id(texto)
    if st != steam_api.RESOLVE_OK or not steam_id:
        return st, []
    return steam_api.fetch_inventory(steam_id)


class ImportarSteamDialog(QDialog):
    """Cola o link do perfil -> busca o inventario publico -> mescla."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Importar inventário da Steam")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._importou = False
        self._resumo: dict | None = None
        self._bridge = _ImportBridge(self)
        self._bridge.terminou.connect(self._on_terminou)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        intro = QLabel(
            "Cole o link do seu perfil da Steam. O SkinVault lê só o que "
            "qualquer pessoa pode ver no seu inventário público — não pede "
            "login nem senha.")
        intro.setWordWrap(True)
        intro.setStyleSheet(t.label_body_muted())
        lay.addWidget(intro)

        self._link = QLineEdit(load_settings().get("steam_profile", "") or "")
        self._link.setPlaceholderText(
            "https://steamcommunity.com/id/seu-apelido")
        self._link.setStyleSheet(t.input_style())
        self._link.returnPressed.connect(self._on_importar)
        lay.addWidget(FormRow(
            "Link do perfil", self._link,
            tooltip="Na Steam: clique no seu nome → Perfil, e copie o "
                    "endereço da página. Também serve o SteamID (número "
                    "de 17 dígitos)."))

        self._remover = QCheckBox(
            "Tirar da carteira os itens que não estão mais no inventário")
        self._remover.setChecked(True)
        self._remover.setStyleSheet(t.checkbox_style())
        self._remover.setToolTip(
            "Itens vendidos ou trocados desde a última importação. Itens "
            "que você adicionou à mão nunca são removidos.")
        lay.addWidget(self._remover)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        lay.addWidget(self._status)

        botoes = QHBoxLayout()
        botoes.addStretch()
        self._cancelar = QPushButton("Cancelar")
        self._cancelar.setStyleSheet(t.btn_ghost())
        self._cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancelar.setToolTip("Fecha sem importar.")
        self._cancelar.clicked.connect(self._on_fechar)
        self._importar = QPushButton("Importar")
        self._importar.setStyleSheet(t.btn_primary())
        self._importar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._importar.setToolTip(
            "Busca o inventário público e coloca os itens na carteira.")
        self._importar.clicked.connect(self._on_importar)
        botoes.addWidget(self._cancelar)
        botoes.addWidget(self._importar)
        lay.addLayout(botoes)
        self._link.setFocus()

    # ── fluxo ────────────────────────────────────────────────
    def _mostrar(self, texto: str, erro: bool = False) -> None:
        cor = t.DANGER if erro else t.TEXT
        self._status.setStyleSheet(
            f"color: {cor}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};")
        self._status.setText(texto)
        self._status.setVisible(True)
        # O resumo pode ter varias linhas: sem isto o dialogo mantinha a
        # altura de antes e cortava a ultima frase.
        self.adjustSize()

    def _on_importar(self) -> None:
        texto = self._link.text().strip()
        tipo, _ = steam_api.parse_profile_input(texto)
        if tipo == "invalid":
            self._mostrar(mensagem_de_erro(steam_api.RESOLVE_INVALID),
                          erro=True)
            self._link.setFocus()
            return
        self._importar.setEnabled(False)
        self._link.setEnabled(False)
        self._mostrar("Buscando seu inventário na Steam…")
        sinal = self._bridge.terminou

        def worker() -> None:
            st, itens = steam_api.INV_ERROR, []
            try:
                st, itens = buscar_inventario(texto)
            except Exception:
                pass
            _safe_emit(sinal, st, itens)

        threading.Thread(target=worker, daemon=True).start()

    def _on_terminou(self, status: str, itens) -> None:
        self._link.setEnabled(True)
        if status != steam_api.INV_OK:
            self._importar.setEnabled(True)
            self._mostrar(mensagem_de_erro(status), erro=True)
            return
        self._resumo = portfolio.merge_steam_inventory(
            itens or [], remove_missing=self._remover.isChecked())
        self._importou = True
        s = load_settings()
        s["steam_profile"] = self._link.text().strip()
        save_settings(s)
        self._mostrar(resumo_importacao(self._resumo))
        self._importar.setVisible(False)
        self._cancelar.setText("Fechar")
        self._cancelar.setStyleSheet(t.btn_primary())
        self._cancelar.setToolTip("Fecha e atualiza o inventário.")

    def _on_fechar(self) -> None:
        if self._importou:
            self.accept()
        else:
            self.reject()

    def importou(self) -> bool:
        return self._importou

    def resumo(self) -> "dict | None":
        return self._resumo


def _sugestoes_de_nome() -> "list[str]":
    """Nomes de mercado pro autocomplete: skins do catalogo do Trade-up
    (se ja' baixado) + caixas e capsulas conhecidas. Sem rede."""
    nomes: set = set()
    try:
        from skinvault import cases, tradeup
        nomes.update(tradeup.input_suggestions(tradeup.load_catalog()))
        for st in ("active", "discontinued", "rare"):
            nomes.update(cases.list_cases_by_status(st))
        nomes.update(cases.list_capsules())
    except Exception:
        pass
    return sorted(nomes)


class AdicionarItemDialog(QDialog):
    """Item a' mao: nome de mercado, quantidade e custo (opcional)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adicionar item")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self._valores: dict | None = None
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        self._nome = QLineEdit()
        self._nome.setPlaceholderText("AK-47 | Redline (Field-Tested)")
        self._nome.setStyleSheet(t.input_style())
        sugestoes = _sugestoes_de_nome()
        if sugestoes:
            comp = QCompleter(sugestoes, self._nome)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            comp.setMaxVisibleItems(12)
            comp.popup().setStyleSheet(
                f"background: {t.BG_ELEVATED}; color: {t.TEXT};")
            self._nome.setCompleter(comp)
        lay.addWidget(FormRow(
            "Nome do item", self._nome,
            tooltip="Exatamente como aparece no Steam Market, com o "
                    "desgaste entre parênteses. Comece a digitar para ver "
                    "sugestões."))

        linha = QHBoxLayout()
        linha.setSpacing(12)
        self._qtd = QSpinBox()
        self._qtd.setRange(1, 9999)
        self._qtd.setStyleSheet(t.spin_style())
        self._qtd.setMaximumWidth(140)
        linha.addWidget(FormRow("Quantidade", self._qtd,
                                tooltip="Quantas unidades você tem."))
        self._custo = QLineEdit()
        self._custo.setPlaceholderText("opcional — ex.: 199,90")
        self._custo.setStyleSheet(t.input_style())
        linha.addWidget(FormRow(
            "Custo por item (R$)", self._custo,
            tooltip="Quanto pagou por unidade. Vazio = não sei (dá para "
                    "definir depois). 0 = veio de drop."), 1)
        lay.addLayout(linha)

        self._erro = QLabel("")
        self._erro.setWordWrap(True)
        self._erro.setStyleSheet(
            f"color: {t.DANGER}; font-size: {t.FS_MUTED};"
            f" font-family: {t.FONT_FAMILY};")
        self._erro.setVisible(False)
        lay.addWidget(self._erro)

        botoes = QHBoxLayout()
        botoes.addStretch()
        cancelar = QPushButton("Cancelar")
        cancelar.setStyleSheet(t.btn_ghost())
        cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        cancelar.setToolTip("Fecha sem adicionar.")
        cancelar.clicked.connect(self.reject)
        ok = QPushButton("Adicionar")
        ok.setStyleSheet(t.btn_primary())
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setToolTip("Coloca o item na carteira.")
        ok.clicked.connect(self._on_ok)
        botoes.addWidget(cancelar)
        botoes.addWidget(ok)
        lay.addLayout(botoes)
        self._nome.setFocus()

    def _falha(self, texto: str, campo: QLineEdit) -> None:
        self._erro.setText(texto)
        self._erro.setVisible(True)
        campo.setFocus()
        campo.selectAll()

    def _on_ok(self) -> None:
        nome = self._nome.text().strip()
        if not nome:
            self._falha("Informe o nome do item.", self._nome)
            return
        texto_custo = self._custo.text().strip()
        custo = None
        if texto_custo:
            try:
                custo = portfolio._parse_brl(texto_custo)
            except ValueError:
                custo = -1
            if custo is None or custo < 0:
                self._falha("Custo inválido — use números, ex.: 199,90 "
                            "(ou deixe vazio se não souber).", self._custo)
                return
            custo = round(custo, 2)
        self._valores = {"name": nome, "quantity": self._qtd.value(),
                         "cost": custo}
        self.accept()

    def valores(self) -> "dict | None":
        return self._valores
