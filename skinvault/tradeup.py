"""Calculadora de EV de trade-up (10->1 e 5 Covert->faca/luva).

Duas metades, separadas de proposito:

1. CATALOGO -- quem esta' em qual colecao, em qual raridade, com qual range
   de float, e qual o pool de faca/luva de cada colecao de caixa. A Steam
   nao expoe nada disso (o market so' tem a tag da colecao, sem os irmaos de
   raridade, sem float e sem o pool raro). O items_game.txt tambem nao: as
   loot lists dos pools raros (ex.: "community_case_3_unusual") sao
   referenciadas la' mas definidas fora do arquivo -- verificado em
   2026-10-17. A fonte e' o dataset publico ByMykel/CSGO-API (GitHub),
   derivado dos arquivos do jogo e atualizado a cada patch. Nao e' mercado:
   o preco continua 100% Steam (SSR cache).

2. MATEMATICA -- pura, sem rede. Regras vigentes (guia SteamDB 2026 +
   patch notes de out/2025 e mai/2026):
   - Contrato normal: 10 itens da MESMA raridade -> 1 da raridade seguinte.
   - Contrato de faca/luva (desde 22/10/2025): 5 Covert -> 1 item raro do
     pool da colecao de um dos inputs.
   - Sorteio em dois passos: um input e' escolhido ao acaso (1/N cada); a
     colecao dele vira a colecao de saida; o resultado sai uniforme entre os
     itens da raridade seguinte (ou do pool raro) daquela colecao.
   - Float de saida: cada input e' normalizado no range do PROPRIO skin,
     faz-se a media, e ela e' mapeada no range do skin de saida.
   - StatTrak e' tudo-ou-nada; 10 ST -> saida ST. Luva nao sai de ST.
   - Souvenir entra junto com itens normais (desde 22/05/2026) e a saida e'
     sempre normal.

O que sai daqui e' DESCRITIVO: valor esperado com os precos medianos
recentes. Nao e' previsao de preco nem promessa de retorno.
"""
from __future__ import annotations

import json
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from skinvault import fee_calculator
from skinvault._paths import DATA_DIR, atomic_write_text

_CATALOG_PATH = DATA_DIR / "tradeup_catalog.json"
#: O dataset muda com patch do jogo (colecao nova, caixa nova), nao todo
#: dia. Uma semana e' folga suficiente; "Atualizar catalogo" forca.
CATALOG_TTL_S = 7 * 24 * 60 * 60
CATALOG_VERSION = 1

_DATASET_BASE = (
    "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/"
)
_SKINS_URL = _DATASET_BASE + "skins.json"
_CRATES_URL = _DATASET_BASE + "crates.json"
_UA = "SkinVault/1.0 (trade-up catalog)"

#: Ordem das raridades de arma, da mais baixa pra mais alta.
RARITIES = ("common", "uncommon", "rare", "mythical", "legendary", "ancient")
RARITY_LABELS = {
    "common": "Consumer",
    "uncommon": "Industrial",
    "rare": "Mil-Spec",
    "mythical": "Restricted",
    "legendary": "Classified",
    "ancient": "Covert",
}

#: (nome, float_min_inclusivo, float_max_exclusivo) -- faixas oficiais.
WEAR_BANDS = (
    ("Factory New", 0.00, 0.07),
    ("Minimal Wear", 0.07, 0.15),
    ("Field-Tested", 0.15, 0.38),
    ("Well-Worn", 0.38, 0.45),
    ("Battle-Scarred", 0.45, 1.00),
)
_WEAR_NAMES = tuple(w[0] for w in WEAR_BANDS)

MODE_STANDARD = "standard"   # 10 -> 1, raridade seguinte
MODE_RARE = "rare"           # 5 Covert -> faca/luva
STANDARD_INPUTS = 10
RARE_INPUTS = 5

STEAM_FEE = 0.15

_ST = "StatTrak™ "
_STAR = "★ "
_SOUVENIR = "Souvenir "
_WEAR_SUFFIX_RE = re.compile(
    r"\s*\((" + "|".join(re.escape(w) for w in _WEAR_NAMES) + r")\)\s*$")


# ---------------------------------------------------------------------------
# Nomes de mercado
# ---------------------------------------------------------------------------

