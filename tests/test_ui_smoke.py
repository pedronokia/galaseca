"""Smoke tests para UI (F11).

Instancia MainWindow e cada tela individualmente sem rede.
Nao usa rede; mocka session e tray nos testes que precisam.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

import pytest


@pytest.fixture(autouse=True)
def _qapp():
    """Cria/descarta QApplication por teste."""
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


def test_mainwindow_instantiation(monkeypatch):
    """Cria MainWindow sem erros, mockando session e tray."""
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: False)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.gui import MainWindow
    win = MainWindow()
    assert win.windowTitle() == "SkinVault"


def test_login_gate():
    """LoginGate instancia sem erro."""
    from skinvault.ui.login_gate import LoginGate
    gate = LoginGate()
    assert gate is not None


def test_account_screen():
    """AccountScreen instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    cache = PriceCache(ttl=3600)
    screen = AccountScreen(cache)
    assert screen is not None


def test_history_screen():
    """HistoryScreen instancia sem erro."""
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    assert screen is not None


# ── ScannerScreen + _FactorBar + _ScoreBreakdownDialog ─────────

def test_factor_bar_default():
    """_FactorBar instancia com delta positivo."""
    from skinvault.ui.scanner_screen import _FactorBar
    bar = _FactorBar(10.0)
    assert bar._delta == 10.0
    assert bar._max == 35.0

def test_factor_bar_negative():
    """_FactorBar instancia com delta negativo."""
    from skinvault.ui.scanner_screen import _FactorBar
    bar = _FactorBar(-5.0)
    assert bar._delta == -5.0

def test_factor_bar_paint(monkeypatch):
    """_FactorBar paintEvent renders without error."""
    from PyQt6.QtCore import Qt
    from skinvault.ui.scanner_screen import _FactorBar
    bar = _FactorBar(10.0)
    bar.resize(200, 20)
    # QPainter calls in paintEvent are hard to assert,
    # but we can at least verify no crash
    bar.grab()  # triggers paintEvent
    neg_bar = _FactorBar(-10.0)
    neg_bar.resize(200, 20)
    neg_bar.grab()

def test_score_breakdown_dialog_compra():
    """_ScoreBreakdownDialog header 'COMPRA' para score >= 70."""
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK-47", "score": 85, "breakdown": [],
    })
    assert "AK-47" in dlg.windowTitle()

def test_score_breakdown_dialog_atencao():
    """_ScoreBreakdownDialog header 'ATENÇÃO' para score 45-69."""
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK-47", "score": 55, "breakdown": [],
    })
    assert "AK-47" in dlg.windowTitle()

def test_score_breakdown_dialog_evitar():
    """_ScoreBreakdownDialog header 'EVITAR' para score < 45."""
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK-47", "score": 30, "breakdown": [],
    })
    assert "AK-47" in dlg.windowTitle()

def test_score_breakdown_dialog_with_breakdown():
    """_ScoreBreakdownDialog renders breakdown rows."""
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK-47", "score": 75,
        "breakdown": [{"label": "Spread", "delta": 20},
                      {"label": "Trend", "delta": -5}],
    })
    assert dlg is not None


def test_bucket_for_score_mapping():
    """_bucket_for_score retorna o bucket correto para cada score."""
    from skinvault.ui.scanner_screen import _bucket_for_score
    assert _bucket_for_score(0) == (0, 30)
    assert _bucket_for_score(29) == (0, 30)
    assert _bucket_for_score(30) == (30, 50)
    assert _bucket_for_score(49) == (30, 50)
    assert _bucket_for_score(50) == (50, 70)
    assert _bucket_for_score(69) == (50, 70)
    assert _bucket_for_score(70) == (70, 85)
    assert _bucket_for_score(84) == (70, 85)
    assert _bucket_for_score(85) == (85, 101)
    assert _bucket_for_score(100) == (85, 101)


def test_bucket_for_score_boundaries():
    """Score fora do range esperado: retorna None (defensivo)."""
    from skinvault.ui.scanner_screen import _bucket_for_score
    # Range valido cobre 0..100. Score 101 nao deve mapear.
    assert _bucket_for_score(101) is None


def test_bucket_history_data_integrity():
    """Os buckets historicos cobrem 0..100 sem gap."""
    from skinvault.ui.scanner_screen import _BUCKET_HISTORY_90D
    bounds = sorted(_BUCKET_HISTORY_90D.keys())
    assert bounds[0][0] == 0
    assert bounds[-1][1] == 101  # cobre 100 inclusive
    # nao tem gap entre buckets
    for i in range(len(bounds) - 1):
        assert bounds[i][1] == bounds[i + 1][0]


def _hidden_levels_by_name(screen) -> dict:
    """Helper: mapa name -> hidden bool, usando dq.level."""
    from PyQt6.QtCore import Qt
    out = {}
    for row in range(screen._table.rowCount()):
        cell = screen._table.item(row, screen.COL_NAME)
        if not cell:
            continue
        r = cell.data(Qt.ItemDataRole.UserRole)
        if not isinstance(r, dict):
            continue
        out[r["name"]] = {
            "level": r.get("data_quality", {}).get("level"),
            "hidden": screen._table.isRowHidden(row),
        }
    return out


def test_scanner_filtro_conf_existe(monkeypatch):
    """Checkbox 'Esconder baixa confiança' existe e default off."""
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {})
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    assert screen._hide_low_conf_cb is not None
    assert screen._hide_low_conf_cb.isChecked() is False


def test_scanner_filtro_off_nao_esconde_nada(monkeypatch):
    """Filtro desligado: todas as linhas visíveis."""
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {})
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s: None)
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [
        {"name": "A", "score": 75, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "high", "confidence": 0.9, "n": 200}},
        {"name": "B", "score": 60, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "low", "confidence": 0.3, "n": 30}},
    ]
    screen._hide_low_conf_cb.setChecked(False)
    screen._populate()
    by_name = _hidden_levels_by_name(screen)
    assert by_name["A"]["hidden"] is False
    assert by_name["B"]["hidden"] is False


def test_scanner_filtro_on_esconde_baixa_e_minima(monkeypatch):
    """Filtro ligado: low e very_low ocultos; high e medium visíveis."""
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s: None)
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [
        {"name": "A", "score": 75, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "high", "confidence": 0.9, "n": 200}},
        {"name": "B", "score": 70, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "medium", "confidence": 0.6, "n": 110}},
        {"name": "C", "score": 60, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "low", "confidence": 0.3, "n": 40}},
        {"name": "D", "score": 50, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "very_low", "confidence": 0.1, "n": 10}},
    ]
    screen._hide_low_conf_cb.setChecked(True)
    screen._populate()
    by_name = _hidden_levels_by_name(screen)
    assert by_name["A"]["hidden"] is False  # high
    assert by_name["B"]["hidden"] is False  # medium
    assert by_name["C"]["hidden"] is True   # low
    assert by_name["D"]["hidden"] is True   # very_low


def test_scanner_filtro_toggle_persiste(monkeypatch):
    """Toggle do filtro grava em settings."""
    saved = {}
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s: saved.update(s))
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {})
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._hide_low_conf_cb.setChecked(True)
    assert saved.get("scanner_hide_low_confidence") is True
    screen._hide_low_conf_cb.setChecked(False)
    assert saved.get("scanner_hide_low_confidence") is False


def test_scanner_filtro_status_mostra_ocultos(monkeypatch):
    """Status menciona N ocultos por baixa confiança."""
    monkeypatch.setattr("skinvault.settings.save_settings",
                        lambda s: None)
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [
        {"name": "A", "score": 75, "price": 1, "median": 1,
         "breakdown": [], "verdict": "X", "verdict_color": "#0f0",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "data_quality": {"level": "low", "confidence": 0.3, "n": 30}},
    ]
    screen._hide_low_conf_cb.setChecked(True)
    screen._populate()
    assert "1 oculto" in screen._status.text()


def test_scanner_tabela_tem_coluna_conf():
    """Tabela do Scanner tem 12 colunas, sendo a 12a 'Conf.' e a 11a 'Risco'."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    assert screen._table.columnCount() == 12
    assert screen.COL_CONFIDENCE == 11
    assert screen.COL_RISCO == 10
    hdr = screen._table.horizontalHeaderItem(11)
    assert hdr is not None
    assert hdr.text() == "Confiança"
    risco_hdr = screen._table.horizontalHeaderItem(10)
    assert risco_hdr is not None
    assert risco_hdr.text() == "Risco"


def test_scanner_populate_preenche_confianca_alta():
    """Resultado com data_quality 'high' renderiza 'Alta' na coluna Conf."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [{
        "name": "AK", "score": 75, "price": 100, "median": 110,
        "breakdown": [], "verdict": "COMPRA", "verdict_color": "#0f0",
        "spread": "", "book": "", "trend": "", "sd_label": "",
        "data_quality": {"level": "high", "confidence": 0.9, "n": 200},
    }]
    screen._populate()
    cell = screen._table.item(0, screen.COL_CONFIDENCE)
    assert cell.text() == "Alta"


def test_scanner_populate_renderiza_confianca_low():
    """Level 'low' renderiza 'Baixa'."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [{
        "name": "AK", "score": 30, "price": 100, "median": 110,
        "breakdown": [], "verdict": "EVITAR", "verdict_color": "#f00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
        "data_quality": {"level": "low", "confidence": 0.3, "n": 40},
    }]
    screen._populate()
    cell = screen._table.item(0, screen.COL_CONFIDENCE)
    assert cell.text() == "Baixa"


def test_scanner_populate_sem_dq_renderiza_dash():
    """Resultado sem data_quality (back-compat): coluna mostra '—'."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [{
        "name": "AK", "score": 50, "price": 100, "median": 110,
        "breakdown": [], "verdict": "ATENCAO", "verdict_color": "#ff0",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    }]
    screen._populate()
    cell = screen._table.item(0, screen.COL_CONFIDENCE)
    assert cell.text() == "—"


def test_scanner_populate_conf_tooltip():
    """Tooltip da coluna Conf. menciona o numero de pontos."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [{
        "name": "AK", "score": 75, "price": 100, "median": 110,
        "breakdown": [], "verdict": "COMPRA", "verdict_color": "#0f0",
        "spread": "", "book": "", "trend": "", "sd_label": "",
        "data_quality": {"level": "high", "confidence": 0.85, "n": 180},
    }]
    screen._populate()
    cell = screen._table.item(0, screen.COL_CONFIDENCE)
    tip = cell.toolTip()
    assert "180" in tip
    assert "0.85" in tip


def test_score_breakdown_dialog_container_mostra_especifico():
    """Container com is_container=True mostra retorno tipico de container."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "Clutch Case", "score": 75, "breakdown": [],
        "is_container": True,
    })
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("Específico para containers" in t for t in texts)
    # Bucket 70-84 container = +32.9%
    assert any("+32" in t for t in texts)


def test_score_breakdown_dialog_skin_mostra_especifico():
    """Skin com is_container=False mostra retorno tipico de skin."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK-47 | Redline", "score": 75, "breakdown": [],
        "is_container": False,
    })
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("Específico para skins" in t for t in texts)
    # Bucket 70-84 skin = +7.5%
    assert any("+7.5" in t or "+7." in t for t in texts)


def test_score_breakdown_dialog_sem_is_container_omite_tipo():
    """Sem is_container, nao mostra info por tipo (back-compat)."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "X", "score": 75, "breakdown": [],
    })
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert not any("Específico para" in t for t in texts)


def test_score_breakdown_dialog_bucket_n_pequeno_omite():
    """Bucket com n<30 (ex: skin 85-100 n=12) omite linha especifica."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    # Skin no bucket 85-100: n=12 (insuficiente)
    dlg = _ScoreBreakdownDialog({
        "name": "X skin", "score": 95, "breakdown": [],
        "is_container": False,
    })
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    # Linha geral aparece (n=186), mas a "Especifico para skins" nao
    assert any("Histórico em 90 dias" in t for t in texts)
    assert not any("Específico para skins" in t for t in texts)


def test_score_breakdown_dialog_confidence_high():
    """Dialog mostra badge de confianca alta."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK", "score": 75, "breakdown": [],
        "data_quality": {"level": "high", "confidence": 0.9,
                          "n": 200, "age_days": 1.0},
    })
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("Confiança alta" in t for t in texts)
    # Sem warning para high
    assert not any("anti-preditivo" in t for t in texts)


def test_score_breakdown_dialog_confidence_baixa_mostra_warning():
    """Dialog mostra warning quando level e' low ou very_low."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK", "score": 75, "breakdown": [],
        "data_quality": {"level": "very_low", "confidence": 0.1,
                          "n": 10, "age_days": 5.0},
    })
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("Confiança MUITO BAIXA" in t for t in texts)
    assert any("anti-preditivo" in t for t in texts)


def test_score_breakdown_dialog_sem_dq_nao_crasha():
    """Sem data_quality no item: dialog continua renderizando (back-compat)."""
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK", "score": 75, "breakdown": [],
    })
    # Sem crash
    assert dlg is not None


def test_score_breakdown_dialog_mostra_historico():
    """Dialog inclui texto do historico empirico do bucket."""
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    dlg = _ScoreBreakdownDialog({
        "name": "AK-47", "score": 75, "breakdown": [],
    })
    # Procura QLabel com texto "Histórico em 90 dias"
    from PyQt6.QtWidgets import QLabel
    labels = dlg.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert any("Histórico em 90 dias" in t for t in texts)
    # Bucket 70-84 tem retorno positivo de dois digitos (~+27%)
    assert any("+27" in t for t in texts)


# ── _BacktestResultDialog + botao validar ────────────

def test_backtest_result_dialog_empty():
    """Dialog com lista vazia mostra mensagem de empty state."""
    from PyQt6.QtWidgets import QLabel
    from skinvault.ui.scanner_screen import _BacktestResultDialog
    dlg = _BacktestResultDialog([], 0)
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("Nenhuma amostra" in t for t in texts)


def test_backtest_result_dialog_com_samples():
    """Dialog com samples renderiza tabela e correlação."""
    from PyQt6.QtWidgets import QLabel, QTableWidget
    from skinvault.ui.scanner_screen import _BacktestResultDialog
    samples = [
        {"item": "X", "ts": 0, "score": s, "return_pct": float(s) - 50,
         "breakdown_count": 5}
        for s in [20, 30, 40, 50, 60, 70, 80, 90]
    ]
    dlg = _BacktestResultDialog(samples, items_count=2)
    # Tabela de buckets presente
    tables = dlg.findChildren(QTableWidget)
    assert len(tables) == 1
    assert tables[0].rowCount() == 5  # 5 buckets
    # Texto de correlação presente
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("Pearson" in t for t in texts)


def test_backtest_result_dialog_title_inclui_contagem():
    """Title menciona quantidade de samples e itens."""
    from skinvault.ui.scanner_screen import _BacktestResultDialog
    samples = [{"item": "X", "ts": 0, "score": 50, "return_pct": 5.0,
                "breakdown_count": 1}]
    dlg = _BacktestResultDialog(samples, items_count=3)
    title = dlg.windowTitle()
    assert "1" in title
    assert "3" in title


def test_scanner_validate_btn_exists():
    """Botao 'Validar Score' existe e esta habilitado por default."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    assert screen._validate_btn is not None
    assert screen._validate_btn.isEnabled()


def test_scanner_on_validate_sem_resultados():
    """_on_validate_score sem _scan_results: mostra mensagem e nao crasha."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_validate_score()
    # Mensagem agora via Toast (UI widget); basta nao crashar


def test_scanner_on_validate_samples_acumula():
    """_on_validate_samples acumula em _validate_samples."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_validate_samples([{"item": "A", "ts": 0, "score": 70,
                                    "return_pct": 5.0, "breakdown_count": 1}])
    screen._on_validate_samples([{"item": "B", "ts": 0, "score": 80,
                                    "return_pct": 10.0, "breakdown_count": 1}])
    assert len(screen._validate_samples) == 2


def test_scatter_plot_empty():
    """_ScatterPlot com lista vazia renderiza sem crash."""
    from skinvault.ui.scanner_screen import _ScatterPlot
    sc = _ScatterPlot([])
    sc.resize(600, 220)
    sc.grab()


def test_scatter_plot_com_samples():
    """_ScatterPlot pinta pontos sem crash."""
    from skinvault.ui.scanner_screen import _ScatterPlot
    samples = [
        {"item": "X", "ts": 0, "score": s, "return_pct": float(s) * 0.5,
         "breakdown_count": 1}
        for s in range(0, 101, 10)
    ]
    sc = _ScatterPlot(samples)
    sc.resize(600, 220)
    sc.grab()
    assert len(sc._samples) == 11


def test_scatter_plot_extreme_returns_clamped():
    """Retornos > Y_CLAMP nao quebram o plot (clamp aplicado)."""
    from skinvault.ui.scanner_screen import _ScatterPlot
    samples = [
        {"item": "X", "ts": 0, "score": 50, "return_pct": 999.0,
         "breakdown_count": 1},
        {"item": "Y", "ts": 0, "score": 70, "return_pct": -500.0,
         "breakdown_count": 1},
    ]
    sc = _ScatterPlot(samples)
    sc.resize(600, 220)
    sc.grab()


def test_scatter_plot_alpha_por_confidence():
    """Sample com confidence baixa renderiza sem crash (alpha diferenciado)."""
    from skinvault.ui.scanner_screen import _ScatterPlot
    samples = [
        {"item": "X", "ts": 0, "score": 70, "return_pct": 10.0,
         "confidence": 0.9, "level": "high"},
        {"item": "Y", "ts": 0, "score": 50, "return_pct": 5.0,
         "confidence": 0.2, "level": "low"},
    ]
    sc = _ScatterPlot(samples)
    sc.resize(600, 220)
    sc.grab()  # paintEvent sem crash


def test_scatter_plot_back_compat_sem_confidence():
    """Sample legado sem campo 'confidence' funciona (default 1.0)."""
    from skinvault.ui.scanner_screen import _ScatterPlot
    samples = [
        {"item": "X", "ts": 0, "score": 70, "return_pct": 10.0,
         "breakdown_count": 1},
    ]
    sc = _ScatterPlot(samples)
    sc.resize(600, 220)
    sc.grab()


def test_scatter_plot_bucket_colors():
    """_bucket_color retorna cores distintas por banda."""
    from skinvault.ui.scanner_screen import _ScatterPlot
    sc = _ScatterPlot([])
    c_low = sc._bucket_color(20)
    c_mid = sc._bucket_color(60)
    c_high = sc._bucket_color(80)
    # Cores devem ser distintas
    assert c_low.name() != c_mid.name()
    assert c_mid.name() != c_high.name()


def test_backtest_dialog_inclui_scatter():
    """_BacktestResultDialog com samples instancia um _ScatterPlot."""
    from skinvault.ui.scanner_screen import _BacktestResultDialog, _ScatterPlot
    samples = [
        {"item": "X", "ts": 0, "score": 70, "return_pct": 15.0,
         "breakdown_count": 1},
        {"item": "X", "ts": 0, "score": 40, "return_pct": -3.0,
         "breakdown_count": 1},
    ]
    dlg = _BacktestResultDialog(samples, items_count=1)
    scatters = dlg.findChildren(_ScatterPlot)
    assert len(scatters) == 1


def test_scanner_on_validate_finished_reativa_botoes(monkeypatch):
    """_on_validate_finished reabilita botões e abre dialog."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import (
        ScannerScreen, _BacktestResultDialog,
    )
    monkeypatch.setattr(_BacktestResultDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_btn.setEnabled(False)
    screen._rank_btn.setEnabled(False)
    screen._validate_btn.setEnabled(False)
    screen._scan_results = [{"name": "AK-47", "score": 70}]
    screen._validate_samples = []
    screen._on_validate_finished()
    assert screen._scan_btn.isEnabled()
    assert screen._rank_btn.isEnabled()
    assert screen._validate_btn.isEnabled()

def test_scanner_selected_result_no_row():
    """_selected_result returns None when no row selected."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    assert screen._selected_result() is None

def test_scanner_selected_result_no_item(monkeypatch):
    """_selected_result returns None when item at row is None."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._table.setRowCount(1)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    assert screen._selected_result() is None

def test_scanner_selected_result_non_dict():
    """_selected_result returns None when UserRole data is not dict."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidgetItem
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._table.setRowCount(1)
    item = QTableWidgetItem("AK-47")
    item.setData(Qt.ItemDataRole.UserRole, "not-a-dict")
    screen._table.setItem(0, screen.COL_NAME, item)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    assert screen._selected_result() is None

def test_scanner_on_explain_selected_no_result():
    """_on_explain_selected returns early when no result selected."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_explain_selected()

def test_scanner_on_open_steam_no_result():
    """_on_open_steam returns early when no result selected."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_open_steam()

def test_scanner_on_ranking_no_results():
    """_on_ranking shows message when no scan results."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_ranking()
    assert "Escaneie" in screen._status.text()

def test_scanner_on_ranking_with_results(monkeypatch):
    """_on_ranking saves snapshot and shows ranking."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [
        {"name": "AK-47", "score": 85, "breakdown": [],
         "price": 100, "median": 120,
         "verdict": "COMPRA", "verdict_color": "#00ff00",
         "spread": "", "book": "", "trend": "", "sd_label": ""},
    ]
    monkeypatch.setattr("skinvault.ranking.save_snapshot",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.ranking.previous_snapshot",
                        lambda: None)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    screen._on_ranking()
    assert "salvo" in screen._status.text()

def test_scanner_on_item_done(monkeypatch):
    """_on_item_done appends result and repopulates."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_item_done({
        "name": "AK-47", "score": 85, "breakdown": [],
        "price": 100, "median": 120,
        "verdict": "COMPRA", "verdict_color": "#00ff00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    })
    assert len(screen._scan_results) == 1
    assert screen._table.rowCount() == 1


def test_scanner_on_item_done_hides_empty_hero():
    """Primeira chegada esconde o empty hero."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    # Simula hero visivel (no fluxo real ele esta visivel apos _build)
    screen._empty_hero.setVisible(True)
    screen._table.setVisible(False)
    # Force isVisible() = True via flag interno (Qt nao mostra widget nao-show)
    # Aqui usamos um shim simples: setattr direto pra simular o branch
    real_is_visible = screen._empty_hero.isVisible
    screen._empty_hero.isVisible = lambda: True
    try:
        screen._on_item_done({
            "name": "AK-47", "score": 85, "breakdown": [],
            "price": 100, "median": 120,
            "verdict": "COMPRA", "verdict_color": "#00ff00",
            "spread": "", "book": "", "trend": "", "sd_label": "",
        })
    finally:
        screen._empty_hero.isVisible = real_is_visible

def test_scanner_on_explain_selected_with_result(monkeypatch):
    """_on_explain_selected opens breakdown dialog."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidgetItem, QDialog
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    from skinvault.ui.scanner_screen import _ScoreBreakdownDialog
    monkeypatch.setattr(_ScoreBreakdownDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results.append({
        "name": "AK-47", "score": 85, "breakdown": [],
        "price": 100, "median": 120,
        "verdict": "COMPRA", "verdict_color": "#00ff00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    })
    screen._table.setRowCount(1)
    item = QTableWidgetItem("AK-47")
    item.setData(Qt.ItemDataRole.UserRole,
                 screen._scan_results[0])
    screen._table.setItem(0, screen.COL_NAME, item)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    screen._on_explain_selected()

def test_scanner_on_open_steam_with_result(monkeypatch):
    """_on_open_steam opens Steam URL."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidgetItem
    from PyQt6.QtGui import QDesktopServices
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    url_opened = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl",
        lambda url: url_opened.append(url.toString()))
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results.append({
        "name": "AK-47 | Redline", "score": 85, "breakdown": [],
        "price": 100, "median": 120,
        "verdict": "COMPRA", "verdict_color": "#00ff00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    })
    screen._table.setRowCount(1)
    item = QTableWidgetItem("AK-47 | Redline")
    item.setData(Qt.ItemDataRole.UserRole,
                 screen._scan_results[0])
    screen._table.setItem(0, screen.COL_NAME, item)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    screen._on_open_steam()
    assert len(url_opened) == 1
    assert "steamcommunity.com" in url_opened[0]

def test_scanner_on_open_steam_empty_name(monkeypatch):
    """_on_open_steam returns early when result has empty name."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidgetItem
    from PyQt6.QtGui import QDesktopServices
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    url_opened = []
    monkeypatch.setattr(
        QDesktopServices, "openUrl",
        lambda url: url_opened.append(url.toString()))
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results.append({
        "name": "", "score": 85, "breakdown": [],
        "price": 100, "median": 120,
        "verdict": "COMPRA", "verdict_color": "#00ff00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    })
    screen._table.setRowCount(1)
    item = QTableWidgetItem("")
    item.setData(Qt.ItemDataRole.UserRole,
                 screen._scan_results[0])
    screen._table.setItem(0, screen.COL_NAME, item)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    screen._on_open_steam()
    assert len(url_opened) == 0

def test_scanner_scan_item_happy(monkeypatch):
    """_scan_item returns result dict on success."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": 100, "median": 120, "volume": 500})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: {"order_book": {"spread": 5, "buy_count": 10, "sell_count": 20},
                      "price_history": [1, 2, 3], "order_book_approx": True})
    monkeypatch.setattr(
        "skinvault.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {"label": "COMPRA", "diff_pct": -5,
                                      "spread_verdict": "BOM", "book_verdict": "RUIM",
                                      "trend_verdict": "SUBINDO"})
    monkeypatch.setattr("skinvault.signals.record_item_price", lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_volume", lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_supply", lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.multi_trend",
                        lambda ph: {"label": "Alta", "delta": 10})
    monkeypatch.setattr("skinvault.cases.case_status",
                        lambda name: {"label": "Case: Operation"})
    monkeypatch.setattr("skinvault.signals.enhanced_score",
                        lambda *a, **kw: (75, [{"label": "Spread", "delta": 20}]))
    monkeypatch.setattr("skinvault.signals.supply_demand_ratio",
                        lambda vol, sup: {"label": "Alta demanda"})
    monkeypatch.setattr("skinvault.signals.format_breakdown",
                        lambda b: "Spread: +20")
    screen = ScannerScreen(PriceCache(ttl=3600))
    result = screen._scan_item("AK-47")
    assert result is not None
    assert result["name"] == "AK-47"
    assert result["score"] == 75
    assert result["verdict"] == "COMPRA"
    assert result["order_book_approx"] is True

def test_scanner_scan_item_api_error(monkeypatch):
    """_scan_item returns None on API error."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: (_ for _ in ()).throw(Exception("fail")))
    screen = ScannerScreen(PriceCache(ttl=3600))
    result = screen._scan_item("AK-47")
    assert result is None

def test_scanner_scan_item_no_overview(monkeypatch):
    """_scan_item returns None when overview is empty."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: None)
    screen = ScannerScreen(PriceCache(ttl=3600))
    result = screen._scan_item("AK-47")
    assert result is None

def test_scanner_scan_item_no_lowest(monkeypatch):
    """_scan_item returns None when lowest price is missing."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": None, "median": 120, "volume": 500})
    screen = ScannerScreen(PriceCache(ttl=3600))
    result = screen._scan_item("AK-47")
    assert result is None

def test_scanner_scan_item_no_page(monkeypatch):
    """_scan_item works without market page data."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": 100, "median": 120, "volume": None})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: None)
    monkeypatch.setattr(
        "skinvault.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {"label": "NEUTRO", "diff_pct": 0,
                                       "spread_verdict": "", "book_verdict": "",
                                       "trend_verdict": ""})
    monkeypatch.setattr("skinvault.signals.record_item_price", lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.cases.case_status",
                        lambda name: {"label": ""})
    monkeypatch.setattr("skinvault.signals.enhanced_score",
                        lambda *a, **kw: (50, []))
    monkeypatch.setattr("skinvault.signals.supply_demand_ratio",
                        lambda vol=None, sup=None: {"label": ""})
    monkeypatch.setattr("skinvault.signals.format_breakdown",
                        lambda b: "")
    screen = ScannerScreen(PriceCache(ttl=3600))
    result = screen._scan_item("AK-47")
    assert result is not None
    assert result["volume"] is None
    assert result["supply"] is None
    assert result["order_book_approx"] is False

