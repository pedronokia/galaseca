"""Login por QR -- sem navegador, sem senha, sem janela extra.

O usuario escaneia o codigo com o Steam Mobile e confirma no celular. O
app nunca ve senha nem abre janela externa, e some a dependencia de ter
Chromium instalado -- que era o que matava o login em maquina sem Chrome.

TRES PECAS
----------
QrCode        widget que so' desenha a matriz (pintura pura, sem I/O)
QrLoginPanel  QR + status + a thread de rede. E' o que o LoginGate embute
              direto na tela: fluxo de um passo so', sem modal.
QrLoginDialog wrapper do painel numa QDialog. Mantido pro caso de alguem
              precisar do login fora da tela de login.

Rede roda em thread com bridge (QObject + pyqtSignal), padrao do projeto:
tocar widget de fora da thread da UI trava ou derruba o Qt.
"""
from __future__ import annotations

import threading
import urllib.parse

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault import steam_qr_auth as qr
from skinvault import steam_session
from skinvault.ui import theme as t

_QUIET = 4  # margem obrigatoria do padrao QR, em modulos

# Cada sessao QR dura ~180s. Renovar automaticamente cobre ~15 minutos --
# tempo de sobra pra achar o celular, sem virar poll infinito se o usuario
# largou a tela aberta e foi embora.
_MAX_RENOVACOES = 5


class _QrBridge(QObject):
    """Thread de rede -> UI."""

    novo_qr = pyqtSignal(str)
    estado = pyqtSignal(str)
    concluido = pyqtSignal(str, object)   # status, SteamSession | None


class QrCode(QWidget):
    """Desenha a matriz do QR. Pintura pura, sem I/O.

    `inverted=True` pinta modulos CLAROS sobre fundo escuro, pra o codigo
    nao virar um retangulo branco no meio de uma UI escura.

    RISCO CONHECIDO: o padrao QR especifica escuro sobre claro. Leitores
    modernos costumam aceitar o invertido, mas nao e' garantido -- se o
    app da Steam recusar, basta voltar `inverted` pra False.
    """

    def __init__(self, parent: QWidget | None = None,
                 inverted: bool = False) -> None:
        super().__init__(parent)
        self._matriz: list = []
        self._inverted = inverted
        self.setMinimumSize(200, 200)

    def set_matrix(self, matriz: list) -> None:
        self._matriz = matriz or []
        self.update()

    def quiet_offset(self) -> int:
        """Px entre a borda do widget e o primeiro modulo desenhado.

        A quiet zone e' exigida pela especificacao e tem a cor do fundo,
        entao e' invisivel -- mas empurra o desenho pra dentro. Quem alinha
        rotulo ao lado do codigo precisa deste recuo, senao a legenda fica
        deslocada do QR por alguns pixels.
        """
        if not self._matriz:
            return 0
        lado = min(self.width(), self.height())
        passo = lado / (len(self._matriz) + _QUIET * 2)
        return int(_QUIET * passo)

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        lado = min(self.width(), self.height())
        fundo = t.BG_ELEVATED if self._inverted else "#FFFFFF"
        modulo = t.TEXT if self._inverted else "#000000"
        p.fillRect(0, 0, lado, lado, QColor(fundo))
        if not self._matriz:
            p.end()
            return
        n = len(self._matriz) + _QUIET * 2
        passo = lado / n
        p.setBrush(QColor(modulo))
        p.setPen(Qt.PenStyle.NoPen)
        for y, linha in enumerate(self._matriz):
            for x, ligado in enumerate(linha):
                if ligado:
                    p.drawRect(
                        int((x + _QUIET) * passo), int((y + _QUIET) * passo),
                        int(passo) + 1, int(passo) + 1)
        p.end()


