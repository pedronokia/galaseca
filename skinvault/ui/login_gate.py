"""LoginGate -- tela inicial bloqueante quando nao ha sessao Steam (F11).

Emite session_connected(SteamSession) ao terminar o login.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from skinvault import steam_session
from skinvault.steam_login_dialog import build_steam_login_dialog
from skinvault.ui.qr_login_dialog import QrLoginPanel
from skinvault.ui import theme as t
from skinvault.ui.components import LineIcon


def _divider() -> QWidget:
    """Linha fina 1px (BORDER) pra separar blocos dentro do cartao."""
    d = QWidget()
    d.setFixedHeight(1)
    d.setStyleSheet(f"background: {t.BORDER};")
    return d


def _feature_row(icon_name: str, title: str, desc: str) -> QWidget:
    """Linha de feature: glifo LineIcon + titulo + descricao (lista limpa)."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)

    icn = LineIcon(icon_name, t.ACCENT)
    lay.addWidget(icn, 0, Qt.AlignmentFlag.AlignTop)

    text = QVBoxLayout()
    text.setContentsMargins(0, 0, 0, 0)
    text.setSpacing(1)

    ttl = QLabel(title)
    ttl.setStyleSheet(
        f"color: {t.TEXT}; font-size: {t.FS_INPUT}; font-weight: 600;"
        f" font-family: {t.FONT_FAMILY};"
    )
    text.addWidget(ttl)

    d = QLabel(desc)
    d.setStyleSheet(t.label_caption())
    # SEM wordWrap de proposito: QLabel embrulhado calcula altura antes de
    # saber a largura final e a segunda linha saia cortada. As descricoes
    # sao curtas o bastante pra caber numa linha -- se alguma crescer,
    # encurte o texto em vez de religar o wrap.
    text.addWidget(d)

    lay.addLayout(text, 1)
    return row