def parse_market_name(name: str) -> dict:
    """market_hash_name -> {base, wear, stattrak, souvenir}.

    `base` e' o nome do skin sem wear e sem prefixo de qualidade, no formato
    do catalogo ("AK-47 | Redline", "★ Karambit | Fade").
    """
    s = (name or "").strip()
    wear = None
    m = _WEAR_SUFFIX_RE.search(s)
    if m:
        wear = m.group(1)
        s = s[: m.start()].rstrip()
    star = s.startswith(_STAR)
    if star:
        s = s[len(_STAR):]
    stattrak = s.startswith(_ST)
    if stattrak:
        s = s[len(_ST):]
    souvenir = s.startswith(_SOUVENIR)
    if souvenir:
        s = s[len(_SOUVENIR):]
    base = (_STAR + s) if star else s
    return {"base": base, "wear": wear, "stattrak": stattrak,
            "souvenir": souvenir}


def market_name(base: str, wear: Optional[str] = None,
                stattrak: bool = False) -> str:
    """Monta o market_hash_name. Faca vanilla (sem '|') nao leva wear."""
    if base.startswith(_STAR):
        nome = _STAR + (_ST if stattrak else "") + base[len(_STAR):]
    else:
        nome = (_ST if stattrak else "") + base
    if wear and "|" in base:
        nome += f" ({wear})"
    return nome


def wear_for_float(f: float) -> str:
    for nome, lo, hi in WEAR_BANDS:
        if lo <= f < hi:
            return nome
    return WEAR_BANDS[-1][0]


def default_float(skin: dict, wear: Optional[str]) -> Optional[float]:
    """Ponto medio da faixa do wear recortada pelo range do skin.

    Sem float informado, o contrato precisa de ALGUM float pra calcular o
    wear de saida; o meio da faixa possivel e' a hipotese mais neutra.
    None quando o wear nao existe pra esse skin (ex.: Redline FN).
    """
    smin = float(skin.get("min", 0.0))
    smax = float(skin.get("max", 1.0))
    if wear is None:
        return (smin + smax) / 2.0
    for nome, lo, hi in WEAR_BANDS:
        if nome == wear:
            a, b = max(lo, smin), min(hi, smax)
            if a >= b:
                return None
            return (a + b) / 2.0
    return None


def output_float(norm_avg: float, out_min: float, out_max: float) -> float:
    return out_min + norm_avg * (out_max - out_min)


def _normalized(f: float, smin: float, smax: float) -> float:
    if smax <= smin:
        return 0.0
    return min(1.0, max(0.0, (f - smin) / (smax - smin)))


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------

def _rarity_key(raw: Optional[str]) -> Optional[str]:
    """'rarity_legendary_weapon' / 'rarity_ancient' -> 'legendary'/'ancient'."""
    if not raw:
        return None
    k = str(raw)
    if k.startswith("rarity_"):
        k = k[len("rarity_"):]
    if k.endswith("_weapon"):
        k = k[: -len("_weapon")]
    return k