class QrLoginPanel(QWidget):
    """QR + status + rede. Embutivel em qualquer tela.

    `start()` e' explicito: sem isso, so' construir o painel ja' dispararia
    requisicao -- ruim pra teste e pra quem monta a tela antes de exibir.
    """

    session_ready = pyqtSignal(object)     # SteamSession
    failed = pyqtSignal(str)               # status do steam_qr_auth
    browser_requested = pyqtSignal()
    # Recuo da quiet zone, pra quem quiser alinhar rotulo ao codigo. So'
    # se sabe depois de conhecer a matriz, por isso e' sinal e nao valor.
    qr_drawn = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None,
                 compact: bool = False, on_light: bool = False,
                 inverted: bool = False) -> None:
        """`on_light`: painel sobre cartao branco, entao o texto escurece.

        `inverted`: QR claro sobre fundo escuro, pra a tela ficar de uma cor
        so'. Ver o aviso de compatibilidade no QrCode.
        """
        super().__init__(parent)
        self.session: steam_session.SteamSession | None = None
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._bridge = _QrBridge()
        self._bridge.novo_qr.connect(self._desenhar)
        self._bridge.estado.connect(self._status)
        self._bridge.concluido.connect(self._fim)

        # Tudo alinhado a esquerda: a legenda acima da coluna tambem esta',
        # e centralizar so' o QR quebrava a linha vertical que a coluna da
        # esquerda respeita.
        alinha = Qt.AlignmentFlag.AlignLeft
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(t.SPACE_XS)

        self._qr = QrCode(inverted=inverted)
        if compact:
            self._qr.setFixedSize(180, 180)
        v.addWidget(self._qr, 0, alinha)

        # Status e link vao num sub-layout pra receberem o mesmo recuo da
        # quiet zone que o QR tem -- senao ficam encostados na borda do
        # painel enquanto o codigo comeca alguns pixels a direita.
        self._rodape = QVBoxLayout()
        self._rodape.setContentsMargins(0, 0, 0, 0)
        self._rodape.setSpacing(t.SPACE_XS)

        cor_texto = "#5A5A5A" if on_light else t.TEXT_MUTED
        cor_hover = "#1A1A1A" if on_light else t.TEXT
        self._lbl = QLabel("Gerando código...")
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet(
            f"color: {cor_texto}; font-size: {t.FS_MUTED};"
            " background: transparent;")
        self._rodape.addWidget(self._lbl, 0, alinha)

        # Link, nao botao: e' acao terciaria. Botao com borda competia com
        # o QR, que e' a acao principal da tela.
        self._btn_browser = QPushButton("Prefiro logar pelo navegador")
        self._btn_browser.setToolTip(
            "Fluxo antigo: abre o Chrome pra voce logar na Steam.")
        self._btn_browser.setFlat(True)
        self._btn_browser.setStyleSheet(
            f"QPushButton {{ color: {cor_texto}; background: transparent;"
            f" border: none; padding: 0px; text-align: left;"
            f" font-size: {t.FS_MUTED}; text-decoration: underline; }}"
            f" QPushButton:hover {{ color: {cor_hover}; }}")
        self._btn_browser.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_browser.clicked.connect(self.browser_requested.emit)
        self._rodape.addWidget(self._btn_browser, 0, alinha)
        v.addLayout(self._rodape)

    # ── controle ───────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is None:
            self._parar.clear()
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._parar.set()

    # ── UI (thread da UI) ──────────────────────────────────────────

    def _desenhar(self, url: str) -> None:
        try:
            self._qr.set_matrix(qr.qr_matrix(url))
        except Exception:
            self._lbl.setText("Nao foi possivel gerar o codigo.")
            return
        recuo = self._qr.quiet_offset()
        self._rodape.setContentsMargins(recuo, 0, 0, 0)
        self.qr_drawn.emit(recuo)

    def _status(self, texto: str) -> None:
        self._lbl.setText(texto)

    def _fim(self, status: str, sess) -> None:
        if status == qr.OK and sess is not None:
            self.session = sess
            self.session_ready.emit(sess)
            return
        self._lbl.setText({
            qr.EXPIRED: "Codigo expirado. Reabra para gerar outro.",
            qr.ERROR: "Falha de conexao com a Steam.",
        }.get(status, "Nao foi possivel concluir o login."))
        self.failed.emit(status)

    # ── rede (thread separada) ─────────────────────────────────────

    def _worker(self) -> None:
        def poll(cid, rid):
            if self._parar.is_set():
                return qr.EXPIRED, {}
            st, d = qr.poll_once(cid, rid)
            if st == qr.PENDING and d.get("had_remote_interaction"):
                self._bridge.estado.emit("Lido. Confirme no celular...")
            return st, d

        # Codigo expirado gera outro sozinho, como o login web da Steam.
        # Antes o painel parava e pedia "reabra pra gerar" -- so' que
        # demorar pra pegar o celular e' o caso NORMAL, nao um erro.
        dados = None
        for tentativa in range(_MAX_RENOVACOES):
            if self._parar.is_set():
                self._bridge.concluido.emit(qr.EXPIRED, None)
                return
            status, sessao = qr.begin_session("SkinVault")
            if status != qr.OK:
                self._bridge.concluido.emit(qr.ERROR, None)
                return
            self._bridge.novo_qr.emit(sessao["challenge_url"])
            self._bridge.estado.emit("Aguardando leitura...")

            st, dados = qr.wait_for_confirmation(
                sessao, poll=poll, on_new_qr=self._bridge.novo_qr.emit)
            if st == qr.OK:
                break
            if st != qr.EXPIRED or self._parar.is_set():
                self._bridge.concluido.emit(st, None)
                return
            self._bridge.estado.emit("Gerando novo código...")
        else:
            self._bridge.concluido.emit(qr.EXPIRED, None)
            return

        self._bridge.estado.emit("Confirmado. Obtendo sessao...")
        token = dados.get("refresh_token", "")
        st, fin = qr.finalize(token)
        if st != qr.OK:
            self._bridge.concluido.emit(qr.ERROR, None)
            return
        # O token vai JUNTO pra sessao: sem ele a sessao morre em ~24h.
        sess = _sessao_de(fin, refresh_token=token)
        self._bridge.concluido.emit(
            qr.OK if (sess and sess.is_complete()) else qr.ERROR, sess)


