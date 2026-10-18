"""Rotas da tela de Limpeza do Sistema -- Fase 9.

Sincrono de proposito (sem SSE): `scan_target`/`clean_target` sao
rapidos na pratica (ver cleanup.py) e um scan ocasional bloqueando UM
request do dev server nao justifica a complexidade de progresso em
background que as telas com rede (Conta, Trade-up) precisam de
verdade. A selecao persiste em settings.json (`cleanup_selected`),
igual o Qt -- a Lixeira nunca volta marcada (alvo destrutivo).
"""
from __future__ import annotations

import time

from flask import Blueprint, jsonify, render_template, request

from skinvault import cleanup as cleanup_mod
from skinvault.settings import load_settings, save_settings

bp = Blueprint("cleanup", __name__)


@bp.route("/limpeza")
def page():
    return render_template("cleanup.html", active="cleanup")


def _target_meta() -> list[dict]:
    return [
        {"key": t.key, "title": t.title, "description": t.description,
         "dangerous": t.dangerous, "needs_admin": t.needs_admin,
         "note": t.note}
        for t in cleanup_mod.TARGETS
    ]


@bp.route("/api/cleanup/status")
def status():
    scans = cleanup_mod.scan_all()
    selected = set(load_settings().get("cleanup_selected") or [])
    targets = []
    for meta in _target_meta():
        s = scans.get(meta["key"])
        targets.append({
            **meta,
            "available": s.available if s else False,
            "files": s.files if s else 0,
            "bytes": s.bytes if s else 0,
            "bytes_human": cleanup_mod.human_bytes(s.bytes if s else 0),
            # Lixeira nunca volta marcada -- alvo destrutivo demais pra
            # um clique acidental em "Limpar selecionados" reesvaziar.
            "selected": meta["key"] in selected and meta["key"] != cleanup_mod.RECYCLE_BIN,
        })
    return jsonify({"targets": targets, "is_admin": cleanup_mod.is_admin()})


@bp.route("/api/cleanup/selection", methods=["POST"])
def save_selection():
    data = request.get_json(silent=True) or {}
    keys = data.get("keys")
    if not isinstance(keys, list):
        return jsonify({"error": "keys precisa ser uma lista"}), 400
    valid = [k for k in keys if k in cleanup_mod.TARGET_KEYS]
    s = load_settings()
    s["cleanup_selected"] = valid
    save_settings(s)
    return jsonify({"ok": True})


@bp.route("/api/cleanup/clean", methods=["POST"])
def clean():
    data = request.get_json(silent=True) or {}
    keys = data.get("keys")
    if not isinstance(keys, list) or not keys:
        return jsonify({"error": "selecione ao menos um alvo"}), 400
    invalid = [k for k in keys if k not in cleanup_mod.TARGET_KEYS]
    if invalid:
        return jsonify({"error": f"alvo(s) desconhecido(s): {invalid}"}), 400
    results = cleanup_mod.clean(keys)
    s = load_settings()
    s["cleanup_last_ts"] = time.time()
    save_settings(s)
    return jsonify({
        "results": {
            key: {"removed": r.removed, "freed": r.freed,
                  "freed_human": cleanup_mod.human_bytes(r.freed),
                  "skipped": r.skipped, "errors": r.errors}
            for key, r in results.items()
        },
    })
