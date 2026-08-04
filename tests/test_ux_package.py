"""Pacote UX — ToastManager, empty state de metas e custo retroativo.

Cobre o pacote entregue em uma passada:
  - ToastManager (skinvault/ui/toast.py): singleton global que envolve o
    Toast de components.py, com `toast_finished`.
  - GoalsCard: empty state interativo ("Criar primeira meta") + toast
    "Metas atualizadas!" ao salvar.
  - HistoryScreen/RetroCostDialog: custo retroativo de posições do sync
    Steam + sinal `costs_updated` (KPI reativa na Conta).
"""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from skinvault import goals


class _FakeSettings:
    def __init__(self, data: dict):
        self.data = data

    def load_settings(self):
        return self.data

    def save_settings(self, data: dict):
        self.data = data


@pytest.fixture
def app():
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    inst = QApplication.instance() or QApplication([])
    yield inst
    for w in list(inst.topLevelWidgets()):
        w.deleteLater()
    inst.processEvents()
    inst.quit()


@pytest.fixture
def st(monkeypatch):
    fake = _FakeSettings({"goals": []})
    monkeypatch.setattr(goals, "_settings", fake)
    return fake


@pytest.fixture
def mgr(app):
    from skinvault.ui.toast import ToastManager
    ToastManager._instance = None
    yield ToastManager.instance()
    ToastManager._instance = None


# ── ToastManager ──────────────────────────────────────────────────

def test_toast_manager_instancia_unica(app):
    from skinvault.ui.toast import ToastManager
    assert ToastManager.instance() is ToastManager.instance()


def test_toast_manager_show_retorna_toastwidget(mgr):
    from skinvault.ui.components import Toast
    from skinvault.ui.toast import ToastWidget
    host = QWidget()
    toast = mgr.show(host, "msg", "success", duration_ms=60_000)
    assert isinstance(toast, ToastWidget)
    assert toast in Toast._stack


def test_toast_manager_variants_do_estilo(mgr):
    from skinvault.ui import theme as t
    host = QWidget()
    esperado = {
        "info": t.ACCENT,
        "success": t.POSITIVE,
        "warning": t.WARN,
        "error": t.DANGER,
    }
    for variant, cor in esperado.items():
        toast = mgr.show(host, "x", variant, duration_ms=60_000)
        assert cor in toast.styleSheet(), variant


def test_toast_manager_toast_finished_sinal(mgr):
    host = QWidget()
    fired = []
    mgr.toast_finished.connect(lambda: fired.append(True))
    toast = mgr.show(host, "msg", "info", duration_ms=60_000)
    toast._on_faded_out()
    assert fired == [True]


def test_toast_manager_atalhos_de_variant(mgr):
    host = QWidget()
    assert mgr.show_success(host, "ok", 60_000).styleSheet()
    assert mgr.show_error(host, "erro", 60_000).styleSheet()
    assert mgr.show_info(host, "info", 60_000).styleSheet()
    assert mgr.show_warning(host, "aviso", 60_000).styleSheet()


# ── GoalsCard: empty state interativo ──────────────────────────────

def _card(app, st):
    from skinvault.ui.goals_card import GoalsCard
    return GoalsCard()


def test_goals_card_empty_cta_visivel_sem_metas(app, st):
    card = _card(app, st)
    assert card._empty.isVisibleTo(card)
    assert card._empty_cta.isVisibleTo(card)
    assert card._empty_cta.text() == "Criar primeira meta"


def test_goals_card_com_metas_esconde_cta(app, st):
    card = _card(app, st)
    goals.upsert_goal("Meta", 1000.0, "net")
    card.refresh_from({"market": 1200.0, "net_if_sold": 1000.0,
                       "pnl": 200.0, "positions": 12})
    assert card._empty.isVisibleTo(card) is False
    assert card._empty_cta.isVisibleTo(card) is False


def test_goals_card_cta_abre_edicao_e_avisa(app, st, monkeypatch):
    from skinvault.ui import goals_card as gc
    from skinvault.ui.toast import ToastManager
    card = _card(app, st)
    execs = []
    monkeypatch.setattr(
        gc.GoalsEditDialog, "exec",
        lambda self: execs.append(True) or QDialog.DialogCode.Accepted)
    toasts = []
    monkeypatch.setattr(
        ToastManager, "show_success",
        lambda self, parent, text, **kw: toasts.append(text))
    card._on_edit()
    assert execs == [True]
    assert toasts == ["Metas atualizadas!"]


