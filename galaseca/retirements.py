"""Registro de aposentadoria de caixas: QUANDO cada uma parou de entrar no jogo.

Por que existe: o estudo de coortes resumido em AGENTS.md mostrou que o retorno de
caixa depende de *anos desde a aposentadoria* -- salto na saida do pool,
depois decaimento -- e nao do ano de lancamento. `cases.py` so' sabia o ano
de lancamento e o status de HOJE. Sem a data, o fator nao podia nem ser
medido (o backtest via toda caixa aposentada como aposentada desde sempre).

De onde vem a data (verificado em 2026-10-17):
- SAIDA DO ARMORY: aparece nos arquivos do jogo (bloco xpshop do
  items_game.txt) e a Valve anuncia nas notas de patch. `gamedata.py`
  detecta o diff e chama `record_from_events`, com a data do commit.
- DROP SEMANAL (Care Package): o pool de caixas fica no servidor da Valve,
  nao esta' nos arquivos, e as notas de patch de 2023-05 a 2026-10 nao
  anunciam entrada/saida de caixa (anunciam so' colecoes de skin). Sem
  fonte publica confiavel -- fica de fora ate' existir uma.

So' fato com fonte entra aqui. Nada de estimativa de data.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from galaseca._paths import DATA_DIR, atomic_write_text, load_json_record

_PATH = DATA_DIR / "case_retirements.json"

CHANNEL_ARMORY = "armory"

#: Aposentadorias confirmadas por nota de patch oficial. O arquivo em disco
#: soma a isto o que o watcher detectar dali pra frente.
SEED: dict = {
    "Gallery Case": {
        "date": "2025-10-01",
        "channel": CHANNEL_ARMORY,
        "source": "Notas de patch da Valve (01/10/2025): 'Removed Gallery "
                  "Case ... from The Armory'",
    },
}

_cache: dict = {"key": None, "data": None}


def _iso_day(raw) -> Optional[str]:
    """'2026-07-08T17:02:11Z' / '2026-07-08' / epoch -> '2026-07-08'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc).date().isoformat()
    s = str(raw).strip()
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def load(path: "Path | str | None" = None) -> dict:
    """SEED + arquivo, {nome_de_mercado: {date, channel, source}}.

    Cacheado por mtime: `cases.case_status` consulta isto por item, e o
    backtest chama case_status centenas de milhares de vezes.
    """
    p = Path(path or _PATH)
    try:
        mtime = os.path.getmtime(p)
    except OSError:
        mtime = None
    key = (str(p), mtime)
    if _cache["key"] == key and _cache["data"] is not None:
        return _cache["data"]
    data = {k: dict(v) for k, v in SEED.items()}
    disco = load_json_record(p, {}) if mtime is not None else {}
    if isinstance(disco, dict):
        for nome, reg in disco.items():
            if isinstance(reg, dict) and _iso_day(reg.get("date")):
                data[str(nome)] = dict(reg)
    _cache["key"], _cache["data"] = key, data
    return data


def get(case_name: Optional[str],
        path: "Path | str | None" = None) -> Optional[dict]:
    if not case_name:
        return None
    return load(path).get(case_name)


def record(case_name: str, when, channel: str, source: str,
           path: "Path | str | None" = None) -> bool:
    """Grava uma aposentadoria. Idempotente: mantem a data MAIS ANTIGA.

    Retorna True se gravou algo novo. Re-rodar o watcher sobre o mesmo
    commit, ou rever o evento num commit posterior, nao move a data.
    """
    dia = _iso_day(when)
    if not case_name or not dia:
        return False
    p = Path(path or _PATH)
    disco = load_json_record(p, {})
    if not isinstance(disco, dict):
        disco = {}
    atual = disco.get(case_name) or SEED.get(case_name)
    if atual and _iso_day(atual.get("date")) and atual["date"] <= dia:
        return False
    disco[case_name] = {"date": dia, "channel": channel, "source": source}
    atomic_write_text(p, json.dumps(disco, indent=2, ensure_ascii=False))
    _cache["key"] = None
    return True


def record_from_events(events: list, path: "Path | str | None" = None) -> list:
    """Converte eventos do gamedata em aposentadorias. Retorna nomes gravados.

    So' `xpshop_removed` de container (`crate_*`): saiu do Armory = parou
    de entrar no jogo por esse canal. `drop_pool_removed` e' colecao de
    SKIN do Care Package, nao caixa -- nao entra.
    """
    gravados = []
    for ev in events or []:
        if not isinstance(ev, dict) or ev.get("type") != "xpshop_removed":
            continue
        interno = str(ev.get("internal") or "")
        if not interno.startswith("crate_"):
            continue
        nome = ev.get("name") or interno
        if nome == interno:
            continue  # sem nome de mercado (localizacao falhou): nao chuta
        quando = ev.get("commit_date") or ev.get("ts") or time.time()
        sha = str(ev.get("commit_sha") or "")[:8]
        fonte = ("items_game.txt (GameTracking-CS2)"
                 + (f", commit {sha}" if sha else "")
                 + ": saiu do bloco do Armory")
        if record(nome, quando, CHANNEL_ARMORY, fonte, path=path):
            gravados.append(nome)
    return gravados


def years_since(reg: Optional[dict], now: Optional[float] = None) -> Optional[float]:
    """Anos (fracionarios) desde a aposentadoria; None sem registro."""
    if not reg:
        return None
    dia = _iso_day(reg.get("date"))
    if not dia:
        return None
    ref = datetime.fromtimestamp(time.time() if now is None else now,
                                 tz=timezone.utc).date()
    return (ref - date.fromisoformat(dia)).days / 365.25