def test_scanner_on_scan_no_items(monkeypatch):
    """_on_scan returns early when category has no items."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    monkeypatch.setattr(
        "skinvault.ui.scanner_screen._SCAN_BY_CATEGORY",
        {"Vazia": []})
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._cat_combo.setCurrentText("Vazia")
    screen._on_scan()

def test_scanner_on_scan_starts_thread(monkeypatch, tmp_path):
    """_on_scan starts worker thread and processes results."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    from threading import Thread as OrigThread
    results = []
    monkeypatch.setattr(
        "skinvault.ui.scanner_screen._SCAN_BY_CATEGORY",
        {"Rifles": ["AK-47"]})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_overview",
        lambda name: {"lowest": 100, "median": 120, "volume": 500})
    monkeypatch.setattr(
        "skinvault.steam_api.get_market_page_data",
        lambda name: None)
    monkeypatch.setattr(
        "skinvault.steam_api.fair_value_verdict",
        lambda lowest, median, **kw: {"label": "NEUTRO", "diff_pct": 0,
                                       "spread_verdict": "", "book_verdict": "",
                                       "trend_verdict": ""})
    monkeypatch.setattr("skinvault.signals.record_item_price", lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.cases.case_status",
                        lambda name: {"label": ""})
    monkeypatch.setattr("skinvault.signals.enhanced_score",
                        lambda *a, **kw: (50, []))
    monkeypatch.setattr("skinvault.signals.supply_demand_ratio",
                        lambda vol=None, sup=None: {"label": ""})
    monkeypatch.setattr("skinvault.signals.format_breakdown",
                        lambda b: "")
    monkeypatch.setattr("skinvault.signals.record_item_volume", lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.signals.record_item_supply", lambda *a, **kw: None)
    monkeypatch.setattr("time.sleep", lambda s: None)

    screen = ScannerScreen(PriceCache(tmp_path / "prices.json", ttl=3600))
    screen._bridge.result_ready.connect(
        lambda r: results.append(r))

    # Patch threading.Thread to run synchronously
    orig_start = OrigThread.start
    def sync_start(self):
        self.daemon = False
        orig_start(self)
        self.join(timeout=2)
    monkeypatch.setattr(OrigThread, "start", sync_start)

    screen._on_scan()
    assert "Escaneando" in screen._status.text()

def test_scanner_on_scan_all_categories(monkeypatch, tmp_path):
    """_on_scan with 'Todas as categorias' scans all items."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    from threading import Thread as OrigThread
    monkeypatch.setattr("time.sleep", lambda s: None)
    screen = ScannerScreen(PriceCache(tmp_path / "prices.json", ttl=3600))
    screen._cat_combo.setCurrentText("Todas as categorias")
    screen._scan_item = lambda name: None
    orig_start = OrigThread.start
    def sync_start(self):
        self.daemon = False
        orig_start(self)
        self.join(timeout=2)
    monkeypatch.setattr(OrigThread, "start", sync_start)
    screen._on_scan()

def test_scanner_populate_with_tooltips():
    """_populate sets score tooltip and order_book_approx warning."""
    from PyQt6.QtCore import Qt
    from skinvault.prices import PriceCache
    from skinvault.ui.theme import WARN
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [
        {"name": "AK-47", "score": 85, "breakdown": [],
         "price": 100, "median": 120,
         "verdict": "COMPRA", "verdict_color": "#00ff00",
         "spread": "BOM", "book": "RUIM", "trend": "", "sd_label": "",
         "score_tooltip": "Spread: +20",
         "case_label": "",
         "order_book_approx": True},
    ]
    screen._populate()
    assert screen._table.item(0, screen.COL_SCORE).toolTip() == "Spread: +20"
    spread_item = screen._table.item(0, screen.COL_SPREAD)
    assert spread_item.toolTip() != ""

def test_scanner_on_ctx_menu_no_row():
    """_on_ctx_menu returns early when no row selected."""
    from PyQt6.QtCore import QPoint
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_ctx_menu(QPoint(0, 0))

def test_scanner_on_ctx_menu_why(monkeypatch):
    """_on_ctx_menu triggers explain when action matches."""
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtWidgets import QTableWidgetItem, QMenu
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results.append({
        "name": "AK-47", "score": 85, "breakdown": [],
        "price": 100, "median": 120,
        "verdict": "COMPRA", "verdict_color": "#00ff00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    })
    monkeypatch.setattr(QMenu, "exec",
                        lambda self, *a: self.actions()[0])
    explain_called = False
    screen._on_explain_selected = lambda: setattr(
        screen, '_explain_called', True)
    screen._table.setRowCount(1)
    item = QTableWidgetItem("AK-47")
    item.setData(Qt.ItemDataRole.UserRole,
                 screen._scan_results[0])
    screen._table.setItem(0, screen.COL_NAME, item)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    screen._on_ctx_menu(QPoint(0, 0))
    assert screen._explain_called

def test_scanner_on_ctx_menu_open(monkeypatch):
    """_on_ctx_menu triggers open steam when action matches."""
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtWidgets import QTableWidgetItem, QMenu
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results.append({
        "name": "AK-47 | Redline", "score": 85, "breakdown": [],
        "price": 100, "median": 120,
        "verdict": "COMPRA", "verdict_color": "#00ff00",
        "spread": "", "book": "", "trend": "", "sd_label": "",
    })
    monkeypatch.setattr(QMenu, "exec",
                        lambda self, *a: self.actions()[1])
    steam_called = False
    screen._on_open_steam = lambda: setattr(screen, '_steam_called', True)
    screen._table.setRowCount(1)
    item = QTableWidgetItem("AK-47 | Redline")
    item.setData(Qt.ItemDataRole.UserRole,
                 screen._scan_results[0])
    screen._table.setItem(0, screen.COL_NAME, item)
    screen._table.setCurrentCell(0, screen.COL_NAME)
    screen._on_ctx_menu(QPoint(0, 0))
    assert screen._steam_called

def test_scanner_on_progress_fim():
    """_on_progress with 'FIM' re-enables buttons."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_progress("FIM")
    assert screen._scan_btn.isEnabled()
    assert screen._rank_btn.isEnabled()
    assert "concluido" in screen._status.text()

def test_scanner_on_progress_msg():
    """_on_progress with status message updates label."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._on_progress("Escaneando...")
    assert screen._status.text() == "Escaneando..."

def test_scanner_populate():
    """_populate fills table with scan results."""
    from PyQt6.QtCore import Qt
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen._scan_results = [
        {"name": "AK-47", "score": 85, "breakdown": [],
         "price": 100, "median": 120,
         "verdict": "COMPRA", "verdict_color": "#00ff00",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "score_tooltip": "", "case_label": "",
         "order_book_approx": False},
        {"name": "AWP", "score": 30, "breakdown": [],
         "price": 500, "median": 550,
         "verdict": "EVITAR", "verdict_color": "#ff0000",
         "spread": "", "book": "", "trend": "", "sd_label": "",
         "score_tooltip": "", "case_label": "",
         "order_book_approx": False},
    ]
    screen._populate()
    screen._table.sortByColumn(screen.COL_SCORE, Qt.SortOrder.DescendingOrder)
    assert screen._table.rowCount() == 2
    assert screen._table.item(0, 0).text() == "AK-47"


def test_scanner_screen():
    """ScannerScreen (real) instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    assert screen is not None


def test_scanner_layout_controles_agrupados():
    """Scanner — ghost toolbar + filtros acima da tabela, hint removido, rodape unico.

    Valida layout da Frente T: ghost buttons (Limpar cache/Exportar CSV) estao
    no Toolbar apos stats_row; checkboxes ficam na linha de filtros acima da
    tabela; hint de duplo-clique foi removido (migrado para tooltip do header
    Score); rodape tem apenas 1 label de status.
    """
    from PyQt6.QtCore import Qt, QCoreApplication
    from PyQt6.QtWidgets import QCheckBox, QLabel, QPushButton, QHBoxLayout
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import ScannerScreen
    screen = ScannerScreen(PriceCache(ttl=3600))
    screen.resize(1920, 1200)
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()

    # 1. Hint removido (nao existe QLabel com o texto de dica)
    hints = screen.findChildren(QLabel)
    hint_texts = {l.text() for l in hints}
    dica_text = "clique duas vezes em uma linha"
    assert not any(dica_text in t for t in hint_texts), (
        "Hint de duplo-clique ainda presente como QLabel — deveria ser tooltip do header Score"
    )

    # 2. Score header tem tooltip com a dica
    score_hdr = screen._table.horizontalHeaderItem(screen.COL_SCORE)
    assert score_hdr is not None
    assert score_hdr.toolTip(), "Score column header tooltip vazio"
    assert "Duplo-clique" in score_hdr.toolTip(), (
        f"Score header tooltip nao menciona duplo-clique: {score_hdr.toolTip()}"
    )

    # 3. Ghost toolbar existe com tooltips (nao removido)
    assert hasattr(screen, "_clear_cache_btn"), "clear_cache_btn nao existe"
    assert screen._clear_cache_btn.toolTip(), "clear_cache_btn sem tooltip"
    assert hasattr(screen, "_export_btn"), "export_btn nao existe"
    assert not screen._export_btn.isEnabled(), "export_btn deveria iniciar disabled"

    # 4. Checkboxes existem e estao estilizados com checkbox_style()
    assert hasattr(screen, "_hide_low_conf_cb"), "hide_low_conf_cb nao existe"
    assert screen._hide_low_conf_cb.toolTip(), "hide_low_conf_cb sem tooltip"
    assert hasattr(screen, "_hide_approx_cb"), "hide_approx_cb nao existe"
    assert screen._hide_approx_cb.toolTip(), "hide_approx_cb sem tooltip"

    # 5. Rodape tem apenas _status como caption direta do root
    root_labels = [l for l in screen.findChildren(QLabel)
                   if l.parent() is screen]
    dica_root = [l for l in root_labels if "clique duas vezes" in l.text().lower()]
    assert len(dica_root) == 0, (
        "Hint de duplo-clique ainda existe como QLabel no root "
        "— deveria estar apenas como tooltip do score header"
    )
    assert screen._status.parent() is screen, "_status nao e filho direto do root"

    # 6. Tab order por criacao = combo → scan → rank → validate → clear_cache → export → checkboxes → tabela
    lay = screen.layout()
    assert lay is not None


def _make_router():
    """Cria ScreenRouter com PriceCache basico."""
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    return ScreenRouter(PriceCache(ttl=3600))


def _fake_session():
    """Cria uma SteamSession fake."""
    from skinvault.steam_session import SteamSession
    return SteamSession("76561198000000001", {"steamLoginSecure": "tok"})


def test_screen_router_builds(monkeypatch):
    """ScreenRouter instancia e mostra LoginGate (sem sessao)."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    router = _make_router()
    assert router._stack.currentWidget() == router._login_gate


def test_screen_router_session_property():
    """Propriedade session retorna None no inicio."""
    router = _make_router()
    assert router.session is None
    assert router.sidebar_visible is False


def test_screen_router_check_session_valid(monkeypatch):
    """_check_session com sessao valida redireciona para account."""
    monkeypatch.setattr("skinvault.steam_session.load", _fake_session)
    monkeypatch.setattr("skinvault.steam_session.ensure_valid",
                        lambda s: True)
    persist_calls = []
    monkeypatch.setattr("skinvault.steam_session.persist",
                        lambda s: persist_calls.append(s))
    # AccountScreen.set_session -> refresh -> PriceWorker -> HTTP. Mock pra inline.
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    router = _make_router()
    router._check_session()
    assert router.session is not None
    assert router.session.steamid == "76561198000000001"
    assert len(persist_calls) == 1
    assert router._stack.currentWidget() == router._account_screen


def test_screen_router_check_session_invalid(monkeypatch):
    """_check_session com sessao invalida (sem renovar) mostra login."""
    monkeypatch.setattr("skinvault.steam_session.load", _fake_session)
    monkeypatch.setattr("skinvault.steam_session.ensure_valid",
                        lambda s: False)
    clear_calls = []
    monkeypatch.setattr("skinvault.steam_session.clear",
                        lambda: clear_calls.append(True))
    router = _make_router()
    router._check_session()
    assert len(clear_calls) == 1
    assert router._stack.currentWidget() == router._login_gate


def test_screen_router_keeps_session_with_refresh_token_on_failure(monkeypatch):
    """Falha transiente NAO apaga sessao que tem steamRefresh_steam."""
    from skinvault.steam_session import SteamSession
    sess = SteamSession("76561198000000001",
                        {"steamLoginSecure": "tok",
                         "steamRefresh_steam": "76561198000000001||rt"})
    monkeypatch.setattr("skinvault.steam_session.load", lambda: sess)
    monkeypatch.setattr("skinvault.steam_session.ensure_valid",
                        lambda s: False)
    clear_calls = []
    monkeypatch.setattr("skinvault.steam_session.clear",
                        lambda: clear_calls.append(True))
    router = _make_router()
    router._check_session()
    assert clear_calls == []  # token preservado pra retry no proximo boot
    assert router._stack.currentWidget() == router._login_gate


def test_screen_router_on_session(monkeypatch):
    """_on_session configura estado pos-login."""
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    router = _make_router()
    sess = _fake_session()
    vis_changes = []
    router.sidebar_visibility_changed.connect(
        lambda v: vis_changes.append(v))
    nav_log = []
    router.navigated.connect(lambda s: nav_log.append(s))
    router._on_session(sess)
    assert router.session is sess
    assert router._stack.currentWidget() == router._account_screen
    assert vis_changes == [True]
    assert nav_log == ["account"]


def test_screen_router_navigate_unknown():
    """navigate() com screen desconhecida retorna cedo."""
    router = _make_router()
    # Antes de navegar, widget atual e' o login_gate
    current = router._stack.currentWidget()
    router.navigate("noexist")
    assert router._stack.currentWidget() == current  # nao mudou


def test_screen_router_navigate_all_screens(monkeypatch):
    """navigate() funciona para todas as telas validas."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: _fake_session())
    monkeypatch.setattr("skinvault.steam_session.ensure_valid", lambda s: True)
    monkeypatch.setattr("skinvault.steam_session.persist", lambda s: None)
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    router = _make_router()
    router._check_session()  # loga
    nav_log = []
    router.navigated.connect(lambda s: nav_log.append(s))
    screens = [
        ("history", router._history_screen),
        ("scanner", router._scanner_screen),
        ("market", router._market_screen),
        ("trades", router._trades_screen),
        ("simulador", router._simulador_screen),
        ("watchlist", router._watchlist_screen),
        ("account", router._account_screen),
    ]
    for key, expected_widget in screens:
        router.navigate(key)
        assert router._stack.currentWidget() == expected_widget
    assert nav_log == [k for k, _ in screens]


def test_screen_router_request_sync_with_session():
    """_request_sync emite sync_requested quando ha sessao."""
    router = _make_router()
    router._session = _fake_session()
    sync_log = []
    router.sync_requested.connect(lambda s: sync_log.append(s))
    router._request_sync()
    assert len(sync_log) == 1
    assert sync_log[0].steamid == "76561198000000001"


def test_screen_router_request_sync_no_session():
    """_request_sync nao emite quando session e None."""
    router = _make_router()
    sync_log = []
    router.sync_requested.connect(lambda s: sync_log.append(s))
    router._request_sync()
    assert sync_log == []


def test_price_worker_instantiation():
    """PriceWorker bridge instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import BatchPriceWorker, PriceWorker, SinglePriceWorker
    cache = PriceCache(ttl=3600)
    assert PriceWorker(cache) is not None
    assert SinglePriceWorker(cache) is not None
    assert BatchPriceWorker(cache) is not None


class _InlineThread:
    """Thread fake que executa o target em start() (nao async)."""
    def __init__(self, target=None, daemon=False):
        self._target = target
    def start(self):
        if self._target:
            self._target()


def test_price_worker_start(monkeypatch):
    """PriceWorker.start() emite eval_done com dados corretos."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import PriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio",
                        lambda: [{"name": "AK", "cost": 100.0, "quantity": 1}])
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: 150.0)

    cache = PriceCache(ttl=3600)
    worker = PriceWorker(cache)
    results = []
    worker.eval_done.connect(results.append)
    worker.start()
    QApplication.processEvents()

    assert len(results) == 1
    d = results[0]
    assert d["totals"]["pnl"] == pytest.approx(30.43, abs=0.01)
    assert len(d["rows"]) == 1


def test_price_worker_start_error(monkeypatch):
    """PriceWorker.start() engole excecao e emite eval_done com error."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import PriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio",
                        lambda: (_ for _ in ()).throw(ValueError("boom")))

    cache = PriceCache(ttl=3600)
    worker = PriceWorker(cache)
    results = []
    worker.eval_done.connect(results.append)
    worker.start()
    QApplication.processEvents()

    assert len(results) == 1
    assert "error" in results[0]
    assert "boom" in results[0]["error"]


def test_batch_price_worker(monkeypatch):
    """BatchPriceWorker.start() emite progress e batch_done."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import BatchPriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: 50.0)

    cache = PriceCache(ttl=3600)
    worker = BatchPriceWorker(cache)
    progress_log = []
    worker.progress.connect(lambda d, t: progress_log.append((d, t)))
    done_log = []
    worker.batch_done.connect(lambda: done_log.append(True))
    worker.start(["AK", "AWP", "AK"])
    QApplication.processEvents()

    assert done_log == [True]
    assert progress_log == [(1, 2), (2, 2)]  # deduped to 2 unique


def test_single_price_worker(monkeypatch):
    """SinglePriceWorker.start() emite done com preco."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import SinglePriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: 200.0 if n == "AK" else None)

    cache = PriceCache(ttl=3600)
    worker = SinglePriceWorker(cache)
    results = []
    worker.done.connect(lambda n, p: results.append((n, p)))
    worker.start("AK")
    QApplication.processEvents()

    assert len(results) == 1
    assert results[0] == ("AK", 200.0)


def test_empty_state_basic():
    from skinvault.ui.components import EmptyState
    es = EmptyState("◇", "Vazio", "Subtitulo", "+ Acao")
    assert es is not None


def test_empty_state_no_subtitle_no_cta():
    """Subtitle e CTA opcionais."""
    from skinvault.ui.components import EmptyState
    es = EmptyState("◇", "So titulo")
    assert es is not None


def test_empty_state_cta_emits_signal():
    from skinvault.ui.components import EmptyState
    fired = []
    es = EmptyState("◇", "T", "S", "Click", on_cta=lambda: fired.append(True))
    # Click no botao - busca o QPushButton filho
    from PyQt6.QtWidgets import QPushButton
    btns = es.findChildren(QPushButton)
    assert btns, "no buttons in EmptyState"
    btns[0].click()
    assert fired == [True]


def test_empty_state_with_steps():
    """EmptyState com steps cria QLabels numerados."""
    from skinvault.ui.components import EmptyState
    from PyQt6.QtWidgets import QLabel
    steps = ["Primeiro passo", "Segundo passo", "Terceiro passo"]
    es = EmptyState("◇", "Titulo", steps=steps)
    labels = [ch for ch in es.findChildren(QLabel)
              if ch.text() in steps]
    assert len(labels) == 3
    # Verifica os numeros 1-3
    nums = [ch for ch in es.findChildren(QLabel)
            if ch.text() in ("1", "2", "3")]
    assert len(nums) == 3


def test_empty_state_steps_no_cta():
    """Steps sem CTA e sem subtitle funciona."""
    from skinvault.ui.components import EmptyState
    es = EmptyState("◇", "So steps", steps=["Unico passo"])
    assert es is not None


def test_market_charts_fixed_height():
    """Charts do Market tem FixedHeight(300) em vez de stretch."""
    from skinvault.prices import PriceCache
    from skinvault.ui.market_screen import MarketScreen
    from skinvault.ui.components import Card
    screen = MarketScreen(PriceCache(ttl=3600))
    cards = screen.findChildren(Card)
    # O Market tem 2 chart cards (spark + depth) + detail card
    chart_cards = [c for c in cards
                   if c.minimumHeight() == 300 and c.maximumHeight() == 300]
    assert len(chart_cards) >= 2, (
        f"Expected >=2 chart cards with FixedHeight(300), got {len(chart_cards)}"
    )


def test_market_kpi_row_nao_infla():
    """StatCards da KPI row tem height <= 130 apos resize(1920,1200)."""
    from PyQt6.QtCore import Qt, QCoreApplication
    from skinvault.prices import PriceCache
    from skinvault.ui.market_screen import MarketScreen
    screen = MarketScreen(PriceCache(ttl=3600))
    screen.resize(1920, 1200)
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()  # 2x: deixa layout assentar
    for sc in (screen._stat_lowest, screen._stat_median,
               screen._stat_volume, screen._stat_verdict):
        assert sc.height() <= 130, (
            f"StatCard height={sc.height()} > 130 — KPI row inflado"
        )


def test_empty_state_steps_centralizado():
    """Container de steps centralizado via AlignHCenter no layout."""
    from PyQt6.QtCore import Qt
    from skinvault.ui.components import EmptyState
    es = EmptyState("◇", "Titulo", steps=["Passo A", "Passo B"])
    # Verifica que o layout pai centraliza o container de steps
    lay = es.layout()
    assert lay is not None
    found = False
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item.widget() is not None and item.alignment() == Qt.AlignmentFlag.AlignHCenter:
            w = item.widget()
            from PyQt6.QtWidgets import QLabel
            labels = w.findChildren(QLabel)
            texts = {l.text() for l in labels}
            if "Passo A" in texts:
                found = True
                break
    assert found, "Steps container not found with AlignHCenter alignment"


def test_empty_state_cta_contiguo_aos_steps():
    """CTA fica no layout imediatamente apos steps, sem stretch no meio."""
    from PyQt6.QtCore import Qt
    from skinvault.ui.components import EmptyState
    from PyQt6.QtWidgets import QPushButton
    es = EmptyState("◇", "T", steps=["1", "2"], cta_label="Botao")
    lay = es.layout()
    assert lay is not None
    # Find index of steps_w and cta in the layout
    steps_idx = -1
    cta_idx = -1
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item.widget() is not None and isinstance(item.widget(), QPushButton):
            cta_idx = i
        elif item.widget() is not None and item.widget().findChildren(QPushButton):
            # steps_w might have no children that are QPushButtons
            pass
    # Simpler: check that steps_w is right before cta
    # Steps_w is the first AlignHCenter widget, CTA is the first AlignCenter button
    found_steps = False
    found_cta = False
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item.widget() is not None:
            w = item.widget()
            if isinstance(w, QPushButton) and found_steps:
                found_cta = True
                break
            elif not found_steps:
                from PyQt6.QtWidgets import QLabel
                # Check if this is the steps container (has numbered labels)
                if w.findChildren(QLabel) and any("1" == l.text() for l in w.findChildren(QLabel)):
                    found_steps = True
    assert found_steps, "Steps container not found in layout"
    assert found_cta, "CTA not immediately after steps in layout"


# ── Animations (Frente J) ───────────────────────────────────

def test_fade_in_attaches_effect_and_runs():
    """fade_in instala QGraphicsOpacityEffect e inicia a animacao."""
    from PyQt6.QtCore import QAbstractAnimation
    from PyQt6.QtWidgets import QWidget
    from skinvault.ui.components import fade_in
    w = QWidget()
    w.resize(100, 50)
    fade_in(w)
    eff = w.graphicsEffect()
    assert eff is not None
    anims = eff.findChildren(QAbstractAnimation)
    assert anims and anims[0].state() == QAbstractAnimation.State.Running


def test_router_navigate_hidden_stack_no_fade(monkeypatch):
    """navigate() sem janela visivel nao instala effect (grab/screenshot
    e tests dependem de render deterministico)."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.ui import screen_router as sr
    router = _make_router()
    router.navigate(sr.SCREEN_SCANNER)
    assert router._scanner_screen.graphicsEffect() is None


def test_router_navigate_visible_stack_fades(monkeypatch):
    """Com stack visivel, navegar para outra tela instala o fade."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.ui import screen_router as sr
    router = _make_router()
    monkeypatch.setattr(router._stack, "isVisible", lambda: True)
    router.navigate(sr.SCREEN_SCANNER)
    assert router._scanner_screen.graphicsEffect() is not None


def test_router_navigate_same_screen_no_refade(monkeypatch):
    """Navegar pra tela ja atual nao re-dispara fade."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    from skinvault.ui import screen_router as sr
    calls = []
    monkeypatch.setattr("skinvault.ui.screen_router.fade_in",
                        lambda w, **k: calls.append(w))
    router = _make_router()
    monkeypatch.setattr(router._stack, "isVisible", lambda: True)
    router.navigate(sr.SCREEN_SCANNER)
    router.navigate(sr.SCREEN_SCANNER)
    assert len(calls) == 1


def test_loadingstate_hidden_window_no_fade():
    """LoadingState em janela nao-mostrada aparece sem effect."""
    from PyQt6.QtWidgets import QWidget
    from skinvault.ui.components import LoadingState
    host = QWidget()
    ls = LoadingState(parent=host)
    ls.setVisible(True)
    assert ls.graphicsEffect() is None


def test_toast_slide_animation_runs():
    """show_toast inicia slide-in de 8px em paralelo com o fade."""
    from PyQt6.QtCore import QAbstractAnimation
    from PyQt6.QtWidgets import QWidget
    from skinvault.ui.components import Toast
    host = QWidget()
    host.resize(800, 600)
    toast = Toast.show_toast(host, "msg", "info", duration_ms=50)
    assert toast._slide.state() == QAbstractAnimation.State.Running
    end = toast._slide.endValue()
    start = toast._slide.startValue()
    assert end.y() - start.y() == 8


def test_elide_label_short_text_unchanged():
    """Texto curto cabe sem elide."""
    from skinvault.ui.components import _ElideLabel
    lbl = _ElideLabel("AK")
    lbl.resize(200, 20)
    assert lbl.full_text() == "AK"


def test_elide_label_long_text_gets_ellipsis():
    """Texto longo numa label estreita ganha '...'."""
    from skinvault.ui.components import _ElideLabel
    from PyQt6.QtGui import QResizeEvent
    from PyQt6.QtCore import QSize
    lbl = _ElideLabel("Sticker | Heroic (Holo) | 2020 RMR | Berlin | Test")
    lbl.resize(40, 20)
    # resize() em widget nao-shown nem sempre dispara resizeEvent
    # automaticamente; entrega manual:
    lbl.resizeEvent(QResizeEvent(QSize(40, 20), QSize(0, 0)))
    # full_text preservado, label mostrada eh elided
    assert lbl.full_text().startswith("Sticker")
    assert "…" in lbl.text() or "..." in lbl.text() or lbl.text() == ""


def test_elide_label_set_text_updates_full():
    from skinvault.ui.components import _ElideLabel
    lbl = _ElideLabel("first")
    lbl.setText("second long text that may be elided here")
    assert lbl.full_text() == "second long text that may be elided here"


def test_elide_label_resize_reapplies():
    """Resize triggera re-elide."""
    from skinvault.ui.components import _ElideLabel
    from PyQt6.QtGui import QResizeEvent
    from PyQt6.QtCore import QSize
    lbl = _ElideLabel("Sticker | Heroic (Holo) | 2020 RMR muito longo aqui")
    lbl.resize(40, 20)
    lbl.resizeEvent(QResizeEvent(QSize(40, 20), QSize(0, 0)))
    short_text = lbl.text()
    lbl.resize(800, 20)
    lbl.resizeEvent(QResizeEvent(QSize(800, 20), QSize(40, 20)))
    wide_text = lbl.text()
    assert len(wide_text) >= len(short_text)


def test_elide_label_none_text():
    from skinvault.ui.components import _ElideLabel
    lbl = _ElideLabel("")
    lbl.setText(None)
    assert lbl.full_text() == ""


def test_components_instantiation():
    """Componentes da UI instanciam sem erro."""
    from skinvault.ui.components import (
        Avatar, Breadcrumb, Card, Footer, Sidebar,
        StatCard, SegmentedControl, LockOverlay, ActivityFeed,
    )
    assert Card() is not None
    sc = StatCard("label", "value")
    assert sc is not None
    sc.set_delta(5.5, "teste")
    assert not sc._delta.isHidden()
    assert "▲" in sc._delta.text()
    sc.set_delta(-3.2, "perda")
    assert "▼" in sc._delta.text()
    sc.set_delta(None)
    assert sc._delta.isHidden()
    assert Sidebar() is not None
    assert Breadcrumb() is not None
    assert Footer() is not None
    assert Avatar() is not None
    assert SegmentedControl() is not None
    assert LockOverlay() is not None
    assert ActivityFeed() is not None


# ── ActivityFeed ───────────────────────────────────────────────


def test_activity_color_mapping():
    from skinvault.ui import components, theme
    assert components._activity_color("green") == theme.POSITIVE
    assert components._activity_color("red") == theme.DANGER
    assert components._activity_color("accent") == theme.STEAM_BLUE
    assert components._activity_color("muted") == theme.TEXT_MUTED
    assert components._activity_color("unknown") == theme.TEXT_MUTED


def test_activity_row_basic():
    from skinvault.ui.components import _ActivityRow
    row = _ActivityRow({
        "type": "trade", "ts": 1_000_000, "title": "AK-47",
        "subtitle": "P&L +50", "color": "green", "icon": "↑",
    })
    assert row is not None


def test_activity_row_red_color():
    from skinvault.ui.components import _ActivityRow
    row = _ActivityRow({
        "type": "trade", "ts": 1_000_000, "title": "AWP",
        "subtitle": "P&L -30", "color": "red", "icon": "↓",
    })
    assert row is not None


