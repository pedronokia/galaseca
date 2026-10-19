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
import time
from typing import Callable

from skinvault import portfolio as portfolio_mod
from skinvault import steam_api
from skinvault.settings import load_settings, save_settings

DoneCb = Callable[[dict], None]
ProgressCb = Callable[[int, int, str], None]

_import_lock = threading.Lock()
_importing = False

_backfill_lock = threading.Lock()
_backfilling = False

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
    base = _MENSAGENS.get(status, _MENSAGENS[steam_api.INV_ERROR])
    if status != steam_api.INV_RATE_LIMITED:
        return base
    # Disjuntor: se a familia ja' esta' em cooldown (de uma tentativa
    # anterior, dessa ou de outra importacao), diz quanto falta de
    # verdade em vez do "alguns minutos" generico -- o usuario ve que
    # a espera tem um numero, nao e' indefinida.
    restante = max(steam_api.cooldown_restante_s("inventory"),
                   steam_api.cooldown_restante_s("resolve"))
    if restante <= 0:
        return base
    minutos = max(1, round(restante / 60))
    return (f"A Steam limitou as consultas agora. Faltam cerca de "
            f"{minutos} minuto(s) antes de tentar de novo.")


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
            # resolve_steam_id ja' pode ter batido na rede (link
            # personalizado -> pagina XML do perfil) -- mesmo intervalo
            # entre chamadas que o resto do app usa, referenciado em
            # tempo de chamada (nao copiado pra constante) pra
            # monkeypatch de teste alcancar (AGENTS.md #13).
            if steam_api.em_cooldown("inventory"):
                # Disjuntor ja' sabe que vai recusar -- nem espera os
                # 4s de pausa nem gasta a 1a tentativa, e PULA o laco
                # de retentativa abaixo (esperar 16s/32s pra ouvir a
                # mesma recusa de novo nao protege nada, so' atrasa o
                # usuario por nada).
                status, itens = steam_api.INV_RATE_LIMITED, []
            else:
                time.sleep(steam_api.RATE_LIMIT_DELAY_S)
                status, itens = steam_api.fetch_inventory(steam_id)
                for mult in steam_api.RATE_LIMIT_RETRY_BACKOFF_MULT:
                    if (status != steam_api.INV_RATE_LIMITED
                            or steam_api.em_cooldown("inventory")):
                        break
                    time.sleep(steam_api.RATE_LIMIT_DELAY_S * mult)
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


def is_backfilling() -> bool:
    return _backfilling


def start_icon_backfill(on_progress: ProgressCb, on_done: DoneCb) -> bool:
    """Busca o icone de toda posicao que ainda nao tem (entrada manual/
    CSV nunca tem -- nao ha' rede nessa importacao; sincronizacao antiga
    pode ter deixado passar), via /market/listings/730/<nome> --
    DOMINIO/endpoint diferente do /inventory/ que a importacao usa
    (icon_backfill.py ja' bate nele pra steam_market_events.json com o
    mesmo throttle, nunca reportado como sensivel do jeito que
    /inventory/ foi hoje). Devolve False sem fazer nada se ja' houver
    uma busca em andamento."""
    global _backfilling
    with _backfill_lock:
        if _backfilling:
            return False
        _backfilling = True

    def _worker() -> None:
        global _backfilling
        try:
            from skinvault import icon_backfill

            nomes = portfolio_mod.positions_missing_icon(
                portfolio_mod.load_portfolio())
            total = len(nomes)
            atualizados = 0
            for i, nome in enumerate(nomes):
                if i:
                    time.sleep(steam_api.RATE_LIMIT_DELAY_S)
                h = icon_backfill.fetch_icon_hash_for_name(nome)
                if h:
                    atualizados += portfolio_mod.set_icon(nome, h)
                on_progress(i + 1, total, nome)
            on_done({"ok": True, "total": total, "atualizados": atualizados})
        except Exception as e:
            print(f"WARNING: inventory_data.start_icon_backfill failed: {e}",
                  file=sys.stderr)
            on_done({"error": "Não consegui buscar as imagens agora."})
        finally:
            with _backfill_lock:
                _backfilling = False

    threading.Thread(target=_worker, daemon=True).start()
    return True
