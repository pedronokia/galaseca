"""Contexto de saida: distancia do topo + faixa de preco (signals.py)."""
from __future__ import annotations

import pytest

from skinvault import signals

DIA = 86400


def _ph(precos):
    return [{"time": i * DIA, "price_median": p, "purchases": 1}
            for i, p in enumerate(precos)]


def test_exit_context_no_topo():
    ctx = signals.exit_context(_ph([10.0] * 9 + [100.0, 95.0]))
    assert ctx["pct_of_ath"] == pytest.approx(0.95)
    assert ctx["level"] == "topo"
    assert ctx["text"] == "95% do topo"
    assert "R$ 95,00" in ctx["tooltip"] and "R$ 100,00" in ctx["tooltip"]


@pytest.mark.parametrize("atual,level", [
    (60.0, "alto"), (30.0, "meio"), (10.0, "baixo"),
])
def test_exit_context_niveis(atual, level):
    ctx = signals.exit_context(_ph([50.0] * 9 + [100.0, atual]))
    assert ctx["level"] == level


def test_exit_context_historico_curto_vazio():
    assert signals.exit_context(_ph([1.0] * 5)) == {}
    assert signals.exit_context(None) == {}


def test_tooltip_faixa_e_universo():
    caixa = signals.format_exit_context(0.5, 1.2, 0.6, is_container=True)
    assert "R$ 0–1" in caixa["tooltip"] and "+73,0%" in caixa["tooltip"]
    assert "pesa bastante em caixas" in caixa["tooltip"]
    skin = signals.format_exit_context(0.5, 2000.0, 900.0)
    assert "acima de R$ 500" in skin["tooltip"]
    assert "em skins esse efeito é fraco" in skin["tooltip"]
    # Descritivo: nada de "venda"/"compre" como instrucao
    for txt in (caixa["tooltip"], skin["tooltip"]):
        assert "previsão" in txt
        assert "venda agora" not in txt.lower()


def test_topo_ignora_ponto_horario_isolado():
    """Caso real (Redline FT, 2026-07-29): 1 compra horaria a R$ 1.403 num
    item de ~R$ 220. O topo sai da serie diaria ponderada por volume."""
    ph = [{"time": i * DIA, "price_median": 200.0, "purchases": 500}
          for i in range(200)]
    ph.append({"time": 150 * DIA + 3600, "price_median": 1403.0,
               "purchases": 1})
    ctx = signals.exit_context(ph)
    assert ctx["ath"] < 210.0  # (500*200 + 1403) / 501 no dia do pico
    assert ctx["level"] == "topo"


def test_topo_no_lancamento_avisa():
    lancamento = _ph([74.0] + [10.0] * 199 + [1.1])
    ctx = signals.exit_context(lancamento)
    assert ctx["at_launch"] is True
    assert "lançamento" in ctx["tooltip"]
    depois = _ph([10.0] * 100 + [50.0] + [20.0] * 99)
    assert signals.exit_context(depois)["at_launch"] is False


def test_rotulo_ath_em_reais():
    rta = signals.relative_to_ath(_ph([1.0] * 9 + [12.5, 10.0]))
    assert rta["label"] == "Preço a 80% do ATH (R$ 12,50)"


# ── celula do inventario ─────────────────────────────────────
def test_celula_topo_do_inventario():
    from PyQt6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from skinvault.ui import theme as t
    from skinvault.ui.inventory_screen import InventoryScreen

    item = InventoryScreen._top_item(
        "AK-47 | Redline (Field-Tested)",
        {"pct_of_ath": 0.93, "ath": 100.0, "current": 93.0, "ts": 1})
    assert item.text() == "93% do topo"
    assert item.foreground().color().name().lower() == t.WARN_TEXT.lower()
    assert "topo histórico" in item.toolTip()

    vazio = InventoryScreen._top_item("X", None)
    assert vazio.text() == "—" and "Atualizar notas" in vazio.toolTip()


def test_rel_ath_do_score_ignora_ponto_horario_isolado():
    """O fator rel_ath da nota usa o mesmo topo diario do exit_context:
    uma compra horaria anomala nao pode virar o "maior preco"."""
    ph = [{"time": i * DIA, "price_median": 200.0, "purchases": 500}
          for i in range(200)]
    ph.append({"time": 150 * DIA + 3600, "price_median": 1403.0,
               "purchases": 1})
    rta = signals.relative_to_ath(ph)
    assert rta["ath"] < 210.0
    assert rta["band"] == "at_ath"