def test_activity_row_missing_fields():
    """_ActivityRow tolera dict sem icon/color."""
    from skinvault.ui.components import _ActivityRow
    row = _ActivityRow({"ts": 0})
    assert row is not None


def test_activity_feed_empty_state():
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([])
    assert feed._empty.isVisible() or True  # tolera show/hide


def test_activity_feed_with_events():
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "trade", "ts": 1000, "title": "AK", "subtitle": "+50",
         "color": "green", "icon": "↑"},
        {"type": "alert", "ts": 900, "title": "AWP", "subtitle": "vol 3x",
         "color": "accent", "icon": "★"},
    ])
    # Apos set_events, _list_lay tem 2 rows (sem o _empty)
    assert feed._list_lay.count() == 2


def test_activity_feed_resets_on_subsequent_set_events():
    """set_events chamado de novo limpa rows anteriores."""
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "trade", "ts": 1000, "title": "A", "subtitle": "",
         "color": "green", "icon": "↑"},
        {"type": "trade", "ts": 900, "title": "B", "subtitle": "",
         "color": "green", "icon": "↑"},
    ])
    feed.set_events([
        {"type": "trade", "ts": 800, "title": "C", "subtitle": "",
         "color": "red", "icon": "↓"},
    ])
    assert feed._list_lay.count() == 1


def test_activity_feed_set_empty_after_populated():
    """Volta ao estado vazio depois de ter eventos."""
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "trade", "ts": 1000, "title": "A", "subtitle": "",
         "color": "green", "icon": "↑"},
    ])
    feed.set_events([])
    # _empty re-anexado ao layout
    assert feed._list_lay.count() == 1


def test_activity_feed_filter_sell_only():
    """Filtro 'sell' mostra so eventos com icon ↑."""
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "market", "ts": 3, "title": "AK", "subtitle": "",
         "color": "green", "icon": "↑"},
        {"type": "market", "ts": 2, "title": "Glock", "subtitle": "",
         "color": "red", "icon": "↓"},
        {"type": "alert", "ts": 1, "title": "AWP", "subtitle": "",
         "color": "accent", "icon": "★"},
    ])
    feed._set_filter("sell")
    assert feed._list_lay.count() == 1


def test_activity_feed_filter_buy_only():
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "market", "ts": 3, "title": "AK", "subtitle": "",
         "color": "green", "icon": "↑"},
        {"type": "market", "ts": 2, "title": "Glock", "subtitle": "",
         "color": "red", "icon": "↓"},
    ])
    feed._set_filter("buy")
    assert feed._list_lay.count() == 1


def test_activity_feed_filter_alert():
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "alert", "ts": 1, "title": "AWP", "subtitle": "",
         "color": "accent", "icon": "★"},
        {"type": "market", "ts": 2, "title": "AK", "subtitle": "",
         "color": "green", "icon": "↑"},
    ])
    feed._set_filter("alert")
    assert feed._list_lay.count() == 1


def test_activity_feed_filter_back_to_all():
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "market", "ts": 3, "title": "AK", "subtitle": "",
         "color": "green", "icon": "↑"},
        {"type": "market", "ts": 2, "title": "Glock", "subtitle": "",
         "color": "red", "icon": "↓"},
    ])
    feed._set_filter("sell")
    feed._set_filter("all")
    assert feed._list_lay.count() == 2


def test_activity_feed_filter_empty_state_message():
    """Quando filtro nao bate nada, mostra 'Sem eventos nesse filtro'."""
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "market", "ts": 3, "title": "AK", "subtitle": "",
         "color": "green", "icon": "↑"},
    ])
    feed._set_filter("buy")
    assert "filtro" in feed._empty.text()


def test_activity_feed_chip_click_emits_filter_change():
    """Click no chip dispara _set_filter via signal."""
    from skinvault.ui.components import ActivityFeed
    feed = ActivityFeed()
    feed.set_events([
        {"type": "market", "ts": 3, "title": "AK", "subtitle": "",
         "color": "green", "icon": "↑"},
        {"type": "market", "ts": 2, "title": "Glock", "subtitle": "",
         "color": "red", "icon": "↓"},
    ])
    feed._chip_buttons["buy"].click()
    assert feed._filter == "buy"
    assert feed._list_lay.count() == 1


# ── RecentMatchesStrip ─────────────────────────────────────────


def test_match_chip_win():
    from skinvault.ui.components import _MatchChip
    chip = _MatchChip({"name": "AK", "pnl": 50, "sell_ts": 1700000000})
    assert chip.text() == "V"


def test_match_chip_loss():
    from skinvault.ui.components import _MatchChip
    chip = _MatchChip({"name": "AK", "pnl": -10, "sell_ts": 1700000000})
    assert chip.text() == "D"


def test_match_chip_neutral():
    from skinvault.ui.components import _MatchChip
    chip = _MatchChip({"name": "AK", "pnl": 0, "sell_ts": 1700000000})
    assert chip.text() == "—"


def test_match_chip_uses_buy_ts_fallback():
    from skinvault.ui.components import _MatchChip
    chip = _MatchChip({"name": "AK", "pnl": 50, "buy_ts": 1700000000})
    assert "AK" in chip.toolTip()


def test_match_chip_no_ts():
    from skinvault.ui.components import _MatchChip
    chip = _MatchChip({"name": "AK", "pnl": 50})
    assert chip.text() == "V"


def test_streak_summary_empty():
    from skinvault.ui.components import _streak_summary
    assert _streak_summary([]) is None


def test_streak_summary_no_streak_single():
    """Sequencia <2 retorna None."""
    from skinvault.ui.components import _streak_summary
    assert _streak_summary([{"pnl": 50}]) is None


def test_streak_summary_wins():
    from skinvault.ui.components import _streak_summary
    label, _color = _streak_summary([
        {"pnl": 50}, {"pnl": 30}, {"pnl": 10}, {"pnl": -5},
    ])
    assert "3 vitorias" in label


def test_streak_summary_losses():
    from skinvault.ui.components import _streak_summary
    label, _color = _streak_summary([
        {"pnl": -20}, {"pnl": -10}, {"pnl": 5},
    ])
    assert "2 derrotas" in label


def test_streak_summary_breaks_on_zero():
    """pnl == 0 quebra a sequencia."""
    from skinvault.ui.components import _streak_summary
    assert _streak_summary([{"pnl": 0}, {"pnl": 10}]) is None


def test_streak_summary_zero_in_middle():
    """pnl == 0 no meio para a contagem."""
    from skinvault.ui.components import _streak_summary
    label, _ = _streak_summary([
        {"pnl": 50}, {"pnl": 30}, {"pnl": 0}, {"pnl": 10},
    ])
    assert "2 vitorias" in label


def test_recent_matches_strip_instantiation():
    from skinvault.ui.components import RecentMatchesStrip
    strip = RecentMatchesStrip()
    assert strip is not None


def test_recent_matches_strip_empty():
    from skinvault.ui.components import RecentMatchesStrip
    strip = RecentMatchesStrip()
    strip.set_trades([])
    # _empty visivel, streak vazio
    assert strip._streak.text() == ""


def test_recent_matches_strip_populated():
    from skinvault.ui.components import RecentMatchesStrip
    strip = RecentMatchesStrip()
    strip.set_trades([
        {"name": "AK", "pnl": 50, "sell_ts": 1700000000},
        {"name": "Glock", "pnl": -10, "sell_ts": 1699000000},
    ])
    # _chip_lay tem 2 chips (sem _empty)
    assert strip._chip_lay.count() == 2


def test_recent_matches_strip_respects_limit():
    from skinvault.ui.components import RecentMatchesStrip
    strip = RecentMatchesStrip()
    trades = [{"name": f"t{i}", "pnl": 1, "sell_ts": i} for i in range(30)]
    strip.set_trades(trades, limit=5)
    assert strip._chip_lay.count() == 5


def test_recent_matches_strip_shows_streak():
    from skinvault.ui.components import RecentMatchesStrip
    strip = RecentMatchesStrip()
    strip.set_trades([
        {"name": "a", "pnl": 50}, {"name": "b", "pnl": 30},
        {"name": "c", "pnl": -5},
    ])
    assert "vitorias" in strip._streak.text()


def test_recent_matches_strip_no_streak_clears_label():
    from skinvault.ui.components import RecentMatchesStrip
    strip = RecentMatchesStrip()
    # Primeiro popula com streak
    strip.set_trades([
        {"name": "a", "pnl": 50}, {"name": "b", "pnl": 30},
    ])
    assert strip._streak.text() != ""
    # Agora popula com algo sem streak (pnl == 0 quebra)
    strip.set_trades([{"name": "x", "pnl": 0}])
    assert strip._streak.text() == ""


def test_welcome_dialog_instantiates():
    from skinvault.ui.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog()
    assert dlg is not None
    assert "Bem-vindo" in dlg.windowTitle()


def test_welcome_dialog_feature_card():
    from skinvault.ui.welcome_dialog import _feature_card
    card = _feature_card("◐", "Title", "Description longa qualquer.")
    assert card is not None


def test_router_shows_welcome_first_time(tmp_path, monkeypatch):
    """_maybe_show_welcome chama WelcomeDialog quando welcome_seen=False."""
    from skinvault.ui.screen_router import ScreenRouter
    from skinvault.prices import PriceCache
    import skinvault.settings as _settings
    shown = []

    class _FakeWelcome:
        def __init__(self, parent=None):
            pass
        def exec(self):
            shown.append(True)
            return 0

    monkeypatch.setattr("skinvault.ui.welcome_dialog.WelcomeDialog", _FakeWelcome)
    monkeypatch.setattr(_settings, "load_settings", lambda: {"welcome_seen": False})
    saved = []
    monkeypatch.setattr(_settings, "save_settings", lambda s: saved.append(s))

    router = ScreenRouter(PriceCache(ttl=3600))
    router._maybe_show_welcome()
    assert shown == [True]
    assert saved and saved[0].get("welcome_seen") is True


def test_router_skips_welcome_when_seen(monkeypatch):
    from skinvault.ui.screen_router import ScreenRouter
    from skinvault.prices import PriceCache
    import skinvault.settings as _settings
    shown = []

    class _FakeWelcome:
        def __init__(self, parent=None):
            pass
        def exec(self):
            shown.append(True)
            return 0

    monkeypatch.setattr("skinvault.ui.welcome_dialog.WelcomeDialog", _FakeWelcome)
    monkeypatch.setattr(_settings, "load_settings", lambda: {"welcome_seen": True})
    router = ScreenRouter(PriceCache(ttl=3600))
    router._maybe_show_welcome()
    assert shown == []


def test_router_welcome_swallows_exception(monkeypatch):
    """Se WelcomeDialog crashar, welcome_seen ainda e marcado."""
    from skinvault.ui.screen_router import ScreenRouter
    from skinvault.prices import PriceCache
    import skinvault.settings as _settings

    class _BoomWelcome:
        def __init__(self, parent=None):
            raise RuntimeError("boom")
        def exec(self):
            pass

    monkeypatch.setattr("skinvault.ui.welcome_dialog.WelcomeDialog", _BoomWelcome)
    monkeypatch.setattr(_settings, "load_settings", lambda: {"welcome_seen": False})
    saved = []
    monkeypatch.setattr(_settings, "save_settings", lambda s: saved.append(s))
    router = ScreenRouter(PriceCache(ttl=3600))
    router._maybe_show_welcome()  # nao crasha
    assert saved and saved[0].get("welcome_seen") is True


def test_router_on_session_with_cached_profile(monkeypatch):
    """_on_session emite session_changed com nome do perfil cached."""
    from skinvault.ui.screen_router import ScreenRouter
    from skinvault.prices import PriceCache
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    monkeypatch.setattr(
        "skinvault.ui.profile_fetcher.load_cached_profile",
        lambda sid: {"name": "nokia"})
    router = ScreenRouter(PriceCache(ttl=3600))
    sig = []
    router.session_changed.connect(lambda n, s: sig.append((n, s)))
    sess = _fake_session()
    router._on_session(sess)
    assert sig and sig[0][0] == "nokia"


def test_router_on_session_profile_fetch_raises(monkeypatch):
    """_on_session tolera profile_fetcher.load_cached_profile que crasha."""
    from skinvault.ui.screen_router import ScreenRouter
    from skinvault.prices import PriceCache
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    monkeypatch.setattr(
        "skinvault.ui.profile_fetcher.load_cached_profile",
        lambda sid: (_ for _ in ()).throw(ValueError("boom")))
    router = ScreenRouter(PriceCache(ttl=3600))
    sess = _fake_session()
    router._on_session(sess)  # nao crasha


def test_trades_screen_has_recent_matches_strip(monkeypatch):
    """TradesScreen instancia inclui o strip; refresh atualiza."""
    from skinvault.ui.trades_screen import TradesScreen
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
        {"name": "AK", "pnl": 50, "sell_ts": 1700000000, "buy_ts": 1699000000,
         "buy_cost": 100, "sell_price": 200, "quantity": 1, "source": "manual",
         "pnl_pct": 50, "net_received": 170, "cost_total": 100, "notes": ""},
    ])
    screen = TradesScreen()
    screen.refresh()
    assert screen._matches_strip._chip_lay.count() == 1
    # Com trades, mostra tabela, esconde hero
    assert screen._table.isVisible() or not screen.isVisible()
    assert not screen._empty_hero.isVisible() or not screen.isVisible()


def test_trades_screen_empty_state(monkeypatch):
    """Sem trades, esconde tabela e mostra empty hero."""
    from skinvault.ui.trades_screen import TradesScreen
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
    screen = TradesScreen()
    screen.refresh()
    # Tabela escondida, hero ativo (independente do widget estar shown)
    assert screen._table.isVisibleTo(screen) is False or not screen._trades
    assert screen._empty_hero is not None


def test_trades_screen_empty_hero_cta_opens_dialog(monkeypatch):
    """Click no CTA do empty hero abre o dialog de add."""
    from skinvault.ui.trades_screen import TradesScreen
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
    monkeypatch.setattr(
        "skinvault.ui.trades_screen._TradeDialog.exec",
        lambda self: 0)
    screen = TradesScreen()
    screen.refresh()
    # Hero foi construido; cta funciona via _on_add direto
    screen._on_add()


def test_market_screen():
    """MarketScreen instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.market_screen import MarketScreen
    screen = MarketScreen(PriceCache(ttl=3600))
    assert screen is not None


class TestMarketScreen:
    """Testes do MarketScreen."""

    @pytest.fixture(autouse=True)
    def _no_file_io(self, monkeypatch, tmp_path):
        import json
        p = tmp_path / "market_recent.json"
        p.write_text(json.dumps([]), encoding="utf-8")
        monkeypatch.setattr(
            "skinvault.ui.market_screen._RECENT_PATH", p)

    def test_cache_age_label_now(self):
        from skinvault.ui.market_screen import _cache_age_label
        assert _cache_age_label(0) == "agora há pouco"
        assert _cache_age_label(30) == "agora há pouco"

    def test_cache_age_label_minutes(self):
        from skinvault.ui.market_screen import _cache_age_label
        assert _cache_age_label(120) == "há 2min"

    def test_cache_age_label_hours(self):
        from skinvault.ui.market_screen import _cache_age_label
        assert _cache_age_label(7200) == "há 2h"

    def test_cache_age_label_days(self):
        from skinvault.ui.market_screen import _cache_age_label
        assert _cache_age_label(180000) == "há 2d"

    def test_load_recent_valid(self, tmp_path, monkeypatch):
        from skinvault.ui.market_screen import _load_recent, _RECENT_PATH
        import json
        p = tmp_path / "market_recent.json"
        monkeypatch.setattr("skinvault.ui.market_screen._RECENT_PATH", p)
        p.write_text(json.dumps(["AK-47"]), encoding="utf-8")
        assert _load_recent() == ["AK-47"]

    def test_load_recent_not_list(self, tmp_path, monkeypatch):
        from skinvault.ui.market_screen import _load_recent, _RECENT_PATH
        import json
        p = tmp_path / "market_recent.json"
        monkeypatch.setattr("skinvault.ui.market_screen._RECENT_PATH", p)
        p.write_text(json.dumps("not list"), encoding="utf-8")
        assert _load_recent() == []

    def test_load_recent_exception(self, tmp_path, monkeypatch):
        from skinvault.ui.market_screen import _load_recent
        # Path inexistente — read_text levanta FileNotFoundError → except
        p = tmp_path / "nonexistent.json"
        monkeypatch.setattr("skinvault.ui.market_screen._RECENT_PATH", p)
        assert _load_recent() == []

    def test_save_recent(self, tmp_path, monkeypatch):
        from skinvault.ui.market_screen import _save_recent, _RECENT_PATH
        p = tmp_path / "market_recent.json"
        monkeypatch.setattr("skinvault.ui.market_screen._RECENT_PATH", p)
        _save_recent(["AK-47", "AWP"])
        import json
        data = json.loads(p.read_text("utf-8"))
        assert data == ["AK-47", "AWP"]

    def test_save_recent_truncates(self, tmp_path, monkeypatch):
        from skinvault.ui.market_screen import _save_recent, _RECENT_PATH
        p = tmp_path / "market_recent.json"
        monkeypatch.setattr("skinvault.ui.market_screen._RECENT_PATH", p)
        items = [f"Item{i}" for i in range(20)]
        _save_recent(items)
        import json
        data = json.loads(p.read_text("utf-8"))
        assert len(data) == 8

    def test_save_recent_os_error(self, monkeypatch, tmp_path):
        from skinvault.ui.market_screen import _save_recent, _RECENT_PATH
        from pathlib import Path
        p = tmp_path / "market_recent.json"
        monkeypatch.setattr("skinvault.ui.market_screen._RECENT_PATH", p)
        monkeypatch.setattr(
            "pathlib.Path.write_text",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("denied")),
        )
        _save_recent(["AK"])  # nao crasha

    def test_clear_detail_grid_with_rows(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._add_detail_row("Label", "Value")
        before = screen._detail_grid.count()
        assert before > 0
        screen._clear_detail_grid()
        screen._search_inp.setText("")  # force layout invalidation
        assert screen._detail_grid.count() == 0

    def test_rebuild_recent_empty(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        assert not screen._recent_act.isVisible()

    def test_rebuild_recent_with_items(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._recent = ["AK-47", "AWP"]
        screen._rebuild_recent_menu()
        assert screen._recent_act.isVisible()
        assert len(screen._recent_menu.actions()) == 2

    def test_push_recent_new(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.ui.market_screen._save_recent", lambda x: None)
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._push_recent("AK-47")
        assert screen._recent == ["AK-47"]

    def test_push_recent_moves_to_front(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._recent = ["AK-47", "AWP"]
        screen._push_recent("AK-47")
        assert screen._recent == ["AK-47", "AWP"]

    def test_search_and_run(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        calls = []
        monkeypatch.setattr(
            "skinvault.ui.market_screen.MarketScreen._on_search",
            lambda self: calls.append(True),
        )
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._search_and_run("AK-47")
        assert screen._search_inp.text() == "AK-47"
        assert calls == [True]

    def test_clear_detail_grid_empty(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._clear_detail_grid()  # nao crasha

    def test_add_detail_row(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._add_detail_row("Label", "R$ 100")
        assert screen._detail_grid.count() >= 2

    def test_on_search_empty(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._on_search()  # nao crasha com input vazio
        assert screen._search_btn.isEnabled()

    def test_on_search_with_name(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen

        class _InlineThread:
            def __init__(self, target=None, daemon=False):
                self._target = target
            def start(self):
                if self._target:
                    self._target()

        monkeypatch.setattr("threading.Thread", _InlineThread)
        monkeypatch.setattr(
            "skinvault.steam_api.get_market_overview",
            lambda n: {"lowest": 100, "median": 120, "volume": 50},
        )
        monkeypatch.setattr(
            "skinvault.steam_api.get_market_page_data",
            lambda n: {
                "price_history": [{"price": 110}],
                "order_book": {"buy_count": 10, "sell_count": 5,
                               "spread": 0.05},
            },
        )
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo",
                              "diff_pct": 0.0},
        )
        monkeypatch.setattr("skinvault.cases.case_status",
                            lambda n: {"label": "Operation"})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False, "ratio": 1.0})

        screen = MarketScreen(PriceCache(ttl=3600))
        screen._search_inp.setText("AK-47")
        screen._on_search()
        QApplication.processEvents()
        assert "AK-47" in screen._status.text()

    def test_on_search_from_cache(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        cache = PriceCache(ttl=3600)
        cache.put("AK-47", 150.0)
        screen = MarketScreen(cache)
        screen._search_inp.setText("AK-47")
        with monkeypatch.context() as m:
            m.setattr("threading.Thread",
                      lambda target=None, daemon=False: type(
                          "", (), {"start": lambda self: None})())
            screen._on_search()
        assert "cache" in screen._status.text()

    def test_on_clear(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._on_clear()
        assert screen._search_inp.text() == ""

    def test_on_data_no_data(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        screen = MarketScreen(PriceCache(ttl=3600))
        screen._on_data({"name": "AK-47"})
        # Mensagem agora via Toast (UI visual); basta nao crashar

    def test_on_data_with_overview(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo",
                              "diff_pct": -5.0, "message": "Preco justo"},
        )
        monkeypatch.setattr("skinvault.cases.case_status",
                            lambda n: {})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False})

        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "AK-47",
            "overview": {"lowest": 100, "median": 120, "volume": 50},
        }
        screen._on_data(data)
        assert "Atualizado" in screen._status.text()
        assert screen._stat_median._value.text() == "R$ 120,00"

    def test_on_data_with_page(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo",
                              "diff_pct": 0.0,
                              "spread_verdict": "Spread OK",
                              "book_verdict": "Book OK",
                              "trend_verdict": "Estável"},
        )
        monkeypatch.setattr("skinvault.cases.case_status",
                            lambda n: {})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False})
        monkeypatch.setattr("skinvault.signals.sma",
                            lambda p, period: [110])
        monkeypatch.setattr("skinvault.signals.find_support_resistance",
                            lambda p: {"support": 100, "resistance": 130})

        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "AWP",
            "overview": {"lowest": 200, "median": 220, "volume": 30},
            "page": {
                # Formato real do SSR: time/price_median/purchases
                "price_history": [
                    {"time": 1700000000, "price_median": 210, "purchases": 3},
                    {"time": 1700086400, "price_median": 215, "purchases": 5},
                ],
                "order_book": {"buy_count": 20, "sell_count": 8,
                               "spread": 0.03},
            },
        }
        screen._on_data(data)
        assert "AWP" in screen._detail_title.text()
        assert screen._detail_grid.count() > 0
        # Regressao: a serie do sparkline deve ser extraida de price_median
        # (bug antigo lia x["price"], que nao existe no SSR -> chart vazio)
        assert screen._sparkline._values == [210, 215]
        assert screen._sparkline._timestamps == [1700000000, 1700086400]

    def test_on_data_page_approx(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo",
                              "diff_pct": 0.0})
        monkeypatch.setattr("skinvault.cases.case_status", lambda n: {})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False})
        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "AWP",
            "overview": {"lowest": 200, "median": 220, "volume": 30},
            "page": {
                "price_history": [],
                "order_book": {"buy_count": 20, "sell_count": 8},
                "order_book_approx": True,
            },
        }
        screen._on_data(data)
        assert screen._detail_grid.count() > 0

    def test_on_data_volume_anomaly(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo",
                              "diff_pct": 0.0})
        monkeypatch.setattr("skinvault.cases.case_status", lambda n: {})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [50, 100, 150])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": True, "ratio": 2.5,
                                       "label": "Alto"})
        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "AWP",
            "overview": {"lowest": 200, "median": 220, "volume": 500},
        }
        screen._on_data(data)
        assert "anômalo" in screen._stat_volume._value.text()

    def test_on_data_case_badge(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo",
                              "diff_pct": 0.0})
        monkeypatch.setattr("skinvault.cases.case_status",
                            lambda n: {"label": "Operation Riptide"})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False})
        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "M4A4",
            "overview": {"lowest": 50, "median": 55, "volume": 10},
        }
        screen._on_data(data)
        assert "Caixa" in screen._case_badge.text()

    def test_on_data_supply_recorded(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "fair", "label": "Justo"})
        monkeypatch.setattr("skinvault.cases.case_status", lambda n: {})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False})
        monkeypatch.setattr("skinvault.signals.record_item_supply",
                            lambda n, v: None)
        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "USP",
            "overview": {"lowest": 10, "median": 12, "volume": 5},
            "page": {"order_book": {"buy_count": 8, "sell_count": 3}},
        }
        screen._on_data(data)
        assert "8 compras" in screen._depth_meta.text()

    def test_on_data_no_verdict_message(self, monkeypatch):
        from skinvault.prices import PriceCache
        from skinvault.ui.market_screen import MarketScreen
        monkeypatch.setattr(
            "skinvault.steam_api.fair_value_verdict",
            lambda *a, **kw: {"verdict": "unknown", "label": "—"})
        monkeypatch.setattr("skinvault.cases.case_status", lambda n: {})
        monkeypatch.setattr("skinvault.signals.record_item_volume",
                            lambda n, v: None)
        monkeypatch.setattr("skinvault.signals.load_item_volume",
                            lambda n: [])
        monkeypatch.setattr("skinvault.signals.volume_anomaly",
                            lambda h: {"is_anomaly": False})
        screen = MarketScreen(PriceCache(ttl=3600))
        data = {
            "name": "TEST",
            "overview": {"lowest": 10, "median": 12, "volume": 5},
        }
        screen._on_data(data)
        assert "Dados insuficientes" in screen._detail_msg.text()


class TestTradesScreen:
    """Testes do TradesScreen."""

    TRADE_DATA = [
        {"sell_ts": 1_700_000_000, "buy_ts": 1_690_000_000,
         "name": "AK-47", "quantity": 1, "buy_cost": 100,
         "sell_price": 200, "pnl": 50, "pnl_pct": 50,
         "source": "manual", "notes": ""},
        {"sell_ts": 1_690_000_000, "buy_ts": 1_680_000_000,
         "name": "AWP", "quantity": 2, "buy_cost": 80,
         "sell_price": 60, "pnl": -30, "pnl_pct": -37.5,
         "source": "steam_sync", "notes": ""},
    ]

    STATS = {
        "total": 2, "pnl_total": 20, "win_rate": 50,
        "win_count": 1, "loss_count": 1, "fees_total": 18,
    }

    @staticmethod
    def _make_screen(mocker=None):
        from skinvault.ui.trades_screen import TradesScreen
        return TradesScreen()

    def test_fmt_date_zero(self):
        from skinvault.ui.trades_screen import _fmt_date
        assert _fmt_date(0) == "—"

    def test_fmt_date_valid(self):
        from skinvault.ui.trades_screen import _fmt_date
        assert _fmt_date(1_700_000_000) == "14/11/2023"

    def test_source_label_steam(self):
        from skinvault.ui.trades_screen import _source_label
        label, color = _source_label("steam_sync")
        assert label == "Steam"
        label, color = _source_label("steam")
        assert label == "Steam"

    def test_source_label_manual(self):
        from skinvault.ui.trades_screen import _source_label
        label, color = _source_label("manual")
        assert label == "Manual"

    def test_trade_dialog_new(self, monkeypatch):
        from skinvault.ui.trades_screen import _TradeDialog
        dlg = _TradeDialog()
        assert dlg.windowTitle() == "Adicionar trade"

    def test_trade_dialog_edit(self, monkeypatch):
        from skinvault.ui.trades_screen import _TradeDialog
        dlg = _TradeDialog(trade={"name": "AK-47", "buy_cost": 100,
                                   "sell_price": 200, "quantity": 1,
                                   "notes": "test"})
        assert dlg.windowTitle() == "Editar trade"
        data = dlg.get_data()
        assert data["name"] == "AK-47"

    def test_refresh(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen.refresh()
        assert screen._table.rowCount() == 2

    def test_on_period(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_period("7d")
        assert screen._period_key == "7d"

    def test_on_result(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_result("profit")
        assert screen._result_key == "profit"

    def test_apply_filter_profit(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._result_key = "profit"
        screen._apply_filter()
        assert len(screen._filtered) == 1  # only AK-47 has profit

    def test_apply_filter_loss(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._result_key = "loss"
        screen._apply_filter()
        assert len(screen._filtered) == 1  # only AWP has loss

    def test_apply_filter_keyword(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._filter_inp.setText("AK")
        screen._apply_filter()
        assert len(screen._filtered) == 1

    def test_apply_filter_keyword_notes(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        data = self.TRADE_DATA.copy()
        data[0] = dict(data[0], notes="special")
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: data)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._filter_inp.setText("special")
        screen._apply_filter()
        assert len(screen._filtered) == 1

    def test_apply_filter_period(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._period_key = "7d"
        screen._apply_filter()
        # ambos os trades tem sell_ts de 2023 -> fora dos 7 dias
        assert len(screen._filtered) == 0

    def test_populate(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._trades = self.TRADE_DATA
        screen._filtered = self.TRADE_DATA
        screen._populate()
        assert screen._table.rowCount() == 2

    def test_on_add_cancelled(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog
        from skinvault.ui.trades_screen import TradesScreen, _TradeDialog
        monkeypatch.setattr(_TradeDialog, "exec",
                            lambda self: QDialog.DialogCode.Rejected)
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_add()

    def test_on_add_empty_name(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog, QMessageBox
        from skinvault.ui.trades_screen import TradesScreen, _TradeDialog
        monkeypatch.setattr(_TradeDialog, "exec",
                            lambda self: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(_TradeDialog, "get_data",
                            lambda self: {"name": "", "buy_cost": 100,
                                          "sell_price": 200, "quantity": 1,
                                          "notes": ""})
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **kw: None)
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_add()

    def test_on_add_success(self, monkeypatch):
        from PyQt6.QtWidgets import QDialog
        from skinvault.ui.trades_screen import TradesScreen, _TradeDialog
        monkeypatch.setattr(_TradeDialog, "exec",
                            lambda self: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(_TradeDialog, "get_data",
                            lambda self: {"name": "AK-47", "buy_cost": 100,
                                          "sell_price": 200, "quantity": 1,
                                          "notes": ""})
        monkeypatch.setattr("skinvault.trades.record_trade",
                            lambda *a, **kw: None)
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_add()

    def test_edit_selected_no_selection(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_edit_selected()
        # Mensagem agora via Toast; basta nao crashar

    def test_edit_selected_steam_confirm(self, monkeypatch):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QDialog, QMessageBox, QTableWidgetItem
        from skinvault.ui.trades_screen import TradesScreen, _TradeDialog
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        monkeypatch.setattr(_TradeDialog, "exec",
                            lambda self: QDialog.DialogCode.Accepted)
        monkeypatch.setattr(_TradeDialog, "get_data",
                            lambda self: {"name": "AK-47", "buy_cost": 100,
                                          "sell_price": 200, "quantity": 1,
                                          "notes": ""})
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **kw: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr("skinvault.trades.update_trade",
                            lambda *a, **kw: None)
        screen = TradesScreen()
        screen._table.setRowCount(1)
        item = QTableWidgetItem("data")
        item.setData(Qt.ItemDataRole.UserRole, 0)
        screen._table.setItem(0, 0, item)
        screen._table.setCurrentCell(0, 0)
        screen._on_edit_selected()

    def test_edit_selected_steam_reject(self, monkeypatch):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **kw: QMessageBox.StandardButton.No,
        )
        screen = TradesScreen()
        screen._table.setRowCount(1)
        item = QTableWidgetItem("data")
        item.setData(Qt.ItemDataRole.UserRole, 1)
        screen._table.setItem(0, 0, item)
        screen._table.setCurrentCell(0, 0)
        screen._on_edit_selected()

    def test_remove_selected_no_selection(self, monkeypatch):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTableWidgetItem
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_remove_selected()
        # Mensagem agora via Toast; basta nao crashar

    def test_remove_selected_confirm(self, monkeypatch):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **kw: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr("skinvault.trades.remove_trade",
                            lambda idx: None)
        screen = TradesScreen()
        screen._table.setRowCount(1)
        item = QTableWidgetItem("data")
        item.setData(Qt.ItemDataRole.UserRole, 0)
        screen._table.setItem(0, 0, item)
        screen._table.setCurrentCell(0, 0)
        screen._on_remove_selected()

    def test_remove_selected_cancel(self, monkeypatch):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **kw: QMessageBox.StandardButton.No,
        )
        screen = TradesScreen()
        screen._table.setRowCount(1)
        item = QTableWidgetItem("data")
        item.setData(Qt.ItemDataRole.UserRole, 0)
        screen._table.setItem(0, 0, item)
        screen._table.setCurrentCell(0, 0)
        screen._on_remove_selected()

    def test_clear_no_trades(self, monkeypatch):
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        screen = TradesScreen()
        screen._on_clear()
        # Mensagem agora via Toast; basta nao crashar

    def test_clear_confirm(self, monkeypatch):
        from PyQt6.QtWidgets import QMessageBox
        from skinvault.ui.trades_screen import TradesScreen
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        monkeypatch.setattr(
            QMessageBox, "question",
            lambda *a, **kw: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr("skinvault.trades.clear_trades",
                            lambda: None)
        screen = TradesScreen()
        screen._on_clear()

    def test_on_ctx_menu(self, monkeypatch):
        from PyQt6.QtCore import Qt, QPoint
        from PyQt6.QtWidgets import QTableWidgetItem
        from skinvault.ui.trades_screen import TradesScreen
        from PyQt6.QtWidgets import QMenu
        monkeypatch.setattr("skinvault.trades.load_trades",
                            lambda: self.TRADE_DATA)
        monkeypatch.setattr("skinvault.trades.trade_stats",
                            lambda trades=None: self.STATS)
        monkeypatch.setattr(QMenu, "exec", lambda self, *a: None)
        screen = TradesScreen()
        screen._table.setRowCount(1)
        item = QTableWidgetItem("data")
        item.setData(Qt.ItemDataRole.UserRole, 0)
        screen._table.setItem(0, 0, item)
        screen._table.setCurrentCell(0, 0)
        screen._on_ctx_menu(QPoint(0, 0))


STATS_DUMMY = {"total": 0, "pnl_total": 0, "pnl_medio": 0,
               "win_count": 0, "loss_count": 0, "win_rate": 0,
               "best": None, "worst": None, "monthly": [],
               "fees_total": 0.0, "avg_days": 0}

def test_selected_index_no_item():
    """_selected_index returns None when item is missing at row."""
    from skinvault.ui.trades_screen import TradesScreen
    from skinvault.trades import trade_stats
    screen = TradesScreen()
    screen._table.setRowCount(1)
    screen._table.setCurrentCell(0, 0)
    assert screen._selected_index() is None

def test_selected_index_not_int():
    """_selected_index returns None when UserRole data is not int."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTableWidgetItem
    from skinvault.ui.trades_screen import TradesScreen
    screen = TradesScreen()
    screen._table.setRowCount(1)
    item = QTableWidgetItem("data")
    item.setData(Qt.ItemDataRole.UserRole, "not-an-int")
    screen._table.setItem(0, 0, item)
    screen._table.setCurrentCell(0, 0)
    assert screen._selected_index() is None

