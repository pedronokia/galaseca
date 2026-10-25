"""Filtro "Sem custo", ultimo scan persistido e "Silenciar por 24h"."""
from __future__ import annotations

import json

import pytest

from skinvault import scan_store, watchlist as wl


@pytest.fixture(autouse=True)
def app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


# ── Inventario: Sem custo ──────────────────────────────────────────

@pytest.fixture
def inv(monkeypatch):
    monkeypatch.setattr("skinvault.markets.cached_market",
                        lambda *a, **k: {})
    monkeypatch.setattr("skinvault.markets.usd_brl", lambda *a, **k: 5.11)
    gravado = {}
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s, *a, **k: gravado.update(s))
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: dict(gravado))
    from skinvault.ui.inventory_screen import InventoryScreen
    tela = InventoryScreen()
    rows = [
        {"name": "Kilowatt Case", "quantity": 21, "price": 1.22,
         "market": 25.62, "net_if_sold": 1.04, "pnl": None},
        {"name": "AK-47 | Redline (Field-Tested)", "quantity": 1,
         "price": 223.5, "market": 223.5, "net_if_sold": 194.35,
         "pnl": 14.35},
        {"name": "AWP | Asiimov (Field-Tested)", "quantity": 1,
         "price": 512.0, "market": 512.0, "net_if_sold": 445.22,
         "pnl": None},
    ]
    pos = [{"name": "Kilowatt Case", "source": "steam_sync", "cost": 0.0},
           {"name": "AK-47 | Redline (Field-Tested)", "source": "manual",
            "cost": 180.0},
           {"name": "AWP | Asiimov (Field-Tested)", "source": "steam_sync",
            "cost": 0.0}]
    tela.set_data(rows, pos, False)
    return tela


def _visiveis_tabela(tela):
    return sorted(tela._nome_da_linha(r) for r in range(tela._table.rowCount())
                  if not tela._table.isRowHidden(r))


def test_sem_custo_aparece_com_contagem_e_filtra_as_duas_visoes(inv):
    from skinvault.ui.inventory_grid import SEM_CUSTO
    btn = inv._cat_botoes.get(SEM_CUSTO)
    assert btn is not None and btn._contagem.text() == "2"
    inv._on_categoria(SEM_CUSTO)
    assert _visiveis_tabela(inv) == ["AWP | Asiimov (Field-Tested)",
                                     "Kilowatt Case"]
    assert len(inv._grid._visiveis) == 2
    assert "Mostrando 2 de 3 itens" in inv._status.text()
    inv._on_categoria(None)
    assert len(_visiveis_tabela(inv)) == 3


def test_tabela_respeita_categoria_do_painel(inv):
    """Antes so' a grade filtrava pela categoria escolhida."""
    from skinvault import portfolio
    cat = portfolio.classify_item("Kilowatt Case")
    inv._on_categoria(cat)
    assert _visiveis_tabela(inv) == ["Kilowatt Case"]


def test_mostrar_sem_custo_abre_tabela_filtrada(inv):
    inv.mostrar_sem_custo()
    assert inv._views.currentIndex() == 1
    assert len(_visiveis_tabela(inv)) == 2


