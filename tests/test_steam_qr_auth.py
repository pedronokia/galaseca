"""Login por QR (device auth). Respostas mockadas no unico ponto de rede."""
from __future__ import annotations

import json

from skinvault import steam_qr_auth as qr


def _resp(payload):
    return 200, json.dumps({"response": payload})


# ── begin_session ──────────────────────────────────────────────────


def test_begin_le_a_resposta_real(monkeypatch):
    """Payload real capturado da Steam em 28/07/2026."""
    monkeypatch.setattr(qr, "_http_post", lambda u, c, **k: _resp({
        "client_id": "15514185061263304759",
        "challenge_url": "https://s.team/q/1/15514185061263304759",
        "request_id": "JnFE/xJxHTqMviDLtDQdbA==",
        "interval": 5,
    }))
    status, s = qr.begin_session()
    assert status == qr.OK
    assert s["challenge_url"].startswith("https://s.team/q/")
    assert s["interval"] == 5.0


def test_begin_manda_platform_type_de_client(monkeypatch):
    """Com platform_type de navegador a Steam recusa o QR."""
    vistos = {}

    def fake(url, campos, **k):
        vistos.update(campos)
        return _resp({"client_id": "1", "challenge_url": "u"})

    monkeypatch.setattr(qr, "_http_post", fake)
    qr.begin_session(device_name="Teste")
    assert vistos["platform_type"] == "2"
    assert vistos["device_friendly_name"] == "Teste"


def test_begin_erros(monkeypatch):
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: (500, None))
    assert qr.begin_session()[0] == qr.ERROR
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: (200, "nao json"))
    assert qr.begin_session()[0] == qr.ERROR
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: _resp({}))
    assert qr.begin_session()[0] == qr.ERROR


def test_begin_intervalo_invalido_vira_default(monkeypatch):
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: _resp({
        "client_id": "1", "challenge_url": "u", "interval": "abc"}))
    assert qr.begin_session()[1]["interval"] == 5.0


# ── poll_once ──────────────────────────────────────────────────────


def test_poll_pendente(monkeypatch):
    """Resposta real enquanto ninguem escaneou."""
    monkeypatch.setattr(qr, "_http_post",
                        lambda *a, **k: _resp({"had_remote_interaction": False}))
    status, d = qr.poll_once("1", "2")
    assert status == qr.PENDING
    assert d["had_remote_interaction"] is False


def test_poll_confirmado(monkeypatch):
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: _resp({
        "refresh_token": "TOKEN", "access_token": "ACC",
        "account_name": "nokia"}))
    status, d = qr.poll_once("1", "2")
    assert status == qr.OK
    assert d["refresh_token"] == "TOKEN"
    assert d["account_name"] == "nokia"


def test_poll_qr_rotacionado(monkeypatch):
    """A Steam troca o codigo; a UI precisa saber pra redesenhar."""
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: _resp({
        "new_challenge_url": "https://s.team/q/1/999",
        "new_client_id": "999"}))
    status, d = qr.poll_once("1", "2")
    assert status == qr.PENDING
    assert d["challenge_url"].endswith("999")
    assert d["client_id"] == "999"


def test_poll_400_e_expirado_nao_erro(monkeypatch):
    """400 = client_id morto. Tratar como erro faria a UI oferecer retry."""
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: (400, None))
    assert qr.poll_once("1", "2")[0] == qr.EXPIRED


def test_poll_outros_erros(monkeypatch):
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: (0, None))
    assert qr.poll_once("1", "2")[0] == qr.ERROR
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: (200, "{"))
    assert qr.poll_once("1", "2")[0] == qr.ERROR


# ── wait_for_confirmation ──────────────────────────────────────────


def _relogio():
    """Relogio falso: cada leitura avanca 1s."""
    t = [0.0]

    def agora():
        t[0] += 1.0
        return t[0]
    return agora