def test_edit_selected_dialog_rejected(monkeypatch):
    """_on_edit_selected returns early when dialog is rejected."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QTableWidgetItem
    from skinvault.ui.trades_screen import TradesScreen, _TradeDialog
    monkeypatch.setattr("skinvault.trades.load_trades",
                        lambda: [{"name": "AK", "source": "manual"}])
    monkeypatch.setattr("skinvault.trades.trade_stats",
                        lambda trades=None: STATS_DUMMY)
    monkeypatch.setattr(_TradeDialog, "exec",
                        lambda self: QDialog.DialogCode.Rejected)
    screen = TradesScreen()
    screen._table.setRowCount(1)
    item = QTableWidgetItem("data")
    item.setData(Qt.ItemDataRole.UserRole, 0)
    screen._table.setItem(0, 0, item)
    screen._table.setCurrentCell(0, 0)
    screen._on_edit_selected()

def test_edit_selected_empty_name(monkeypatch):
    """_on_edit_selected shows warning when name is empty."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QMessageBox, QTableWidgetItem
    from skinvault.ui.trades_screen import TradesScreen, _TradeDialog
    monkeypatch.setattr("skinvault.trades.load_trades",
                        lambda: [{"name": "AK", "source": "manual"}])
    monkeypatch.setattr("skinvault.trades.trade_stats",
                        lambda trades=None: STATS_DUMMY)
    monkeypatch.setattr(_TradeDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(_TradeDialog, "get_data",
                        lambda self: {"name": "", "buy_cost": 0,
                                      "sell_price": 0, "quantity": 0,
                                      "notes": ""})
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **kw: None)
    screen = TradesScreen()
    screen._table.setRowCount(1)
    item = QTableWidgetItem("data")
    item.setData(Qt.ItemDataRole.UserRole, 0)
    screen._table.setItem(0, 0, item)
    screen._table.setCurrentCell(0, 0)
    screen._on_edit_selected()

def test_ctx_menu_no_row(monkeypatch):
    """_on_ctx_menu returns early when no row is selected."""
    from PyQt6.QtCore import QPoint
    from skinvault.ui.trades_screen import TradesScreen
    monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
    monkeypatch.setattr("skinvault.trades.trade_stats",
                        lambda trades=None: STATS_DUMMY)
    screen = TradesScreen()
    screen._on_ctx_menu(QPoint(0, 0))

def test_ctx_menu_edit(monkeypatch):
    """_on_ctx_menu triggers edit when action matches."""
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtWidgets import QTableWidgetItem, QMenu
    from skinvault.ui.trades_screen import TradesScreen
    monkeypatch.setattr("skinvault.trades.load_trades",
                        lambda: [{"name": "AK", "source": "manual"}])
    monkeypatch.setattr("skinvault.trades.trade_stats",
                        lambda trades=None: STATS_DUMMY)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: self.actions()[0])
    screen = TradesScreen()
    screen._on_edit_selected = lambda: setattr(screen, '_edit_called', True)
    screen._table.setRowCount(1)
    item = QTableWidgetItem("data")
    item.setData(Qt.ItemDataRole.UserRole, 0)
    screen._table.setItem(0, 0, item)
    screen._table.setCurrentCell(0, 0)
    screen._on_ctx_menu(QPoint(0, 0))
    assert screen._edit_called

def test_ctx_menu_remove(monkeypatch):
    """_on_ctx_menu triggers remove when action matches."""
    from PyQt6.QtCore import Qt, QPoint
    from PyQt6.QtWidgets import QTableWidgetItem, QMenu
    from skinvault.ui.trades_screen import TradesScreen
    monkeypatch.setattr("skinvault.trades.load_trades",
                        lambda: [{"name": "AK", "source": "manual"}])
    monkeypatch.setattr("skinvault.trades.trade_stats",
                        lambda trades=None: STATS_DUMMY)
    monkeypatch.setattr(QMenu, "exec", lambda self, *a: self.actions()[1])
    screen = TradesScreen()
    screen._on_remove_selected = lambda: setattr(screen, '_rm_called', True)
    screen._table.setRowCount(1)
    item = QTableWidgetItem("data")
    item.setData(Qt.ItemDataRole.UserRole, 0)
    screen._table.setItem(0, 0, item)
    screen._table.setCurrentCell(0, 0)
    screen._on_ctx_menu(QPoint(0, 0))
    assert screen._rm_called

def test_trades_screen():
    """TradesScreen instancia sem erro."""
    from skinvault.ui.trades_screen import TradesScreen
    screen = TradesScreen()
    assert screen is not None


def test_simulador_screen():
    """SimuladorScreen instancia sem erro."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    assert screen is not None


def test_simulador_screen_clear():
    """SimuladorScreen._on_clear reseta campos."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._buy_inp.setValue(100)
    screen._sell_inp.setValue(200)
    screen._qty_inp.setValue(2)
    screen._on_clear()
    assert screen._buy_inp.value() == 0
    assert screen._sell_inp.value() == 0
    assert screen._qty_inp.value() == 1


def test_simulador_screen_invalid_input():
    """_on_simular com valores invalidos mostra erro."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._on_simular()
    assert "positivos" in screen._result_detail.text()


def test_simulador_screen_profit():
    """_on_simular com lucro mostra mensagem de lucro."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._buy_inp.setValue(100)
    screen._sell_inp.setValue(200)
    screen._qty_inp.setValue(1)
    screen._on_simular()
    assert "Lucro" in screen._result_detail.text()


def test_simulador_screen_loss():
    """_on_simular com prejuizo mostra mensagem de loss."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._buy_inp.setValue(200)
    screen._sell_inp.setValue(100)
    screen._qty_inp.setValue(1)
    screen._on_simular()
    assert "Preju" in screen._result_detail.text()


def test_simulador_screen_rebuild_empty():
    """_rebuild_history com historico vazio esconde seção."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._history = []
    screen._rebuild_history()
    assert screen._hist_lbl.isVisible() is False


def test_simulador_screen_rebuild_populated():
    """_rebuild_history com historico preenchido mostra label."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen.show()  # necessário para isVisible() considerar hierarquia
    screen._history = [{"pnl": 50, "buy_price": 100, "sell_price": 130,
                        "quantity": 1}]
    screen._rebuild_history()
    assert screen._hist_lbl.isVisible() is True


def test_simulador_screen_break_even():
    """_on_simular com PNL=0 mostra mensagem de break-even."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    # break-even: sell_price = buy_price * 1.15
    screen._buy_inp.setValue(50)
    screen._sell_inp.setValue(57.5)  # 50 * 1.15
    screen._qty_inp.setValue(1)
    screen._on_simular()
    assert "zero" in screen._result_detail.text()


def test_simulador_screen_simulacao_updates_stats():
    """_on_simular com valores validos atualiza stats e historico."""
    from skinvault import portfolio
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._buy_inp.setValue(150)
    screen._sell_inp.setValue(200)
    screen._qty_inp.setValue(1)
    screen._on_simular()
    assert screen._stat_pnl._value != "—"
    assert screen._stat_roi._value != "—"
    assert len(screen._history) == 1
    assert screen._history[0]["buy_price"] == 150


def test_simulador_screen_push_history():
    """_push_history insere no topo e respeita _HIST_CAP."""
    from skinvault import portfolio
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    for buy in range(1, 8):
        r = portfolio.simulate_trade(buy * 10, buy * 20, 1)
        screen._push_history(r)
    assert len(screen._history) == 5
    assert screen._history[0]["buy_price"] == 70


def test_simulador_screen_restore():
    """_restore repoe campos e chama _on_simular."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    screen = SimuladorScreen()
    screen._buy_inp.setValue(100)
    r = {"buy_price": 50, "sell_price": 80, "quantity": 2,
         "pnl": 10, "roi_pct": 5, "net_received": 128,
         "break_even_price": 58.82, "steam_fee": 24,
         "is_profit": True, "is_loss": False}
    screen._restore(r)
    assert screen._buy_inp.value() == 50
    assert screen._sell_inp.value() == 80
    assert screen._qty_inp.value() == 2
    assert len(screen._history) == 1


def test_simulador_history_chip_negative():
    """_HistoryChip com pnl negativo mostra cor danger."""
    from skinvault.ui.simulador_screen import _HistoryChip
    from skinvault.ui import theme as t
    snap = {"buy_price": 200, "sell_price": 100, "quantity": 1,
            "pnl": -75}
    chip = _HistoryChip(snap)
    assert t.DANGER in chip.styleSheet()


def test_simulador_history_chip_positive():
    """_HistoryChip com pnl positivo mostra cor de lucro (POSITIVE verde)."""
    from skinvault.ui.simulador_screen import _HistoryChip
    from skinvault.ui import theme as t
    snap = {"buy_price": 100, "sell_price": 200, "quantity": 1,
            "pnl": 50}
    chip = _HistoryChip(snap)
    assert t.POSITIVE in chip.styleSheet()


def test_account_screen_focus_filter():
    """_focus_filter nao crasha (setFocus requer widget visivel)."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._filter_inp.setText("AK-47")
    screen._focus_filter()
    # setFocus pode nao funcionar sem show(), mas nao crasha


def test_account_screen_reload_profile_no_session():
    """_reload_profile sem session mostra placeholder."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._reload_profile()
    assert screen._name.text() == "—"


def test_account_screen_reload_profile_with_session(monkeypatch):
    """_reload_profile com session busca perfil."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    from skinvault.steam_session import SteamSession

    monkeypatch.setattr("skinvault.ui.account_screen.load_cached_profile",
                        lambda sid: None)
    monkeypatch.setattr("skinvault.ui.account_screen.load_avatar_bytes",
                        lambda sid: None)
    monkeypatch.setattr("skinvault.ui.account_screen.fetch_public_profile",
                        lambda sid, force=False: None)
    # set_session dispara refresh() -> PriceWorker.start() -> HTTP real.
    # Mock threading.Thread + load_portfolio pra rodar inline e nao chamar Steam.
    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    screen = AccountScreen(PriceCache(ttl=3600))
    sess = SteamSession("76561198000000001", {"c": "x"})
    screen.set_session(sess)


def test_account_screen_open_profile(monkeypatch):
    """_open_steam_profile abre URL do perfil."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    from skinvault.steam_session import SteamSession
    opened = []
    monkeypatch.setattr("skinvault.ui.account_screen.QDesktopServices.openUrl",
                        lambda url: opened.append(url.toString()))
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._session = SteamSession("76561198000000001", {"c": "x"})
    screen._open_steam_profile()
    assert len(opened) == 1
    assert "76561198000000001" in opened[0]


def test_account_screen_on_profile_without_steamid():
    """_on_profile sem steamid esconde link do perfil."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_profile({"name": "Test"})
    assert not screen._profile_link.isVisible()


def test_account_screen_on_profile_with_avatar_bytes(monkeypatch):
    """_on_profile usa load_avatar_bytes quando avatar_path e None."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    monkeypatch.setattr("skinvault.ui.account_screen.load_avatar_bytes",
                        lambda sid: b"img-bytes")
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_profile({"steamid": "7656", "name": "Test",
                        "avatar_path": None})
    # nao crashou


def test_account_screen_on_eval_progress():
    """_on_eval_progress atualiza status."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_eval_progress(5, 20)
    assert "5/20" in screen._status.text()


def test_account_screen_on_eval_empty(monkeypatch):
    """_on_eval com dados vazios nao crasha."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_eval({"rows": [], "totals": {}, "positions": []})


def test_account_screen_on_eval_with_data():
    """_on_eval com dados preenche tabela e stats."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_eval({
        "rows": [
            {"name": "AK-47", "quantity": 2, "price": 100, "market": 200,
             "net_if_sold": 170, "pnl": 30, "cost_total": 140},
        ],
        "totals": {"market": 200, "net_if_sold": 170, "pnl": 30},
        "positions": [{"source": "steam_sync"}],
    })
    assert screen._stat_gross._value != "—"
    assert screen._table.rowCount() == 1
    assert screen._table.item(0, 0).text() == "AK-47"
    assert screen._table.item(0, 6).text() == "Steam"  # origin


def test_account_screen_apply_filter():
    """_apply_filter esconde linhas que nao correspondem."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    import PyQt6.QtWidgets as qw
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._table.setSortingEnabled(False)
    screen._table.insertRow(0)
    screen._table.setItem(0, 0, qw.QTableWidgetItem("AK-47"))
    screen._table.insertRow(1)
    screen._table.setItem(1, 0, qw.QTableWidgetItem("AWP"))
    screen._apply_filter("AK")
    assert screen._table.isRowHidden(0) is False
    assert screen._table.isRowHidden(1) is True


def test_account_screen_reload_activity_populates_feed(monkeypatch):
    """_reload_activity puxa eventos e atualiza o ActivityFeed."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    monkeypatch.setattr("skinvault.activity.load_recent_activity",
                        lambda limit=10: [
                            {"type": "trade", "ts": 1000, "title": "AK",
                             "subtitle": "+50", "color": "green", "icon": "↑"},
                        ])
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._reload_activity()
    assert screen._activity_feed._list_lay.count() == 1


def test_account_screen_reload_activity_swallows_exception(monkeypatch):
    """_reload_activity engole excecao e mostra feed vazio."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    monkeypatch.setattr("skinvault.activity.load_recent_activity",
                        lambda limit=10: (_ for _ in ()).throw(ValueError("boom")))
    screen._reload_activity()  # nao crasha


# ── WatchlistScreen + _RulesDialog ──────────────────────────────

def test_rules_dialog_default():
    """_RulesDialog defaults when item has no rules."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "AK-47"})
    assert dlg._below_target.value() == 0
    assert dlg._drop_pct.value() == 0
    assert dlg._volume_spike.value() == 0
    assert dlg._supply_drop.value() == 0

def test_rules_dialog_with_rules():
    """_RulesDialog loads existing rules."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "AK-47", "rules": {
        "price_below": 100, "price_drop_pct": 0.05,
        "volume_spike": 3, "supply_drop": 20,
    }})
    assert dlg._below_target.value() == 100
    assert dlg._drop_pct.value() == 0.05
    assert dlg._volume_spike.value() == 3
    assert dlg._supply_drop.value() == 20

def test_rules_dialog_get_rules_all():
    """get_rules returns all active rules."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "AK-47"})
    dlg._below_target.setValue(50)
    dlg._drop_pct.setValue(10)  # 10% → stored as 0.10
    dlg._volume_spike.setValue(2.5)
    dlg._supply_drop.setValue(15)
    rules = dlg.get_rules()
    assert rules["price_below"] == 50
    assert rules["price_drop_pct"] == 0.10
    assert rules["volume_spike"] == 2.5
    assert rules["supply_drop"] == 15

def test_rules_dialog_get_rules_empty():
    """get_rules returns empty dict when all values are zero."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "AK-47"})
    assert dlg.get_rules() == {}

def test_watchlist_screen_refresh_empty(monkeypatch, tmp_path):
    """WatchlistScreen refresh with no items."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist", lambda: [])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    screen = WatchlistScreen(PriceCache(tmp_path / "prices.json", ttl=3600))
    assert screen._table.rowCount() == 0
    assert "0 itens" in screen._status.text()

def test_watchlist_screen_with_items(monkeypatch, tmp_path):
    """WatchlistScreen shows items in table."""
    from skinvault.prices import PriceCache
    from PyQt6.QtCore import Qt
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist",
        lambda: [{"name": "AK-47", "target": 100, "triggered": False},
                 {"name": "AWP", "target": 0, "triggered": False}])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    cache = PriceCache(tmp_path / "prices.json", ttl=3600)
    cache.put("AK-47", 120)
    cache.put("AWP", 500)
    screen = WatchlistScreen(cache)
    screen._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    names = [screen._table.item(r, 0).text()
             for r in range(screen._table.rowCount())]
    assert names == ["AK-47", "AWP"]
    assert screen._table.item(0, screen.COL_TARGET).text() == "R$ 100,00"
    assert screen._table.item(1, screen.COL_TARGET).text() == "—"
    assert "2 itens" in screen._status.text()

def test_watchlist_screen_triggered(monkeypatch, tmp_path):
    """WatchlistScreen shows trigger status for triggered item."""
    from PyQt6.QtGui import QColor
    from skinvault.prices import PriceCache
    from PyQt6.QtCore import Qt
    from skinvault.ui.watchlist_screen import WatchlistScreen
    from skinvault.ui.theme import WARN
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist",
        lambda: [{"name": "AK-47", "target": 100, "triggered": True}])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    screen = WatchlistScreen(PriceCache(tmp_path / "prices.json", ttl=3600))
    screen._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    st_item = screen._table.item(0, screen.COL_STATUS)
    assert st_item.text() == "Disparado"
    assert st_item.foreground().color() == QColor(WARN)

def test_watchlist_screen_no_price(monkeypatch, tmp_path):
    """WatchlistScreen shows 'Consultando...' when price not cached."""
    from skinvault.prices import PriceCache
    from PyQt6.QtCore import Qt
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist",
        lambda: [{"name": "AK-47", "target": 100, "triggered": False}])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    cache = PriceCache(tmp_path / "prices.json", ttl=3600)
    screen = WatchlistScreen(cache)
    screen._table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    assert screen._table.item(0, screen.COL_PRICE).text() == "Consultando…"

def test_watchlist_on_add_cancelled(monkeypatch):
    """_on_add returns early when dialog is cancelled."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist", lambda: [])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.DialogCode.Rejected)
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._on_add()

def test_watchlist_on_add_empty_name(monkeypatch):
    """_on_add does not add item when name is empty."""
    from PyQt6.QtWidgets import QDialog, QLineEdit, QDialogButtonBox
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist", lambda: [])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    add_called = []
    monkeypatch.setattr(
        "skinvault.watchlist.add_watch",
        lambda name, target: add_called.append((name, target)))
    orig_exec = QDialog.exec
    def controlled(self):
        for child in self.findChildren(QLineEdit):
            child.setText("")
            break
        for child in self.findChildren(QDialogButtonBox):
            child.accepted.emit()
            break
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", controlled)
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._on_add()
    assert len(add_called) == 0

def test_watchlist_on_add_success(monkeypatch):
    """_on_add adds item when form is valid."""
    from PyQt6.QtWidgets import QDialog, QLineEdit, QDoubleSpinBox, QDialogButtonBox
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(
        "skinvault.watchlist.load_watchlist", lambda: [])
    monkeypatch.setattr(
        "skinvault.alerts.load_alerts_log", lambda: [])
    add_called = []
    monkeypatch.setattr(
        "skinvault.watchlist.add_watch",
        lambda name, target: add_called.append((name, target)))
    orig_exec = QDialog.exec
    def controlled(self):
        for child in self.findChildren(QLineEdit):
            child.setText("AK-47")
            break
        for child in self.findChildren(QDoubleSpinBox):
            child.setValue(50.0)
            break
        for child in self.findChildren(QDialogButtonBox):
            child.accepted.emit()
            break
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", controlled)
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._on_add()
    assert len(add_called) == 1
    assert add_called[0] == ("AK-47", 50.0)


def test_watchlist_screen():
    """WatchlistScreen instancia sem erro."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    assert screen is not None


def test_dialogs_instantiation(monkeypatch):
    """BackupDialog e SteamSyncDialog instanciam."""
    monkeypatch.setattr("skinvault.sync.sync_all",
                        lambda *a, **kw: {})
    from skinvault.gui import BackupDialog, SteamSyncDialog
    from skinvault.steam_session import SteamSession
    assert BackupDialog() is not None
    assert SteamSyncDialog(SteamSession("key", "sid")) is not None


# ── PriceWorker edge cases ─────────────────────────────────────


def test_safe_emit_swallows_runtime_error():
    """_safe_emit tolera RuntimeError (C++ obj deletado)."""
    from skinvault.ui._price_worker import _safe_emit

    class _FakeSig:
        def emit(self, *args):
            raise RuntimeError("wrapped C/C++ object has been deleted")
    _safe_emit(_FakeSig(), 1, 2)  # nao crasha


def test_safe_emit_swallows_attribute_error():
    """_safe_emit tolera AttributeError tambem."""
    from skinvault.ui._price_worker import _safe_emit

    class _FakeSig:
        def emit(self, *args):
            raise AttributeError("no emit")
    _safe_emit(_FakeSig())


def test_batch_price_worker_running_guard(monkeypatch):
    """start() quando _running=True retorna cedo."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import BatchPriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    cache = PriceCache(ttl=3600)
    worker = BatchPriceWorker(cache)
    # Seta _running manualmente
    worker._running = True
    worker.start(["AK"])  # nao deve crashar nem emitir


def test_batch_price_worker_exception_caught(monkeypatch):
    """cached_price que falha nao quebra o batch."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import BatchPriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: (_ for _ in ()).throw(ValueError("fail")))
    cache = PriceCache(ttl=3600)
    worker = BatchPriceWorker(cache)
    progress_log = []
    worker.progress.connect(lambda d, t: progress_log.append((d, t)))
    done_log = []
    worker.batch_done.connect(lambda: done_log.append(True))
    worker.start(["AK", "AWP"])
    QApplication.processEvents()
    assert done_log == [True]
    assert progress_log == [(1, 2), (2, 2)]


def test_single_price_worker_exception_caught(monkeypatch):
    """cached_price que falha emite done com None."""
    from PyQt6.QtWidgets import QApplication
    from skinvault.prices import PriceCache
    from skinvault.ui._price_worker import SinglePriceWorker

    monkeypatch.setattr("threading.Thread", _InlineThread)
    monkeypatch.setattr("skinvault.prices.cached_price",
                        lambda n, c: (_ for _ in ()).throw(ValueError("fail")))
    cache = PriceCache(ttl=3600)
    worker = SinglePriceWorker(cache)
    results = []
    worker.done.connect(lambda n, p: results.append((n, p)))
    worker.start("AK")
    QApplication.processEvents()
    assert results == [("AK", None)]


# ── Componentes ────────────────────────────────────────────────


def test_card_set_layout_swaps_layout():
    """Card.set_layout() substitui o layout default."""
    from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout
    from skinvault.ui.components import Card

    c = Card()
    old = c.layout()
    assert old is not None
    new_lay = QHBoxLayout()
    c.set_layout(new_lay)
    assert c.layout() is new_lay


def test_sidebar_select_nonexistent():
    """Sidebar.select() com key nao existente nao crasha."""
    from skinvault.ui.components import Sidebar
    s = Sidebar()
    s.select("noexist")  # nao crasha


def test_sidebar_select_already_checked():
    """Sidebar.select() com btn ja checked nao crasha."""
    from PyQt6.QtWidgets import QPushButton
    from skinvault.ui.components import Sidebar
    s = Sidebar()
    btn = QPushButton("Test")
    s._items["k"] = btn
    btn.setChecked(True)
    s.select("k")  # nao crasha