def test_conta_botao_informar_custos(monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    tela = AccountScreen(PriceCache(ttl=3600))
    rows = [{"name": "A", "quantity": 1, "price": 10.0, "has_cost": True,
             "pnl": 1.0, "cost_total": 9.0},
            {"name": "B", "quantity": 1, "price": 5.0, "has_cost": False}]
    tela._on_eval({"positions": [], "rows": rows,
                   "totals": {"unknown_cost": 1, "pnl": 1.0},
                   "rate_limited": False})
    assert not tela._sem_custo_btn.isHidden()
    assert "(1)" in tela._sem_custo_btn.text()
    pedidos = []
    tela.ver_sem_custo.connect(lambda: pedidos.append(1))
    tela._sem_custo_btn.click()
    assert pedidos == [1]


# ── scan_store ─────────────────────────────────────────────────────

def test_scan_store_ida_e_volta(tmp_path):
    p = tmp_path / "s.json"
    scan_store.save_last_scan("Rifles", [{"name": "X", "score": 70}], p,
                              now=1000.0)
    salvo = scan_store.load_last_scan(p)
    assert salvo == {"ts": 1000.0, "category": "Rifles",
                     "results": [{"name": "X", "score": 70}]}


@pytest.mark.parametrize("conteudo", [
    "nao e json", "[]", json.dumps({"results": []}),
    json.dumps({"results": [{"sem": "nome"}]}),
])
def test_scan_store_arquivo_ruim_vira_none(tmp_path, conteudo):
    p = tmp_path / "s.json"
    p.write_text(conteudo, encoding="utf-8")
    assert scan_store.load_last_scan(p) is None
    assert scan_store.load_last_scan(tmp_path / "nao_existe.json") is None


def test_idade_txt():
    assert scan_store.idade_txt(1000, now=1030) == "agora há pouco"
    assert scan_store.idade_txt(0, now=300) == "há 5 min"
    assert scan_store.idade_txt(0, now=2 * 3600) == "há 2 h"
    assert scan_store.idade_txt(0, now=86400) == "há 1 dia"
    assert scan_store.idade_txt(0, now=3 * 86400) == "há 3 dias"


def test_proxima_txt():
    assert scan_store.proxima_txt(0, 6, now=6 * 3600 - 30) == "a qualquer momento"
    assert scan_store.proxima_txt(0, 6, now=6 * 3600 - 1200) == "em ~20 min"
    assert scan_store.proxima_txt(0, 6, now=0) == "em ~6 h"


def test_registrar_ciclo_sucesso(tmp_path):
    p = tmp_path / "h.json"
    scan_store.registrar_ciclo(42, 25.7, p, now=1000.0)
    hist = scan_store.load_historico_ciclos(p)
    assert hist == [{"ts": 1000.0, "itens": 42, "duracao_min": 25.7,
                     "sucesso": True}]


def test_registrar_ciclo_falha(tmp_path):
    """itens=0 marca sucesso=False -- é o que distingue 'bloqueado' de
    'funcionou normal' na página /status (achado real de 2026-10-24)."""
    p = tmp_path / "h.json"
    scan_store.registrar_ciclo(0, 26.4, p, now=1000.0)
    hist = scan_store.load_historico_ciclos(p)
    assert hist[0]["sucesso"] is False


def test_registrar_ciclo_cap_no_tamanho_maximo(tmp_path):
    p = tmp_path / "h.json"
    for i in range(scan_store._HISTORICO_MAX + 5):
        scan_store.registrar_ciclo(1, 1.0, p, now=float(i))
    hist = scan_store.load_historico_ciclos(p)
    assert len(hist) == scan_store._HISTORICO_MAX
    assert hist[-1]["ts"] == float(scan_store._HISTORICO_MAX + 4)


def test_load_historico_ciclos_ausente_vira_lista_vazia(tmp_path):
    assert scan_store.load_historico_ciclos(tmp_path / "nao_existe.json") == []


def test_scanner_reabre_com_ultimo_scan(monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    res = [{"name": "AK-47 | Redline (Field-Tested)", "score": 80,
            "price": 100.0, "price_str": "R$ 100,00", "median": 110.0,
            "breakdown": {}, "data_quality": {"level": "high"},
            "verdict": "abaixo do típico", "verdict_color": "#000000",
            "verdict_ok": True, "spread": "", "book": "", "trend": "",
            "trend_code": "", "sd_label": "", "score_tooltip": "",
            "pump_risk": {"level": "low", "reasons": []},
            "is_container": False}]
    monkeypatch.setattr(scan_store, "load_last_scan", lambda *a, **k: {
        "ts": 0.0, "category": "Rifles", "results": res})
    tela = ScannerScreen(PriceCache(ttl=3600))
    assert tela._table.rowCount() == 1
    assert tela._cat_combo.currentText() == "Rifles"
    assert "Último scan: Rifles" in tela._status.text()
    assert tela._empty_hero.isHidden()


def test_scanner_grava_ao_concluir(monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(scan_store, "load_last_scan", lambda *a, **k: None)
    gravados = []
    monkeypatch.setattr(scan_store, "save_last_scan",
                        lambda cat, r, *a, **k: gravados.append((cat, r)))
    tela = ScannerScreen(PriceCache(ttl=3600))
    tela._scan_cat = "Facas"
    tela._scan_results = [{"name": "X", "score": 50}]
    tela._on_progress("FIM")
    assert gravados == [("Facas", [{"name": "X", "score": 50}])]
    gravados.clear()
    tela._on_progress("CANCELADO")   # parcial nao substitui o ultimo bom
    assert gravados == []


def test_backup_inclui_ultimo_scan():
    from skinvault import backup
    assert "scanner_last.json" in backup._DATA_FILES


# ── watchlist: silenciar ───────────────────────────────────────────

def test_set_muted_e_is_muted(tmp_path):
    p = tmp_path / "wl.json"
    wl.add_watch("Fever Case", 4.0, path=p)
    wl.set_muted("Fever Case", 24, path=p, now=1000.0)
    item = wl.load_watchlist(p)[0]
    assert item["muted_until"] == pytest.approx(1000.0 + 24 * 3600)
    assert wl.is_muted(item, now=1000.0 + 3600)
    assert not wl.is_muted(item, now=1000.0 + 25 * 3600)
    wl.set_muted("Fever Case", None, path=p)
    assert "muted_until" not in wl.load_watchlist(p)[0]


def test_alerta_de_item_silenciado_nao_notifica(monkeypatch):
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda *a, **k: {"tray_notifications": True})
    import time
    itens = [{"name": "Fever Case", "target": 4.0,
              "muted_until": time.time() + 3600},
             {"name": "Kilowatt Case", "target": 1.0}]
    monkeypatch.setattr(wl, "load_watchlist", lambda *a, **k: itens)
    tela = WatchlistScreen(PriceCache(ttl=3600))
    avisos = []
    tela.notification_requested.connect(
        lambda *a: avisos.append(a[1]))
    tela._on_alert_fired("Fever Case", {"rule": "x", "label": "y"})
    assert avisos == []
    tela._on_alert_fired("Kilowatt Case", {"rule": "x", "label": "y"})
    assert len(avisos) == 1