def build_catalog(skins: list, crates: list,
                  now: Optional[float] = None) -> dict:
    """Monta o catalogo compacto a partir do dataset. Logica pura.

    Fases de Doppler aparecem como entradas separadas no dataset, mas
    compartilham o MESMO market_hash_name -- no catalogo viram um resultado
    so'. O pool raro e' tratado como uniforme por nome de mercado.
    """
    cat_skins: dict = {}
    collections: dict = {}
    for s in skins or []:
        if not isinstance(s, dict):
            continue
        nome = s.get("name")
        if not nome:
            continue
        rar = _rarity_key((s.get("rarity") or {}).get("id"))
        cols = s.get("collections") or []
        col = cols[0].get("name") if cols and isinstance(cols[0], dict) else None
        cat = (s.get("category") or {}).get("id") or ""
        entry = cat_skins.get(nome)
        if entry is None:
            try:
                smin = float(s.get("min_float") if s.get("min_float") is not None else 0.0)
                smax = float(s.get("max_float") if s.get("max_float") is not None else 1.0)
            except (TypeError, ValueError):
                smin, smax = 0.0, 1.0
            entry = {"c": col, "r": rar, "min": smin, "max": smax,
                     "st": bool(s.get("stattrak")),
                     "glove": "gloves" in cat}
            cat_skins[nome] = entry
        if col and rar in RARITIES:
            tiers = collections.setdefault(
                col, {"tiers": {}, "rare": [], "rare_st": []})["tiers"]
            lst = tiers.setdefault(rar, [])
            if nome not in lst:
                lst.append(nome)

    # Pool raro: caixa -> colecao(oes) dos skins que ela contem.
    for cr in crates or []:
        if not isinstance(cr, dict):
            continue
        rares = [r.get("name") for r in (cr.get("contains_rare") or [])
                 if isinstance(r, dict) and r.get("name")]
        if not rares:
            continue
        cols = set()
        for it in cr.get("contains") or []:
            if not isinstance(it, dict):
                continue
            meta = cat_skins.get(it.get("name"))
            if meta and meta.get("c"):
                cols.add(meta["c"])
        for col in cols:
            info = collections.setdefault(
                col, {"tiers": {}, "rare": [], "rare_st": []})
            for nome in rares:
                if nome not in info["rare"]:
                    info["rare"].append(nome)
                meta = cat_skins.get(nome)
                if meta and meta.get("st") and nome not in info["rare_st"]:
                    info["rare_st"].append(nome)

    for info in collections.values():
        for lst in info["tiers"].values():
            lst.sort()
        info["rare"].sort()
        info["rare_st"].sort()

    return {
        "version": CATALOG_VERSION,
        "ts": time.time() if now is None else now,
        "source": "ByMykel/CSGO-API",
        "skins": cat_skins,
        "collections": collections,
    }


def _http_get(url: str) -> "tuple[int, Optional[str]]":
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=90.0) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError):
        return 0, None


def fetch_catalog() -> Optional[dict]:
    """Baixa o dataset e monta o catalogo. None em qualquer falha."""
    dados = []
    for url in (_SKINS_URL, _CRATES_URL):
        code, body = _http_get(url)
        if code != 200 or body is None:
            return None
        try:
            payload = json.loads(body)
        except ValueError:
            return None
        if not isinstance(payload, list):
            return None
        dados.append(payload)
    cat = build_catalog(dados[0], dados[1])
    return cat if cat["skins"] and cat["collections"] else None