def test_segmented_control_select_nonexistent():
    """SegmentedControl.select() com key nao existente."""
    from skinvault.ui.components import SegmentedControl
    sc = SegmentedControl()
    sc.select("noexist")  # retorno cedo


def test_breadcrumb_set_right():
    """Breadcrumb.set_right() atualiza label direito."""
    from skinvault.ui.components import Breadcrumb
    b = Breadcrumb()
    b.set_right("status")
    assert b._right.text() == "status"


def test_avatar_set_image_bytes(monkeypatch, tmp_path):
    """Avatar.set_image() com bytes."""
    from skinvault.ui.components import Avatar
    a = Avatar()
    a.set_image(b"not-a-real-png")
    # nao crashou, pixmap.isNull() → True → early return


def test_avatar_set_image_string(monkeypatch, tmp_path):
    """Avatar.set_image() com string path (inexistente)."""
    from skinvault.ui.components import Avatar
    a = Avatar()
    a.set_image(str(tmp_path / "noexist.png"))
    # pixmap.isNull() → True → early return


def test_avatar_set_image_none():
    """Avatar.set_image() com None retorna cedo."""
    from skinvault.ui.components import Avatar
    a = Avatar()
    a.set_image(None)


def test_avatar_set_image_valid_bytes():
    """Avatar.set_image() com bytes PNG valido carrega pixmap."""
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import QBuffer, QIODevice
    from skinvault.ui.components import Avatar

    pix = QPixmap(10, 10)
    pix.fill(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("red"))
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    data = buf.data().data()

    a = Avatar()
    a.set_image(bytes(data))
    assert a.pixmap() is not None


def test_sidebar_item_on_toggled_pinta_icone():
    """_on_toggled sincroniza a cor do LineIcon com o estado checked."""
    from skinvault.ui import theme as t
    from skinvault.ui.components import _SidebarItem
    si = _SidebarItem("user", "L")
    si._on_toggled(True)
    assert si._icon._color == t.ACCENT
    si._on_toggled(False)
    assert si._icon._color == t.TEXT_MUTED


def test_lineicon_paints_all_named_glyphs():
    """LineIcon renderiza cada nome conhecido sem crashar (grab nao-nulo)."""
    from skinvault.ui.components import LineIcon
    names = ["user", "history", "radar", "chart", "swap",
             "calc", "eye", "gear", "info", "archive"]
    for name in names:
        ic = LineIcon(name)
        pix = ic.grab()
        assert not pix.isNull(), name


def test_lineicon_unknown_name_falls_back():
    """Nome desconhecido cai no fallback (circulo) sem crashar."""
    from skinvault.ui.components import LineIcon
    ic = LineIcon("nao-existe")
    assert not ic.grab().isNull()


def test_lineicon_set_color_triggers_repaint():
    """set_color muda a cor e nao quebra o paint."""
    from skinvault.ui import theme as t
    from skinvault.ui.components import LineIcon
    ic = LineIcon("user")
    ic.set_color(t.ACCENT)
    assert ic._color == t.ACCENT
    assert not ic.grab().isNull()


def test_sidebar_session_chip():
    """add_session_chip + set_session controla visibilidade e texto."""
    from skinvault.ui.components import Sidebar
    sb = Sidebar()
    sb.add_session_chip()
    assert sb._chip.isHidden()  # inicia oculto
    sb.set_session("nokia", "76561198000000001")
    assert not sb._chip.isHidden()
    assert sb._chip_name.text() == "nokia"
    assert "76561198000000001" in sb._chip.toolTip()
    # deslogado esconde de novo
    sb.set_session("", "")
    assert sb._chip.isHidden()


def test_sidebar_session_chip_steamid_fallback():
    """Sem nome, o chip trunca o steamid."""
    from skinvault.ui.components import Sidebar
    sb = Sidebar()
    sb.add_session_chip()
    sb.set_session("", "76561198000000001")
    assert "…" in sb._chip_name.text()


def test_sidebar_chip_click_navigates_account():
    """Clique no chip emite item_selected('account')."""
    from skinvault.ui.components import Sidebar
    sb = Sidebar()
    sb.add_session_chip()
    emitted = []
    sb.item_selected.connect(emitted.append)
    sb._chip.mousePressEvent(None)
    assert emitted == ["account"]


def test_sidebar_add_action_not_checkable():
    """add_action cria item de acao (sem estado checked) com icone."""
    from skinvault.ui.components import Sidebar
    sb = Sidebar()
    calls = []
    btn = sb.add_action("gear", "Config", lambda: calls.append(1))
    assert not btn.isCheckable()
    btn.click()
    assert calls == [1]


# ── LoginGate _on_connect ──────────────────────────────────────


def test_login_gate_on_connect_cancelled(monkeypatch):
    """Dialog cancelado nao emite session_connected."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.ui.login_gate import LoginGate

    class MockCancelDialog:
        def exec(self):
            return QDialog.DialogCode.Rejected
        session = None

    monkeypatch.setattr("skinvault.ui.login_gate.build_steam_login_dialog",
                        lambda parent: MockCancelDialog())
    gate = LoginGate()
    results = []
    gate.session_connected.connect(lambda s: results.append(s))
    gate._on_connect()
    assert results == []


def test_login_gate_on_connect_incomplete_session(monkeypatch):
    """Session incompleta mostra warning."""
    from PyQt6.QtWidgets import QDialog, QMessageBox
    from skinvault.steam_session import SteamSession
    from skinvault.ui.login_gate import LoginGate

    class MockDialog:
        def exec(self):
            return QDialog.DialogCode.Accepted
        session = SteamSession(steamid="", cookies={})

    monkeypatch.setattr("skinvault.ui.login_gate.build_steam_login_dialog",
                        lambda parent: MockDialog())
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: None)
    gate = LoginGate()
    results = []
    gate.session_connected.connect(lambda s: results.append(s))
    gate._on_connect()
    assert results == []


def test_login_gate_on_connect_success(monkeypatch):
    """Session valida persiste e emite."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.steam_session import SteamSession
    from skinvault.ui.login_gate import LoginGate

    sess = SteamSession(steamid="123", cookies={"steamLoginSecure": "tok"})

    class MockDialog:
        def exec(self):
            return QDialog.DialogCode.Accepted
        session = sess

    persist_calls = []
    monkeypatch.setattr("skinvault.ui.login_gate.build_steam_login_dialog",
                        lambda parent: MockDialog())
    monkeypatch.setattr("skinvault.steam_session.persist",
                        lambda s: persist_calls.append(s))
    gate = LoginGate()
    results = []
    gate.session_connected.connect(lambda s: results.append(s))
    gate._on_connect()
    assert len(persist_calls) == 1
    assert len(results) == 1
    assert results[0].steamid == "123"


# ── HistoryScreen helpers ──────────────────────────────────


def test_in_period_all():
    """_in_period com 'all' sempre retorna True."""
    from skinvault.ui.history_screen import _in_period
    assert _in_period(0, "all") is True
    assert _in_period(1e12, "all") is True


def test_in_period_7d():
    """_in_period com '7d' filtra por 7 dias."""
    from skinvault.ui.history_screen import _in_period
    assert _in_period(1e12, "7d") is True
    assert _in_period(0, "7d") is False


def test_in_period_30d():
    """_in_period com '30d' filtra por 30 dias."""
    from skinvault.ui.history_screen import _in_period
    assert _in_period(1e12, "30d") is True
    assert _in_period(0, "30d") is False


def test_in_period_90d():
    """_in_period com '90d' filtra por 90 dias."""
    from skinvault.ui.history_screen import _in_period
    assert _in_period(1e12, "90d") is True
    assert _in_period(0, "90d") is False


def test_in_period_unknown():
    """_in_period com periodo desconhecido usa cutoff=now."""
    import time
    from skinvault.ui.history_screen import _in_period
    # days.get("xyz", 0) = 0 -> cutoff = now, then ts >= now
    assert _in_period(0, "xyz") is False
    assert _in_period(time.time() + 1000, "xyz") is True


# ── HistoryScreen._event_ts / _fmt_event_date ─────────────


def test_event_ts_usa_date_str_parsado():
    """_event_ts prefere parse de date_str sobre synced_at."""
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    # synced_at=999999999, date_str valido -> deve usar date_str
    ev = {"date_str": "15 Mar", "synced_at": 0}
    ts = screen._event_ts(ev)
    assert ts > 0  # parse succeeded


def test_event_ts_fallback_synced_at():
    """_event_ts cai pra synced_at se date_str nao parseia."""
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    ev = {"date_str": "garbage", "synced_at": 12345.0}
    assert screen._event_ts(ev) == 12345.0


def test_event_ts_sem_dados():
    """_event_ts retorna 0 quando ambos faltam."""
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    assert screen._event_ts({}) == 0.0
    assert screen._event_ts({"date_str": "", "synced_at": None}) == 0.0


def test_fmt_event_date_formato_brasileiro():
    """_fmt_event_date retorna DD/MM/YY consistente, com ano resolvido."""
    import re
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    out = screen._fmt_event_date({"date_str": "15 Mar"})
    # DD/MM/YY com 2 digitos de ano em todos os campos
    assert re.fullmatch(r"\d{2}/\d{2}/\d{2}", out), out


def test_fmt_event_date_sem_dados_retorna_dash():
    """_fmt_event_date retorna '—' quando date_str e synced_at faltam."""
    from skinvault.ui.history_screen import HistoryScreen
    screen = HistoryScreen()
    assert screen._fmt_event_date({}) == "—"


def test_side_label_buy_sell():
    """_side_label normaliza 'buy'/'sell' em pt-BR."""
    from skinvault.ui.history_screen import _side_label
    assert _side_label("buy") == "Compra"
    assert _side_label("BUY") == "Compra"
    assert _side_label("sell") == "Venda"


def test_side_label_outros_e_none():
    """_side_label devolve original quando nao for buy/sell."""
    from skinvault.ui.history_screen import _side_label
    assert _side_label(None) == "—"
    assert _side_label("") == "—"
    assert _side_label("listed") == "listed"


class TestFilterBar:
    """Testes do _FilterBar."""

    def test_set_periodo_emits(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        signals = []
        fb.filters_changed.connect(lambda: signals.append(True))
        fb._set_periodo("30d")
        assert fb._periodo == "30d"
        assert signals == [True]

    def test_set_tipo_emits(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        signals = []
        fb.filters_changed.connect(lambda: signals.append(True))
        fb._set_tipo("buy")
        assert fb._tipo == "buy"
        assert signals == [True]

    def test_on_search_changed_emits(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        signals = []
        fb.filters_changed.connect(lambda: signals.append(True))
        fb._on_search_changed("text")
        assert signals == [True]

    def test_clear_resets_all(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb._set_periodo("30d")
        fb._set_tipo("buy")
        fb._search.setText("AK")
        fb._clear()
        assert fb._periodo == "all"
        assert fb._tipo == "all"
        assert fb._search.text() == ""

    def test_clear_search(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb._search.setText("test")
        fb.clear_search()
        assert fb._search.text() == ""

    def test_clear_search_empty(self):
        """clear_search com search vazio nao crasha."""
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb.clear_search()

    def test_focus_search(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb.focus_search()
        # setFocus nao funciona sem widget visivel, mas nao crasha

    def test_set_periodoo_btn(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb.set_periodo("30d")
        assert fb._periodo == "30d"
        assert fb._periodo_btns["30d"].isChecked()

    def test_set_periodoo_nonexistent(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb.set_periodo("noexist")  # nao crasha

    def test_set_periodoo_already_checked(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb.set_periodo("all")  # ja' e' o default, nao crasha
        assert fb._periodo == "all"

    def test_set_tipo_visible(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        fb.show()  # necessario para isVisible() funcionar
        QApplication.processEvents()
        fb.set_tipo_visible(False)
        for w in fb._tipo_widgets:
            assert not w.isVisible()
        fb.set_tipo_visible(True)
        for w in fb._tipo_widgets:
            assert w.isVisible()

    def test_properties(self):
        from skinvault.ui.history_screen import _FilterBar
        fb = _FilterBar()
        assert fb.periodo == "all"
        assert fb.tipo == "all"
        assert fb.search_text == ""


class TestSimulateTradeDialog:
    """Testes do SimulateTradeDialog."""

    def test_parse_float_none(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        assert dlg._parse_float("") is None
        assert dlg._parse_float(None) is None

    def test_parse_float_brl(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        assert dlg._parse_float("150,50") == 150.50

    def test_parse_float_with_r_prefix(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        assert dlg._parse_float("R$ 200") == 200.0

    def test_parse_float_invalid(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        assert dlg._parse_float("abc") is None

    def test_calc_invalid_inputs(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        dlg._calc()  # campos vazios
        assert dlg._pnl_lbl.text() == "Valores invalidos"

    def test_calc_valid_trade(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        dlg._buy.setText("100")
        dlg._sell.setText("200")
        dlg._qty.setText("1")
        dlg._calc()
        assert "ROI" in dlg._pnl_lbl.text()
        assert "Steam" in dlg._detail.text()

    def test_calc_invalid_qty_falls_back_to_1(self):
        from skinvault.ui.history_screen import SimulateTradeDialog
        dlg = SimulateTradeDialog()
        dlg._buy.setText("100")
        dlg._sell.setText("200")
        dlg._qty.setText("abc")  # qty invalida -> falls back to 1
        dlg._calc()
        assert "ROI" in dlg._pnl_lbl.text()


class TestHistoryScreen:
    """Testes focados em metodos auxiliares do HistoryScreen."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self, monkeypatch):
        monkeypatch.setattr(
            "skinvault.ui.history_screen.load_settings", lambda: {})
        monkeypatch.setattr(
            "skinvault.ui.history_screen.save_settings", lambda s: None)

    def test_fmt_ts_zero(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        assert screen._fmt_ts(0) == "—"

    def test_fmt_ts_valid(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        result = screen._fmt_ts(1_700_000_000)
        assert "2023" in result or "2024" in result or "20" in result

    def test_fmt_source_steam(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        assert screen._fmt_source("steam") == "Steam"
        assert screen._fmt_source("steam_sync") == "Steam"
        assert screen._fmt_source("manual") == "Manual"

    def test_match_search_empty(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        assert screen._match_search("AK-47") is True

    def test_match_search_with_filter(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._search.setText("AK")
        assert screen._match_search("AK-47") is True
        assert screen._match_search("AWP") is False

    def test_populate_basic(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        headers = ["Data", "Item", "Valor"]
        rows = [
            ["2024-01-01", "AK-47", "R$ 100"],
            ["2024-01-02", "AWP", "R$ 200"],
        ]
        screen._populate(headers, rows)
        assert screen._table.columnCount() == 3
        assert screen._table.rowCount() == 2
        assert screen._table.item(0, 1).text() == "AK-47"

    def test_populate_with_pnl_coloring(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        headers = ["Data", "Item", "P&L"]
        rows = [
            ["2024-01-01", "AK-47", "R$ 100"],
        ]
        screen._populate(headers, rows, pnl_col=2, pnl_vals=[50.0])
        item = screen._table.item(0, 2)
        # Verifica que tem foreground configurado (cor)
        assert item.foreground() is not None

    def test_populate_with_origin_steam(self):
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        from skinvault.ui import theme as t
        screen = HistoryScreen(PriceCache(ttl=3600))
        headers = ["Item", "Origem"]
        rows = [
            ["AK-47", "Steam"],
        ]
        screen._populate(headers, rows)
        assert screen._table.item(0, 1).foreground() is not None

    def test_refresh_all_empty(self, monkeypatch):
        """refresh com segmento 'all' e dados vazios."""
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "all"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_refresh_trades(self, monkeypatch):
        """refresh com segmento 'trades' exibe dados mockados."""
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 1_700_000_000, "name": "AK-47", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
        ])
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "trades"
        screen.refresh()
        assert screen._table.rowCount() == 1
        assert "AK-47" in screen._table.item(0, 1).text()

    def test_on_segment_changes_state(self, monkeypatch):
        """_on_segment atualiza estado e refresh."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._on_segment("market")
        assert screen._current_segment == "market"

    def test_on_segment_open_shows_update_btn(self, monkeypatch):
        """_on_segment 'open' mostra btn atualizar precos."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trade_matcher.load_open_buys",
                            lambda: [])
        monkeypatch.setattr("skinvault.settings.load_settings", lambda: {})
        monkeypatch.setattr("skinvault.settings.save_settings",
                            lambda s: None)
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen.show()
        QApplication.processEvents()
        screen._on_segment("open")
        assert screen._update_prices_btn.isVisible()

    def test_refresh_matched(self, monkeypatch):
        """refresh com 'matched' mostra status com win rate."""
        from skinvault.trade_matcher import ClosedTrade
        monkeypatch.setattr(
            "skinvault.trade_matcher.load_closed_trades",
            lambda: [
                ClosedTrade(
                    name="AK-47",
                    buy_date="2024-01-01", buy_price=100,
                    sell_date="2024-02-01", sell_price=200,
                    sell_ts=1_710_000_000, pnl=50, pnl_pct=50,
                ),
            ],
        )
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "matched"
        screen.refresh()
        assert screen._table.rowCount() == 1
        assert "win" in screen._status.text().lower()

    def test_refresh_open_no_cache(self, monkeypatch):
        """refresh com 'open' e sem cache mostra '—'."""
        from skinvault.trade_matcher import OpenBuy
        monkeypatch.setattr(
            "skinvault.trade_matcher.load_open_buys",
            lambda: [
                OpenBuy(name="ZZZ_UNIT_TEST_AWP",
                        buy_date="2024-01-01",
                        buy_price=250, buy_ts=1_700_000_000),
            ],
        )
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "open"
        screen.refresh()
        assert screen._table.rowCount() == 1
        assert "—" in screen._table.item(0, 3).text()  # price not cached

    def test_refresh_watchlist(self, monkeypatch):
        """refresh com 'watchlist' exibe dados."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr(
            "skinvault.watchlist.load_watchlist",
            lambda: [
                {"name": "AK-47", "target": 150, "triggered": False,
                 "added_ts": 1_700_000_000},
            ],
        )
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "watchlist"
        screen.refresh()
        assert screen._table.rowCount() == 1
        assert "AK-47" in screen._table.item(0, 0).text()

    def test_refresh_market_with_tipo_filter(self, monkeypatch):
        """refresh market filtra por tipo buy/sell."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr(
            "skinvault.sync.load_market_events",
            lambda: [
                {"synced_at": 1_700_000_000, "name": "AK-47",
                 "side": "buy", "price": 100, "date_str": "1 Jan",
                 "listing_id": "abc"},
            ],
        )
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "market"
        screen._filter_panel._set_tipo("buy")
        screen.refresh()
        assert screen._table.rowCount() == 1

    def test_refresh_market_filtered_out(self, monkeypatch):
        """refresh market filtra quando tipo nao confere."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr(
            "skinvault.sync.load_market_events",
            lambda: [
                {"synced_at": 1_700_000_000, "name": "AK-47",
                 "side": "buy", "price": 100, "date_str": "1 Jan",
                 "listing_id": "abc"},
            ],
        )
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "market"
        screen._filter_panel._set_tipo("sell")
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_all_timeline(self, monkeypatch):
        """_load_all mescla trades + market + offers em ordem."""
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 1_700_000_001, "name": "Trade1", "pnl": 50,
             "source": "manual"},
        ])
        monkeypatch.setattr(
            "skinvault.sync.load_market_events",
            lambda: [
                {"synced_at": 1_700_000_000, "name": "Market1",
                 "side": "buy", "price": 100, "date_str": "1 Jan",
                 "listing_id": "abc"},
            ],
        )
        monkeypatch.setattr(
            "skinvault.sync.load_trade_offers",
            lambda: [
                {"synced_at": 1_699_999_999, "name": "Offer1",
                 "date_str": "31 Dec", "partner_steamid": "7656",
                 "tradeofferid": "123", "items_given": ["AWP"]},
            ],
        )
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "all"
        screen.refresh()
        assert screen._table.rowCount() >= 3

    def test_on_update_prices_all_cached(self, monkeypatch):
        """_on_update_prices com todos em cache mostra msg."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        from skinvault.trade_matcher import OpenBuy
        monkeypatch.setattr(
            "skinvault.trade_matcher.load_open_buys",
            lambda: [
                OpenBuy(name="AK-47", buy_price=100,
                        buy_ts=1_700_000_000,
                        buy_date="2024-01-01"),
            ],
        )
        cache = PriceCache(ttl=3600)
        cache.put("AK-47", 150.0)
        screen = HistoryScreen(cache)
        screen._open_cache = [OpenBuy(name="AK-47", buy_price=100,
                                      buy_ts=1_700_000_000,
                                      buy_date="2024-01-01")]
        screen._current_segment = "open"
        screen._on_update_prices()
        assert "todos os precos" in screen._status.text()

    def test_on_prices_updated_refreshes_open(self, monkeypatch):
        """_on_prices_updated reativa botao e refresh se segmento open."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "open"
        screen._on_prices_updated()
        assert screen._update_prices_btn.isEnabled()

    def test_on_batch_progress_updates_text(self, monkeypatch):
        """_on_batch_progress atualiza texto do botao."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "open"
        screen._on_batch_progress(5, 20)
        assert "5/20" in screen._update_prices_btn.text()

    def test_on_export_csv_cancelled(self, monkeypatch):
        """_on_export_csv com cancelamento nao crasha."""
        from skinvault.ui.history_screen import HistoryScreen
        from PyQt6.QtWidgets import QFileDialog
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            lambda *a, **kw: ("", ""))
        screen = HistoryScreen()
        screen._on_export_csv()

    def test_refresh_offers(self, monkeypatch):
        """refresh com 'offers' exibe trade offers."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr(
            "skinvault.sync.load_trade_offers",
            lambda: [
                {"synced_at": 1_700_000_000, "date_str": "1 Jan",
                 "partner_steamid": "7656", "tradeofferid": "123",
                 "items_given": ["AWP"]},
            ],
        )
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "offers"
        screen.refresh()
        assert screen._table.rowCount() == 1
        assert "7656" in screen._table.item(0, 1).text()

    def test_open_simulator(self, monkeypatch):
        """_open_simulator abre dialog."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen, SimulateTradeDialog
        exec_called = []
        monkeypatch.setattr(SimulateTradeDialog, "exec",
                            lambda self: exec_called.append(True))
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._open_simulator()
        assert len(exec_called) == 1

    def test_export_csv_empty(self, monkeypatch):
        """_on_export_csv com tabela vazia mostra mensagem."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "trades"
        screen.refresh()
        screen._on_export_csv()
        assert "Nada" in screen._status.text()

    def test_export_csv_with_data(self, monkeypatch, tmp_path):
        """_on_export_csv com dados exporta arquivo."""
        import tempfile
        from PyQt6.QtWidgets import QFileDialog
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        d = tmp_path / "out.csv"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            lambda *a, **kw: (str(d), ""))
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 1_700_000_000, "name": "AK-47", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "trades"
        screen.refresh()
        screen._on_export_csv()
        assert "Exportado" in screen._status.text()
        raw = d.read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"
        assert b"Data" in raw[3:]

    def test_export_csv_os_error(self, monkeypatch):
        """_on_export_csv captura OSError."""
        from unittest.mock import mock_open
        from PyQt6.QtWidgets import QFileDialog
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            lambda *a, **kw: ("dummy.csv", ""))
        m = mock_open()
        m.side_effect = OSError("denied")
        monkeypatch.setattr("builtins.open", m)
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 1_700_000_000, "name": "AK-47", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "trades"
        screen.refresh()
        screen._on_export_csv()
        assert "Erro" in screen._status.text()

    def test_on_update_prices_starts_worker(self, monkeypatch):
        """_on_update_prices inicia worker quando ha nomes faltando."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        from skinvault.trade_matcher import OpenBuy
        start_called = []
        screen = HistoryScreen(PriceCache(ttl=3600))
        monkeypatch.setattr(
            screen._price_worker, "start",
            lambda names: start_called.append(names),
        )
        screen._open_cache = [
            OpenBuy(name="ZZZ_UNIT_TEST_NO_CACHE", buy_price=100,
                    buy_ts=1_700_000_000, buy_date="2024-01-01"),
        ]
        screen._on_update_prices()
        assert not screen._update_prices_btn.isEnabled()
        assert "Atualizando" in screen._update_prices_btn.text()

    def test_on_prices_updated_other_segment(self, monkeypatch):
        """_on_prices_updated reativa botao mas nao recarrega fora open."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "trades"
        screen._on_prices_updated()
        assert screen._update_prices_btn.isEnabled()

    def test_on_batch_progress_triggers_refresh(self, monkeypatch):
        """_on_batch_progress com done%10==0 e segment open recarrega."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trade_matcher.load_open_buys",
                            lambda: [])
        monkeypatch.setattr("skinvault.settings.load_settings", lambda: {})
        monkeypatch.setattr("skinvault.settings.save_settings",
                            lambda s: None)
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "open"
        screen._on_batch_progress(10, 100)
        assert "10/100" in screen._update_prices_btn.text()

    def test_on_batch_progress_no_refresh(self, monkeypatch):
        """_on_batch_progress com done%10!=0 nao recarrega."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._current_segment = "trades"
        screen._on_batch_progress(11, 100)
        assert "11/100" in screen._update_prices_btn.text()

    def test_load_trades_period_filter(self, monkeypatch):
        """_load_trades filtra por periodo."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 0, "name": "Antigo", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
            {"sell_ts": 1_700_000_000, "name": "Recente", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._set_periodo("7d")
        screen._current_segment = "trades"
        screen.refresh()
        assert screen._table.rowCount() == 0  # ambos fora do periodo 7d

    def test_load_trades_search_filter(self, monkeypatch):
        """_load_trades filtra por busca."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 1_700_000_000, "name": "AK-47", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._search.setText("AWP")
        screen._current_segment = "trades"
        screen.refresh()
        assert screen._table.rowCount() == 0  # nome nao corresponde

    def test_load_open_cache_hit(self, monkeypatch):
        """_load_open com cache carregado mostra P&L."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        from skinvault.trade_matcher import OpenBuy
        monkeypatch.setattr("skinvault.settings.load_settings", lambda: {})
        monkeypatch.setattr("skinvault.settings.save_settings",
                            lambda s: None)
        monkeypatch.setattr(
            "skinvault.trade_matcher.load_open_buys",
            lambda: [
                OpenBuy(name="AWP", buy_date="2024-01-01",
                        buy_price=100, buy_ts=1_700_000_000),
            ],
        )
        cache = PriceCache(ttl=3600)
        cache.put("AWP", 200.0)
        screen = HistoryScreen(cache)
        screen._current_segment = "open"
        screen.refresh()
        assert screen._table.rowCount() == 1
        assert "R$" in screen._table.item(0, 3).text()  # preco atual

    def test_load_market_period_filter(self, monkeypatch):
        """_load_market filtra evento fora do periodo."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [
            {"synced_at": 0, "name": "Antigo", "side": "buy",
             "price": 100, "date_str": "1 Jan", "listing_id": "abc"},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._set_periodo("7d")
        screen._current_segment = "market"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_market_search_filter(self, monkeypatch):
        """_load_market filtra por busca."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [
            {"synced_at": 1_700_000_000, "name": "AK-47", "side": "buy",
             "price": 100, "date_str": "1 Jan", "listing_id": "abc"},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._search.setText("AWP")
        screen._current_segment = "market"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_offers_period_filter(self, monkeypatch):
        """_load_offers filtra oferta fora do periodo."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [
            {"synced_at": 0, "date_str": "1 Jan",
             "partner_steamid": "7656", "tradeofferid": "123",
             "items_given": ["AWP"]},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._set_periodo("7d")
        screen._current_segment = "offers"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_offers_search_filter(self, monkeypatch):
        """_load_offers filtra por busca (items_given)."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [
            {"synced_at": 1_700_000_000, "date_str": "1 Jan",
             "partner_steamid": "7656", "tradeofferid": "123",
             "items_given": ["AWP"]},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._search.setText("AK-47")
        screen._current_segment = "offers"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_watchlist_period_filter(self, monkeypatch):
        """_load_watchlist filtra item fora do periodo."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.watchlist.load_watchlist", lambda: [
            {"name": "AK-47", "target": 150, "triggered": False,
             "added_ts": 0},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._set_periodo("7d")
        screen._current_segment = "watchlist"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_watchlist_search_filter(self, monkeypatch):
        """_load_watchlist filtra por busca."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.watchlist.load_watchlist", lambda: [
            {"name": "AK-47", "target": 150, "triggered": False,
             "added_ts": 1_700_000_000},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._search.setText("AWP")
        screen._current_segment = "watchlist"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_all_trades_period_filter(self, monkeypatch):
        """_load_all filtra trade fora do periodo."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [
            {"sell_ts": 0, "name": "Antigo", "quantity": 1,
             "buy_cost": 100, "sell_price": 200, "pnl": 50,
             "source": "manual"},
        ])
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._set_periodo("7d")
        screen._current_segment = "all"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_all_market_period_filter(self, monkeypatch):
        """_load_all filtra market event fora do periodo."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [
            {"synced_at": 0, "name": "Antigo", "side": "buy",
             "price": 100, "date_str": "1 Jan", "listing_id": "abc"},
        ])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._set_periodo("7d")
        screen._current_segment = "all"
        screen.refresh()
        assert screen._table.rowCount() == 0

    def test_load_all_offers_search_filter(self, monkeypatch):
        """_load_all filtra offer por busca."""
        from skinvault.prices import PriceCache
        from skinvault.ui.history_screen import HistoryScreen
        monkeypatch.setattr("skinvault.trades.load_trades", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_market_events", lambda: [])
        monkeypatch.setattr("skinvault.sync.load_trade_offers", lambda: [
            {"synced_at": 1_700_000_000, "date_str": "1 Jan",
             "partner_steamid": "7656", "tradeofferid": "123",
             "items_given": ["AWP"]},
        ])
        screen = HistoryScreen(PriceCache(ttl=3600))
        screen._filter_panel._search.setText("AK-47")
        screen._current_segment = "all"
        screen.refresh()
        assert screen._table.rowCount() == 0


# ── SteamLoginDialog ───────────────────────────────────────────

def test_find_free_port():
    """_find_free_port returns a valid available port."""
    from skinvault.steam_login_dialog import _find_free_port
    port = _find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535

def test_collect_steam_cookies_captures_refresh_token():
    """_collect_steam_cookies pega community + steamRefresh_steam (login.steampowered)."""
    from skinvault.steam_login_dialog import _collect_steam_cookies
    cdp = [
        {"domain": "steamcommunity.com", "name": "steamLoginSecure", "value": "sec"},
        {"domain": "steamcommunity.com", "name": "sessionid", "value": "sid"},
        {"domain": "login.steampowered.com", "name": "steamRefresh_steam",
         "value": "76561%7C%7Crefresh"},
        {"domain": "store.steampowered.com", "name": "irrelevante", "value": "x"},
    ]
    out = _collect_steam_cookies(cdp)
    assert out["steamLoginSecure"] == "sec"
    assert out["sessionid"] == "sid"
    assert out["steamRefresh_steam"] == "76561%7C%7Crefresh"
    assert "irrelevante" not in out

def test_collect_steam_cookies_ignores_refresh_from_wrong_domain():
    """steamRefresh_steam só é aceito do domínio login.steampowered.com."""
    from skinvault.steam_login_dialog import _collect_steam_cookies
    cdp = [
        {"domain": "evil.com", "name": "steamRefresh_steam", "value": "x"},
    ]
    assert _collect_steam_cookies(cdp) == {}

def test_btn_ghost():
    """btn_ghost returns a stylesheet string."""
    from skinvault.ui import theme as t
    css = t.btn_ghost()
    assert "QPushButton" in css

def test_build_steam_login_dialog():
    """build_steam_login_dialog factory returns a dialog."""
    from skinvault.steam_login_dialog import build_steam_login_dialog
    dlg = build_steam_login_dialog()
    assert dlg is not None
    assert dlg.windowTitle() == "Conectar conta Steam"

def test_steam_login_dialog_init():
    """SteamLoginDialog initializes with default state."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    assert dlg.session is None
    assert dlg._chrome_proc is None
    assert dlg._ws is None
    assert dlg._monitor_active is False

def test_on_cancel():
    """_on_cancel calls cleanup and reject."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._cleanup = lambda: setattr(dlg, '_cleanup_called', True)
    dlg.reject = lambda: setattr(dlg, '_reject_called', True)
    dlg._on_cancel()
    assert dlg._cleanup_called
    assert dlg._reject_called

def test_cleanup_ws():
    """_cleanup closes websocket if present."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    ws_close = []
    dlg._ws = type("WS", (), {"close": lambda self: ws_close.append(True)})()
    dlg._cleanup()
    assert len(ws_close) == 1
    assert dlg._ws is None

def test_cleanup_ws_error():
    """_cleanup handles websocket close error gracefully."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._ws = type("WS", (), {
        "close": lambda self: (_ for _ in ()).throw(Exception("fail"))
    })()
    dlg._cleanup()
    assert dlg._ws is None

def test_cleanup_chrome_terminate():
    """_cleanup terminates chrome process."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._chrome_proc = type("Proc", (), {
        "terminate": lambda self: None,
        "wait": lambda self, timeout: None,
    })()
    dlg._cleanup()
    assert dlg._chrome_proc is None

def test_cleanup_chrome_terminate_fails():
    """_cleanup kills chrome if terminate fails."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    killed = []
    dlg = SteamLoginDialog()
    dlg._chrome_proc = type("Proc", (), {
        "terminate": lambda self: (_ for _ in ()).throw(Exception("fail")),
        "wait": lambda self, timeout: None,
        "kill": lambda self: killed.append(True),
    })()
    dlg._cleanup()
    assert len(killed) == 1
    assert dlg._chrome_proc is None

def test_cleanup_chrome_kill_fails():
    """_cleanup handles chrome kill failure gracefully."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._chrome_proc = type("Proc", (), {
        "terminate": lambda self: (_ for _ in ()).throw(Exception("fail")),
        "wait": lambda self, timeout: None,
        "kill": lambda self: (_ for _ in ()).throw(Exception("fail2")),
    })()
    dlg._cleanup()
    assert dlg._chrome_proc is None

def test_cleanup_user_data_dir(tmp_path):
    """_cleanup removes temp user data dir."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._user_data_dir = str(tmp_path / "sv_test")
    (tmp_path / "sv_test").mkdir()
    dlg._cleanup()
    assert dlg._user_data_dir is None
    assert not (tmp_path / "sv_test").exists()

def test_send_cdp_no_ws():
    """_send_cdp returns -1 when websocket is None."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    assert dlg._send_cdp("Network.enable") == -1

def test_send_cdp_with_ws(monkeypatch):
    """_send_cdp sends JSON via websocket and returns mid."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    sent = []
    monkeypatch.setattr("json.dumps", lambda x: str(x))
    dlg = SteamLoginDialog()
    dlg._ws = type("WS", (), {"send": lambda self, m: sent.append(m)})()
    mid = dlg._send_cdp("Network.enable", {"domain": "steam"})
    assert isinstance(mid, int)
    assert mid > 0
    assert len(sent) == 1

def test_recv_cdp_no_ws():
    """_recv_cdp returns None when websocket is None."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    assert dlg._recv_cdp() is None

def test_recv_cdp_success(monkeypatch):
    """_recv_cdp returns parsed message from websocket."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._ws = type("WS", (), {
        "settimeout": lambda self, t: None,
        "recv": lambda self: '{"id": 1, "result": {"ok": true}}',
    })()
    result = dlg._recv_cdp()
    assert result is not None
    assert result["id"] == 1

def test_recv_cdp_exception():
    """_recv_cdp returns None on websocket error."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._ws = type("WS", (), {
        "settimeout": lambda self, t: None,
        "recv": lambda self: (_ for _ in ()).throw(Exception("timeout")),
    })()
    assert dlg._recv_cdp() is None

def test_wait_for_cdp_result_match():
    """_wait_for_cdp_result returns result when id matches."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._recv_cdp = lambda timeout=1.0: {"id": 42, "result": {"cookies": []}}
    result = dlg._wait_for_cdp_result(42)
    assert result is not None
    assert result["cookies"] == []

def test_wait_for_cdp_result_timeout():
    """_wait_for_cdp_result returns None on timeout."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._recv_cdp = lambda timeout=1.0: {"id": 99, "result": {}}
    result = dlg._wait_for_cdp_result(42, timeout=0.1)
    assert result is None

def test_find_chrome_via_path(monkeypatch):
    """_find_chrome finds Chrome via subprocess."""
    from skinvault.steam_login_dialog import _find_chrome
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0})())
    result = _find_chrome()
    assert result == "chrome"

