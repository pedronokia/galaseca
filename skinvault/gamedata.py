"""Watcher de arquivos do jogo via GameTracking-CS2 (SteamDB).

O repositorio publico SteamDatabase/GameTracking-CS2 commita automaticamente
os arquivos do CS2 minutos apos cada update da Valve. Este modulo monitora o
items_game.txt e extrai mudancas de regime de oferta -- os eventos que a
pesquisa de backtest mostrou serem os maiores drivers de retorno (cases
descontinuadas dominam o bucket 85+; rotacao de drop pool e o evento gerador).

Sinais extraidos (todos factuais, nunca previsao):
- timed_drop_sets: colecoes do weekly drop ativo (loot lists set_timed_drops_*)
- xpshop_rewards: itens resgataveis no Armory/XP shop (bloco seasonaloperations
  com redeemable_goods=xpshop)
- crates: containers conhecidos + first_sale_date
- crate_series: registro mestre serie -> container (revolving_loot_lists);
  entrada nova = container novo no jogo

Fluxo: check_for_updates() compara o commit mais recente do arquivo com o
estado persistido em data/gamedata_state.json; se mudou, baixa, extrai,
diffa e loga eventos em data/gamedata_events.json (cap 500).

Complementa skinvault/valve_events.py (catalogo manual): eventos detectados
aqui viram candidatos a entrada la apos interpretacao humana.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from skinvault._paths import DATA_DIR

_REPO = "SteamDatabase/GameTracking-CS2"
_ITEMS_PATH = "game/csgo/pak01_dir/scripts/items/items_game.txt"
_ENGLISH_PATH = "game/csgo/pak01_dir/resource/csgo_english.txt"

_API_COMMITS_URL = (
    f"https://api.github.com/repos/{_REPO}/commits"
    f"?path={_ITEMS_PATH}&per_page={{n}}"
)
_RAW_URL = f"https://raw.githubusercontent.com/{_REPO}/{{ref}}/{{path}}"

_STATE_PATH = DATA_DIR / "gamedata_state.json"
_EVENTS_LOG_PATH = DATA_DIR / "gamedata_events.json"
_LOG_CAP = 500

_UA = "SkinVault/1.0 (game data watcher)"

# Sufixos de tier das loot lists -- strip pra chegar no nome base da colecao
_TIER_SUFFIXES = (
    "_common", "_uncommon", "_rare", "_mythical", "_legendary", "_ancient",
    "_desc",
)


def _http_get(url: str, timeout: float = 60.0) -> "tuple[int, Optional[str]]":
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError):
        return 0, None


# ---------------------------------------------------------------------------
# Parsing do items_game.txt
# ---------------------------------------------------------------------------

def _strip_tier(name: str) -> str:
    for suf in _TIER_SUFFIXES:
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def _extract_timed_drop_sets(text: str) -> "list[str]":
    """Colecoes do weekly drop ativo (set_timed_drops_*)."""
    found = set()
    for m in re.finditer(r'"set_timed_drops_([a-z0-9_]+)"', text):
        found.add(_strip_tier("set_timed_drops_" + m.group(1)))
    return sorted(found)


def _extract_xpshop_rewards(text: str) -> "list[str]":
    """Itens resgataveis no Armory (blocos seasonaloperations com xpshop).

    Faz scan linha a linha com contagem de chaves; regex pura nao serve
    porque o arquivo tem varios blocos seasonaloperations (historicos).
    """
    rewards: "set[str]" = set()
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        if '"seasonaloperations"' in lines[i]:
            # coleta o bloco inteiro (ate fechar a chave de abertura)
            depth = 0
            opened = False
            block: "list[str]" = []
            j = i + 1
            while j < n:
                line = lines[j]
                depth += line.count("{") - line.count("}")
                if not opened and "{" in line:
                    opened = True
                block.append(line)
                if opened and depth <= 0:
                    break
                j += 1
            block_text = "\n".join(block)
            if '"xpshop"' in block_text:
                for m in re.finditer(
                    r'"item_name"\s+"(?:lootlist:)?([a-z0-9_:]+)"', block_text
                ):
                    rewards.add(m.group(1))
            i = j + 1
        else:
            i += 1
    return sorted(rewards)


def _extract_crates(text: str) -> "dict[str, str]":
    """Containers (crate_*) -> first_sale_date ("" quando ausente).

    Containers pos-2024 nao carregam first_sale_date; o nome sozinho ja
    basta pra detectar container novo no diff. Quando a data existe, o
    bloco de item a lista a poucas linhas do "name" (janela de 15 linhas).
    """
    crates: "dict[str, str]" = {}
    pending: "Optional[tuple[str, int]]" = None
    for idx, line in enumerate(text.splitlines()):
        m = re.search(r'"name"\s+"(crate_[a-z0-9_]+)"', line)
        if m:
            crates.setdefault(m.group(1), "")
            pending = (m.group(1), idx)
            continue
        if pending is None:
            continue
        m = re.search(r'"first_sale_date"\s+"([0-9/]+)"', line)
        if m:
            if idx - pending[1] <= 15:
                crates[pending[0]] = m.group(1)
            pending = None
    return crates


def _extract_crate_series(text: str) -> "dict[str, str]":
    """Registro mestre serie -> loot list (revolving_loot_lists, merged)."""
    series: "dict[str, str]" = {}
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip() == '"revolving_loot_lists"':
            depth = 0
            opened = False
            j = i + 1
            while j < n:
                line = lines[j]
                if "{" in line:
                    opened = True
                depth += line.count("{") - line.count("}")
                m = re.search(r'"(\d+)"\s+"([a-z0-9_]+)"', line)
                if m:
                    series[m.group(1)] = m.group(2)
                if opened and depth <= 0:
                    break
                j += 1
            i = j + 1
        else:
            i += 1
    return series


def extract_state(items_text: str) -> dict:
    """Snapshot dos sinais de oferta extraidos do items_game.txt."""
    return {
        "timed_drop_sets": _extract_timed_drop_sets(items_text),
        "xpshop_rewards": _extract_xpshop_rewards(items_text),
        "crates": _extract_crates(items_text),
        "crate_series": _extract_crate_series(items_text),
    }


# ---------------------------------------------------------------------------
# Nomes amigaveis (csgo_english.txt)
# ---------------------------------------------------------------------------

def parse_localization(english_text: str) -> "dict[str, str]":
    """Mapa token -> nome de mercado a partir do csgo_english.txt."""
    loc: "dict[str, str]" = {}
    for m in re.finditer(r'"(CSGO_[^"]+)"\s+"([^"]*)"', english_text):
        loc[m.group(1)] = m.group(2)
    return loc


def display_name(internal: str, loc: "dict[str, str]") -> str:
    """Nome de mercado pra um nome interno; fallback no proprio interno."""
    for key in (f"CSGO_{internal}", f"CSGO_set_{internal}"):
        if loc.get(key):
            return loc[key]
    return internal


# ---------------------------------------------------------------------------
# Diff -> eventos factuais
# ---------------------------------------------------------------------------

def diff_states(old: dict, new: dict,
                loc: "Optional[dict[str, str]]" = None) -> "list[dict]":
    """Compara dois snapshots e retorna eventos factuais (sem previsao).

    Tipos: drop_pool_added, drop_pool_removed, xpshop_added, xpshop_removed,
    new_container.
    """
    loc = loc or {}
    events: "list[dict]" = []

    def _ev(etype: str, internal: str, summary: str) -> dict:
        return {
            "type": etype,
            "internal": internal,
            "name": display_name(internal, loc),
            "summary": summary,
        }

    old_drops = set(old.get("timed_drop_sets", []))
    new_drops = set(new.get("timed_drop_sets", []))
    for s in sorted(new_drops - old_drops):
        events.append(_ev(
            "drop_pool_added", s,
            f"Colecao '{display_name(s, loc)}' entrou no weekly drop ativo "
            "(oferta passa a crescer).",
        ))
    for s in sorted(old_drops - new_drops):
        events.append(_ev(
            "drop_pool_removed", s,
            f"Colecao '{display_name(s, loc)}' saiu do weekly drop ativo "
            "(oferta congela a partir de agora).",
        ))

    old_shop = set(old.get("xpshop_rewards", []))
    new_shop = set(new.get("xpshop_rewards", []))
    for s in sorted(new_shop - old_shop):
        events.append(_ev(
            "xpshop_added", s,
            f"Item '{display_name(s, loc)}' entrou no Armory/XP shop "
            "(novo canal de oferta ativo).",
        ))
    for s in sorted(old_shop - new_shop):
        events.append(_ev(
            "xpshop_removed", s,
            f"Item '{display_name(s, loc)}' saiu do Armory/XP shop "
            "(canal de oferta fechou).",
        ))

    old_crates = set(old.get("crates", {}))
    for c in sorted(set(new.get("crates", {})) - old_crates):
        sale = new["crates"].get(c, "")
        extra = f" (first_sale_date {sale})" if sale else ""
        events.append(_ev(
            "new_container", c,
            f"Container novo '{display_name(c, loc)}' nos arquivos do "
            f"jogo{extra}.",
        ))

    return events


# ---------------------------------------------------------------------------
# GitHub: commits e download
# ---------------------------------------------------------------------------

def fetch_recent_commits(n: int = 30) -> "list[dict]":
    """Commits recentes que tocaram o items_game.txt (mais novo primeiro).

    Retorna [{sha, date, message}]. Lista vazia em erro de rede/rate limit.
    """
    code, body = _http_get(_API_COMMITS_URL.format(n=n))
    if code != 200 or not body:
        return []
    try:
        raw = json.loads(body)
    except ValueError:
        return []
    out = []
    for c in raw:
        try:
            out.append({
                "sha": c["sha"],
                "date": c["commit"]["committer"]["date"],
                "message": c["commit"]["message"].splitlines()[0],
            })
        except (KeyError, IndexError):
            continue
    return out


def fetch_items_game(ref: str = "master") -> "Optional[str]":
    code, body = _http_get(_RAW_URL.format(ref=ref, path=_ITEMS_PATH))
    return body if code == 200 else None


def fetch_localization(ref: str = "master") -> "dict[str, str]":
    code, body = _http_get(_RAW_URL.format(ref=ref, path=_ENGLISH_PATH))
    return parse_localization(body) if code == 200 and body else {}


# ---------------------------------------------------------------------------
# Persistencia + ciclo de checagem
# ---------------------------------------------------------------------------

def load_state(path: "Path | str" = _STATE_PATH) -> "Optional[dict]":
    p = Path(path)
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else None
    except Exception:
        return None


def save_state(state: dict, path: "Path | str" = _STATE_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def log_events(events: "list[dict]",
               path: "Path | str" = _EVENTS_LOG_PATH) -> None:
    if not events:
        return
    p = Path(path)
    try:
        data = json.loads(p.read_text("utf-8")) if p.exists() else []
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    data.extend(events)
    if len(data) > _LOG_CAP:
        data = data[-_LOG_CAP:]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_events_log(path: "Path | str" = _EVENTS_LOG_PATH) -> "list[dict]":
    p = Path(path)
    try:
        data = json.loads(p.read_text("utf-8")) if p.exists() else []
        return data if isinstance(data, list) else []
    except Exception:
        return []


_EVENT_SEVERITY = {
    # Oferta congela -> tese de escassez estrutural (bucket 85+ do backtest)
    "drop_pool_removed": "opportunity",
    "xpshop_removed": "opportunity",
}


def record_events_as_alerts(events: "list[dict]",
                            path: "Optional[Path | str]" = None) -> "list[tuple[str, dict]]":
    """Registra eventos do watcher no log de alertas (rule=game_update).

    Reusa o log/UI de alertas existente. Retorna [(name, alert)] gravados.
    """
    from skinvault import alerts
    recorded: "list[tuple[str, dict]]" = []
    for ev in events:
        alert = {
            "rule": "game_update",
            "label": ev.get("summary", ""),
            "severity": _EVENT_SEVERITY.get(ev.get("type", ""), "info"),
            "value": None,
        }
        name = ev.get("name") or ev.get("internal", "")
        if path is None:
            alerts.record_alert(name, alert)
        else:
            alerts.record_alert(name, alert, path=path)
        recorded.append((name, alert))
    return recorded


def check_for_updates(state_path: "Path | str" = _STATE_PATH,
                      log_path: "Path | str" = _EVENTS_LOG_PATH) -> dict:
    """Ciclo completo: novo commit? -> baixa, extrai, diffa, persiste, loga.

    Retorna {"changed": bool, "events": [...], "commit": {...} | None,
    "error": str | None}. Na primeira execucao grava baseline sem eventos.
    """
    commits = fetch_recent_commits(n=1)
    if not commits:
        return {"changed": False, "events": [], "commit": None,
                "error": "network"}
    head = commits[0]

    stored = load_state(state_path)
    if stored and stored.get("sha") == head["sha"]:
        return {"changed": False, "events": [], "commit": head, "error": None}

    text = fetch_items_game(ref=head["sha"])
    if text is None:
        return {"changed": False, "events": [], "commit": head,
                "error": "network"}
    new_state = extract_state(text)

    events: "list[dict]" = []
    if stored and isinstance(stored.get("state"), dict):
        loc = fetch_localization(ref=head["sha"])
        events = diff_states(stored["state"], new_state, loc)
        now = time.time()
        for ev in events:
            ev["ts"] = now
            ev["commit_sha"] = head["sha"]
            ev["commit_date"] = head["date"]
        log_events(events, path=log_path)

    save_state({
        "sha": head["sha"],
        "commit_date": head["date"],
        "fetched_at": time.time(),
        "state": new_state,
    }, path=state_path)

    return {"changed": True, "events": events, "commit": head, "error": None}