def load_catalog(path: "Path | str" = _CATALOG_PATH) -> Optional[dict]:
    """Catalogo em disco (sem olhar TTL). Ilegivel/versao velha -> None.

    E' cache regeneravel: arquivo corrompido vira None e o proximo refresh
    reescreve, sem quarentena.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get("version") != CATALOG_VERSION
            or not isinstance(data.get("skins"), dict)
            or not isinstance(data.get("collections"), dict)):
        return None
    return data


def save_catalog(catalog: dict, path: "Path | str" = _CATALOG_PATH) -> None:
    atomic_write_text(path, json.dumps(catalog, ensure_ascii=False))


CATALOG_CACHED = "cached"
CATALOG_UPDATED = "updated"
CATALOG_STALE = "stale"          # rede falhou, usando o que tinha em disco
CATALOG_UNAVAILABLE = "unavailable"


def refresh_catalog(path: "Path | str" = _CATALOG_PATH, force: bool = False,
                    ttl: float = CATALOG_TTL_S,
                    now: Optional[float] = None) -> "tuple[str, Optional[dict]]":
    """Catalogo pronto pra uso. Rede so' quando expirou (ou `force`).

    Falha de rede com catalogo velho em disco devolve o velho (STALE): o
    pool de uma colecao antiga nao muda, entao dado velho ainda serve.
    """
    agora = time.time() if now is None else now
    atual = load_catalog(path)
    if atual and not force and agora - float(atual.get("ts", 0)) <= ttl:
        return CATALOG_CACHED, atual
    novo = fetch_catalog()
    if novo:
        try:
            save_catalog(novo, path)
        except OSError:
            pass
        return CATALOG_UPDATED, novo
    if atual:
        return CATALOG_STALE, atual
    return CATALOG_UNAVAILABLE, None


def input_suggestions(catalog: Optional[dict]) -> "list[str]":
    """market_hash_names possiveis como input (pro autocomplete da UI).

    So' skins de colecao com wear valido; inclui a versao StatTrak quando o
    skin tem StatTrak.
    """
    out: "list[str]" = []
    if not catalog:
        return out
    for base, meta in catalog.get("skins", {}).items():
        if not meta.get("c") or meta.get("r") not in RARITIES:
            continue
        for wear in _WEAR_NAMES:
            if default_float(meta, wear) is None:
                continue
            out.append(market_name(base, wear))
            if meta.get("st"):
                out.append(market_name(base, wear, stattrak=True))
    out.sort()
    return out


# ---------------------------------------------------------------------------
# Plano do contrato (sem preco)
# ---------------------------------------------------------------------------

def _next_rarity(r: str) -> Optional[str]:
    try:
        i = RARITIES.index(r)
    except ValueError:
        return None
    return RARITIES[i + 1] if i + 1 < len(RARITIES) else None


def _err(plan: dict, msg: str) -> dict:
    plan["errors"].append(msg)
    return plan


def plan_contract(inputs: "list[dict]", catalog: dict) -> dict:
    """Resolve inputs e enumera os resultados possiveis com probabilidade.

    `inputs`: [{name, float?, cost?}] -- um dict por ITEM (repita o dict
    pra quantidade). Devolve {mode, stattrak, inputs, outcomes, errors,
    warnings}. Com `errors` nao vazio o contrato e' invalido e `outcomes`
    vem vazio.
    """
    plan: dict = {"mode": None, "stattrak": False, "inputs": [],
                  "outcomes": [], "errors": [], "warnings": []}
    skins = (catalog or {}).get("skins") or {}
    collections = (catalog or {}).get("collections") or {}
    if not inputs:
        return _err(plan, "Adicione itens ao contrato.")

    resolved = []
    for i, raw in enumerate(inputs, 1):
        nome = str(raw.get("name") or "").strip()
        p = parse_market_name(nome)
        meta = skins.get(p["base"])
        if meta is None:
            return _err(plan, f"Item {i}: '{nome}' não está no catálogo.")
        if not meta.get("c"):
            return _err(plan, f"Item {i}: '{nome}' não pertence a uma coleção "
                              "(faca e luva não entram em contrato).")
        if meta.get("r") not in RARITIES:
            return _err(plan, f"Item {i}: a raridade de '{nome}' não entra "
                              "em contrato.")
        if p["wear"] is None:
            return _err(plan, f"Item {i}: informe o desgaste de '{nome}' "
                              "(ex.: Field-Tested).")
        f = raw.get("float")
        if f is None:
            f = default_float(meta, p["wear"])
            if f is None:
                return _err(plan, f"Item {i}: '{nome}' não existe nesse desgaste.")
            float_assumido = True
        else:
            try:
                f = float(f)
            except (TypeError, ValueError):
                return _err(plan, f"Item {i}: float inválido.")
            if not (meta["min"] <= f <= meta["max"]):
                return _err(plan, f"Item {i}: float {f:.4f} fora do possível "
                                  f"para esse skin ({meta['min']:.2f} a "
                                  f"{meta['max']:.2f}).")
            if wear_for_float(f) != p["wear"]:
                return _err(plan, f"Item {i}: float {f:.4f} não corresponde "
                                  f"a {p['wear']}.")
            float_assumido = False
        resolved.append({
            "name": nome, "base": p["base"], "wear": p["wear"],
            "stattrak": p["stattrak"], "souvenir": p["souvenir"],
            "collection": meta["c"], "rarity": meta["r"],
            "float": f, "float_assumed": float_assumido,
            "norm": _normalized(f, meta["min"], meta["max"]),
            "cost": raw.get("cost"),
        })
    plan["inputs"] = resolved

    rarities = {r["rarity"] for r in resolved}
    if len(rarities) > 1:
        return _err(plan, "Todos os itens precisam ter a mesma raridade.")
    rarity = rarities.pop()
    st_flags = {r["stattrak"] for r in resolved}
    if len(st_flags) > 1:
        return _err(plan, "StatTrak é tudo-ou-nada: não misture com itens "
                          "normais.")
    stattrak = st_flags.pop()
    plan["stattrak"] = stattrak

    n = len(resolved)
    if rarity == "ancient":
        plan["mode"] = MODE_RARE
        if n != RARE_INPUTS:
            return _err(plan, f"Contrato de faca/luva usa {RARE_INPUTS} "
                              f"Covert (tem {n}).")
    else:
        plan["mode"] = MODE_STANDARD
        if n != STANDARD_INPUTS:
            return _err(plan, f"Contrato normal usa {STANDARD_INPUTS} itens "
                              f"(tem {n}).")

    if any(r["souvenir"] for r in resolved):
        plan["warnings"].append(
            "Souvenir entra no contrato, mas o item que sai é sempre "
            "normal.")
    if any(r["float_assumed"] for r in resolved):
        plan["warnings"].append(
            "Float não informado em parte dos itens: usamos o meio da "
            "faixa do desgaste. O desgaste do item que sai pode ser "
            "outro.")

    norm_avg = sum(r["norm"] for r in resolved) / n
    plan["norm_avg"] = norm_avg

    # Peso por colecao = fracao dos inputs que vem dela.
    pesos: dict = {}
    for r in resolved:
        pesos[r["collection"]] = pesos.get(r["collection"], 0) + 1

    alvo = _next_rarity(rarity) if plan["mode"] == MODE_STANDARD else None
    outcomes = []
    for col, qtd in sorted(pesos.items()):
        info = collections.get(col) or {}
        if plan["mode"] == MODE_RARE:
            pool = info.get("rare_st" if stattrak else "rare") or []
            if not pool:
                motivo = ("não tem faca/luva StatTrak (luva não sai de "
                          "StatTrak)"
                          if stattrak and info.get("rare") else
                          "não tem faca/luva (coleção sem caixa)")
                return _err(plan, f"'{col}' {motivo}.")
        else:
            pool = (info.get("tiers") or {}).get(alvo) or []
            if not pool:
                return _err(plan, f"'{col}' não tem itens "
                                  f"{RARITY_LABELS.get(alvo, alvo)}.")
        p_col = qtd / n
        for base in pool:
            meta = skins.get(base) or {"min": 0.0, "max": 1.0}
            if "|" in base:
                f_out = output_float(norm_avg, meta["min"], meta["max"])
                wear = wear_for_float(f_out)
            else:  # faca vanilla: sem float de mercado
                f_out, wear = None, None
            outcomes.append({
                "base": base, "collection": col,
                "prob": p_col / len(pool),
                "float": f_out, "wear": wear,
                "name": market_name(base, wear, stattrak=stattrak),
            })
    plan["outcomes"] = outcomes
    return plan


# ---------------------------------------------------------------------------
# Precificacao
# ---------------------------------------------------------------------------

def price_names(plan: dict) -> "list[str]":
    """Nomes que precisam de preco (inputs sem custo + resultados), sem
    repeticao e agrupados por skin -- a pagina de um wear semeia os outros
    no cache, entao vizinhos viram cache hit."""
    nomes: "list[str]" = []
    for r in plan.get("inputs", []):
        if r.get("cost") is None:
            nomes.append(r["name"])
    for o in plan.get("outcomes", []):
        nomes.append(o["name"])
    vistos: set = set()
    unicos = []
    for nome in nomes:
        if nome not in vistos:
            vistos.add(nome)
            unicos.append(nome)
    return sorted(unicos, key=lambda n: (parse_market_name(n)["base"], n))


def evaluate(plan: dict, price_fn: "Callable[[str], Optional[float]]",
             fee: float = STEAM_FEE) -> dict:
    """Aplica precos ao plano e calcula EV. Logica pura (price_fn injetado).

    Preco de referencia = mediana recente do Steam Market (bruto). Valor do
    resultado = liquido da taxa da Steam (modelo seller_added, como o resto
    do app). Resultado sem preco fica fora do EV e reduz `coverage`.
    """
    res: dict = {"mode": plan.get("mode"), "errors": list(plan.get("errors", [])),
                 "warnings": list(plan.get("warnings", [])),
                 "inputs": [], "outcomes": [], "cost": None,
                 "ev_net": None, "profit": None, "roi": None,
                 "prob_profit": None, "coverage": 0.0,
                 "missing_inputs": 0}
    if res["errors"]:
        return res

    custo = 0.0
    faltando = 0
    for r in plan["inputs"]:
        c = r.get("cost")
        if c is None:
            c = price_fn(r["name"])
        item = dict(r)
        item["cost"] = c
        res["inputs"].append(item)
        if c is None:
            faltando += 1
        else:
            custo += float(c)
    res["missing_inputs"] = faltando

    ev = 0.0
    cobertura = 0.0
    outs = []
    for o in plan["outcomes"]:
        preco = price_fn(o["name"])
        item = dict(o)
        item["price"] = preco
        item["net"] = (fee_calculator.net_proceeds(preco, fee, "seller_added")
                       if preco is not None else None)
        outs.append(item)
        if item["net"] is not None:
            ev += o["prob"] * item["net"]
            cobertura += o["prob"]
    outs.sort(key=lambda x: (-(x["net"] if x["net"] is not None else -1.0),
                             x["name"]))
    res["outcomes"] = outs
    res["coverage"] = cobertura

    if faltando:
        res["warnings"].append(
            f"{faltando} item(ns) do contrato sem preço: informe quanto "
            "pagou.")
        return res
    res["cost"] = custo
    if cobertura <= 0:
        res["warnings"].append("Nenhum resultado possível tem preço no Steam Market.")
        return res
    if cobertura < 0.999:
        res["warnings"].append(
            f"Só achamos preço para {cobertura * 100:.0f}% das chances: "
            "o valor médio está incompleto (o que não tem preço conta "
            "como zero).")
    res["ev_net"] = ev
    res["profit"] = ev - custo
    res["roi"] = (ev - custo) / custo if custo > 0 else None
    res["prob_profit"] = sum(
        o["prob"] for o in outs
        if o["net"] is not None and o["net"] >= custo)
    return res


def reference_price(price_history: "list[dict] | None",
                    days: int = 7) -> Optional[float]:
    """Mediana dos precos diarios dos ultimos `days` dias do historico."""
    if not price_history:
        return None
    from skinvault.signals import recent_prices
    precos = [p for p in recent_prices(price_history, days=days)
              if p is not None and p > 0]
    return float(statistics.median(precos)) if precos else None


class SsrPricer:
    """price_fn com SSR cache + ritmo de rede + corte por bloqueio.

    Cache hit nao custa nada. Cache miss busca a listing page (que semeia
    todas as variantes do skin) e espera RATE_LIMIT_DELAY_S entre buscas.
    Tres buscas seguidas que nao trazem pagina nenhuma = provavel rate
    limit: para de bater na Steam e o resto fica sem preco (EV parcial),
    em vez de prolongar o bloqueio.
    """

    MAX_FALHAS = 3

    def __init__(self, cache=None, days: int = 7,
                 sleep: "Callable[[float], None]" = time.sleep) -> None:
        from skinvault.ssr_cache import PriceHistoryCache
        self.cache = cache if cache is not None else PriceHistoryCache()
        self.days = days
        self._sleep = sleep
        self._memo: dict = {}
        self.fetches = 0
        self._falhas = 0
        self.blocked = False

    def pending(self, names: "list[str]") -> int:
        """Quantas paginas, no maximo, ainda precisam vir da rede."""
        bases = {parse_market_name(n)["base"]
                 for n in names if not self.cache.has(n)}
        return len(bases)

    def __call__(self, name: str) -> Optional[float]:
        if name in self._memo:
            return self._memo[name]
        from skinvault import steam_api
        ph = self.cache.get(name)
        if ph is None and not self.blocked:
            if self.fetches:
                self._sleep(steam_api.RATE_LIMIT_DELAY_S)
            self.fetches += 1
            # Busca direta (e nao ssr_cache.cached_price_history) pra
            # distinguir "pagina nao veio" (falha/rate limit) de "pagina veio
            # mas esse wear nao tem historico" -- so' o primeiro conta falha.
            page = steam_api.get_market_page_data(name)
            if not page:
                self._falhas += 1
                if self._falhas >= self.MAX_FALHAS:
                    self.blocked = True
            else:
                self._falhas = 0
                # So' a serie do nome EXATO. page["price_history"] cai pra
                # match por substring quando o exato nao existe e devolveria
                # a serie de outra variante ("StatTrak(TM) X" contem "X").
                variants = page.get("variants")
                if isinstance(variants, dict):
                    self.cache.put_many(variants)
                    ph = variants.get(name)
        preco = reference_price(ph, self.days)
        self._memo[name] = preco
        return preco
