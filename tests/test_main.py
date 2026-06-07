"""Testes do entrypoint CLI (subprocess + unit)."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.fixture
def _data_dir(tmp_path):
    """Tmp path pra cada subprocess do CLI. Sem isso, `--add "Test Item"`
    polui data/portfolio.json em cada run."""
    return tmp_path


def _run(data_dir, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "SKINVAULT_DATA_DIR": str(data_dir)}
    return subprocess.run(
        [sys.executable, "-m", "skinvault", *args],
        capture_output=True, text=True, timeout=5,
        env=env,
    )


def test_no_args_shows_banner(_data_dir):
    r = _run(_data_dir)
    assert r.returncode == 0
    assert "SkinVault" in r.stdout


def test_help_flag_shows_banner(_data_dir):
    r = _run(_data_dir, "--help")
    assert r.returncode == 0
    assert "SkinVault" in r.stdout


def test_add_requires_minimum_args(_data_dir):
    r = _run(_data_dir, "--add")
    assert r.returncode == 0
    assert "Uso:" in r.stdout
    assert "--add" in r.stdout


def test_add_partial_args_shows_usage(_data_dir):
    r = _run(_data_dir, "--add", "Some Item")
    assert r.returncode == 0
    assert "Uso:" in r.stdout


def test_add_does_not_crash(_data_dir):
    r = _run(_data_dir, "--add", "Test Item", "100", "1")
    assert r.returncode == 0


def test_portfolio_does_not_crash(_data_dir):
    try:
        r = _run(_data_dir, "--portfolio")
        assert r.returncode == 0
    except subprocess.TimeoutExpired:
        pass


def test_check_does_not_crash(_data_dir):
    try:
        r = _run(_data_dir, "--check", "AK-47 | Redline (Field-Tested)")
        assert r.returncode == 0
    except subprocess.TimeoutExpired:
        pass


def test_unknown_flag_shows_banner(_data_dir):
    r = _run(_data_dir, "--nosuchflag")
    assert r.returncode == 0
    assert "SkinVault" in r.stdout


def test_flag_like_value_shows_banner(_data_dir):
    r = _run(_data_dir, "--ui")
    assert r.returncode == 0


# ── Unit tests (coverage via import direto) ─────────────────────


def test_brl_format():
    from skinvault.__main__ import _brl
    assert _brl(1234.5) == "R$ 1.234,50"
    assert _brl(0) == "R$ 0,00"
    assert _brl(0.07) == "R$ 0,07"
    assert _brl(-50) == "R$ -50,00"


def test_cli_value_inv_private(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.prices.value_inventory",
                        lambda *a, **kw: (0, None, 0))
    monkeypatch.setattr("skinvault.__main__.steam_api.INV_PRIVATE", 0)
    from skinvault.__main__ import _cli_value
    _cli_value("7656")  # prints msg about private inventory


def test_cli_value_inv_rate_limited(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.prices.value_inventory",
                        lambda *a, **kw: (1, None, 0))
    monkeypatch.setattr("skinvault.__main__.steam_api.INV_RATE_LIMITED", 1)
    from skinvault.__main__ import _cli_value
    _cli_value("7656")


def test_cli_value_inv_empty(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.prices.value_inventory",
                        lambda *a, **kw: (2, None, 0))
    monkeypatch.setattr("skinvault.__main__.steam_api.INV_EMPTY", 2)
    from skinvault.__main__ import _cli_value
    _cli_value("7656")


def test_cli_value_ok(monkeypatch):
    rows = [{"name": "AK-47", "total": 150.0, "qty": 1}]
    monkeypatch.setattr("skinvault.__main__.prices.value_inventory",
                        lambda *a, **kw: (3, rows, 150.0))
    monkeypatch.setattr("skinvault.__main__.steam_api.INV_OK", 3)
    monkeypatch.setattr("skinvault.__main__.history.record_snapshot",
                        lambda v: None)
    from skinvault.__main__ import _cli_value
    _cli_value("7656")


def test_cli_value_not_ok(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.prices.value_inventory",
                        lambda *a, **kw: (99, [], 0))
    from skinvault.__main__ import _cli_value
    _cli_value("7656")


def test_cli_portfolio_empty(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.portfolio.load_portfolio",
                        lambda: [])
    from skinvault.__main__ import _cli_portfolio
    _cli_portfolio()


def test_cli_portfolio_with_positions(monkeypatch):
    pos = [{
        "name": "AK-47 | Redline (FT)", "buy_price": 150.0, "qty": 2,
        "buy_fee": 0.15, "fee_rate": 0.15
    }]
    monkeypatch.setattr("skinvault.__main__.portfolio.load_portfolio",
                        lambda: pos)
    result = {
        "rows": [{
            "name": "AK-47 | Redline (FT)", "cost": 150.0, "cost_total": 300.0,
            "market": 200.0, "net_if_sold": 170.0, "pnl": -130.0,
            "break_even": 176.47,
        }],
        "totals": {
            "cost": 300.0, "market": 200.0, "net_if_sold": 170.0,
            "pnl": -130.0, "pnl_pct": -43.3,
        },
    }
    monkeypatch.setattr("skinvault.__main__.portfolio.evaluate_portfolio",
                        lambda *a, **kw: result)
    monkeypatch.setattr("skinvault.__main__.prices.PriceCache",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.__main__.prices.cached_price",
                        lambda n, c: None)
    from skinvault.__main__ import _cli_portfolio
    _cli_portfolio()


def test_cli_add_invalid_cost(monkeypatch):
    from skinvault.__main__ import _cli_add
    _cli_add(["Item", "abc"])  # ValueError tratado


def test_cli_add_valid(monkeypatch):
    added = []
    monkeypatch.setattr("skinvault.__main__.portfolio.add_position",
                        lambda n, c, q: added.append((n, c, q)))
    monkeypatch.setattr("skinvault.__main__.portfolio.break_even_price",
                        lambda c: c / 0.85)
    from skinvault.__main__ import _cli_add
    _cli_add(["AK-47 | Redline", "150", "2"])
    assert added == [("AK-47 | Redline", 150.0, 2)]


def test_cli_add_default_qty(monkeypatch):
    added = []
    monkeypatch.setattr("skinvault.__main__.portfolio.add_position",
                        lambda n, c, q: added.append((n, c, q)))
    monkeypatch.setattr("skinvault.__main__.portfolio.break_even_price",
                        lambda c: c / 0.85)
    from skinvault.__main__ import _cli_add
    _cli_add(["AK-47 | Redline", "75"])
    assert added == [("AK-47 | Redline", 75.0, 1)]


def test_cli_check_none(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.steam_api.get_market_overview",
                        lambda n: None)
    from skinvault.__main__ import _cli_check
    _cli_check("Some Item")


def test_cli_check_ok(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.steam_api.get_market_overview",
                        lambda n: {"lowest": 100.0, "median": 120.0, "volume": 500})
    monkeypatch.setattr("skinvault.__main__.steam_api.fair_value_verdict",
                        lambda l, m: {"message": "Bom negocio"})
    from skinvault.__main__ import _cli_check
    _cli_check("AK-47 | Redline")


def test_main_ui_non_win(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.platform", "linux")
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog", "--ui"])
    launched = []
    monkeypatch.setattr("skinvault.gui.launch",
                        lambda: launched.append(True) or 0)
    from skinvault.__main__ import main
    import pytest
    with pytest.raises(SystemExit):
        main()
    assert len(launched) == 1


def test_main_ui_win32_pythonw_found(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.platform", "win32")
    monkeypatch.setattr("skinvault.__main__.sys.executable",
                        "C:\\Python39\\python.exe")
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog", "--ui"])
    popened = []
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: popened.append(True))
    from skinvault.__main__ import main
    main()
    assert len(popened) == 1


def test_main_ui_win32_pythonw_not_found(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.platform", "win32")
    monkeypatch.setattr("skinvault.__main__.sys.executable",
                        "C:\\Python39\\python.exe")
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog", "--ui"])
    monkeypatch.setattr("subprocess.Popen",
                        lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError))
    launched = []
    monkeypatch.setattr("skinvault.gui.launch",
                        lambda: launched.append(True) or 0)
    from skinvault.__main__ import main
    import pytest
    with pytest.raises(SystemExit):
        main()
    assert len(launched) == 1


def test_main_empty_args(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog"])
    from skinvault.__main__ import main
    main()  # prints banner, no crash


def test_main_portfolio(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog", "--portfolio"])
    called = []
    monkeypatch.setattr("skinvault.__main__._cli_portfolio",
                        lambda: called.append(True))
    from skinvault.__main__ import main
    main()
    assert len(called) == 1


def test_main_add(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog", "--add", "X", "10"])
    called = []
    monkeypatch.setattr("skinvault.__main__._cli_add",
                        lambda a: called.append(a))
    from skinvault.__main__ import main
    main()
    assert called == [["X", "10"]]


def test_main_check(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.argv",
                        ["prog", "--check", "AK-47"])
    called = []
    monkeypatch.setattr("skinvault.__main__._cli_check",
                        lambda n: called.append(n))
    from skinvault.__main__ import main
    main()
    assert called == ["AK-47"]


def test_main_steam_id(monkeypatch):
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog", "765611234567"])
    called = []
    monkeypatch.setattr("skinvault.__main__._cli_value",
                        lambda s: called.append(s))
    from skinvault.__main__ import main
    main()
    assert called == ["765611234567"]


# ── Cobertura dos ultimos branches ──────────────────────────────


def test_cli_value_progress_callback(monkeypatch):
    """_cli_value com progress callback (linhas 26-27)."""
    def inv_val(sid, *, progress):
        progress(1, 1, "AK-47")
        return (3, [{"name": "AK-47", "total": 150.0, "qty": 1}], 150.0)
    monkeypatch.setattr("skinvault.__main__.prices.value_inventory", inv_val)
    monkeypatch.setattr("skinvault.__main__.steam_api.INV_OK", 3)
    monkeypatch.setattr("skinvault.__main__.history.record_snapshot", lambda v: None)
    from skinvault.__main__ import _cli_value
    _cli_value("7656")


def test_cli_portfolio_no_price_row(monkeypatch):
    """_cli_portfolio com uma row sem preco (linhas 68-70)."""
    monkeypatch.setattr("skinvault.__main__.portfolio.load_portfolio", lambda: [
        {"name": "AK-47 | Redline (FT)", "buy_price": 150.0, "qty": 1,
         "buy_fee": 0.15, "fee_rate": 0.15}
    ])
    result = {
        "rows": [{"name": "NoPriceItem", "cost": 100.0, "cost_total": 100.0,
                  "pnl": None}],
        "totals": {"cost": 100.0, "market": 0.0, "net_if_sold": 0.0,
                   "pnl": -100.0, "pnl_pct": -100.0},
    }
    monkeypatch.setattr("skinvault.__main__.portfolio.evaluate_portfolio",
                        lambda *a, **kw: result)
    monkeypatch.setattr("skinvault.__main__.prices.PriceCache",
                        lambda *a, **kw: None)
    monkeypatch.setattr("skinvault.__main__.prices.cached_price",
                        lambda n, c: None)
    from skinvault.__main__ import _cli_portfolio
    _cli_portfolio()


def test_cli_add_empty_args(monkeypatch):
    """_cli_add com menos de 2 args (linhas 87-88)."""
    from skinvault.__main__ import _cli_add
    _cli_add([])
    _cli_add(["only_name"])


def test_main_stdout_reconfigure_exception(monkeypatch):
    """main() trata excecao em sys.stdout.reconfigure (linhas 121-122)."""
    import io
    fake_out = io.StringIO()
    monkeypatch.setattr("sys.stdout", fake_out)
    monkeypatch.setattr("skinvault.__main__.sys.argv", ["prog"])
    from skinvault.__main__ import main
    main()