def test_wait_retorna_ao_confirmar():
    respostas = [(qr.PENDING, {}), (qr.PENDING, {}),
                 (qr.OK, {"refresh_token": "T"})]
    status, d = qr.wait_for_confirmation(
        {"client_id": "1", "request_id": "2", "interval": 5},
        poll=lambda c, r: respostas.pop(0),
        sleep=lambda s: None, now=_relogio())
    assert status == qr.OK
    assert d["refresh_token"] == "T"


def test_wait_avisa_quando_o_qr_muda():
    novos = []
    respostas = [
        (qr.PENDING, {"challenge_url": "https://s.team/q/1/999",
                      "client_id": "999"}),
        (qr.OK, {"refresh_token": "T"}),
    ]
    qr.wait_for_confirmation(
        {"client_id": "1", "request_id": "2", "interval": 1},
        poll=lambda c, r: respostas.pop(0),
        sleep=lambda s: None, now=_relogio(),
        on_new_qr=novos.append)
    assert novos == ["https://s.team/q/1/999"]


def test_wait_usa_o_client_id_novo_apos_rotacao():
    usados = []

    def poll(c, r):
        usados.append(c)
        if len(usados) == 1:
            return qr.PENDING, {"challenge_url": "u2", "client_id": "999"}
        return qr.OK, {"refresh_token": "T"}

    qr.wait_for_confirmation(
        {"client_id": "1", "request_id": "2", "interval": 1},
        poll=poll, sleep=lambda s: None, now=_relogio())
    assert usados == ["1", "999"], "continuou pollando o codigo morto"


def test_wait_desiste_no_limite():
    status, _ = qr.wait_for_confirmation(
        {"client_id": "1", "request_id": "2", "interval": 1},
        poll=lambda c, r: (qr.PENDING, {}),
        sleep=lambda s: None, now=_relogio(), max_wait=5)
    assert status == qr.EXPIRED


def test_wait_propaga_expirado_na_hora():
    status, _ = qr.wait_for_confirmation(
        {"client_id": "1", "request_id": "2", "interval": 1},
        poll=lambda c, r: (qr.EXPIRED, {}),
        sleep=lambda s: None, now=_relogio())
    assert status == qr.EXPIRED


# ── finalize ───────────────────────────────────────────────────────


def test_finalize_devolve_transfer_info(monkeypatch):
    monkeypatch.setattr(qr, "_http_post", lambda *a, **k: (200, json.dumps({
        "steamID": "76561198000000042",
        "transfer_info": [{"url": "https://steamcommunity.com/login/settoken",
                           "params": {"nonce": "n", "auth": "a"}}],
    })))
    status, d = qr.finalize("TOKEN")
    assert status == qr.OK
    assert d["steamID"].startswith("765611")
    assert len(d["transfer_info"]) == 1


def test_finalize_sem_token(monkeypatch):
    monkeypatch.setattr(qr, "_http_post",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("nao devia chamar a rede")))
    assert qr.finalize("")[0] == qr.ERROR


def test_finalize_sem_transfer_info(monkeypatch):
    monkeypatch.setattr(qr, "_http_post",
                        lambda *a, **k: (200, json.dumps({"steamID": "1"})))
    assert qr.finalize("TOKEN")[0] == qr.ERROR


# ── QR ─────────────────────────────────────────────────────────────


def test_matriz_do_qr():
    m = qr.qr_matrix("https://s.team/q/1/11608128350182512574")
    assert len(m) == len(m[0]), "QR e' quadrado"
    assert len(m) >= 21
    # Padrao localizador: canto superior esquerdo comeca com 7 modulos.
    assert all(m[0][i] for i in range(7))
    assert all(m[i][0] for i in range(7))


def test_matriz_muda_com_a_url():
    a = qr.qr_matrix("https://s.team/q/1/111")
    b = qr.qr_matrix("https://s.team/q/1/222")
    assert a != b
