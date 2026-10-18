"""Rotas da tela de Configuracoes -- Fase 6.

Subconjunto das chaves do SettingsScreen do Qt: tema/cor de
destaque/largura da sidebar/densidade de tabela ficam fora porque o
CSS da UI web ainda e' um unico tema escuro fixo (sem variante clara
nem sistema de accent) -- portar isso sem o sistema de cores por baixo
seria um controle que nao faz nada.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from skinvault import backup as backup_mod
from skinvault.settings import DEFAULTS, load_settings, save_settings
from skinvault.webapp import window as window_mod

bp = Blueprint("settings", __name__)

#: Chaves que esta tela gerencia -- "Restaurar padroes" so' toca nestas.
_KEYS = (
    "auto_backup", "keep_backups", "start_minimized",
    "minimize_to_tray_on_close", "overlay_mode",
    "cache_ttl_hours", "fee_rate",
)
_BOOL_KEYS = {"auto_backup", "start_minimized", "minimize_to_tray_on_close",
              "overlay_mode"}
_INT_KEYS = {"keep_backups", "cache_ttl_hours"}
_FLOAT_KEYS = {"fee_rate"}


@bp.route("/configuracoes")
def page():
    return render_template("settings.html", active="settings")


def _payload() -> dict:
    s = load_settings()
    return {k: s.get(k, DEFAULTS[k]) for k in _KEYS}


@bp.route("/api/settings")
def get_settings():
    return jsonify(_payload())


@bp.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json(silent=True) or {}
    unknown = [k for k in data if k not in _KEYS]
    if unknown:
        return jsonify({"error": f"chave(s) desconhecida(s): {unknown}"}), 400
    s = load_settings()
    for key, value in data.items():
        if key in _BOOL_KEYS:
            value = bool(value)
        elif key in _INT_KEYS:
            try:
                value = int(value)
            except (TypeError, ValueError):
                return jsonify({"error": f"{key} precisa ser um número"}), 400
            if value < 0:
                return jsonify({"error": f"{key} não pode ser negativo"}), 400
        elif key in _FLOAT_KEYS:
            try:
                value = float(value)
            except (TypeError, ValueError):
                return jsonify({"error": f"{key} precisa ser um número"}), 400
            if not (0.0 <= value <= 1.0):
                return jsonify({"error": "fee_rate precisa estar entre 0 e 1"}), 400
        s[key] = value
    save_settings(s)
    if "overlay_mode" in data:
        # No-op se nao houver janela pywebview ativa (dev server isolado).
        window_mod.apply_overlay(bool(data["overlay_mode"]))
    return jsonify(_payload())


@bp.route("/api/settings/reset", methods=["POST"])
def reset_settings():
    s = load_settings()
    for key in _KEYS:
        s[key] = DEFAULTS[key]
    save_settings(s)
    window_mod.apply_overlay(bool(DEFAULTS["overlay_mode"]))
    return jsonify(_payload())


@bp.route("/api/settings/backups")
def list_backups():
    backups = backup_mod.list_backups()
    return jsonify({"backups": backups})


@bp.route("/api/settings/backup", methods=["POST"])
def make_backup():
    path = backup_mod.make_backup()
    if path is None:
        return jsonify({"error": "Nada para fazer backup (sem dados ainda)."}), 400
    return jsonify({"path": path, "backups": backup_mod.list_backups()})


@bp.route("/api/settings/restore", methods=["POST"])
def restore_backup():
    data = request.get_json(silent=True) or {}
    path = data.get("path") or ""
    allowed = {b["path"] for b in backup_mod.list_backups()}
    if path not in allowed:
        return jsonify({"error": "backup não encontrado"}), 404
    count = backup_mod.restore_backup(path)
    return jsonify({"count": count})