def test_goals_card_cta_cancelar_nao_avisa(app, st, monkeypatch):
    from skinvault.ui import goals_card as gc
    from skinvault.ui.toast import ToastManager
    card = _card(app, st)
    monkeypatch.setattr(
        gc.GoalsEditDialog, "exec",
        lambda self: QDialog.DialogCode.Rejected)
    toasts = []
    monkeypatch.setattr(
        ToastManager, "show_success",
        lambda self, parent, text, **kw: toasts.append(text))
    card._on_edit()
    assert toasts == []


# ── RetroCostDialog ────────────────────────────────────────────────

POS_SEM_CUSTO = {"name": "AK-47 | Redline (Field-Tested)", "cost": 0.0,
                 "quantity": 1, "source": "steam_sync"}
POS_COM_CUSTO = {"name": "Kilowatt Case", "cost": 120.0, "quantity": 3,
                 "source": "manual"}


def test_retro_cost_lista_so_sem_custo(app, st):
    from skinvault.ui.history_screen import RetroCostDialog
    dlg = RetroCostDialog(positions=[POS_SEM_CUSTO, POS_COM_CUSTO])
    assert len(dlg._rows) == 1
    assert dlg._rows[0][0] == "AK-47 | Redline (Field-Tested)"


def test_retro_cost_tudo_com_custo_desabilita_save(app, st):
    from skinvault.ui.history_screen import RetroCostDialog
    dlg = RetroCostDialog(positions=[POS_COM_CUSTO])
    assert dlg._rows == []
    assert dlg._save_btn.isEnabled() is False


def test_retro_cost_salva_custos(app, st, monkeypatch):
    from skinvault import portfolio as p
    from skinvault.ui.history_screen import RetroCostDialog
    salvo = []
    monkeypatch.setattr(
        p, "update_position_cost",
        lambda name, cost, **kw: (salvo.append((name, cost)) or [POS_SEM_CUSTO]))
    dlg = RetroCostDialog(positions=[POS_SEM_CUSTO, POS_COM_CUSTO])
    dlg._rows[0][1].setText("199,90")
    dlg._on_save()
    assert salvo == [("AK-47 | Redline (Field-Tested)", 199.9)]
    assert dlg.updated == 1


def test_retro_cost_valor_invalido_mostra_erro(app, st, monkeypatch):
    from skinvault import portfolio as p
    from skinvault.ui.history_screen import RetroCostDialog
    chamado = []
    monkeypatch.setattr(p, "update_position_cost",
                        lambda name, cost, **kw: chamado.append(name))
    dlg = RetroCostDialog(positions=[POS_SEM_CUSTO])
    dlg._rows[0][1].setText("abc")
    dlg._on_save()
    assert dlg._erro.isVisibleTo(dlg)
    assert chamado == []
    assert dlg.updated == 0


# ── HistoryScreen: custo retroativo reativo ────────────────────────

def test_history_costs_updated_emite_e_avisa(app, st, monkeypatch):
    from skinvault.ui import history_screen as hs
    from skinvault.ui.toast import ToastManager
    screen = hs.HistoryScreen()

    def _fake_exec(self):
        self._updated = 2
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(hs.RetroCostDialog, "exec", _fake_exec)
    toasts = []
    monkeypatch.setattr(
        ToastManager, "show_success",
        lambda self, parent, text, **kw: toasts.append(text))
    signals = []
    screen.costs_updated.connect(lambda n: signals.append(n))
    screen._open_retro_cost()
    assert signals == [2]
    assert toasts and toasts[0] == "2 custo(s) atualizado(s) — reavaliando…"


def test_history_costs_updated_cancelado_nao_emite(app, st, monkeypatch):
    from skinvault.ui import history_screen as hs
    screen = hs.HistoryScreen()
    monkeypatch.setattr(
        hs.RetroCostDialog, "exec",
        lambda self: QDialog.DialogCode.Rejected)
    signals = []
    screen.costs_updated.connect(lambda n: signals.append(n))
    screen._open_retro_cost()
    assert signals == []