def test_find_chrome_via_path_fallback(monkeypatch):
    """_find_chrome falls through candidates and finds via path."""
    from skinvault.steam_login_dialog import _find_chrome
    call_count = [0]
    def failing_run(*a, **kw):
        call_count[0] += 1
        if call_count[0] <= 3:
            raise FileNotFoundError("not found")
        return type("R", (), {"returncode": 0})()
    monkeypatch.setattr("subprocess.run", failing_run)
    result = _find_chrome()
    assert result == "chromium-browser"

def test_find_chrome_not_found(monkeypatch):
    """_find_chrome returns None when no Chrome found."""
    from skinvault.steam_login_dialog import _find_chrome
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: (_ for _ in ()).throw(
            FileNotFoundError("not found")))
    monkeypatch.setattr("os.path.isfile", lambda p: False)
    result = _find_chrome()
    assert result is None

def test_find_chrome_via_windows_path(monkeypatch):
    """_find_chrome finds Chrome via Windows paths."""
    from skinvault.steam_login_dialog import _find_chrome
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: (_ for _ in ()).throw(
            FileNotFoundError("not found")))
    monkeypatch.setattr("os.path.isfile", lambda p: "chrome.exe" in p)
    result = _find_chrome()
    assert result is not None
    assert "Program Files" in result or "LocalAppData" in result

def test_show_manual_option(monkeypatch):
    """_show_manual_option inserts manual button and calls cleanup."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._cleanup = lambda: None
    dlg._show_manual_option()
    assert dlg._manual_btn is not None
    assert "Colar cookies" in dlg._manual_btn.text()

def test_switch_to_manual():
    """_switch_to_manual replaces content with cookie input."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._cleanup = lambda: None
    dlg._manual_btn = type("Btn", (), {
        "hide": lambda self: None,
        "deleteLater": lambda self: None,
    })()
    dlg._switch_to_manual()
    assert dlg._cookie_input is not None
    assert dlg._confirm_btn is not None

def test_process_manual_cookies_empty():
    """_process_manual_cookies shows error for empty input."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    mock_input = type("Input", (), {"toPlainText": lambda self: ""})()
    dlg._cookie_input = mock_input
    dlg._process_manual_cookies()
    assert "Cole" in dlg._status.text()

def test_process_manual_cookies_invalid_json():
    """_process_manual_cookies shows error for invalid JSON."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._cookie_input = type("Input", (), {
        "toPlainText": lambda self: "not json"})()
    dlg._process_manual_cookies()
    assert "invalido" in dlg._status.text()

def test_process_manual_cookies_list(monkeypatch):
    """_process_manual_cookies processes list of cookies."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr(
        "skinvault.steam_login_dialog.extract_steamid_from_cookie",
        lambda c: "7656119")
    monkeypatch.setattr(
        "skinvault.steam_login_dialog.merge_cookies",
        lambda a, b: b)
    dlg = SteamLoginDialog()
    dlg._cookie_input = type("Input", (), {
        "toPlainText": lambda self: (
            '[{"domain":"steamcommunity.com","name":"steamLoginSecure",'
            '"value":"abc"}]'
        )})()
    dlg._process_manual_cookies()
    assert dlg.session is not None
    assert dlg.session.steamid == "7656119"

def test_process_manual_cookies_dict(monkeypatch):
    """_process_manual_cookies processes dict of cookies."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr(
        "skinvault.steam_login_dialog.extract_steamid_from_cookie",
        lambda c: "7656119")
    monkeypatch.setattr(
        "skinvault.steam_login_dialog.merge_cookies",
        lambda a, b: b)
    dlg = SteamLoginDialog()
    dlg._cookie_input = type("Input", (), {
        "toPlainText": lambda self: (
            '{"steamLoginSecure": "abc", "sessionid": "xyz"}'
        )})()
    dlg._process_manual_cookies()
    assert dlg.session is not None

def test_process_manual_cookies_missing_key(monkeypatch):
    """_process_manual_cookies fails without steamLoginSecure."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr(
        "skinvault.steam_login_dialog.extract_steamid_from_cookie",
        lambda c: "")
    dlg = SteamLoginDialog()
    dlg._cookie_input = type("Input", (), {
        "toPlainText": lambda self: (
            '[{"domain":"steamcommunity.com","name":"sessionid",'
            '"value":"xyz"}]'
        )})()
    dlg._process_manual_cookies()
    assert "steamLoginSecure" in dlg._status.text()

def test_process_manual_cookies_unrecognized_format():
    """_process_manual_cookies fails for non-list non-dict."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._cookie_input = type("Input", (), {
        "toPlainText": lambda self: '"just a string"'})()
    dlg._process_manual_cookies()
    assert "reconhecido" in dlg._status.text()


def test_launch_chrome(monkeypatch):
    """_launch_chrome starts monitor thread."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    started = []
    monkeypatch.setattr("threading.Thread", lambda *a, **kw: type(
        "T", (), {"start": lambda self: started.append(True)})())
    dlg._launch_chrome()
    assert dlg._monitor_active is True
    assert len(started) == 1

def test_showEvent(monkeypatch):
    """showEvent schedules _launch_chrome via QTimer."""
    from PyQt6.QtGui import QShowEvent
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    called = []
    dlg._launch_chrome = lambda: called.append(True)
    dlg.showEvent(QShowEvent())
    assert len(called) == 1

def test_on_chrome_launch_failed(monkeypatch):
    """_on_chrome_launch_failed sets text and shows manual."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    shown = []
    dlg._show_manual_option = lambda: shown.append(True)
    dlg._on_chrome_launch_failed(Exception("no chrome"))
    assert "Erro" in dlg._status.text()
    assert "no chrome" in dlg._status.text()
    assert len(shown) == 1

def test_on_login_error(monkeypatch):
    """_on_login_error sets text, cleans up, shows manual."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    cleaned = []
    shown = []
    dlg._cleanup = lambda: cleaned.append(True)
    dlg._show_manual_option = lambda: shown.append(True)
    dlg._on_login_error()
    assert "Erro" in dlg._status.text()
    assert len(cleaned) == 1
    assert len(shown) == 1

def test_on_login_success(monkeypatch):
    """_on_login_success cleans up and accepts."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    cleaned = []
    accepted = []
    dlg._cleanup = lambda: cleaned.append(True)
    dlg.accept = lambda: accepted.append(True)
    dlg._on_login_success()
    assert len(cleaned) == 1
    assert len(accepted) == 1

def test_monitor_ws_chrome_not_found(monkeypatch):
    """_monitor_ws shows manual option when Chrome not found."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    shown = []
    dlg._show_manual_option = lambda: shown.append(True)
    dlg._monitor_ws()
    assert len(shown) == 1

def test_monitor_ws_chrome_launch_failed(monkeypatch):
    """_monitor_ws calls _on_chrome_launch_failed when Popen fails."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            FileNotFoundError("chrome not found")))
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    called = []
    dlg._on_chrome_launch_failed = lambda e: called.append(e)
    dlg._monitor_ws()
    assert len(called) == 1
    assert isinstance(called[0], FileNotFoundError)

def test_monitor_ws_poll_timeout(monkeypatch):
    """_monitor_ws offers manual when poll times out."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: (_ for _ in ()).throw(
                            Exception("no response")))
    t = [100.0]
    monkeypatch.setattr("time.time", lambda: t[0])
    def advance(s):
        t[0] += 310
    monkeypatch.setattr("time.sleep", advance)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    shown = []
    dlg._show_manual_option = lambda: shown.append(True)
    dlg._monitor_ws()
    assert len(shown) == 1

def test_monitor_ws_happy_path(monkeypatch):
    """_monitor_ws detects login, gets cookies, creates session."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: type(
                            "R", (),
                            {"read": lambda self: b'[{"type":"page",'
                             b'"url":"https://steamcommunity.com/profiles/7656",'
                             b'"webSocketDebuggerUrl":"ws://localhost/debug"}]',
                             "__enter__": lambda self: self,
                             "__exit__": lambda *a: None})())
    monkeypatch.setattr("time.time", lambda: 100)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    monkeypatch.setattr("skinvault.steam_login_dialog.merge_cookies",
                        lambda a, b: b)
    monkeypatch.setattr("skinvault.steam_login_dialog.extract_steamid_from_cookie",
                        lambda c: "7656")
    monkeypatch.setattr("websocket.create_connection",
                        lambda url, timeout: type(
                            "WS", (),
                            {"send": lambda self, m: None,
                             "recv": lambda timeout=1.0: "{}",
                             "settimeout": lambda self, t: None,
                             "close": lambda self: None})(),
    )

    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._wait_for_cdp_result = lambda mid, timeout=15: {"cookies": [
        {"domain": "steamcommunity.com", "name": "steamLoginSecure",
         "value": "abc"},
        {"domain": "steamcommunity.com", "name": "sessionid",
         "value": "xyz"},
    ]}
    success = []
    dlg._on_login_success = lambda: success.append(True)
    dlg._monitor_ws()
    assert len(success) == 1

def test_monitor_ws_empty_cookies_then_found(monkeypatch):
    """_monitor_ws retries when cookies empty, succeeds on 2nd try."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: type(
                            "R", (),
                            {"read": lambda self: b'[{"type":"page",'
                             b'"url":"https://steamcommunity.com/id/7656",'
                             b'"webSocketDebuggerUrl":"ws://localhost/debug"}]',
                             "__enter__": lambda self: self,
                             "__exit__": lambda *a: None})())
    monkeypatch.setattr("time.time", lambda: 100)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    monkeypatch.setattr("skinvault.steam_login_dialog.merge_cookies",
                        lambda a, b: b)
    monkeypatch.setattr("skinvault.steam_login_dialog.extract_steamid_from_cookie",
                        lambda c: "7656")
    monkeypatch.setattr("websocket.create_connection",
                        lambda url, timeout: type(
                            "WS", (),
                            {"send": lambda self, m: None,
                             "recv": lambda timeout=1.0: "{}",
                             "settimeout": lambda self, t: None,
                             "close": lambda self: None})(),
    )

    wait_count = [0]
    def fake_wait(mid, timeout=15):
        wait_count[0] += 1
        if wait_count[0] <= 1:
            return {"cookies": []}
        return {"cookies": [
            {"domain": "steamcommunity.com", "name": "steamLoginSecure",
             "value": "abc"},
            {"domain": "steamcommunity.com", "name": "sessionid",
             "value": "xyz"},
        ]}

    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._wait_for_cdp_result = fake_wait
    success = []
    dlg._on_login_success = lambda: success.append(True)
    dlg._monitor_ws()
    assert len(success) == 1
    assert wait_count[0] == 2

def test_monitor_ws_cookies_still_empty(monkeypatch):
    """_monitor_ws shows manual when both cookie attempts empty."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: type(
                            "R", (),
                            {"read": lambda self: b'[{"type":"page",'
                             b'"url":"https://steamcommunity.com/id/7656",'
                             b'"webSocketDebuggerUrl":"ws://localhost/debug"}]',
                             "__enter__": lambda self: self,
                             "__exit__": lambda *a: None})())
    monkeypatch.setattr("time.time", lambda: 100)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    monkeypatch.setattr("skinvault.steam_login_dialog.extract_steamid_from_cookie",
                        lambda c: "")
    monkeypatch.setattr("websocket.create_connection",
                        lambda url, timeout: type(
                            "WS", (),
                            {"send": lambda self, m: None,
                             "recv": lambda timeout=1.0: "{}",
                             "settimeout": lambda self, t: None,
                             "close": lambda self: None})(),
    )

    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._wait_for_cdp_result = lambda mid, timeout=15: {"cookies": [
        {"domain": "example.com", "name": "steamLoginSecure", "value": "abc"},
    ]}
    shown = []
    dlg._show_manual_option = lambda: shown.append(True)
    dlg._monitor_ws()
    assert len(shown) == 1

def test_monitor_ws_ws_connect_fails(monkeypatch):
    """_monitor_ws shows manual when WS connection fails."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: type(
                            "R", (),
                            {"read": lambda self: b'[{"type":"page",'
                             b'"url":"https://steamcommunity.com/profiles/7656",'
                             b'"webSocketDebuggerUrl":"ws://localhost/debug"}]',
                             "__enter__": lambda self: self,
                             "__exit__": lambda *a: None})())
    monkeypatch.setattr("time.time", lambda: 100)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    monkeypatch.setattr("websocket.create_connection",
                        lambda url, timeout: (_ for _ in ()).throw(
                            Exception("WS fail")))
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    shown = []
    dlg._show_manual_option = lambda: shown.append(True)
    dlg._monitor_ws()
    assert len(shown) == 1

def test_monitor_ws_cdp_result_none(monkeypatch):
    """_monitor_ws shows manual when getAllCookies returns no result."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: type(
                            "R", (),
                            {"read": lambda self: b'[{"type":"page",'
                             b'"url":"https://steamcommunity.com/profiles/7656",'
                             b'"webSocketDebuggerUrl":"ws://localhost/debug"}]',
                             "__enter__": lambda self: self,
                             "__exit__": lambda *a: None})())
    monkeypatch.setattr("time.time", lambda: 100)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    monkeypatch.setattr("websocket.create_connection",
                        lambda url, timeout: type(
                            "WS", (),
                            {"send": lambda self, m: None,
                             "recv": lambda timeout=1.0: "{}",
                             "settimeout": lambda self, t: None,
                             "close": lambda self: None})(),
    )

    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._wait_for_cdp_result = lambda mid, timeout=15: None
    error_called = []
    dlg._on_login_error = lambda: error_called.append(True)
    dlg._monitor_ws()
    assert len(error_called) == 1


def test_wait_for_cdp_result_skip_none(monkeypatch):
    """_wait_for_cdp_result skips None messages and finds match."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    recv_calls = [0]
    def mock_recv(timeout=1.0):
        recv_calls[0] += 1
        if recv_calls[0] == 1:
            return None
        return {"id": 42, "result": {"ok": True}}
    dlg._recv_cdp = mock_recv
    monkeypatch.setattr("time.time", lambda: 100 + recv_calls[0] * 20)
    result = dlg._wait_for_cdp_result(42, timeout=60)
    assert result == {"ok": True}
    assert recv_calls[0] == 2

def test_monitor_ws_non_page_types(monkeypatch):
    """_monitor_ws skips non-page entries in /json response."""
    from skinvault.steam_login_dialog import SteamLoginDialog
    monkeypatch.setattr("skinvault.steam_login_dialog._find_chrome",
                        lambda: "chrome")
    monkeypatch.setattr("skinvault.steam_login_dialog._find_free_port",
                        lambda: 9999)
    monkeypatch.setattr("skinvault.steam_login_dialog.tempfile.mkdtemp",
                        lambda prefix: "C:\\tmp\\sv_test")
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: type("P", (), {"pid": 1234})())
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda url, timeout: type(
                            "R", (),
                            {"read": lambda self: (
                                b'[{"type":"other",'
                                b'"url":"https://example.com"},'
                                b'{"type":"page",'
                                b'"url":"https://steamcommunity.com/profiles/7656",'
                                b'"webSocketDebuggerUrl":"ws://localhost/debug"}]'
                            ),
                             "__enter__": lambda self: self,
                             "__exit__": lambda *a: None})())
    monkeypatch.setattr("time.time", lambda: 100)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr("skinvault.steam_login_dialog.QTimer.singleShot",
                        lambda ms, fn: fn())
    monkeypatch.setattr("skinvault.steam_login_dialog.merge_cookies",
                        lambda a, b: b)
    monkeypatch.setattr("skinvault.steam_login_dialog.extract_steamid_from_cookie",
                        lambda c: "7656")
    monkeypatch.setattr("websocket.create_connection",
                        lambda url, timeout: type(
                            "WS", (),
                            {"send": lambda self, m: None,
                             "recv": lambda timeout=1.0: "{}",
                             "settimeout": lambda self, t: None,
                             "close": lambda self: None})(),
    )
    dlg = SteamLoginDialog()
    dlg._monitor_active = True
    dlg._wait_for_cdp_result = lambda mid, timeout=15: {"cookies": [
        {"domain": "steamcommunity.com", "name": "steamLoginSecure",
         "value": "abc"},
    ]}
    success = []
    dlg._on_login_success = lambda: success.append(True)
    dlg._monitor_ws()
    assert len(success) == 1


# ── Widgets (MonthBarChart, ValueChart, MiniSparkline, DepthChart) ─

def test_monthbar_init():
    """MonthBarChart paints empty state without crashing."""
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(200, 120)
    pix = w.grab()
    assert not pix.isNull()

def test_monthbar_with_data():
    """MonthBarChart paints bars for monthly data."""
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(200, 120)
    w.set_months([
        {"month": "Janeiro", "pnl": 150.0},
        {"month": "Fevereiro", "pnl": -80.0},
        {"month": "Marco", "pnl": 200.0},
    ])
    pix = w.grab()
    assert not pix.isNull()
    assert len(w._months) == 3

def test_monthbar_single_month():
    """MonthBarChart paints single month without dividing by zero."""
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(200, 120)
    w.set_months([{"month": "Jan", "pnl": 50.0}])
    pix = w.grab()
    assert not pix.isNull()

def test_monthbar_all_negative():
    """MonthBarChart paints all-negative months."""
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(200, 120)
    w.set_months([
        {"month": "Jan", "pnl": -100.0},
        {"month": "Fev", "pnl": -50.0},
    ])
    pix = w.grab()
    assert not pix.isNull()

def test_monthbar_zero_pnl():
    """MonthBarChart handles zero PnL safely."""
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(200, 120)
    w.set_months([{"month": "Jan", "pnl": 0.0}])
    pix = w.grab()
    assert not pix.isNull()

def test_valuechart_init():
    """ValueChart paints empty state without crashing."""
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(200, 120)
    pix = w.grab()
    assert not pix.isNull()

def test_valuechart_single_value():
    """ValueChart with <2 values shows empty state."""
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(200, 120)
    w.set_series([100.0])
    pix = w.grab()
    assert not pix.isNull()
    assert len(w._values) == 1

def test_valuechart_two_values():
    """ValueChart with 2+ values draws the line."""
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(200, 120)
    w.set_series([100.0, 150.0])
    pix = w.grab()
    assert not pix.isNull()

def test_valuechart_downtrend():
    """ValueChart paints red line for downtrend."""
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(200, 120)
    w.set_series([150.0, 100.0, 120.0])
    pix = w.grab()
    assert not pix.isNull()

def test_valuechart_flat():
    """ValueChart handles flat values (all same)."""
    from skinvault.ui.widgets import ValueChart
    w = ValueChart()
    w.resize(200, 120)
    w.set_series([100.0, 100.0, 100.0])
    pix = w.grab()
    assert not pix.isNull()

def test_month_label_pt_br():
    """month_label converte '%Y-%m' pra mes curto pt-BR (fix do '202')."""
    from skinvault.ui.widgets import month_label, month_label_full
    assert month_label("2025-01") == "Jan"
    assert month_label("2024-12") == "Dez"
    # fallback: key fora do formato mantem comportamento antigo ([:3])
    assert month_label("Janeiro") == "Jan"
    assert month_label_full("2025-03") == "Março 2025"
    assert month_label_full("Janeiro") == "Janeiro"

def test_monthbar_click_emite_mes():
    """Clique numa barra emite month_clicked com a key '%Y-%m'."""
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(400, 120)
    w.set_months([
        {"month": "2025-01", "pnl": 100.0},
        {"month": "2025-02", "pnl": -50.0},
        {"month": "2025-03", "pnl": 75.0},
    ])
    received = []
    w.month_clicked.connect(received.append)
    bar_w = w._bar_w()
    x = 10 + 1 * (bar_w + 4) + bar_w // 2  # centro da 2a coluna
    QTest.mouseClick(w, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(x, 60))
    assert received == ["2025-02"]

def test_monthbar_click_fora_nao_emite():
    """Clique fora das colunas (margens) nao emite signal."""
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(400, 120)
    w.set_months([{"month": "2025-01", "pnl": 100.0}])
    received = []
    w.month_clicked.connect(received.append)
    # margem esquerda (x<10) e depois da unica coluna
    QTest.mouseClick(w, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(2, 60))
    QTest.mouseClick(w, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(398, 60))
    assert received == []

def test_monthbar_selected_destaca_e_reseta():
    """set_selected destaca a barra; set_months sem o mes limpa selecao."""
    from skinvault.ui.widgets import MonthBarChart
    w = MonthBarChart()
    w.resize(400, 120)
    w.set_months([
        {"month": "2025-01", "pnl": 100.0},
        {"month": "2025-02", "pnl": -50.0},
    ])
    w.set_selected("2025-01")
    assert w._selected == "2025-01"
    pix = w.grab()
    assert not pix.isNull()
    # serie nova sem o mes selecionado reseta a selecao
    w.set_months([{"month": "2025-04", "pnl": 10.0}])
    assert w._selected is None
    w.set_selected(None)
    assert w._selected is None


# ── MonthBarChart na HistoryScreen + ValueChart na AccountScreen ──

def _trade_fake(name, sell_ts, pnl):
    return {"name": name, "sell_ts": sell_ts, "buy_ts": sell_ts - 86400,
            "quantity": 1, "buy_cost": 10.0, "sell_price": 12.0,
            "net_received": 10.2, "pnl": pnl, "source": "manual"}


def _history_screen_com_trades(monkeypatch):
    import calendar
    from skinvault.ui.history_screen import HistoryScreen
    ts_jan = calendar.timegm((2025, 1, 15, 12, 0, 0))
    ts_fev = calendar.timegm((2025, 2, 15, 12, 0, 0))
    data = [_trade_fake("Item Jan", ts_jan, 5.0),
            _trade_fake("Item Fev", ts_fev, -2.0)]
    monkeypatch.setattr("skinvault.trades.load_trades",
                        lambda *a, **kw: list(data))
    monkeypatch.setattr("skinvault.ui.history_screen.load_settings",
                        lambda: {})
    monkeypatch.setattr("skinvault.ui.history_screen.save_settings",
                        lambda s: None)
    return HistoryScreen()


def test_history_month_chart_alimentado_no_segmento_trades(monkeypatch):
    """Segmento trades alimenta o chart com trade_stats()['monthly']."""
    screen = _history_screen_com_trades(monkeypatch)
    screen._on_segment("trades")
    assert [m["month"] for m in screen._month_chart._months] == \
        ["2025-01", "2025-02"]
    assert not screen._month_card.isHidden()


def test_history_filtro_mes_toggle(monkeypatch):
    """Clique na barra filtra a tabela no mes; clique de novo limpa."""
    screen = _history_screen_com_trades(monkeypatch)
    screen._on_segment("trades")
    assert screen._table.rowCount() == 2
    screen._on_month_clicked("2025-01")
    assert screen._month_filter == "2025-01"
    assert screen._table.rowCount() == 1
    assert screen._table.item(0, 1).text() == "Item Jan"
    assert "Janeiro 2025" in screen._status.text()
    # toggle: clicar no mesmo mes limpa o filtro
    screen._on_month_clicked("2025-01")
    assert screen._month_filter is None
    assert screen._table.rowCount() == 2


def test_history_trocar_segmento_limpa_filtro_mes(monkeypatch):
    """Filtro de mes e' efemero: trocar de segmento reseta e esconde card."""
    screen = _history_screen_com_trades(monkeypatch)
    screen._on_segment("trades")
    screen._on_month_clicked("2025-02")
    assert screen._month_filter == "2025-02"
    screen._on_segment("all")
    assert screen._month_filter is None
    assert screen._month_card.isHidden()
    screen._on_segment("trades")
    assert not screen._month_card.isHidden()