class LoginGate(QWidget):
    """Tela de login: cartao flutuante, duas colunas, QR visivel de cara.

    As opcoes ficam LADO A LADO, sem clique intermediario pra revelar --
    esconder o QR atras de um botao era um passo a mais pra a unica acao
    da tela.

    Diferenca proposital em relacao ao login da Steam: onde eles poem
    usuario e senha, aqui vai o que o app faz. O SkinVault nunca tem campo
    de senha, e isso e' principio de seguranca, nao recurso faltando.

    O QR e' desenhado INVERTIDO (modulos claros sobre fundo escuro) pra a
    tela ficar de uma cor so'. Ver o aviso de compatibilidade no QrCode.
    """

    session_connected = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LoginGate")
        # Mesmo tom do router no login: qualquer diferenca aqui vira
        # moldura escura em volta do conteudo.
        self.setStyleSheet(
            f"QWidget#LoginGate {{ background: {t.BG_ELEVATED}; }}")
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Sem cartao recortado: o conteudo fica direto sobre a superficie.
        # Cartao com fundo proprio exigia um fundo DIFERENTE atras dele, e
        # esse fundo aparecia como borda preta em volta.
        card = QWidget()
        card.setObjectName("LoginCard")
        card.setMaximumWidth(700)
        card.setMinimumWidth(540)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(t.SPACE_2XL, t.SPACE_XL,
                                    t.SPACE_2XL, t.SPACE_XL)
        card_lay.setSpacing(0)

        marca = QHBoxLayout()
        marca.setSpacing(t.SPACE_MD)
        traco = QLabel()
        traco.setFixedSize(4, 28)
        traco.setStyleSheet(f"background: {t.ACCENT}; border-radius: 2px;")
        titulo = QLabel("SkinVault")
        titulo.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE}; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY}; letter-spacing: -1px;")
        marca.addWidget(traco)
        marca.addWidget(titulo)
        marca.addStretch(1)
        card_lay.addLayout(marca)

        card_lay.addSpacing(t.SPACE_SM)
        tagline = QLabel("Análise inteligente do Steam Community Market")
        tagline.setStyleSheet(t.label_body_muted())
        card_lay.addWidget(tagline)

        card_lay.addSpacing(t.SPACE_XL)
        card_lay.addWidget(_divider())
        card_lay.addSpacing(t.SPACE_XL)

        colunas = QHBoxLayout()
        colunas.setSpacing(t.SPACE_2XL)
        colunas.addWidget(self._build_pitch(), 1)
        colunas.addWidget(self._build_qr_col(), 0)
        card_lay.addLayout(colunas)

        card_lay.addSpacing(t.SPACE_XL)
        rodape = QLabel(
            "Sua senha nunca passa pelo SkinVault · Cookies de sessão salvos "
            "localmente · Desconecte quando quiser")
        rodape.setWordWrap(True)
        rodape.setStyleSheet(t.label_caption())
        card_lay.addWidget(rodape)

        outer.addStretch(1)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def _caption(self, texto: str) -> QLabel:
        """Rotulo curto em caixa alta sobre cada coluna."""
        lbl = QLabel(texto)
        lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_MUTED};"
            " font-weight: 600; letter-spacing: 0.8px;")
        return lbl

    def _build_pitch(self) -> QWidget:
        """Coluna esquerda: o que o app faz."""
        w = QWidget()
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        col.addWidget(self._caption("O QUE VOCÊ VAI VER"))
        col.addSpacing(t.SPACE_LG)

        for i, (icone, ttl, desc) in enumerate((
            ("wallet", "Inventário", "Valor real, já com a taxa"),
            ("history", "Histórico", "Evolução do patrimônio"),
            ("calc", "Simulação", "Teste trades antes de fazer"),
            ("radar", "Scanner", "Score 0–100 por item"),
        )):
            if i:
                col.addSpacing(t.SPACE_LG)
            col.addWidget(_feature_row(icone, ttl, desc))
        col.addStretch(1)
        return w

    def _build_qr_col(self) -> QWidget:
        """Coluna direita: o QR, na mesma cor do resto da tela."""
        w = QWidget()
        w.setFixedWidth(230)
        col = QVBoxLayout(w)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)

        self._qr_caption = self._caption("OU ENTRE COM O APP STEAM")
        col.addWidget(self._qr_caption)
        col.addSpacing(t.SPACE_MD)

        # Sem moldura branca: o cartao claro era a unica mancha de cor da
        # tela. O contraste vem da inversao do proprio codigo.
        self._qr_panel = QrLoginPanel(compact=True, inverted=True)
        self._qr_panel.session_ready.connect(self._on_session)
        self._qr_panel.browser_requested.connect(self._on_browser)
        self._qr_panel.qr_drawn.connect(self._alinhar_legenda)
        col.addWidget(self._qr_panel)
        col.addStretch(1)
        return w

    def _alinhar_legenda(self, recuo: int) -> None:
        """Empurra a legenda pro mesmo x do primeiro modulo do QR.

        A quiet zone do codigo e' invisivel mas ocupa espaco, entao sem
        isto a legenda fica alguns pixels a esquerda do desenho.
        """
        self._qr_caption.setContentsMargins(recuo, 0, 0, 0)

    # ── ciclo ─────────────────────────────────────────────

    def showEvent(self, event) -> None:  # noqa: N802
        """Gera o QR ao exibir a tela -- sem clique intermediario.

        `start()` e' idempotente, entao reexibir nao dispara outra thread.
        """
        super().showEvent(event)
        self._qr_panel.start()

    def _on_browser(self) -> None:
        """Saida de emergencia: fluxo antigo via Chrome.

        Existe porque o passo `finalize` do QR e' o unico que nao consegui
        verificar sozinho (exige confirmacao no celular). Se ele falhar num
        formato que eu nao previ, o usuario nao pode ficar trancado fora da
        propria conta.
        """
        self._qr_panel.stop()
        dlg = build_steam_login_dialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._on_session(dlg.session)

    def _on_session(self, sess) -> None:
        if sess is None:
            return
        if not sess.is_complete():
            QMessageBox.warning(
                self, "Login incompleto",
                "Nao foi possivel capturar a sessao. Tente novamente."
            )
            return
        steam_session.persist(sess)
        self.session_connected.emit(sess)
