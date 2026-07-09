"""Dialog de login Steam automatico via Chrome DevTools Protocol (WS).

Abre uma janela Chrome para o usuario logar na Steam.
Apos o login, extrai cookies via CDP sobre WebSocket
(incluindo HTTP-only) e cria a sessao automaticamente.

Sem dependencia de selenium nem QtWebEngine.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from skinvault.steam_session import (
    SteamSession,
    extract_steamid_from_cookie,
    merge_cookies,
)
from skinvault.ui import theme as t

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://steamcommunity.com/login/home/?goto=my"
_SUCCESS_FRAGMENTS = ("/profiles/", "/id/")


def _collect_steam_cookies(cdp_cookies: list) -> dict:
    """Filtra os cookies relevantes da resposta do CDP Network.getAllCookies.

    Pega cookies de steamcommunity.com (sessao web) E o steamRefresh_steam
    do dominio steampowered.com (refresh token de longa duracao, usado pra
    renovar a sessao sem novo login). Sem este ultimo, a sessao morre em
    ~24h e o usuario precisa relogar toda hora.

    O filtro do refresh token aceita qualquer subdominio *.steampowered.com
    (login./store./host-only) — dependendo de onde o redirect de login
    assenta, o Chrome pode armazenar o cookie sob dominios diferentes; um
    match estrito em 'login.steampowered.com' deixaria o token escapar e o
    auto-refresh nunca ativaria.
    """
    cookies: dict = {}
    for c in cdp_cookies:
        domain = c.get("domain", "")
        name = c.get("name", "")
        if "steamcommunity.com" in domain:
            cookies[name] = c.get("value", "")
        elif name == "steamRefresh_steam" and "steampowered.com" in domain:
            cookies[name] = c.get("value", "")
    return cookies


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return int(s.getsockname()[1])


def _find_chrome() -> str | None:
    """Procura o executavel do Chrome no PATH e locais comuns."""
    candidates = ["chrome", "google-chrome", "chromium", "chromium-browser"]
    for name in candidates:
        try:
            subprocess.run(
                [name, "--version"],
                capture_output=True, timeout=5, check=True,
            )
            return name
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass
    paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\Chromium\Application\chrome.exe"),
    ]
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


class SteamLoginDialog(QDialog):
    """Dialog que abre Chrome automaticamente para login Steam.

    Chrome e' lancado com um perfil temporario e porta de debugging.
    Acompanha navegacao via CDP (WebSocket). Quando detecta redirect para
    profiles/id, extrai cookies via CDP e finaliza.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Conectar conta Steam")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {t.BG_ELEVATED}; }}")
        self.session: Optional[SteamSession] = None
        self._chrome_proc: Optional[subprocess.Popen] = None
        self._ws: Optional["websocket.WebSocket"] = None  # noqa: F821
        self._user_data_dir: Optional[str] = None
        self._monitor_active = False
        self._manual_btn: Optional[QPushButton] = None
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 18, 20, 18)

        title = QLabel("Conectar conta Steam")
        title.setStyleSheet(
            f"color: {t.TEXT}; font-size: 14pt; font-weight: 700;"
            f" font-family: {t.FONT_FAMILY};"
        )
        layout.addWidget(title)

        self._status = QLabel(
            "Abrindo Chrome para login na Steam...\n"
            "Faça login normalmente (incluindo 2FA se tiver).\n"
            "A janela fechará automaticamente após o login."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: {t.FS_BODY};"
            f" font-family: {t.FONT_FAMILY};"
        )
        layout.addWidget(self._status, 1)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(t.btn_ghost())
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self._cancel_btn)
        layout.addLayout(btn_row)

    def reject(self) -> None:
        self._cleanup()
        super().reject()

    def _on_cancel(self) -> None:
        self.reject()

    def _cleanup(self) -> None:
        self._monitor_active = False
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception as exc:
                logger.warning("Falha ao fechar WebSocket: %s", exc)
            self._ws = None
        if self._chrome_proc is not None:
            try:
                self._chrome_proc.terminate()
                self._chrome_proc.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_proc.kill()
                except Exception:
                    pass
            self._chrome_proc = None
        if self._user_data_dir is not None and os.path.isdir(self._user_data_dir):
            try:
                import shutil
                shutil.rmtree(self._user_data_dir, ignore_errors=True)
            except Exception:
                pass
            self._user_data_dir = None

    def _send_cdp(self, method: str, params: dict | None = None) -> int:
        """Envia comando CDP e retorna o message id."""
        if self._ws is None:
            return -1
        mid = int(time.time() * 1000) & 0xFFFFFF
        msg = {"id": mid, "method": method}
        if params:
            msg["params"] = params
        self._ws.send(json.dumps(msg))
        return mid

    def _recv_cdp(self, timeout: float = 30) -> Optional[dict]:
        """Le uma mensagem CDP do WebSocket."""
        if self._ws is None:
            return None
        try:
            self._ws.settimeout(timeout)
            raw = self._ws.recv()
            return json.loads(raw)
        except Exception:
            return None

    def _wait_for_cdp_result(self, expected_id: int, timeout: float = 30) -> Optional[dict]:
        """Le mensagens ate encontrar a resposta com o id esperado."""
        deadline = time.time() + timeout
        while self._monitor_active and time.time() < deadline:
            msg = self._recv_cdp(1.0)
            if msg is None:
                continue
            if msg.get("id") == expected_id:
                return msg.get("result")
        return None

    def _monitor_ws(self) -> None:
        """Thread principal: poll URL via HTTP /json, depois extrai cookies via WS.

        Em vez de manter WebSocket aberto ouvindo eventos, faz polling simples
        do endpoint HTTP /json que ja expoe a URL atual de cada pagina.
        Quando detecta /profiles/ ou /id/, conecta via WebSocket SO' pra
        chamar Network.getAllCookies.
        """
        port = _find_free_port()
        chrome_exe = _find_chrome()
        if chrome_exe is None:
            logger.error("Chrome nao encontrado no sistema")
            QTimer.singleShot(0, self._show_manual_option)
            return

        self._user_data_dir = tempfile.mkdtemp(prefix="sv_")

        try:
            self._chrome_proc = subprocess.Popen(
                [
                    chrome_exe,
                    f"--remote-debugging-port={port}",
                    "--remote-allow-origins=*",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--no-first-run",
                    "--disable-default-apps",
                    f"--user-data-dir={self._user_data_dir}",
                    "--window-size=1024,768",
                    _LOGIN_URL,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.exception("Falha ao lancar Chrome: %s", exc)
            QTimer.singleShot(0, lambda e=exc: self._on_chrome_launch_failed(e))
            return

        logger.info("Chrome lancado (PID=%d), aguardando DevTools na porta %d",
                     self._chrome_proc.pid, port)

        # Poll HTTP /json ate detectar login na URL
        deadline = time.time() + 300  # 5 min
        ws_url: Optional[str] = None

        while self._monitor_active and time.time() < deadline:
            try:
                resp = urllib.request.urlopen(
                    f"http://localhost:{port}/json", timeout=3
                )
                pages = json.loads(resp.read().decode("utf-8"))
                for page in pages:
                    if page.get("type") != "page":
                        continue
                    url = page.get("url", "")
                    if any(f in url for f in _SUCCESS_FRAGMENTS):
                        logger.info("Login detectado via /json: %s", url[:100])
                        ws_url = page.get("webSocketDebuggerUrl") or ""
                        if ws_url and not ws_url.startswith("ws://"):
                            ws_url = ""
                        break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(1.0)

        if not ws_url:
            if self._monitor_active:
                logger.info("Timeout de login, oferecendo modo manual")
                QTimer.singleShot(0, self._show_manual_option)
            return

        # Conecta WebSocket so' pra extrair cookies
        import websocket

        try:
            self._ws = websocket.create_connection(ws_url, timeout=10)
        except Exception as exc:
            logger.exception("Falha ao conectar WS para cookies: %s", exc)
            QTimer.singleShot(0, self._show_manual_option)
            return

        logger.info("WS conectado, requisitando cookies...")
        self._send_cdp("Network.enable")
        time.sleep(0.5)  # aguarda Network domain ficar pronto
        mid = self._send_cdp("Network.getAllCookies")
        result = self._wait_for_cdp_result(mid, timeout=15)

        if not result:
            logger.error("getAllCookies nao retornou resultado")
            QTimer.singleShot(0, self._on_login_error)
            return

        cookies = _collect_steam_cookies(result.get("cookies", []))

        logger.info("Extraidos %d cookies Steam via CDP (total=%d)",
                     len(cookies), len(result.get("cookies", [])))

        # Se veio vazio, tenta uma segunda vez
        if not cookies:
            logger.info("Cookies vazio, tentando novamente...")
            time.sleep(1.0)
            mid = self._send_cdp("Network.getAllCookies")
            result = self._wait_for_cdp_result(mid, timeout=15)
            if result:
                cookies = _collect_steam_cookies(result.get("cookies", []))
                logger.info("Tentativa 2: %d cookies Steam via CDP", len(cookies))

        steamid = extract_steamid_from_cookie(cookies) or ""
        logger.info(
            "Cookies capturados: steamid=%s, has_secure=%s, has_refresh_token=%s",
            bool(steamid), bool(cookies.get("steamLoginSecure")),
            bool(cookies.get("steamRefresh_steam")),
        )
        if not steamid or not cookies.get("steamLoginSecure"):
            logger.warning(
                "Cookies insuficientes: steamid=%s, has_secure=%s",
                bool(steamid), bool(cookies.get("steamLoginSecure")),
            )
            QTimer.singleShot(0, self._show_manual_option)
            return

        merged = merge_cookies({}, cookies)
        self.session = SteamSession(
            steamid=steamid,
            cookies=merged,
            captured_at=time.time(),
        )
        logger.info("Sessao Steam capturada: steamid=%s", steamid)
        QTimer.singleShot(0, self._on_login_success)

    def _on_chrome_launch_failed(self, exc: Exception) -> None:
        self._status.setText(f"Erro ao abrir Chrome: {exc}")
        self._show_manual_option()

    def _on_login_error(self) -> None:
        """Main-thread: feedback de erro no login, oferece manual."""
        self._status.setText("Erro ao capturar cookies. Tente o modo manual abaixo.")
        self._cleanup()
        self._show_manual_option()

    def _on_login_success(self) -> None:
        """Main-thread: fecha tudo e aceita o dialog."""
        self._cleanup()
        self.accept()

    def _launch_chrome(self) -> None:
        """Lanca Chrome em thread separada com CDP via WebSocket."""
        logger.info("Lancando Chrome para login Steam (CDP raw)...")
        self._monitor_active = True
        t = threading.Thread(target=self._monitor_ws, daemon=True)
        t.start()

    def _show_manual_option(self) -> None:
        """Troca para modo manual: text area para colar cookies."""
        self._cleanup()
        self._manual_btn = QPushButton("Colar cookies manualmente")
        self._manual_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manual_btn.setStyleSheet(t.btn_secondary())
        self._manual_btn.clicked.connect(self._switch_to_manual)
        self.layout().insertWidget(2, self._manual_btn)

    def _switch_to_manual(self) -> None:
        """Substitui o conteudo por um text area para colar cookies."""
        self._cleanup()
        if self._manual_btn is not None:
            self._manual_btn.hide()
            self._manual_btn.deleteLater()
            self._manual_btn = None

        self._status.setText(
            "Faça login na Steam pelo seu navegador normalmente.\n"
            "Depois cole aqui os cookies copiados (F12 > Application > Cookies\n"
            "> steamcommunity.com > selecione tudo > Copy como JSON)."
        )

        self._cookie_input = QPlainTextEdit()
        self._cookie_input.setPlaceholderText(
            '[{"domain":"steamcommunity.com","name":"steamLoginSecure",...}]'
        )
        self._cookie_input.setStyleSheet(
            f"background: {t.SURFACE}; color: {t.TEXT};"
            f" border: 1px solid {t.BORDER}; border-radius: 6px;"
            f" padding: 10px; font-size: 9pt;"
            " font-family: 'Consolas', monospace;"
        )
        self._cookie_input.setMinimumHeight(160)
        self.layout().insertWidget(2, self._cookie_input)

        self._confirm_btn = QPushButton("Validar cookies")
        self._confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._confirm_btn.setStyleSheet(t.btn_primary())
        self._confirm_btn.clicked.connect(self._process_manual_cookies)
        self.layout().insertWidget(3, self._confirm_btn)

    def _process_manual_cookies(self) -> None:
        """Processa cookies colados manualmente."""
        raw = self._cookie_input.toPlainText().strip()
        if not raw:
            self._status.setText("Cole os cookies primeiro.")
            return
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._status.setText(f"JSON invalido: {exc}")
            return
        if isinstance(parsed, list):
            cookies: dict = _collect_steam_cookies(parsed)
        elif isinstance(parsed, dict):
            cookies = dict(parsed)
        else:
            self._status.setText("Formato nao reconhecido. Use array de cookies ou dict.")
            return
        steamid = extract_steamid_from_cookie(cookies) or ""
        if not steamid or not cookies.get("steamLoginSecure"):
            self._status.setText(
                "Cookie steamLoginSecure nao encontrado. "
                "Certifique-se de copiar cookies de steamcommunity.com."
            )
            return
        merged = merge_cookies({}, cookies)
        self.session = SteamSession(
            steamid=steamid,
            cookies=merged,
            captured_at=time.time(),
        )
        logger.info("Sessao Steam via cookies manuais: steamid=%s", steamid)
        self._cleanup()
        self.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(100, self._launch_chrome)

def build_steam_login_dialog(
    parent: QWidget | None = None,
) -> SteamLoginDialog:
    """Cria o dialog de login Steam (automatico via Chrome)."""
    return SteamLoginDialog(parent)