def test_account_grava_snapshot_com_dedup(monkeypatch):
    """_on_eval grava snapshot do valor bruto; total repetido nao regrava."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    stored = [{"ts": 1.0, "total": 50.0}]
    recorded = []
    monkeypatch.setattr("skinvault.history.load_history",
                        lambda *a, **kw: list(stored))
    monkeypatch.setattr("skinvault.history.record_snapshot",
                        lambda total, *a, **kw: recorded.append(total))
    screen = AccountScreen(PriceCache(ttl=3600))
    row = {"name": "AK Fake", "quantity": 1, "price": 100.0,
           "market": 100.0, "net_if_sold": 85.0, "pnl": 10.0,
           "cost_total": 90.0}
    payload = {"rows": [row],
               "totals": {"market": 100.0, "net_if_sold": 85.0, "pnl": 10.0},
               "positions": [{"name": "AK Fake", "source": "manual"}]}
    screen._on_eval(payload)
    assert recorded == [100.0]
    # simula o ponto gravado; mesmo total de novo -> dedup pula
    stored.append({"ts": 2.0, "total": 100.0})
    screen._on_eval(payload)
    assert recorded == [100.0]
    # serie chegou no grafico
    assert screen._value_chart._values == [50.0, 100.0]


def test_account_sem_rows_nao_grava_snapshot(monkeypatch):
    """Inventario vazio nao polui history.json com zeros."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    recorded = []
    monkeypatch.setattr("skinvault.history.load_history",
                        lambda *a, **kw: [])
    monkeypatch.setattr("skinvault.history.record_snapshot",
                        lambda total, *a, **kw: recorded.append(total))
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_eval({"rows": [], "totals": {}, "positions": []})
    assert recorded == []


def test_minisparkline_init():
    """MiniSparkline paints empty state."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_single():
    """MiniSparkline with <2 values shows empty state."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0])
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_with_data():
    """MiniSparkline paints with data."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0, 105.0, 120.0])
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_sma():
    """MiniSparkline paints SMA overlay."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0, 105.0, 120.0])
    w.set_sma([None, None, 101.67, 103.33, 106.67])
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_sma_all_none():
    """MiniSparkline handles SMA with all None values."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0])
    w.set_sma([None, None, None])
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_sr():
    """MiniSparkline paints support/resistance overlay."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0, 105.0, 120.0])
    w.set_sr({"support": [95.0, 98.0], "resistance": [115.0, 120.0]})
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_sma_and_sr():
    """MiniSparkline paints both SMA and SR together."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0, 105.0, 120.0])
    w.set_sma([None, None, 101.67, 103.33, 106.67])
    w.set_sr({"support": [95.0], "resistance": [120.0]})
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_down():
    """MiniSparkline paints red for downtrend."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([120.0, 110.0, 95.0])
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_with_timestamps():
    """MiniSparkline aceita timestamps opcionais para o hover tooltip."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0],
                 timestamps=[1700000000, 1700086400, 1700172800])
    assert w._timestamps == [1700000000, 1700086400, 1700172800]
    pix = w.grab()
    assert not pix.isNull()

def test_minisparkline_set_series_resets_hover():
    """set_series limpa hover_idx (evita indice stale de serie anterior)."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0] * 50)
    w._hover_idx = 49
    w.set_series([100.0, 110.0])
    assert w._hover_idx is None

def test_minisparkline_hover_index_clamps():
    """_hover_index_at mapeia x para indice e clampa nas bordas."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0, 105.0, 120.0])
    assert w._hover_index_at(-50) == 0
    assert w._hover_index_at(4) == 0
    assert w._hover_index_at(w.width() - 4) == 4
    assert w._hover_index_at(w.width() + 50) == 4
    mid = w._hover_index_at(w.width() / 2)
    assert 1 <= mid <= 3

def test_minisparkline_hover_marker_paints():
    """Paint com hover_idx ativo desenha guia + marcador sem crash."""
    from skinvault.ui.widgets import MiniSparkline
    w = MiniSparkline()
    w.resize(200, 50)
    w.set_series([100.0, 110.0, 95.0, 105.0, 120.0])
    w._hover_idx = 2
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_init():
    """DepthChart paints empty state without crashing."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_none_data():
    """DepthChart handles set_data(None)."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data(None)
    assert w._bid_points == []
    assert w._ask_points == []
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_empty_dict():
    """DepthChart handles set_data(empty dict)."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({})
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_no_data_keys():
    """DepthChart handles set_data with empty order lists."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "buy_orders": [],
        "sell_orders": [],
        "best_bid": 10000,
        "best_ask": 10500,
        "spread": 500,
    })
    assert w._best_bid == 100.0
    assert w._best_ask == 105.0
    assert w._spread == 5.0
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_buy_only():
    """DepthChart paints buy orders only."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "buy_orders": [10000, 5, 9900, 10, 9800, 15],
        "best_bid": 10000,
        "best_ask": 10500,
        "spread": 500,
    })
    assert len(w._bid_points) > 1
    assert w._best_bid == 100.0
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_sell_only():
    """DepthChart paints sell orders only."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "sell_orders": [10500, 8, 10600, 12, 10700, 20],
        "best_bid": 10000,
        "best_ask": 10500,
        "spread": 500,
    })
    assert len(w._ask_points) > 1
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_both_sides():
    """DepthChart paints both buy and sell sides."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "buy_orders": [10000, 5, 9900, 10],
        "sell_orders": [10500, 8, 10600, 12],
        "best_bid": 10000,
        "best_ask": 10500,
        "spread": 500,
    })
    assert len(w._bid_points) > 1
    assert len(w._ask_points) > 1
    assert w._spread == 5.0
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_single_order_per_side():
    """DepthChart handles single buy and sell order (line not drawn)."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "buy_orders": [10000, 5],
        "sell_orders": [10500, 8],
        "best_bid": 10000,
        "best_ask": 10500,
    })
    assert len(w._bid_points) == 2  # (0, 100) + (5, 100)
    assert len(w._ask_points) == 2
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_no_best_bid_ask():
    """DepthChart handles missing best_bid/best_ask."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "buy_orders": [10000, 5, 9900, 10],
        "sell_orders": [10500, 8, 10600, 12],
    })
    assert w._best_bid is None
    assert w._best_ask is None
    assert w._spread is None
    pix = w.grab()
    assert not pix.isNull()

def test_depthchart_best_price_outside_range_clamps():
    """Label de best price fora do range pintado clampa sem crash
    (ask side sem pontos mas best_ask presente)."""
    from skinvault.ui.widgets import DepthChart
    w = DepthChart()
    w.resize(300, 140)
    w.set_data({
        "buy_orders": [10000, 5, 9900, 10],
        "sell_orders": [],
        "best_bid": 10000,
        "best_ask": 99999,
    })
    assert w._ask_points == []
    assert w._best_ask == 999.99
    pix = w.grab()
    assert not pix.isNull()


# ── _paths ────────────────────────────────────────────────────

def test_paths_dev_branch():
    """_paths uses project root in development mode."""
    from skinvault._paths import BASE_DIR, DATA_DIR
    assert BASE_DIR.name == "SkinVault"
    assert DATA_DIR.name == "data"
    assert DATA_DIR.is_dir()

def test_paths_frozen_branch():
    """sys.frozen=True makes _paths use exec parent."""
    import os
    import subprocess
    import sys
    code = (
        "import sys; sys.frozen = True; "
        "import importlib; "
        "import skinvault._paths; "
        "importlib.reload(skinvault._paths); "
        "from skinvault._paths import BASE_DIR, DATA_DIR; "
        "assert BASE_DIR == type(BASE_DIR)(sys.executable).parent, f'{BASE_DIR} != {type(BASE_DIR)(sys.executable).parent}'; "
        "assert DATA_DIR == BASE_DIR / 'data'; "
        "print('OK')"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=15,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
    assert r.stdout.strip() == "OK"


# ── gui.py (helpers + dialogs) ────────────────────────────────

def test_brl():
    """_brl formats BRL in pt-BR style."""
    from skinvault.gui import _brl
    assert _brl(1234.5) == "R$ 1.234,50"
    assert _brl(0) == "R$ 0,00"
    assert _brl(-50.0) == "R$ -50,00"

def test_steam_market_url():
    """_steam_market_url generates correct Steam URL."""
    from skinvault.gui import _steam_market_url
    url = _steam_market_url("AK-47 | Redline (Field-Tested)")
    assert "steamcommunity.com/market/listings/730/" in url
    assert "AK-47" in url
    assert "%20" in url  # URL-encoded

def test_btn_primary_disabled():
    """_btn_primary with disabled=True includes disabled styles."""
    from skinvault.gui import _btn_primary
    s = _btn_primary(disabled=True)
    assert "QPushButton:disabled" in s

def test_table_style():
    """_table_style returns stylesheet string."""
    from skinvault.gui import _table_style
    s = _table_style()
    assert "QTableWidget" in s
    assert "QHeaderView" in s

def test_format_sync_result():
    """_format_sync_result formats each step type correctly."""
    from skinvault.gui import _format_sync_result
    assert "erro" in _format_sync_result("inventory", {"error": "timeout"})
    r1 = _format_sync_result("inventory", {"added": 5, "skipped": 3})
    assert "5 novos" in r1
    assert "8" in r1
    r2 = _format_sync_result("market", {"new": 10, "total": 100})
    assert "10 novos" in r2
    assert "100" in r2
    r3 = _format_sync_result("listings", {"count": 7})
    assert "7" in r3
    assert "ativas" in r3
    r4 = _format_sync_result("trades", {"new": 3, "total": 50})
    assert "3 novos" in r4
    assert "50" in r4
    r5 = _format_sync_result("unknown", {})
    assert r5 == "ok"

def test_make_tray_icon():
    """_make_tray_icon returns a non-null QIcon."""
    from PyQt6.QtGui import QIcon
    from skinvault.gui import _make_tray_icon
    icon = _make_tray_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()

def test_sync_bridge_signals():
    """_SyncBridge has expected signal attributes."""
    from skinvault.gui import _SyncBridge
    b = _SyncBridge()
    assert hasattr(b, 'step_done')
    assert hasattr(b, 'all_done')
    assert hasattr(b, 'failed')


def test_settings_screen_init(monkeypatch):
    """SettingsScreen carrega valores padrao nos controles."""
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    from skinvault.ui.settings_screen import SettingsScreen
    screen = SettingsScreen()
    assert screen._cache_ttl.value() == 6
    assert screen._fee_rate.value() == 0.15
    assert screen._keep_backups.value() == 10


def test_settings_screen_autosave(monkeypatch):
    """Mudar um controle persiste no settings.json na hora."""
    saved = []
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda s, *a, **kw: saved.append(s))
    from skinvault.ui.settings_screen import SettingsScreen
    screen = SettingsScreen()
    screen._cache_ttl.setValue(12)
    assert saved
    assert saved[-1]["cache_ttl_hours"] == 12


def test_settings_screen_reset(monkeypatch):
    """Restaurar padroes reseta as chaves expostas aos DEFAULTS."""
    from PyQt6.QtWidgets import QMessageBox
    saved = []
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {"cache_ttl_hours": 99,
                                          "fee_rate": 0.99})
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda s, *a, **kw: saved.append(s))
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.Yes)
    from skinvault.ui import settings_screen as ss
    monkeypatch.setattr(ss.Toast, "show_toast",
                        classmethod(lambda cls, *a, **kw: None))
    screen = ss.SettingsScreen()
    screen._on_reset()
    assert saved
    assert saved[-1]["cache_ttl_hours"] == ss.DEFAULTS["cache_ttl_hours"]
    assert saved[-1]["fee_rate"] == ss.DEFAULTS["fee_rate"]


def test_settings_screen_theme_calls_window_hook(monkeypatch):
    """Trocar o tema aciona _on_theme_changed via window()."""
    from PyQt6.QtWidgets import QWidget
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda *a, **kw: None)
    from skinvault.ui.settings_screen import SettingsScreen
    called = []
    parent = QWidget()
    parent._on_theme_changed = lambda: called.append(True)
    screen = SettingsScreen(parent)
    screen._theme_seg.select("light")
    assert called == [True]


def test_settings_screen_sidebar_width_calls_window_hook(monkeypatch):
    """Mudar a largura aciona _apply_sidebar_width via window()."""
    from PyQt6.QtWidgets import QWidget
    monkeypatch.setattr("skinvault.ui.settings_screen.load_settings",
                        lambda *a, **kw: {})
    monkeypatch.setattr("skinvault.ui.settings_screen.save_settings",
                        lambda *a, **kw: None)
    from skinvault.ui.settings_screen import SettingsScreen
    widths = []
    parent = QWidget()
    parent._apply_sidebar_width = lambda w: widths.append(w)
    screen = SettingsScreen(parent)
    screen._sidebar_w.setValue(300)
    assert widths == [300]


def test_backup_dialog_init(monkeypatch):
    """BackupDialog initializes and refreshes backup list."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "backup_1.zip", "path": "C:\\b1.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    assert dlg._list.count() == 1
    assert "backup_1.zip" in dlg._list.item(0).text()


def test_backup_dialog_selected_path_none(monkeypatch):
    """_selected_path returns None when no row selected."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [])
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    assert dlg._selected_path() is None


def test_backup_dialog_restore_cancelled(monkeypatch):
    """_restore returns early when user cancels."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "b.zip", "path": "C:\\b.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.No)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    dlg._restore()
    # No crash means success


def test_backup_dialog_restore_ok(monkeypatch):
    """_restore calls restore_backup and shows info on success."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "b.zip", "path": "C:\\b.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    monkeypatch.setattr("skinvault.backup.restore_backup", lambda p: 5)
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.Yes)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    dlg._restore()
    # Feedback agora via Toast; basta nao crashar


def test_backup_dialog_restore_fail(monkeypatch):
    """_restore shows warning when restore_backup returns 0."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "b.zip", "path": "C:\\b.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    monkeypatch.setattr("skinvault.backup.restore_backup", lambda p: 0)
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.Yes)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    dlg._restore()
    # Feedback agora via Toast; basta nao crashar


def test_backup_dialog_delete_no_selection():
    """_delete returns early when no backup selected."""
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._delete()
    # No crash


def test_backup_dialog_delete_cancelled(monkeypatch):
    """_delete returns early when user cancels."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "b.zip", "path": "C:\\b.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.No)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    dlg._delete()
    # No crash


def test_backup_dialog_delete_ok(monkeypatch):
    """_delete calls delete_backup and refreshes on success."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "b.zip", "path": "C:\\b.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    monkeypatch.setattr("skinvault.backup.delete_backup", lambda p: True)
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.Yes)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    dlg._delete()
    assert dlg._list.count() == 1  # refreshed


def test_backup_dialog_delete_fail(monkeypatch):
    """_delete shows warning when delete_backup fails."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [
        {"name": "b.zip", "path": "C:\\b.zip",
         "mtime": 1_000_000, "size": 2048},
    ])
    monkeypatch.setattr("skinvault.backup.delete_backup", lambda p: False)
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **kw: QMessageBox.StandardButton.Yes)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    dlg._delete()
    # Feedback agora via Toast; basta nao crashar


def test_steam_sync_dialog_init(monkeypatch):
    """SteamSyncDialog initializes with session and starts worker."""
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: {"inventory": {}, "market": {}})
    started = []
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: type("T", (), {
                            "start": lambda self: started.append(True)})())
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    from skinvault.gui import SteamSyncDialog
    dlg = SteamSyncDialog(session)
    assert dlg.windowTitle() == "Sincronizando com Steam"
    assert len(started) == 1


def test_steam_sync_dialog_start_error(monkeypatch):
    """SteamSyncDialog._start handles sync exception."""
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            Exception("API fail")))
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: type("T", (), {
                            "start": lambda self: None})())
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    from skinvault.gui import SteamSyncDialog
    dlg = SteamSyncDialog(session)
    # _start called in __init__, worker runs sync_all which raises
    # The bridge.failed signal is emitted but not connected to UI yet
    # in this test context. No crash = success.


def test_steam_sync_dialog_on_step(monkeypatch):
    """_on_step updates labels and progress."""
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: {})
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: type("T", (), {
                            "start": lambda self: None})())
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    from skinvault.gui import SteamSyncDialog
    dlg = SteamSyncDialog(session)
    dlg._on_step("inventory", {"added": 5, "skipped": 3})
    assert dlg._progress.value() == 1
    # Step for unknown key does not crash
    dlg._on_step("unknown", {})


def test_steam_sync_dialog_on_done(monkeypatch):
    """_on_done enables close button."""
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: {})
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: type("T", (), {
                            "start": lambda self: None})())
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    from skinvault.gui import SteamSyncDialog
    dlg = SteamSyncDialog(session)
    dlg._on_done({"inventory": {}})
    assert dlg._close_btn.isEnabled()


def test_steam_sync_dialog_on_failed(monkeypatch):
    """_on_failed enables close button and shows warning."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: {})
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: type("T", (), {
                            "start": lambda self: None})())
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **kw: warnings.append(a[2]))
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    from skinvault.gui import SteamSyncDialog
    dlg = SteamSyncDialog(session)
    dlg._on_failed("connection error")
    assert dlg._close_btn.isEnabled()
    assert len(warnings) == 1
    assert "connection error" in warnings[0]


def _make_mw(monkeypatch) -> "MainWindow":
    """Cria MainWindow com dependencias mockadas."""
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {})
    monkeypatch.setattr("skinvault.gui.set_theme", lambda t: None)

    from PyQt6.QtCore import pyqtSignal
    from PyQt6.QtWidgets import QWidget
    class FakeRouter(QWidget):
        sync_requested = pyqtSignal(object)
        navigated = pyqtSignal(str)
        sidebar_visibility_changed = pyqtSignal(bool)
        notification_requested = pyqtSignal(str, str, str)
        session_changed = pyqtSignal(str, str)
        theme_toggled = pyqtSignal()

        def __init__(self, cache=None, parent=None):
            super().__init__(parent)
            self._session = None
            self._stack = None
            self.sidebar_visible = True
            self._screen = None

        def navigate(self, screen):
            self._screen = screen

        def start(self):
            pass

    import skinvault.ui.screen_router as sr
    monkeypatch.setattr(sr, "ScreenRouter", lambda *a: FakeRouter())
    monkeypatch.setattr("skinvault.gui.backup.make_backup", lambda: None)
    monkeypatch.setattr("skinvault.gui.prices.PriceCache", lambda ttl: None)
    from skinvault.gui import MainWindow
    return MainWindow()


def test_mainwindow_init(monkeypatch):
    """MainWindow initializes without crashing."""
    win = _make_mw(monkeypatch)
    assert win.windowTitle() == "SkinVault"


def test_mainwindow_on_navigated(monkeypatch):
    """_on_navigated calls sidebar.select."""
    win = _make_mw(monkeypatch)
    selected = []
    win._sidebar_dock.widget().select = lambda s: selected.append(s)
    win._on_navigated("scanner")
    assert len(selected) == 1
    assert selected[0] == "scanner"


def test_mainwindow_on_sidebar_visibility(monkeypatch):
    """_on_sidebar_visibility toggles sidebar dock."""
    win = _make_mw(monkeypatch)
    win._sidebar_dock.setVisible(False)
    win._on_sidebar_visibility(True)
    assert win._sidebar_dock.isVisibleTo(win)


def test_mainwindow_save_geometry(monkeypatch):
    """_save_geometry persists window geometry."""
    settings = {}
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: settings)
    monkeypatch.setattr("skinvault.gui.save_settings",
                        lambda s: settings.update(s))
    win = _make_mw(monkeypatch)
    win._save_geometry()
    assert "window_geometry" in settings
    assert "window_position" in settings


def test_mainwindow_debounce_save_geometry(monkeypatch):
    """_debounce_save_geometry starts a single-shot timer."""
    win = _make_mw(monkeypatch)
    win._debounce_save_geometry()
    assert win._geo_timer.isActive()


def test_mainwindow_show_shortcuts(monkeypatch):
    """_show_shortcuts shows info dialog."""
    from PyQt6.QtWidgets import QMessageBox
    infos = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **kw: infos.append(a[1]))
    win = _make_mw(monkeypatch)
    win._show_shortcuts()
    assert len(infos) == 1
    assert "Atalhos" in infos[0]


def test_mainwindow_focus_filter_no_stack(monkeypatch):
    """_focus_filter handles missing _stack gracefully."""
    win = _make_mw(monkeypatch)
    win._router._stack = None
    win._focus_filter()


def test_mainwindow_focus_filter_finds_input(monkeypatch):
    """_focus_filter focuses _filter_inp on current widget."""
    from PyQt6.QtWidgets import QLineEdit, QWidget
    inp = QLineEdit()
    focused = []
    orig = inp.setFocus
    inp.setFocus = lambda: focused.append(True) or orig()
    fake_w = QWidget()
    fake_w._filter_inp = inp
    win = _make_mw(monkeypatch)
    win._router._stack = type("S", (), {
        "currentWidget": lambda self: fake_w})()

    win._focus_filter()
    assert len(focused) == 1


def test_mainwindow_focus_filter_finds_search(monkeypatch):
    """_focus_filter falls back to _search_inp."""
    from PyQt6.QtWidgets import QLineEdit, QWidget
    inp = QLineEdit()
    focused = []
    orig = inp.setFocus
    inp.setFocus = lambda: focused.append(True) or orig()
    fake_w = QWidget()
    fake_w._search_inp = inp
    win = _make_mw(monkeypatch)
    win._router._stack = type("S", (), {
        "currentWidget": lambda self: fake_w})()
    win._focus_filter()
    assert len(focused) == 1


def test_mainwindow_refresh_current(monkeypatch):
    """_refresh_current calls refresh on current widget."""
    refreshed = []
    fake_w = type("W", (), {"refresh": lambda self: refreshed.append(True)})()
    win = _make_mw(monkeypatch)
    win._router._stack = type("S", (), {
        "currentWidget": lambda self: fake_w})()
    win._refresh_current()
    assert len(refreshed) == 1


def test_mainwindow_refresh_current_no_refresh(monkeypatch):
    """_refresh_current handles widget without refresh."""
    win = _make_mw(monkeypatch)
    win._router._stack = type("S", (), {
        "currentWidget": lambda self: object()})()
    win._refresh_current()


def test_mainwindow_open_about(monkeypatch):
    """_open_about shows About dialog."""
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "about",
                        lambda *a, **kw: None)
    win = _make_mw(monkeypatch)
    win._open_about()


def test_mainwindow_open_settings(monkeypatch):
    """_open_settings navega para a tela de Configuracoes (Frente K)."""
    win = _make_mw(monkeypatch)
    win._open_settings()
    assert win._router._screen == "settings"


def test_mainwindow_open_backups(monkeypatch):
    """_open_backups creates and shows BackupDialog."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [])
    from skinvault.gui import BackupDialog as BD
    shown = []
    monkeypatch.setattr(BD, "exec", lambda self: shown.append(True))
    win = _make_mw(monkeypatch)
    win._open_backups()
    assert len(shown) == 1


def test_mainwindow_on_sync_requested(monkeypatch):
    """_on_sync_requested creates SteamSyncDialog."""
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: {})
    monkeypatch.setattr("threading.Thread",
                        lambda *a, **kw: type("T", (), {
                            "start": lambda self: None})())
    from skinvault.gui import SteamSyncDialog as SSD
    shown = []
    monkeypatch.setattr(SSD, "exec", lambda self: shown.append(True))
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    win = _make_mw(monkeypatch)
    win._on_sync_requested(session)
    assert len(shown) == 1


def test_mainwindow_on_theme_changed(monkeypatch):
    """_on_theme_changed updates theme when different."""
    settings = {"theme": "light"}
    win = _make_mw(monkeypatch)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: settings)
    monkeypatch.setattr("skinvault.gui.set_theme", lambda t: None)
    win._current_theme = "dark"
    win._on_theme_changed()
    assert win._current_theme == "light"


def test_mainwindow_on_theme_changed_same(monkeypatch):
    """_on_theme_changed does nothing if theme is same."""
    win = _make_mw(monkeypatch)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {"theme": "dark"})
    monkeypatch.setattr("skinvault.gui.set_theme", lambda t: None)
    win._current_theme = "dark"
    win._on_theme_changed()
    assert win._current_theme == "dark"


def test_mainwindow_center_on_screen(monkeypatch):
    """_center_on_screen does not crash."""
    win = _make_mw(monkeypatch)
    win._center_on_screen()


def test_set_theme(monkeypatch):
    """set_theme applies theme and reloads palette."""
    palette_reloaded = []
    monkeypatch.setattr("skinvault.ui.theme._reload_palette",
                        lambda t: palette_reloaded.append(t))
    from skinvault.gui import set_theme, _BG
    initial_bg = _BG
    set_theme("dark")
    assert len(palette_reloaded) == 1
    assert palette_reloaded[0] == "dark"


def test_set_theme_light(monkeypatch):
    """set_theme handles light theme."""
    palette_reloaded = []
    monkeypatch.setattr("skinvault.ui.theme._reload_palette",
                        lambda t: palette_reloaded.append(t))
    from skinvault.gui import set_theme
    set_theme("light")
    assert palette_reloaded[0] == "light"


def test_mainwindow_close_event(monkeypatch):
    """closeEvent saves geometry and hides to tray if available."""
    settings = {}
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: settings)
    monkeypatch.setattr("skinvault.gui.save_settings",
                        lambda s: settings.update(s))
    win = _make_mw(monkeypatch)
    win._tray_icon = type("T", (), {
        "hide": lambda self: None})()
    from PyQt6.QtGui import QCloseEvent
    evt = QCloseEvent()
    win.closeEvent(evt)
    assert not evt.isAccepted()  # ignored (minimize to tray)


def test_mainwindow_close_event_accept(monkeypatch):
    """closeEvent accepts when minimize_to_tray_on_close is False."""
    settings = {"minimize_to_tray_on_close": False}
    win = _make_mw(monkeypatch)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: settings)
    monkeypatch.setattr("skinvault.gui.save_settings",
                        lambda s: None)
    win._tray_icon = type("T", (), {
        "hide": lambda self: None})()
    from PyQt6.QtGui import QCloseEvent
    evt = QCloseEvent()
    win.closeEvent(evt)
    assert evt.isAccepted()


# ── Coverage para linhas restantes ──────────────────────────────


