from __future__ import annotations

import json
from pathlib import Path

from skinvault._paths import DATA_DIR

_DEFAULT_PATH = DATA_DIR / "settings.json"

DEFAULTS = {
    "cache_ttl_hours": 6,
    "fee_rate": 0.15,
    "auto_backup": True,
    "tray_notifications": True,
    "keep_backups": 10,
    "theme": "dark",
    "start_minimized": False,
    "minimize_to_tray_on_close": True,
    "history_last_segment": "all",
    "history_last_periodo": "all",
    "column_widths": {},
    "window_geometry": {},
    "window_position": {},
    "last_scenario": {},
    "sidebar_width": 220,
    "scanner_unlocked": False,
    "welcome_seen": False,
    "overlay_mode": False,  # janela "stays on top" + show sem roubar foco
    "scanner_hide_low_confidence": False,
    "validate_interval_minutes": 30,  # 0 = desliga schedule automatico
}


def load_settings(path: Path | str = _DEFAULT_PATH) -> dict:
    p = Path(path)
    try:
        data = json.loads(p.read_text("utf-8"))
        return {**DEFAULTS, **data}
    except Exception:
        return dict(DEFAULTS)


def save_settings(settings: dict, path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"WARNING: failed to save settings: {e}", file=__import__('sys').stderr)
