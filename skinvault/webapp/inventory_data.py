"""Importar inventario publico da Steam pra carteira -- sem Flask,
testavel isolado.

Equivalente web de `ui/inventory_dialogs.py` (ImportarSteamDialog),
que so' existia na tela Qt. So' dado publico: link/apelido/ID do
perfil -> inventario publico (/inventory/<id>/730/2), sem login, sem
cookie, sem chave de API -- mesma regra do resto do app.

Mensagens duplicadas de `inventory_dialogs.MENSAGENS` de proposito: o
webapp nao importa nada de skinvault.ui (pacote Qt, puxaria PyQt6)
pra nao criar acoplamento cruzado (mesmo principio de scanner_data.py).
"""
from __future__ import annotations

import sys
import threading
from typing import Callable

from skinvault import portfolio as portfolio_mod
from skinvault import steam_api
from skinvault.settings import load_settings, save_settings

DoneCb = Callable[[dict], None]

_import_lock = threading.Lock()
_importing = False

_MENSAGENS = {
    steam_api.RESOLVE_INVALID: (
        "Isso não parece um perfil da Steam. Cole o link do seu perfil, "
        "por exemplo: https://steamcommunity.com/id/seu-apelido"),
    steam_api.RESOLVE_NOT_FOUND: (
        "Não achamos esse perfil na Steam. Confira o link ou o apelido."),
    steam_api.INV_PRIVATE: (
        "Esse inventário está privado. Na Steam, abra Editar perfil → "
        "Configurações de privacidade e deixe o Inventário como Público. "
        "Depois tente de novo."),
    steam_api.INV_EMPTY: (
        "Não encontramos itens de CS2 que possam ser vendidos nesse "
        "inventário."),
    steam_api.INV_RATE_LIMITED: (
        "A Steam limitou as consultas agora. Espere alguns minutos e "
        "tente de novo."),
    steam_api.INV_ERROR: (
        "Não deu para falar com a Steam. Verifique a internet e tente de "
        "novo."),
}


def _mensagem_de_erro(status: str) -> str:
    return _MENSAGENS.get(status, _MENSAGENS[steam_api.INV_ERROR])


def _resumo_importacao(r: dict) -> str:
    linhas = [f"{r['itens_no_inventario']} item(ns) encontrados no "
              "inventário."]
    if r["adicionados"]:
        linhas.append(f"{r['adicionados']} novo(s) na carteira.")
    if r["atualizados"]:
        linhas.append(f"{r['atualizados']} já estavam e foram atualizados.")
    if r["manuais_mantidos"]:
        linhas.append(f"{r['manuais_mantidos']} você já acompanhava à mão "
                      "e ficaram como estavam.")
    if r["removidos"]:
        linhas.append(f"{r['removidos']} não estavam mais no inventário e "
                      "saíram da carteira.")
    return " ".join(linhas)


def is_importing() -> bool:
    return _importing


def start_import(profile: str, remove_missing: bool,
                  on_done: DoneCb) -> bool:
    """Resolve o perfil, busca o inventario publico e mescla na
    carteira, numa thread daemon. Devolve False sem fazer nada se ja'
    houver uma importacao em andamento."""
    global _importing
    with _import_lock:
        if _importing:
            return False
        _importing = True

    def _worker() -> None:
        global _importing
        try:
            status, steam_id = steam_api.resolve_steam_id(profile)
            if status != steam_api.RESOLVE_OK or not steam_id:
                on_done({"error": _mensagem_de_erro(status)})
                return
            status, itens = steam_api.fetch_inventory(steam_id)
            if status != steam_api.INV_OK:
                on_done({"error": _mensagem_de_erro(status)})
                return
            resumo = portfolio_mod.merge_steam_inventory(
                itens, remove_missing=remove_missing)
            s = load_settings()
            s["steam_profile"] = profile.strip()
            save_settings(s)
            on_done({"ok": True, "resumo": resumo,
                     "mensagem": _resumo_importacao(resumo)})
        except Exception as e:
            print(f"WARNING: inventory_data.start_import failed: {e}",
                  file=sys.stderr)
            on_done({"error": _mensagem_de_erro(steam_api.INV_ERROR)})
        finally:
            with _import_lock:
                _importing = False

    threading.Thread(target=_worker, daemon=True).start()
    return True