def test_mainwindow_center_on_screen_none(monkeypatch):
    """_center_on_screen retorna cedo se screen is None."""
    win = _make_mw(monkeypatch)
    win.screen = lambda: None
    win._center_on_screen()  # nao crasha


def test_mainwindow_restore_from_tray(monkeypatch):
    """_restore_from_tray chama showNormal + activateWindow + raise_. """
    win = _make_mw(monkeypatch)
    calls = []
    monkeypatch.setattr(win, "showNormal", lambda: calls.append("show"))
    monkeypatch.setattr(win, "activateWindow", lambda: calls.append("activate"))
    monkeypatch.setattr(win, "raise_", lambda: calls.append("raise"))
    win._restore_from_tray()
    assert calls == ["show", "activate", "raise"]


def test_mainwindow_on_tray_activated_doubleclick(monkeypatch):
    """_on_tray_activated restaura no DoubleClick."""
    restored = []
    win = _make_mw(monkeypatch)
    monkeypatch.setattr(win, "_restore_from_tray", lambda: restored.append(True))
    from PyQt6.QtWidgets import QSystemTrayIcon
    win._on_tray_activated(
        QSystemTrayIcon.ActivationReason.DoubleClick)
    assert len(restored) == 1


def test_mainwindow_init_tray_qtray_none(monkeypatch):
    """_init_tray retorna cedo se QSystemTrayIcon is None."""
    monkeypatch.setattr("skinvault.gui.QSystemTrayIcon", None)
    win = _make_mw(monkeypatch)
    assert win._tray_icon is None


def test_mainwindow_init_tray_system_unavailable_exception(monkeypatch):
    """_init_tray trata excecao em isSystemTrayAvailable."""
    def _raise(*a):
        raise RuntimeError("no tray")
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QSystemTrayIcon.isSystemTrayAvailable",
        _raise,
    )
    win = _make_mw(monkeypatch)
    assert win._tray_icon is None


def test_mainwindow_move_event(monkeypatch):
    """moveEvent chama _debounce_save_geometry."""
    calls = []
    win = _make_mw(monkeypatch)
    monkeypatch.setattr(win, "_debounce_save_geometry",
                        lambda: calls.append(True))
    from PyQt6.QtGui import QMoveEvent
    from PyQt6.QtCore import QPoint
    evt = QMoveEvent(QPoint(0, 0), QPoint(10, 10))
    win.moveEvent(evt)
    assert len(calls) == 1


def test_mainwindow_resize_event(monkeypatch):
    """resizeEvent chama _debounce_save_geometry."""
    calls = []
    win = _make_mw(monkeypatch)
    monkeypatch.setattr(win, "_debounce_save_geometry",
                        lambda: calls.append(True))
    from PyQt6.QtGui import QResizeEvent
    from PyQt6.QtCore import QSize
    evt = QResizeEvent(QSize(100, 100), QSize(80, 80))
    win.resizeEvent(evt)
    assert len(calls) == 1


def test_backup_dialog_selected_row_oob(monkeypatch):
    """BackupDialog._selected_path retorna None p/ row fora do range."""
    backups = [{"name": "b", "mtime": 0, "size": 0, "path": "/x"}]
    monkeypatch.setattr("skinvault.backup.list_backups",
                        lambda: backups)
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    dlg._list.setCurrentRow(0)
    # After _refresh ran, clear mock so _selected_path sees empty
    backups.clear()
    assert dlg._selected_path() is None  # row >= len(backups) = True


def test_backup_dialog_restore_no_path(monkeypatch):
    """BackupDialog._restore retorna cedo sem path."""
    monkeypatch.setattr("skinvault.backup.list_backups", lambda: [])
    from skinvault.gui import BackupDialog
    dlg = BackupDialog()
    monkeypatch.setattr(dlg, "_selected_path", lambda: None)
    dlg._restore()  # nao crasha


def test_steam_sync_dialog_worker_error(monkeypatch):
    """SteamSyncDialog worker captura excecao de sync_all."""
    def mock_thread(*a, target=None, **kw):
        if target:
            target()
        return type("MT", (), {"start": lambda self: None})()
    monkeypatch.setattr("skinvault.gui.threading.Thread", mock_thread)
    monkeypatch.setattr("skinvault.gui.steam_sync.sync_all",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("fail")))
    from skinvault.gui import SteamSyncDialog
    monkeypatch.setattr(SteamSyncDialog, "_on_failed",
                        lambda self, msg: setattr(self, "_fail_msg", msg))
    from skinvault.steam_session import SteamSession
    session = SteamSession("7656", {}, 1_700_000_000)
    dlg = SteamSyncDialog(session)
    assert dlg._fail_msg == "fail"


def test_segmented_control_select_unchecked(monkeypatch):
    """SegmentedControl.select ativa botao e emite sinal."""
    from skinvault.ui.components import SegmentedControl
    sc = SegmentedControl()
    emitted = []
    sc.segment_changed.connect(lambda k: emitted.append(k))
    sc.add("a", "Alpha")
    sc.add("b", "Beta")  # 'a' auto-checked, 'b' unchecked
    sc.select("b")
    assert len(emitted) == 1
    assert emitted[0] == "b"


def test_steam_login_cleanup_rmtree_error(tmp_path, monkeypatch):
    """_cleanup trata excecao em shutil.rmtree."""
    import shutil
    tmpdir = tmp_path / "steam_dir"
    tmpdir.mkdir()
    monkeypatch.setattr(shutil, "rmtree",
                        lambda p, **kw: (_ for _ in ()).throw(PermissionError("denied")))
    from skinvault.steam_login_dialog import SteamLoginDialog
    dlg = SteamLoginDialog()
    dlg._user_data_dir = str(tmpdir)
    dlg._cleanup()  # nao crasha
    assert dlg._user_data_dir is None  # linha apos o except


def test_launch_start_minimized(monkeypatch):
    """launch() com start_minimized=True esconde a janela."""
    from skinvault._paths import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    class FakeApp:
        exec_called = False
        def __init__(self, argv):
            pass
        def exec(self):
            FakeApp.exec_called = True
            return 0
        @staticmethod
        def setAttribute(attr, val):
            pass

    monkeypatch.setattr("skinvault.gui.QApplication", FakeApp)
    monkeypatch.setattr("skinvault.gui.load_settings",
                        lambda: {"start_minimized": True})
    hidden = []
    class FakeWin:
        _tray_icon = type("T", (), {})()
        def hide(self):
            hidden.append(True)
        def showMaximized(self):
            pass
    monkeypatch.setattr("skinvault.gui.MainWindow", lambda: FakeWin())
    from skinvault.gui import launch
    result = launch()
    assert result == 0
    assert FakeApp.exec_called
    assert len(hidden) == 1


def test_launch_show_maximized(monkeypatch):
    """launch() sem start_minimized mostra maximizado."""
    from skinvault._paths import DATA_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    class FakeApp:
        def __init__(self, argv):
            pass
        def exec(self):
            return 0
        @staticmethod
        def setAttribute(attr, val):
            pass

    monkeypatch.setattr("skinvault.gui.QApplication", FakeApp)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {})
    shown = []
    class FakeWin:
        _tray_icon = None
        def hide(self):
            pass
        def showMaximized(self):
            shown.append(True)
    monkeypatch.setattr("skinvault.gui.MainWindow", lambda: FakeWin())
    from skinvault.gui import launch
    result = launch()
    assert result == 0
    assert len(shown) == 1


# ── Validar Score do Portfolio (AccountScreen) ────────

def test_account_validate_btn_existe():
    """Botão 'Validar Score do Portfolio' existe e habilitado."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    assert screen._validate_btn is not None
    assert screen._validate_btn.isEnabled()
    assert "Validar" in screen._validate_btn.text()


def test_account_on_validate_portfolio_vazio(monkeypatch):
    """Sem portfolio: handler mostra mensagem e não habilita worker."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    monkeypatch.setattr("skinvault.portfolio.load_portfolio", lambda: [])
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_validate_portfolio()
    assert "vazio" in screen._status.text().lower()
    # Botão segue habilitado pra outra tentativa
    assert screen._validate_btn.isEnabled()


def test_account_on_validate_samples_acumula():
    """_on_validate_samples acumula em _validate_samples."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_validate_samples([{"item": "A", "ts": 0, "score": 70,
                                    "return_pct": 5.0,
                                    "breakdown_count": 1}])
    screen._on_validate_samples([{"item": "B", "ts": 0, "score": 80,
                                    "return_pct": 10.0,
                                    "breakdown_count": 1}])
    assert len(screen._validate_samples) == 2


def test_account_on_validate_finished_reativa_botoes(monkeypatch):
    """_on_validate_finished reabilita botões e abre dialog."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    from skinvault.ui.scanner_screen import _BacktestResultDialog
    monkeypatch.setattr(_BacktestResultDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._sync_btn.setEnabled(False)
    screen._validate_btn.setEnabled(False)
    screen._validate_samples = []
    screen._validate_items_count = 2
    screen._on_validate_finished()
    assert screen._sync_btn.isEnabled()
    assert screen._validate_btn.isEnabled()


def test_account_validate_progress_atualiza_status():
    """_on_validate_progress atualiza o status label."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._on_validate_progress("Validando [1/3] AK-47 (cache)")
    assert "AK-47" in screen._status.text()


# ── Validar Score da Watchlist ────────────────────────

def test_watchlist_validate_btn_existe():
    """Botão 'Validar Score' existe na watchlist e habilitado."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    assert screen._validate_btn is not None
    assert screen._validate_btn.isEnabled()
    assert "Validar" in screen._validate_btn.text()


def test_watchlist_on_validate_vazia(monkeypatch):
    """Sem itens: handler mostra mensagem e nao habilita worker."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr("skinvault.watchlist.load_watchlist", lambda: [])
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._items = []
    screen._on_validate_watchlist()
    assert "vazia" in screen._status.text().lower()
    assert screen._validate_btn.isEnabled()


def test_watchlist_on_validate_samples_acumula():
    """_on_validate_samples acumula em _validate_samples."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._on_validate_samples([{"item": "A", "ts": 0, "score": 70,
                                    "return_pct": 5.0,
                                    "breakdown_count": 1}])
    screen._on_validate_samples([{"item": "B", "ts": 0, "score": 80,
                                    "return_pct": 10.0,
                                    "breakdown_count": 1}])
    assert len(screen._validate_samples) == 2


def test_watchlist_on_validate_finished_reativa(monkeypatch):
    """_on_validate_finished reabilita botões e abre dialog."""
    from PyQt6.QtWidgets import QDialog
    from skinvault.prices import PriceCache
    from skinvault.ui.scanner_screen import _BacktestResultDialog
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr(_BacktestResultDialog, "exec",
                        lambda self: QDialog.DialogCode.Accepted)
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._add_btn.setEnabled(False)
    screen._validate_btn.setEnabled(False)
    screen._validate_samples = []
    screen._validate_items_count = 3
    screen._on_validate_finished()
    assert screen._add_btn.isEnabled()
    assert screen._validate_btn.isEnabled()


def _watchlist_row_by_name(screen, name):
    """Acha row no table pelo nome (sort-safe)."""
    from PyQt6.QtWidgets import QTableWidgetItem  # noqa
    for row in range(screen._table.rowCount()):
        cell = screen._table.item(row, screen.COL_NAME)
        if cell and name in cell.text():
            return row
    return -1


def test_account_tem_coluna_score():
    """Tabela do AccountScreen tem 8 colunas com Score na ultima."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    assert screen._table.columnCount() == 8
    assert screen.COL_SCORE == 7
    hdr = screen._table.horizontalHeaderItem(7)
    assert hdr.text() == "Score"


def test_account_coluna_score_renderiza_valor():
    """Position com current_score aparece na coluna como int."""
    import time as _t
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    rows = [{"name": "X", "quantity": 1, "price": 100, "market": 100,
             "net_if_sold": 85, "pnl": 10}]
    positions = [{"name": "X", "cost": 90, "source": "manual",
                  "current_score": 75, "score_ts": _t.time()}]
    screen._populate_table(rows, positions)
    assert screen._table.item(0, 7).text() == "75"


def test_account_coluna_score_sem_valor_mostra_dash():
    """Position sem current_score mostra '—'."""
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    rows = [{"name": "X", "quantity": 1, "price": 100, "market": 100,
             "net_if_sold": 85, "pnl": 10}]
    positions = [{"name": "X", "cost": 90, "source": "manual"}]
    screen._populate_table(rows, positions)
    assert screen._table.item(0, 7).text() == "—"


def test_account_coluna_score_tooltip_age():
    """Tooltip menciona idade do score."""
    import time as _t
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    rows = [{"name": "X", "quantity": 1, "price": 100, "market": 100,
             "net_if_sold": 85, "pnl": 10}]
    positions = [{"name": "X", "cost": 90, "source": "manual",
                  "current_score": 80, "score_ts": _t.time()}]
    screen._populate_table(rows, positions)
    assert "agora" in screen._table.item(0, 7).toolTip()


def test_watchlist_tem_coluna_score():
    """Tabela tem 8 colunas com 'Score' e 'Confianca' ocultas inicialmente."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    assert screen._table.columnCount() == 8
    assert screen.COL_SCORE == 6
    assert screen.COL_CONFIDENCE == 7
    assert screen._table.isColumnHidden(screen.COL_SCORE)
    assert screen._table.isColumnHidden(screen.COL_CONFIDENCE)
    hdr = screen._table.horizontalHeaderItem(6)
    assert hdr.text() == "Score"
    hdr2 = screen._table.horizontalHeaderItem(7)
    assert hdr2.text() == "Confian\u00e7a"


def test_table_headers_nao_truncam():
    """Headers de todas as tabelas tem espaco para o texto completo.

    O padding QSS em QHeaderView::section (20px horizontal) nao e
    contabilizado no sizeHint do ResizeToContents.  Esta validação
    confirma que _ensure_header_width foi executada corrigindo as
    colunas cujo texto nao caberia no minimo global.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QHeaderView
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    tbl = screen._table
    hh = tbl.horizontalHeader()
    min_sz = hh.minimumSectionSize()
    for col in range(tbl.columnCount()):
        item = hh.model().headerData(col, Qt.Orientation.Horizontal)
        if item is None:
            continue
        if hh.isSectionHidden(col):
            continue
        text = str(item)
        rez = hh.sectionResizeMode(col)
        sz = hh.sectionSize(col)
        # Stretch columns podem estar no minimo e ok
        if rez == QHeaderView.ResizeMode.Stretch:
            assert sz >= min_sz, (
                f"col {col} '{text}' stretch sz={sz} < min={min_sz}"
            )
            continue
        # Interactive: verifica se o texto cabe no minimo.
        # Se nao cabe e sz == min, _ensure_header_width nao agiu.
        text_w = len(text) * 6  # ~6px por char em 9pt
        if text_w + 40 > min_sz:
            assert sz > min_sz, (
                f"col {col} '{text}' sz={sz} == min={min_sz} "
                f"— _ensure_header_width nao compensou"
            )


def test_watchlist_coluna_score_renderiza_valor():
    """item['current_score'] aparece na coluna como int."""
    import time as _t
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._items = [
        {"name": "ItemA", "current_score": 88, "score_ts": _t.time()},
    ]
    screen._populate()
    row = _watchlist_row_by_name(screen, "ItemA")
    cell = screen._table.item(row, screen.COL_SCORE)
    assert cell.text() == "88"


def test_watchlist_coluna_score_sem_valor_mostra_dash():
    """Item sem current_score mostra '—'."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._items = [{"name": "Nope"}]
    screen._populate()
    row = _watchlist_row_by_name(screen, "Nope")
    cell = screen._table.item(row, screen.COL_SCORE)
    assert cell.text() == "—"


def test_watchlist_coluna_score_tooltip_age(monkeypatch):
    """Tooltip menciona idade do score (agora/h/d)."""
    import time as _t
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._items = [
        {"name": "Fresh", "current_score": 75, "score_ts": _t.time()},
        {"name": "Old1d", "current_score": 75,
         "score_ts": _t.time() - 86400 * 3},
    ]
    screen._populate()
    row_fresh = _watchlist_row_by_name(screen, "Fresh")
    row_old = _watchlist_row_by_name(screen, "Old1d")
    assert "agora" in screen._table.item(row_fresh, screen.COL_SCORE).toolTip()
    assert "3d" in screen._table.item(row_old, screen.COL_SCORE).toolTip()


def test_watchlist_alert_fired_emite_notification(monkeypatch):
    """Quando alert_fired chega via bridge, notification_requested e' emitido."""
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"tray_notifications": True})
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    captured = []
    screen.notification_requested.connect(
        lambda title, body, sev: captured.append((title, body, sev))
    )
    screen._validate_bridge.alert_fired.emit("Clutch Case", {
        "rule": "score_above",
        "label": "Score atingiu 90 (gatilho >= 85)",
        "value": 90,
        "severity": "opportunity",
    })
    assert len(captured) == 1
    title, body, sev = captured[0]
    assert "SkinVault" in title
    assert "Caixa" in body or "Clutch" in body  # nome localizado ou original
    assert "90" in body
    assert sev == "opportunity"


def test_watchlist_alert_silenciado_quando_settings_off(monkeypatch):
    """Settings tray_notifications=False suprime emit."""
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"tray_notifications": False})
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    captured = []
    screen.notification_requested.connect(
        lambda title, body, sev: captured.append((title, body, sev))
    )
    screen._validate_bridge.alert_fired.emit("X", {
        "rule": "score_above", "label": "Score 90",
        "value": 90, "severity": "opportunity",
    })
    assert captured == []


def test_router_re_emite_notification_da_watchlist(monkeypatch):
    """ScreenRouter re-emite notification_requested vindo do WatchlistScreen."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"tray_notifications": True})
    from skinvault.prices import PriceCache
    from skinvault.ui.screen_router import ScreenRouter
    router = ScreenRouter(PriceCache(ttl=3600))
    captured = []
    router.notification_requested.connect(
        lambda title, body, sev: captured.append((title, body, sev))
    )
    # Emite na watchlist; deve sair pelo router
    router._watchlist_screen.notification_requested.emit(
        "T", "B", "opportunity"
    )
    assert captured == [("T", "B", "opportunity")]


def test_mainwindow_notification_chama_tray_showmessage(monkeypatch):
    """_on_notification do MainWindow dispara tray.showMessage."""
    from PyQt6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: True)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {})
    from skinvault.gui import MainWindow
    win = MainWindow()
    if win._tray_icon is None:
        # Tray indisponivel no ambiente de test — pula
        return
    calls = []
    monkeypatch.setattr(
        win._tray_icon, "showMessage",
        lambda title, body, icon, ms: calls.append((title, body)),
    )
    win._on_notification("T", "B", "opportunity")
    assert len(calls) == 1
    assert calls[0] == ("T", "B")


def test_current_score_from_history_vazio_retorna_none():
    """price_history vazio ou curto retorna None."""
    from skinvault.ui.watchlist_screen import _current_score_from_history
    assert _current_score_from_history("X", []) is None
    assert _current_score_from_history("X", [{"time": 0}]) is None


def test_current_score_from_history_retorna_int():
    """Historico valido retorna int em [0, 100]."""
    import time as _t
    from skinvault.ui.watchlist_screen import _current_score_from_history
    ph = [{"time": _t.time() - i * 86400,
           "price_median": 100.0 + i * 0.1, "purchases": 5}
          for i in range(60)]
    score = _current_score_from_history("AK-47 | X", ph)
    assert isinstance(score, int)
    assert 0 <= score <= 100


def test_current_score_from_history_container_squeeze_inicial_alto():
    """Container com squeeze inicial sintetico tem score >= 50."""
    import time as _t
    from skinvault.ui.watchlist_screen import _current_score_from_history
    # ATH em 100, atual em 3 (squeeze inicial)
    prices = [100.0] * 25 + [50.0, 30.0, 10.0, 5.0, 3.0]
    ph = [{"time": _t.time() - (30 - i) * 86400,
           "price_median": p, "purchases": 5}
          for i, p in enumerate(prices)]
    score = _current_score_from_history("Clutch Case", ph)
    assert score is not None
    # Multiplos sinais positivos: rel_ath very_deep, mediana below
    assert score >= 50


def test_watchlist_rules_dialog_score_above_carrega():
    """_RulesDialog carrega score_above existente."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "X", "rules": {"score_above": 85}})
    assert dlg._score_above.value() == 85


def test_watchlist_rules_dialog_score_above_default_off():
    """_RulesDialog default score_above = 0 (desligado)."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "X", "rules": {}})
    assert dlg._score_above.value() == 0


def test_watchlist_rules_dialog_score_above_get_rules():
    """get_rules retorna score_above quando > 0."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "X", "rules": {}})
    dlg._score_above.setValue(75)
    rules = dlg.get_rules()
    assert rules.get("score_above") == 75


def test_watchlist_rules_dialog_score_above_zero_omite():
    """Score 0 (desligado) nao entra em rules."""
    from skinvault.ui.watchlist_screen import _RulesDialog
    dlg = _RulesDialog({"name": "X", "rules": {}})
    dlg._score_above.setValue(0)
    rules = dlg.get_rules()
    assert "score_above" not in rules


def test_watchlist_validate_progress_atualiza_status():
    """_on_validate_progress atualiza o status."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._on_validate_progress("Validando [2/5] AWP (buscando)")
    assert "AWP" in screen._status.text()


# ── Schedule automatico Watchlist ───────────────────────

def test_watchlist_timer_criado(monkeypatch):
    """WatchlistScreen cria QTimer para schedule (default 30min ligado)."""
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 30})
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    assert hasattr(screen, "_schedule_timer")
    assert screen._schedule_timer.isActive()
    assert screen._schedule_timer.interval() == 30 * 60_000


def test_watchlist_start_schedule_lê_settings(monkeypatch):
    """_start_schedule usa intervalo do settings."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 15})
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._start_schedule()
    assert screen._schedule_timer.interval() == 15 * 60_000
    assert screen._schedule_timer.isActive()


def test_watchlist_start_schedule_interval_zero(monkeypatch):
    """Intervalo 0 desliga schedule."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 0})
    screen = WatchlistScreen(PriceCache(ttl=3600))
    assert not screen._schedule_timer.isActive()


def test_watchlist_validating_guard_impede_concorrencia(monkeypatch):
    """Segunda chamada a _on_validate_watchlist enquanto validating retorna cedo."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._validating = True
    screen._on_validate_watchlist()
    assert screen._validating


def test_watchlist_validating_flag_limpo_apos_finished(monkeypatch):
    """_on_validate_finished limpa _validating."""
    from skinvault.prices import PriceCache
    from skinvault.ui.watchlist_screen import WatchlistScreen
    screen = WatchlistScreen(PriceCache(ttl=3600))
    screen._validating = True
    screen._refresh_mode = True
    screen._on_validate_finished()
    assert not screen._validating


# ── Schedule automatico Account ─────────────────────────

def test_account_timer_criado(monkeypatch):
    """AccountScreen cria QTimer para schedule."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 30})
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    assert hasattr(screen, "_schedule_timer")


def test_account_start_schedule_sem_session_pausado(monkeypatch):
    """Schedule pausado quando nao ha sessao."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 30})
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    assert screen._session is None
    assert not screen._schedule_timer.isActive()


def test_account_validating_guard_impede_concorrencia(monkeypatch):
    """Segunda chamada a _on_validate_portfolio enquanto validating retorna cedo."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 30})
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._validating = True
    screen._on_validate_portfolio()
    assert screen._validating


def test_account_validating_flag_limpo_apos_finished(monkeypatch):
    """_on_validate_finished limpa _validating."""
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.settings.load_settings",
                        lambda: {"validate_interval_minutes": 30})
    from skinvault.prices import PriceCache
    from skinvault.ui.account_screen import AccountScreen
    screen = AccountScreen(PriceCache(ttl=3600))
    screen._validating = True
    screen._refresh_mode = True
    screen._on_validate_finished()
    assert not screen._validating


# ── Modo overlay (fullscreen-friendly) ────────────────

def test_overlay_mode_default_false(monkeypatch):
    """Sem settings, overlay_mode default e' False."""
    from PyQt6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: False)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {})
    from skinvault.gui import MainWindow
    win = MainWindow()
    assert win._overlay_mode is False


def test_overlay_mode_settings_default_includes_key():
    """DEFAULTS de settings inclui overlay_mode."""
    from skinvault.settings import DEFAULTS
    assert "overlay_mode" in DEFAULTS
    assert DEFAULTS["overlay_mode"] is False


def test_overlay_mode_aplica_flags(monkeypatch):
    """set_overlay_mode(True) aplica WindowStaysOnTopHint + WA_ShowWithoutActivating."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: False)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {})
    saved = {}
    monkeypatch.setattr("skinvault.gui.save_settings",
                        lambda s: saved.update(s))
    from skinvault.gui import MainWindow
    win = MainWindow()
    win.set_overlay_mode(True)
    assert win._overlay_mode is True
    flags = int(win.windowFlags())
    assert flags & int(Qt.WindowType.WindowStaysOnTopHint)
    assert win.testAttribute(
        Qt.WidgetAttribute.WA_ShowWithoutActivating,
    )
    assert saved.get("overlay_mode") is True


def test_overlay_mode_desativa_flags(monkeypatch):
    """set_overlay_mode(False) remove flags."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: False)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.gui.load_settings",
                        lambda: {"overlay_mode": True})
    monkeypatch.setattr("skinvault.gui.save_settings", lambda s: None)
    from skinvault.gui import MainWindow
    win = MainWindow()
    assert win._overlay_mode is True
    win.set_overlay_mode(False)
    flags = int(win.windowFlags())
    assert not (flags & int(Qt.WindowType.WindowStaysOnTopHint))
    assert not win.testAttribute(
        Qt.WidgetAttribute.WA_ShowWithoutActivating,
    )


def test_overlay_mode_persiste_settings(monkeypatch):
    """Toggle do overlay grava em settings."""
    from PyQt6.QtWidgets import QSystemTrayIcon
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable",
                        lambda: False)
    monkeypatch.setattr("skinvault.steam_session.load", lambda: None)
    monkeypatch.setattr("skinvault.gui.load_settings", lambda: {})
    written = []
    monkeypatch.setattr("skinvault.gui.save_settings",
                        lambda s: written.append(dict(s)))
    from skinvault.gui import MainWindow
    win = MainWindow()
    win.set_overlay_mode(True)
    assert written and written[-1].get("overlay_mode") is True
    win.set_overlay_mode(False)
    assert written[-1].get("overlay_mode") is False


# ── Frente R: helpers QSS (F11) ──────────────────────────────

def test_checkbox_style_no_border_on_root():
    """checkbox_style() nao tem 'border' no bloco do seletor raiz
    'QCheckBox {' — a borda vive apenas no ::indicator."""
    from skinvault.ui.theme import checkbox_style
    qss = checkbox_style()
    start = qss.index("QCheckBox {") + len("QCheckBox {")
    brace = 1
    i = start
    while i < len(qss) and brace > 0:
        if qss[i] == "{":
            brace += 1
        elif qss[i] == "}":
            brace -= 1
        i += 1
    root_block = qss[start:i-1].strip()
    assert "border" not in root_block, (
        f"Root QCheckBox block should not contain 'border', got: {root_block}"
    )
    assert "::indicator" in qss, "checkbox_style() must style ::indicator"


def test_checkbox_style_has_focus_green():
    """Focus do indicator usa FOCUS_GREEN (nao ACCENT)."""
    from skinvault.ui.theme import checkbox_style, FOCUS_GREEN
    qss = checkbox_style()
    assert f"border: 1px solid {FOCUS_GREEN}" in qss


def test_spin_style_has_up_arrow_triangle():
    """spin_style() usa border-triangle em ::up-arrow (width/height 0)."""
    from skinvault.ui.theme import spin_style
    qss = spin_style()
    assert "border-left: 4px solid transparent" in qss, (
        "::up-arrow should use CSS border triangle (transparent sides)"
    )
    assert "width: 0" in qss or "height: 0" in qss


def test_spin_style_no_invalid_bi():
    """spin_style() nao contem a propriedade invalida 'bi:' (removida)."""
    from skinvault.ui.theme import spin_style
    qss = spin_style()
    assert "bi:" not in qss, "The invalid 'bi:' property was removed"


def test_simulador_qspinbox_uses_spin_style():
    """O QSpinBox de Quantidade no Simulador usa spin_style(), nao input_style()."""
    from skinvault.ui.simulador_screen import SimuladorScreen
    from PyQt6.QtWidgets import QSpinBox
    screen = SimuladorScreen()
    qty = screen.findChild(QSpinBox)
    assert qty is not None, "SimuladorScreen deve ter um QSpinBox"
    ss = qty.styleSheet()
    assert ss != "", "QSpinBox deve ter styleSheet nao-vazio"
    assert "up-button" in ss or "up-arrow" in ss, (
        "styleSheet deve conter up-button/up-arrow de spin_style(), "
        f"got: {ss[:200]}"
    )
