"""Dialog de login por QR: montagem da sessao, desenho e ciclo."""
from __future__ import annotations

import pytest

from skinvault import steam_qr_auth as qr
from skinvault.ui.qr_login_dialog import (
    QrCode,
    QrLoginDialog,
    QrLoginPanel,
    _sessao_de,
)


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


# ── _sessao_de: logica pura ────────────────────────────────────────


def test_sessao_com_cookie_direto():
    s = _sessao_de({
        "steamID": "76561198000000042",
        "transfer_info": [
            {"params": {"steamLoginSecure": "76561198000000042%7C%7CTOK"}},
        ],
    })
    assert s is not None
    assert s.steamid == "76561198000000042"
    assert s.is_complete()


def test_sessao_guarda_o_refresh_token():
    """Sem ele a sessao morre em ~24h e o app apaga na validacao.

    Bug real: a primeira versao descartava o token e o log registrava
    "Sessao invalida e sem refresh token -- sera necessario relogin".
    """
    s = _sessao_de(
        {"steamID": "765611",
         "transfer_info": [{"params": {"steamLoginSecure": "765611%7C%7CT"}}]},
        refresh_token="REFRESH",
    )
    assert s is not None
    assert s.cookies["steamRefresh_steam"] == "REFRESH"


def test_sessao_sem_refresh_token_ainda_e_criada():
    """Degrada, nao quebra: sessao curta e' melhor que nenhuma."""
    s = _sessao_de(
        {"steamID": "765611",
         "transfer_info": [{"params": {"steamLoginSecure": "765611%7C%7CT"}}]})
    assert s is not None
    assert "steamRefresh_steam" not in s.cookies


def test_sessao_monta_cookie_a_partir_de_auth():
    """Quando a Steam devolve so' nonce/auth, o cookie e' montado."""
    s = _sessao_de({
        "steamID": "76561198000000042",
        "transfer_info": [{"params": {"nonce": "N", "auth": "TOK"}}],
    })
    assert s is not None
    assert "76561198000000042" in s.cookies["steamLoginSecure"]
    assert "TOK" in s.cookies["steamLoginSecure"]
    assert s.is_complete()


def test_sessao_sem_steamid_nem_cookie():
    assert _sessao_de({}) is None
    assert _sessao_de({"transfer_info": []}) is None


def test_sessao_sem_token_e_none():
    assert _sessao_de({"steamID": "765611", "transfer_info": [{}]}) is None


def test_sessao_tolera_entrada_suja():
    assert _sessao_de({"steamID": "765611",
                       "transfer_info": [None, {"params": None}]}) is None


# ── QrCode: desenho ────────────────────────────────────────────────


def test_qrcode_aceita_matriz():
    w = QrCode()
    m = qr.qr_matrix("https://s.team/q/1/123")
    w.set_matrix(m)
    assert w._matriz == m


def test_qrcode_vazio_nao_quebra():
    w = QrCode()
    w.set_matrix([])
    w.set_matrix(None)
    assert w._matriz == []


def test_qrcode_invertido_usa_a_paleta_do_tema():
    """QR claro sobre escuro: a tela fica de uma cor so'.

    Risco conhecido e aceito: o padrao QR especifica escuro sobre claro.
    Se o app da Steam recusar, e' so' voltar `inverted` pra False.
    """
    normal = QrCode()
    invertido = QrCode(inverted=True)
    assert normal._inverted is False
    assert invertido._inverted is True


def test_qrcode_invertido_pinta_sem_erro():
    from PyQt6.QtGui import QPixmap
    w = QrCode(inverted=True)
    w.resize(200, 200)
    w.set_matrix(qr.qr_matrix("https://s.team/q/1/123"))
    pm = QPixmap(w.size())
    w.render(pm)
    assert not pm.isNull()


def test_painel_repassa_o_modo_invertido():
    p = QrLoginPanel(inverted=True)
    assert p._qr._inverted is True


def test_qrcode_pinta_sem_erro():
    from PyQt6.QtGui import QPixmap
    w = QrCode()
    w.resize(240, 240)
    w.set_matrix(qr.qr_matrix("https://s.team/q/1/123"))
    pm = QPixmap(w.size())
    w.render(pm)          # levanta se o paintEvent estourar
    assert not pm.isNull()


# ── ciclo do dialog ────────────────────────────────────────────────


def test_painel_comeca_sem_sessao():
    p = QrLoginPanel()
    assert p.session is None


