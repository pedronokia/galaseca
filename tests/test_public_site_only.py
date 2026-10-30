from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_desktop_and_local_web_ui_are_removed():
    removed_paths = [
        ROOT / "galaseca" / "gui.py",
        ROOT / "galaseca" / "__main__.py",
        ROOT / "galaseca" / "ui",
        ROOT / "galaseca" / "webapp",
        ROOT / "run.py",
        ROOT / "run_web.py",
        ROOT / "requirements.txt",
        ROOT / "galaseca" / "assets" / "icon.ico",
        ROOT / ".claude" / "launch.json",
        ROOT / "scripts" / "dev_web_server.py",
        ROOT / "scripts" / "criar_atalho.ps1",
        ROOT / "scripts" / "build_icon.py",
        ROOT / "scripts" / "build_icon_concepts.py",
        ROOT / "scripts" / "check_tooltips.py",
    ]
    removed_modules = (
        "activity", "backtest", "backup", "cleanup", "fee_calculator",
        "goals", "history", "icon_backfill", "icons",
        "markets", "reports", "settings", "single_instance", "ssr_cache",
        "sync", "trade_matcher", "tradeup", "watchlist",
    )
    removed_paths.extend(
        ROOT / "galaseca" / f"{module}.py" for module in removed_modules
    )

    assert all(not path.exists() for path in removed_paths)


def test_runtime_dependencies_are_for_the_public_site_only():
    requirements = [
        line.strip().lower()
        for line in (ROOT / "requirements-public-site.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert any(line.startswith("flask") for line in requirements)
    assert any(line.startswith("httpx") for line in requirements)
    assert not any(
        name in line
        for line in requirements
        for name in ("pyqt", "pywebview", "pystray", "winotify")
    )
