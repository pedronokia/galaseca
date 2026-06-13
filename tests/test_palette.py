"""Testes da command palette (Frente V).

palette_rank e' logica pura (sem GUI). A CommandPalette tem smoke tests
que exigem QApplication (criada pela fixture global de tests/conftest ou
pelo proprio teste).
"""
from __future__ import annotations

import pytest

from skinvault.ui.palette import _fuzzy_score, palette_rank


def _items(*labels):
    return [{"label": lbl, "category": "x", "icon": "", "run": lambda: None}
            for lbl in labels]


class TestPaletteRank:
    def test_empty_query_returns_all_in_order(self):
        items = _items("Scanner", "Market", "Trades")
        out = palette_rank("", items)
        assert [i["label"] for i in out] == ["Scanner", "Market", "Trades"]

    def test_no_match_returns_empty(self):
        out = palette_rank("zzz", _items("Scanner", "Market"))
        assert out == []

    def test_case_insensitive(self):
        out = palette_rank("SCAN", _items("Scanner"))
        assert len(out) == 1 and out[0]["label"] == "Scanner"

    def test_prefix_beats_midmatch(self):
        # "mar" e' prefixo de "Market", substring tardia em "Steam Market"
        out = palette_rank("mar", _items("Steam Market", "Market"))
        assert out[0]["label"] == "Market"

    def test_contiguous_beats_scattered(self):
        # "ist" e' contiguo em "Historico", espalhado em "Inativos sem trade"
        out = palette_rank("ist", _items("Inativos sem trade", "Historico"))
        assert out[0]["label"] == "Historico"

    def test_subsequence_matches_scattered(self):
        # "stt" casa espalhado em "Sincronizar Trade Total"
        out = palette_rank("stt", _items("Sincronizar Trade Total"))
        assert len(out) == 1

    def test_stable_order_on_tie(self):
        # labels identicos -> mantem ordem original (idx como desempate)
        items = [
            {"label": "Ir: X", "category": "a", "icon": "", "run": None},
            {"label": "Ir: X", "category": "b", "icon": "", "run": None},
        ]
        out = palette_rank("ir", items)
        assert [i["category"] for i in out] == ["a", "b"]

    def test_filters_out_nonmatching(self):
        out = palette_rank("trade", _items("Trades", "Scanner", "Market"))
        assert [i["label"] for i in out] == ["Trades"]


class TestFuzzyScore:
    def test_prefix_scores_higher_than_mid(self):
        assert _fuzzy_score("ab", "abc") > _fuzzy_score("ab", "xabc")

    def test_contiguous_scores_higher_than_scattered(self):
        assert _fuzzy_score("ab", "xabx") > _fuzzy_score("ab", "axbx")

    def test_no_match_returns_none(self):
        assert _fuzzy_score("zq", "abc") is None

    def test_empty_query_zero(self):
        assert _fuzzy_score("", "abc") == 0


# ── smoke do dialog (precisa de QApplication) ─────────────────
@pytest.fixture(scope="module")
def _qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def _cmds_with_spy():
    fired = []
    cmds = [
        {"label": "Ir: Scanner", "category": "Navegar", "icon": "radar",
         "run": lambda: fired.append("scanner")},
        {"label": "Ir: Market", "category": "Navegar", "icon": "chart",
         "run": lambda: fired.append("market")},
        {"label": "Adicionar trade", "category": "Acao", "icon": "swap",
         "run": lambda: fired.append("trade")},
    ]
    return cmds, fired


def test_palette_opens_and_lists_all(_qapp):
    from skinvault.ui.palette import CommandPalette
    cmds, _ = _cmds_with_spy()
    pal = CommandPalette(cmds)
    assert pal._list.count() == 3


def test_palette_filter_narrows(_qapp):
    from skinvault.ui.palette import CommandPalette
    cmds, _ = _cmds_with_spy()
    pal = CommandPalette(cmds)
    pal._refilter("scan")
    assert pal._list.count() == 1
    assert pal._filtered[0]["label"] == "Ir: Scanner"


def test_palette_execute_runs_command(_qapp):
    from skinvault.ui.palette import CommandPalette
    cmds, fired = _cmds_with_spy()
    pal = CommandPalette(cmds)
    pal._refilter("scan")
    pal._execute_current()
    assert fired == ["scanner"]


def test_palette_move_wraps(_qapp):
    from skinvault.ui.palette import CommandPalette
    cmds, _ = _cmds_with_spy()
    pal = CommandPalette(cmds)
    assert pal._list.currentRow() == 0
    pal._move(-1)  # wrap pro ultimo
    assert pal._list.currentRow() == 2
    pal._move(1)   # wrap pro primeiro
    assert pal._list.currentRow() == 0


def test_palette_enter_executes_via_keyboard(_qapp):
    """Enter no input (focado) propaga pro keyPressEvent e executa.

    Regressao: o smoke chama _execute_current direto; este exercita o
    caminho real de teclado (QLineEdit ignora Return -> dialog trata)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from skinvault.ui.palette import CommandPalette
    cmds, fired = _cmds_with_spy()
    pal = CommandPalette(cmds)
    pal.show()
    pal._refilter("scan")
    QTest.keyClick(pal._input, Qt.Key.Key_Return)
    assert fired == ["scanner"]
    pal.close()


def test_palette_arrow_down_navigates_via_keyboard(_qapp):
    """Down no input move a selecao (propaga pro keyPressEvent)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from skinvault.ui.palette import CommandPalette
    cmds, _ = _cmds_with_spy()
    pal = CommandPalette(cmds)
    pal.show()
    QTest.keyClick(pal._input, Qt.Key.Key_Down)
    assert pal._list.currentRow() == 1
    pal.close()
