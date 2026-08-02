from __future__ import annotations

import json
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

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
    # Barra lateral recolhida (rail de icones) contra expandida com
    # rotulos. Default recolhida: e' o estado que o app sempre teve.
    "sidebar_collapsed": True,
    # Visao do inventario: "grid" (cards) ou "table" (tabela detalhada).
    "inventory_view": "grid",
    # Densidade das tabelas do app inteiro: "compact" | "standard" |
    # "comfortable". Ver theme.TABLE_ROW_H / theme.TABLE_CELL_PAD.
    "table_density": "standard",
    "scanner_unlocked": False,
    "welcome_seen": False,
    "overlay_mode": False,  # janela "stays on top" + show sem roubar foco
    "scanner_hide_low_confidence": False,
    "validate_interval_minutes": 30,  # 0 = desliga schedule automatico
    # Descoberta de itens por faceta no Market em vez da lista fixa do
    # scanner. Default OFF: o caminho de rede ainda nao foi validado
    # ponta a ponta contra a Steam (bloqueio de rate limit persistente em
    # 2026-07-28). Ligado, cai na lista fixa em qualquer falha.
    "scanner_discovery": False,
    # Tela de Limpeza: quais alvos vem marcados. A lixeira nunca persiste
    # marcada (alvo destrutivo) -- vide CleanupScreen._load_selection.
    "cleanup_selected": [],
    "cleanup_last_ts": 0,
}


def load_settings(path: Path | str = _DEFAULT_PATH) -> dict:
    data = load_json_record(path, None)
    if not isinstance(data, dict):
        return dict(DEFAULTS)
    return {**DEFAULTS, **data}


def save_settings(settings: dict, path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        atomic_write_text(p, json.dumps(settings, indent=2))
    except OSError as e:
        print(f"WARNING: failed to save settings: {e}", file=__import__('sys').stderr)