def test_painel_desenha_qr_recebido():
    p = QrLoginPanel()
    p._desenhar("https://s.team/q/1/123")
    assert len(p._qr._matriz) >= 21


def test_painel_url_invalida_nao_derruba(monkeypatch):
    p = QrLoginPanel()
    monkeypatch.setattr("skinvault.steam_qr_auth.qr_matrix",
                        lambda u: (_ for _ in ()).throw(RuntimeError()))
    p._desenhar("qualquer")
    assert "codigo" in p._lbl.text().lower()


def test_painel_sucesso_emite_sessao():
    from skinvault.steam_session import SteamSession
    p = QrLoginPanel()
    sess = SteamSession(steamid="765611", cookies={"steamLoginSecure": "x"})
    vistos = []
    p.session_ready.connect(vistos.append)
    p._fim(qr.OK, sess)
    assert p.session is sess
    assert vistos == [sess]


def test_painel_expirado_avisa_e_emite_falha():
    p = QrLoginPanel()
    falhas = []
    p.failed.connect(falhas.append)
    p._fim(qr.EXPIRED, None)
    assert p.session is None
    assert "expirado" in p._lbl.text().lower()
    assert falhas == [qr.EXPIRED]


def test_painel_erro_de_rede_avisa():
    p = QrLoginPanel()
    p._fim(qr.ERROR, None)
    assert "conexao" in p._lbl.text().lower()


def test_stop_sinaliza_parada():
    p = QrLoginPanel()
    assert p._parar.is_set() is False
    p.stop()
    assert p._parar.is_set() is True, "worker continuaria pollando"


def test_start_e_explicito():
    """Construir o painel nao pode disparar requisicao sozinho."""
    p = QrLoginPanel()
    assert p._thread is None


def test_status_atualiza_o_rotulo():
    p = QrLoginPanel()
    p._status("Confirme no celular...")
    assert "celular" in p._lbl.text()


def test_botao_do_painel_pede_navegador():
    p = QrLoginPanel()
    pedidos = []
    p.browser_requested.connect(lambda: pedidos.append(1))
    p._btn_browser.click()
    assert pedidos == [1]


# ── dialog (wrapper, mantido pra uso fora da tela de login) ────────


def test_dialog_expoe_a_sessao_do_painel():
    from skinvault.steam_session import SteamSession
    d = QrLoginDialog()
    assert d.session is None
    sess = SteamSession(steamid="1", cookies={"steamLoginSecure": "x"})
    d.panel._fim(qr.OK, sess)
    assert d.session is sess
    assert d.result() == int(QrLoginDialog.DialogCode.Accepted)


def test_dialog_reject_para_o_painel():
    d = QrLoginDialog()
    d.reject()
    assert d.panel._parar.is_set() is True


def test_build_devolve_o_dialog():
    from skinvault.ui.qr_login_dialog import build_qr_login_dialog
    assert isinstance(build_qr_login_dialog(), QrLoginDialog)


# ── integracao com o LoginGate ─────────────────────────────────────
#
# O gate embute o PAINEL, nao abre dialog. O caminho feliz e o fallback
# de navegador estao cobertos em test_ui_smoke; aqui fica a ligacao dos
# sinais, que e' o que o refactor pode quebrar sem ninguem notar.


def test_gate_liga_os_sinais_do_painel(monkeypatch):
    from skinvault.steam_session import SteamSession
    from skinvault.ui.login_gate import LoginGate
    monkeypatch.setattr("skinvault.steam_session.persist", lambda s: None)
    g = LoginGate()
    vistos = []
    g.session_connected.connect(vistos.append)
    # Emitir pelo painel tem que chegar no gate, sem dialog nenhum.
    g._qr_panel.session_ready.emit(
        SteamSession(steamid="123", cookies={"steamLoginSecure": "t"}))
    assert vistos and vistos[0].steamid == "123"


def test_gate_liga_o_pedido_de_navegador(monkeypatch):
    from PyQt6.QtWidgets import QDialog
    from skinvault.ui.login_gate import LoginGate

    class M:
        def exec(self):
            return QDialog.DialogCode.Rejected
        session = None

    chamou = []
    monkeypatch.setattr(
        "skinvault.ui.login_gate.build_steam_login_dialog",
        lambda parent: chamou.append(1) or M())
    g = LoginGate()
    g._qr_panel.browser_requested.emit()
    assert chamou == [1]
