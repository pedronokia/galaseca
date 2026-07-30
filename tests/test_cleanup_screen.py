"""Smoke tests da CleanupScreen.

`skinvault.cleanup` NUNCA e' exercitado de verdade aqui: todo teste mocka
`scan_all` / `clean` no modulo. A tela e' um disparador de remocao de
arquivo -- rodar a coisa real numa suite significaria apagar o %TEMP% da
maquina de quem rodou `pytest`.

Os workers vao pra `_InlineThread` (roda no proprio processo) pra o sinal
chegar antes do assert, sem sleep.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

import pytest

from skinvault import cleanup as cleanup_mod


@pytest.fixture(autouse=True)
def _qapp():
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
    for w in list(app.topLevelWidgets()):
        w.deleteLater()
    app.processEvents()
    app.quit()


class _InlineThread:
    """Thread falsa: executa no ato, no processo do teste."""

    def __init__(self, target=None, daemon=None, **kw):
        self._target = target

    def start(self):
        if self._target is not None:
            self._target()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """settings em tmp_path + threads inline + limpeza real bloqueada."""
    monkeypatch.setattr("threading.Thread", _InlineThread)

    store = {}

    monkeypatch.setattr("skinvault.ui.cleanup_screen.load_settings",
                        lambda: dict(store))
    monkeypatch.setattr("skinvault.ui.cleanup_screen.save_settings",
                        lambda s: store.update(s))

    def _boom(*a, **kw):  # pragma: no cover - so' dispara se o mock furar
        raise AssertionError("a limpeza REAL foi chamada num teste")

    monkeypatch.setattr(cleanup_mod, "clean", _boom)
    monkeypatch.setattr(cleanup_mod, "clean_target", _boom)
    return store


def _scan(**por_alvo):
    """Monta o dict de ScanResult que o worker devolveria.

    Cada alvo aceita (files, bytes) ou (files, bytes, available).
    """
    out = {}
    for key in cleanup_mod.TARGET_KEYS:
        spec = por_alvo.get(key, (0, 0))
        files, size = spec[0], spec[1]
        avail = spec[2] if len(spec) > 2 else True
        out[key] = cleanup_mod.ScanResult(key, files, size, avail)
    return out


def _make(monkeypatch, scan=None):
    from skinvault.ui.cleanup_screen import CleanupScreen
    monkeypatch.setattr(cleanup_mod, "scan_all",
                        lambda keys=None: scan if scan is not None else _scan())
    return CleanupScreen()


# ── construcao ───────────────────────────────────────────────
def test_tela_tem_uma_linha_por_alvo(monkeypatch):
    scr = _make(monkeypatch)
    assert set(scr._rows) == set(cleanup_mod.TARGET_KEYS)
    for key, row in scr._rows.items():
        assert row.target.title in row._title.text()


def test_botao_comeca_desabilitado_sem_selecao(monkeypatch):
    scr = _make(monkeypatch)
    assert scr.selected_keys() == []
    assert scr._clean_btn.isEnabled() is False


def test_linha_perigosa_usa_cor_de_danger(monkeypatch):
    from skinvault.ui import theme as t
    scr = _make(monkeypatch)
    row = scr._rows[cleanup_mod.RECYCLE_BIN]
    assert t.DANGER in row._title.styleSheet()


# ── selecao / persistencia ───────────────────────────────────
def test_marcar_habilita_o_botao(monkeypatch):
    scr = _make(monkeypatch)
    scr._rows[cleanup_mod.TEMP_FILES].set_checked(True)
    assert scr.selected_keys() == [cleanup_mod.TEMP_FILES]
    assert scr._clean_btn.isEnabled() is True


def test_selecao_persiste_em_settings(monkeypatch, _isolate):
    scr = _make(monkeypatch)
    scr._rows[cleanup_mod.TEMP_FILES].set_checked(True)
    assert _isolate["cleanup_selected"] == [cleanup_mod.TEMP_FILES]


def test_lixeira_nunca_persiste_marcada(monkeypatch, _isolate):
    """Alvo destrutivo marcado de uma sessao pra outra transforma clique
    distraido em perda permanente."""
    scr = _make(monkeypatch)
    scr._rows[cleanup_mod.RECYCLE_BIN].set_checked(True)
    assert _isolate["cleanup_selected"] == []


def test_selecao_salva_volta_no_load(monkeypatch, _isolate):
    _isolate["cleanup_selected"] = [cleanup_mod.PREFETCH,
                                    cleanup_mod.RECYCLE_BIN]
    scr = _make(monkeypatch)
    # prefetch volta; a lixeira e' filtrada mesmo estando no arquivo
    assert scr.selected_keys() == [cleanup_mod.PREFETCH]


def test_selecao_corrompida_em_settings_nao_derruba(monkeypatch, _isolate):
    _isolate["cleanup_selected"] = "nao e' lista"
    scr = _make(monkeypatch)
    assert scr.selected_keys() == []


# ── medicao ──────────────────────────────────────────────────
def test_refresh_preenche_tamanhos(monkeypatch):
    scr = _make(monkeypatch, scan=_scan(temp_files=(3, 2048, True)))
    scr.refresh()
    txt = scr._rows[cleanup_mod.TEMP_FILES]._size.text()
    assert "2,0 KB" in txt
    assert "3 itens" in txt


def test_alvo_indisponivel_desliga_a_linha(monkeypatch):
    scr = _make(monkeypatch, scan=_scan(prefetch=(0, 0, False)))
    scr.refresh()
    row = scr._rows[cleanup_mod.PREFETCH]
    assert row._size.text() == "n/d"
    assert row._toggle.isEnabled() is False
    assert row.is_checked() is False


def test_total_selecionado_soma_so_o_marcado(monkeypatch):
    scr = _make(monkeypatch, scan=_scan(temp_files=(1, 1024),
                                        prefetch=(1, 3072)))
    scr.refresh()
    scr._rows[cleanup_mod.TEMP_FILES].set_checked(True)
    assert "1,0 KB" in scr._total_lbl.text()
    scr._rows[cleanup_mod.PREFETCH].set_checked(True)
    assert "4,0 KB" in scr._total_lbl.text()


def test_scan_falho_nao_derruba_a_tela(monkeypatch):
    from skinvault.ui.cleanup_screen import CleanupScreen
    monkeypatch.setattr(cleanup_mod, "scan_all",
                        lambda keys=None: (_ for _ in ()).throw(OSError("x")))
    scr = CleanupScreen()
    scr.refresh()
    assert scr._rows[cleanup_mod.TEMP_FILES]._size.text() == "—"
    assert scr._rescan_btn.isEnabled() is True


# ── confirmacao ──────────────────────────────────────────────
def test_clique_sem_confirmar_nao_limpa(monkeypatch):
    scr = _make(monkeypatch)
    scr._rows[cleanup_mod.TEMP_FILES].set_checked(True)
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.No)
    chamado = []
    monkeypatch.setattr(scr._clean_worker, "start",
                        lambda keys: chamado.append(keys))
    scr._on_clean_clicked()
    assert chamado == []


def test_confirmar_dispara_worker_com_os_marcados(monkeypatch):
    scr = _make(monkeypatch)
    scr._rows[cleanup_mod.TEMP_FILES].set_checked(True)
    scr._rows[cleanup_mod.THUMBNAILS].set_checked(True)
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.Yes)
    chamado = []
    monkeypatch.setattr(scr._clean_worker, "start",
                        lambda keys: chamado.append(list(keys)))
    scr._on_clean_clicked()
    assert chamado == [[cleanup_mod.TEMP_FILES, cleanup_mod.THUMBNAILS]]


def test_confirmacao_avisa_da_lixeira(monkeypatch):
    """O aviso de permanencia precisa estar no texto do dialogo."""
    scr = _make(monkeypatch, scan=_scan(recycle_bin=(2, 500)))
    scr.refresh()
    scr._rows[cleanup_mod.RECYCLE_BIN].set_checked(True)
    visto = {}
    monkeypatch.setattr(QMessageBox, "setText",
                        lambda self, txt: visto.update(txt=txt))
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.No)
    scr._confirm([cleanup_mod.RECYCLE_BIN])
    assert "PERMANENTEMENTE" in visto["txt"]


def test_confirmacao_avisa_falta_de_admin(monkeypatch):
    scr = _make(monkeypatch)
    monkeypatch.setattr(cleanup_mod, "is_admin", lambda: False)
    visto = {}
    monkeypatch.setattr(QMessageBox, "setText",
                        lambda self, txt: visto.update(txt=txt))
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.No)
    scr._confirm([cleanup_mod.PREFETCH])
    assert "administrador" in visto["txt"]


def test_confirmacao_sem_aviso_de_admin_quando_elevado(monkeypatch):
    scr = _make(monkeypatch)
    monkeypatch.setattr(cleanup_mod, "is_admin", lambda: True)
    visto = {}
    monkeypatch.setattr(QMessageBox, "setText",
                        lambda self, txt: visto.update(txt=txt))
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.No)
    scr._confirm([cleanup_mod.PREFETCH])
    assert "administrador" not in visto["txt"]


def test_botao_default_do_dialogo_e_nao(monkeypatch):
    """Enter distraido no dialogo nao pode disparar remocao."""
    scr = _make(monkeypatch)
    visto = {}
    monkeypatch.setattr(QMessageBox, "setDefaultButton",
                        lambda self, b: visto.update(btn=b))
    monkeypatch.setattr(QMessageBox, "exec",
                        lambda self: QMessageBox.StandardButton.No)
    scr._confirm([cleanup_mod.TEMP_FILES])
    assert visto["btn"] == QMessageBox.StandardButton.No


# ── resultado ────────────────────────────────────────────────
def test_resultado_grava_timestamp_e_reabilita(monkeypatch, _isolate):
    scr = _make(monkeypatch)
    r = cleanup_mod.CleanResult(cleanup_mod.TEMP_FILES,
                               removed=4, freed=2048, skipped=1)
    scr._on_clean_done({cleanup_mod.TEMP_FILES: r})
    assert _isolate["cleanup_last_ts"] > 0
    assert "Última limpeza:" in scr._last_lbl.text()
    assert scr._clean_btn.text() == "Limpar Selecionados"
    assert scr._rows[cleanup_mod.TEMP_FILES]._toggle.isEnabled() is True


def test_resultado_vazio_nao_quebra(monkeypatch):
    scr = _make(monkeypatch)
    scr._on_clean_done({})
    assert scr._clean_btn.text() == "Limpar Selecionados"


def test_last_label_sem_limpeza_previa(monkeypatch):
    scr = _make(monkeypatch)
    assert scr._last_lbl.text() == "Nunca executada"


def test_last_label_ignora_timestamp_invalido(monkeypatch):
    scr = _make(monkeypatch)
    scr._set_last_label("abc")
    assert scr._last_lbl.text() == "Nunca executada"


# ── workers ──────────────────────────────────────────────────
def test_scan_worker_nao_reentra(monkeypatch):
    from skinvault.ui.cleanup_screen import ScanWorker
    w = ScanWorker()
    w._running = True
    chamadas = []
    monkeypatch.setattr(cleanup_mod, "scan_all",
                        lambda keys=None: chamadas.append(1) or {})
    w.start()
    assert chamadas == []


def test_clean_worker_nao_reentra(monkeypatch):
    from skinvault.ui.cleanup_screen import CleanWorker
    w = CleanWorker()
    w._running = True
    w.start([cleanup_mod.TEMP_FILES])  # o mock de `clean` levantaria


# ── integracao com o router ──────────────────────────────────
def test_router_navega_pra_limpeza(monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui import screen_router as sr
    monkeypatch.setattr(cleanup_mod, "scan_all", lambda keys=None: _scan())
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    router = sr.ScreenRouter(PriceCache())
    router.navigate(sr.SCREEN_CLEANUP)
    assert router._stack.currentWidget() is router._cleanup_screen