class QrLoginDialog(QDialog):
    """Wrapper do painel numa janela. Expõe `.session` como o antigo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.usar_navegador = False
        self.setWindowTitle("Conectar conta Steam")
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")

        v = QVBoxLayout(self)
        v.setContentsMargins(t.SPACE_XL, t.SPACE_XL, t.SPACE_XL, t.SPACE_LG)
        v.setSpacing(t.SPACE_MD)

        titulo = QLabel("Escaneie com o app Steam")
        titulo.setStyleSheet(
            f"color: {t.TEXT}; font-size: {t.FS_TITLE_SM}; font-weight: 600;")
        v.addWidget(titulo)

        self.panel = QrLoginPanel()
        self.panel.session_ready.connect(lambda _s: self.accept())
        self.panel.browser_requested.connect(self._pedir_navegador)
        v.addWidget(self.panel)

        linha = QHBoxLayout()
        linha.addStretch(1)
        self._btn = QPushButton("Cancelar")
        self._btn.setStyleSheet(t.btn_ghost())
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.clicked.connect(self.reject)
        linha.addWidget(self._btn)
        v.addLayout(linha)

    @property
    def session(self):
        return self.panel.session

    def _pedir_navegador(self) -> None:
        self.usar_navegador = True
        self.reject()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.panel.start()

    def reject(self) -> None:
        self.panel.stop()
        super().reject()


def _sessao_de(fin: dict,
               refresh_token: str = "") -> "steam_session.SteamSession | None":
    """Monta a SteamSession a partir do retorno do finalizelogin.

    Logica pura (sem Qt, sem rede) pra ser testavel: o transfer_info traz
    um destino por dominio, e o que interessa e' o steamLoginSecure --
    exatamente o cookie que o fluxo do Chrome extraia por CDP.

    `refresh_token` NAO e' opcional na pratica. O fluxo do Chrome captura o
    steamRefresh_steam de proposito porque sem ele a sessao morre em ~24h e
    o usuario precisa relogar toda hora. A primeira versao disto descartava
    o token, e a sessao era apagada na validacao seguinte com
    "sem refresh token -- sera necessario relogin".
    """
    cookies: dict = {}
    if refresh_token:
        cookies["steamRefresh_steam"] = refresh_token
    for alvo in fin.get("transfer_info") or []:
        params = (alvo or {}).get("params") or {}
        valor = params.get("steamLoginSecure")
        if valor:
            cookies["steamLoginSecure"] = valor
    steamid = str(fin.get("steamID") or "")
    if not cookies.get("steamLoginSecure") and steamid:
        # A Steam pode devolver o token so' no par nonce/auth; nesse caso o
        # cookie e' montado no formato "<steamid>||<token>".
        for alvo in fin.get("transfer_info") or []:
            token = ((alvo or {}).get("params") or {}).get("auth")
            if token:
                cookies["steamLoginSecure"] = urllib.parse.quote(
                    f"{steamid}||{token}", safe="")
                break
    if not steamid:
        steamid = steam_session.extract_steamid_from_cookie(cookies) or ""
    if not steamid or not cookies.get("steamLoginSecure"):
        return None
    return steam_session.SteamSession(steamid=steamid, cookies=cookies)


def build_qr_login_dialog(parent: QWidget | None = None) -> QrLoginDialog:
    """Mesma assinatura de build_steam_login_dialog."""
    return QrLoginDialog(parent)
