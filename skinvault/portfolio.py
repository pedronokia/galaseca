"""Portfolio fee-aware -- a verdade do 'quanto paguei / quanto devo vender'.

O pulo do gato e' a taxa de ~15% do Steam. Voce lista por P, mas recebe ~P/1.15.
Logo, 'vale mais do que paguei' NAO e' lucro -- so' e' lucro DEPOIS da taxa. Este
modulo faz essa conta honesta + o preco de break-even.

Persiste local em data/portfolio.json (sem login, sem nuvem). Custo e' entrada
manual: privado e on-brand. Obs: o 'lucro' aqui e' em saldo Steam (a Wallet nao
saca pra conta) -- a ferramenta e' pra quem opera dentro do Steam.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from skinvault._paths import DATA_DIR, atomic_write_text, load_json_record

_DEFAULT_PATH = DATA_DIR / "portfolio.json"

# ~5% Steam + 10% jogo, cobrados sobre o valor que o VENDEDOR recebe.
STEAM_FEE = 0.15


def net_proceeds(price: float, fee_rate: float = STEAM_FEE) -> float:
    """Quanto VOCE recebe ao vender por `price` (liquido da taxa).
    Steam: buyer_price = seller_amount * (1+fee) => seller = price/(1+fee)."""
    return price / (1.0 + fee_rate)


def break_even_price(cost: float, fee_rate: float = STEAM_FEE) -> float:
    """Preco de LISTAGEM necessario pra receber de volta o que custou."""
    return cost * (1.0 + fee_rate)


def max_buy_price(sell_price: float, margin_pct: float = 0.0,
                  fee_rate: float = STEAM_FEE) -> float:
    """Maximo a pagar hoje pra, vendendo por `sell_price`, sobrar a margem.

    Responde a pergunta do Scanner: "vale a pena comprar por quanto?".
    Com margem 0 devolve o preco de indiferenca -- pagar mais que isso da'
    prejuizo mesmo que a venda saia no preco previsto.
    """
    liquido = net_proceeds(sell_price, fee_rate)
    return liquido / (1.0 + margin_pct / 100.0)


def sell_guidance(current_price: float | None,
                  cost: float | None = None,
                  lowest: float | None = None,
                  fee_rate: float = STEAM_FEE) -> dict:
    """Por quanto vender ESTE item, e o que sobra em cada cenario.

    `current_price` e' a referencia de venda (a mediana serve melhor que a
    menor listagem: a menor e' quem esta' com pressa).
    `lowest` e' a menor listagem ativa, pra dar o cenario "vender hoje".
    `cost` None = posicao sem base de custo (veio do sync) -- ai' nao ha'
    lucro a calcular, so' quanto entra no bolso.

    Todos os precos sao de LISTAGEM (o que o comprador paga). O liquido
    ja' desconta a taxa, que na Steam incide sobre o valor do vendedor:
    lista 115 -> recebe 100.
    """
    out = {
        "break_even_list": None,   # preco de listagem pra empatar
        "target_list": None,       # alvo realista (a mediana)
        "net_at_target": None,     # o que entra no bolso vendendo no alvo
        "profit_at_target": None,  # lucro no alvo (None sem custo)
        "fast_list": None,         # vender hoje: cobre a menor listagem
        "net_at_fast": None,
        "clears": None,            # o alvo cobre o custo?
        "gap_pct": None,           # quanto o preco precisa subir pra empatar
    }
    if cost is not None and cost > 0:
        out["break_even_list"] = round(break_even_price(cost, fee_rate), 2)

    if current_price and current_price > 0:
        out["target_list"] = round(current_price, 2)
        liquido = net_proceeds(current_price, fee_rate)
        out["net_at_target"] = round(liquido, 2)
        if cost is not None and cost > 0:
            out["profit_at_target"] = round(liquido - cost, 2)
            out["clears"] = liquido >= cost
            be = out["break_even_list"]
            out["gap_pct"] = round((be / current_price - 1) * 100, 1)

    if lowest and lowest > 0:
        # Pra vender rapido a pratica e' cobrir a menor listagem por 1
        # centavo. Nao ha' magica: o liquido cai junto.
        rapido = max(0.01, round(lowest - 0.01, 2))
        out["fast_list"] = rapido
        out["net_at_fast"] = round(net_proceeds(rapido, fee_rate), 2)
    return out


def position_pnl(cost: float, current_price: float, quantity: int = 1,
                 fee_rate: float = STEAM_FEE) -> dict:
    """Breakdown honesto de UMA posicao. 'market' e' o bruto (o que aparenta
    valer); 'net_if_sold' e' o que voce realmente recebe; 'pnl' e' a verdade."""
    cost_total = cost * quantity
    market = current_price * quantity
    net = net_proceeds(current_price, fee_rate) * quantity
    pnl = net - cost_total
    if pnl > 0.005:
        status = "profit"
    elif pnl < -0.005:
        status = "loss"
    else:
        status = "even"
    return {
        "cost_total": cost_total,
        "market": market,
        "net_if_sold": net,
        "pnl": pnl,
        "pnl_pct": (pnl / cost_total * 100) if cost_total else 0.0,
        "break_even": break_even_price(cost, fee_rate),
        "status": status,
    }


def has_cost_basis(pos: dict) -> bool:
    """True se a posicao tem custo CONHECIDO.

    O sync grava `cost: 0.0` porque a Steam nao diz quanto voce pagou --
    isso e' "desconhecido", nao "custou zero". Tratar os dois igual faz o
    P&L reportar o inventario inteiro como lucro: foi o que aconteceu na
    tela de conta (R$ 850,42 de "lucro" com R$ 0,00 investido).

    Item de drop realmente custou zero, mas ai' e' entrada manual --
    por isso a distincao olha a origem, nao so' o valor.
    """
    cost = pos.get("cost")
    if cost is None:
        return False
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return False
    if cost > 0:
        return True
    return pos.get("source") != "steam_sync"


def evaluate_portfolio(positions: list[dict], price_fn,
                       fee_rate: float = STEAM_FEE) -> dict:
    """positions: [{name, cost, quantity}]. price_fn(name) -> float | None.
    Retorna {rows, totals}. price_fn None -> linha sem preco (item ilustravel).

    P&L so' agrega posicoes com custo conhecido (ver has_cost_basis). Valor
    de mercado e liquido agregam TUDO -- esses nao dependem de custo.
    `totals.unknown_cost` diz quantas ficaram de fora, pra UI poder avisar
    em vez de exibir lucro inventado.

    Dois totais de custo, porque respondem perguntas diferentes:

    - `cost_known` -- tudo que o dono declarou ter pago, tenha o item
      cotacao ou nao. E' o "Total investido" da tela.
    - `cost` -- so' o custo das posicoes que entraram no P&L. Fica de par
      com `pnl`/`pnl_pct`; misturar as duas daria uma porcentagem sobre um
      custo cujo retorno nao foi medido.

    Sao iguais quando toda posicao tem preco, e divergem exatamente quando
    a Steam nao respondeu.
    """
    rows: list[dict] = []
    t_cost = t_market = t_net = 0.0
    t_cost_known = 0.0
    t_net_conhecido = 0.0
    sem_custo = 0
    com_custo = 0
    for pos in positions:
        name = pos["name"]
        conhecido = has_cost_basis(pos)
        cost = float(pos.get("cost") or 0.0)
        qty = int(pos.get("quantity", 1))
        # Ter custo e' fato da POSICAO, nao da cotacao. Contabilizar isso
        # so' no ramo com preco fazia o lote inteiro sem preco (Steam em
        # 429) reportar `unknown_cost: 0` e "Total investido R$ 0,00" pra
        # quem tinha R$ 850,00 declarados -- o mesmo erro de tratar
        # "desconhecido" e "zero" como a mesma coisa, do avesso.
        if conhecido:
            t_cost_known += cost * qty
        else:
            sem_custo += 1
        price = price_fn(name)
        icon = pos.get("icon")
        if price is None:
            rows.append({"name": name, "cost": cost, "quantity": qty,
                         "price": None, "pnl": None,
                         "cost_total": cost * qty,
                         "has_cost": conhecido, "icon": icon})
            continue
        d = position_pnl(cost, price, qty, fee_rate)
        if not conhecido:
            # Sem custo nao ha' lucro nem prejuizo -- ha' valor.
            d["pnl"] = None
            d["pnl_pct"] = None
            d["is_profit"] = False
            d["is_loss"] = False
        rows.append({"name": name, "cost": cost, "quantity": qty,
                     "price": price, "has_cost": conhecido, "icon": icon,
                     **d})
        t_market += d["market"]
        t_net += d["net_if_sold"]
        if conhecido:
            com_custo += 1
            t_cost += d["cost_total"]
            t_net_conhecido += d["net_if_sold"]
    # O gatilho e' EXISTIR posicao com custo conhecido, nao o custo somar
    # mais que zero: drop declarado manualmente custa zero e tem P&L real.
    pnl = (t_net_conhecido - t_cost) if com_custo else None
    totals = {
        "cost": t_cost,
        "cost_known": t_cost_known,
        "market": t_market,
        "net_if_sold": t_net,
        "pnl": pnl,
        "pnl_pct": (pnl / t_cost * 100) if (pnl is not None and t_cost) else None,
        "unknown_cost": sem_custo,
        "known_cost": len(positions) - sem_custo,
        "positions": len(positions),
    }
    return {"rows": rows, "totals": totals}


_PREFIXO_CATEGORIA = (
    ("Sticker |", "Adesivos"),
    ("Sealed Graffiti |", "Grafites"),
    ("Patch |", "Patches"),
    ("Music Kit |", "Music Kits"),
)


def classify_item(name: str) -> str:
    """Categoria do item pelo NOME cru (market_hash_name).

    Descritivo, nao analitico: serve pra dizer onde a carteira esta'
    concentrada. O que nao casa com nenhuma regra vira "Outros" em vez de
    ser empurrado pra uma categoria vizinha -- item novo da Valve aparece
    todo mes, e chutar a categoria dele seria afirmar o que nao se sabe.
    """
    from skinvault import cases

    nome = (name or "").strip()
    if not nome:
        return "Outros"
    # Facas e luvas antes do teste de "|": elas tambem tem barra no nome.
    if nome.startswith("★"):
        return "Facas e luvas"
    for prefixo, categoria in _PREFIXO_CATEGORIA:
        if nome.startswith(prefixo):
            return categoria
    if cases.is_container(nome):
        return "Caixas e cápsulas"
    if "|" in nome:
        return "Skins"
    return "Outros"


def composition(rows: list[dict]) -> list[dict]:
    """Agrupa linhas avaliadas por categoria.

    Conta SEMPRE e soma valor SO' onde ha' preco, em campos separados. Com
    a Steam racionada o valor vem zerado e a contagem continua valendo --
    um total unico faria a carteira inteira parecer vazia.
    """
    grupos: dict = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        cat = classify_item(r.get("name") or "")
        g = grupos.setdefault(
            cat, {"label": cat, "count": 0, "value": 0.0, "priced": 0})
        try:
            qty = int(r.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        g["count"] += qty
        valor = r.get("market")
        if valor is not None:
            g["value"] += valor
            g["priced"] += 1
    out = list(grupos.values())
    out.sort(key=lambda g: (g["value"], g["count"]), reverse=True)
    return out


def containers(rows: list) -> list:
    """Containers da carteira com o estado de drop de cada um.

    Descritivo: "descontinuada" e' fato sobre a OFERTA (parou de entrar em
    drop), nao previsao de preco. Item que o catalogo nao conhece fica de
    fora em vez de ser chutado como ativo -- `cases.case_status` devolve
    `is_discontinued: False` pra desconhecido, e ler esse False como
    "ainda cai" seria afirmar o que nao se sabe.
    """
    from skinvault import cases

    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        nome = r.get("name") or ""
        if not cases.is_container(nome):
            continue
        info = cases.case_status(nome) or {}
        if info.get("status") == "unknown" or not info.get("case"):
            continue
        try:
            qty = int(r.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        out.append({
            "name": nome,
            "qty": qty,
            "year": info.get("year"),
            "discontinued": bool(info.get("is_discontinued")),
        })
    # Descontinuadas primeiro, depois as mais antigas: e' a ordem da tese.
    out.sort(key=lambda c: (not c["discontinued"], c["year"] or 9999))
    return out


# --- persistencia local -------------------------------------------------------
def load_portfolio(path: Path | str = _DEFAULT_PATH) -> list[dict]:
    data = load_json_record(path, [])
    return data if isinstance(data, list) else []


def save_portfolio(positions: list[dict], path: Path | str = _DEFAULT_PATH) -> None:
    p = Path(path)
    try:
        atomic_write_text(p, json.dumps(positions, indent=2))
    except OSError as e:
        print(f"WARNING: failed to save portfolio: {e}", file=sys.stderr)


def add_position(name: str, cost: "float | None", quantity: int = 1,
                 path: Path | str = _DEFAULT_PATH,
                 source: str = "manual") -> list[dict]:
    """Adiciona posicao. source distingue entrada manual de item vindo do
    inventario da Steam -- usado pra preservar cost manual em importacoes.

    `cost=None` = custo NAO informado (o botao "Adicionar item" deixa o
    campo opcional). E' diferente de 0, que numa posicao manual quer dizer
    "foi drop": `has_cost_basis` devolve False pra None e o lucro fica de
    fora ate' o custo ser definido.
    """
    positions = load_portfolio(path)
    positions.append({"name": name,
                      "cost": None if cost is None else float(cost),
                      "quantity": int(quantity), "added_ts": time.time(),
                      "source": source})
    save_portfolio(positions, path)
    return positions


#: Origem das posicoes que vieram do inventario da Steam (custo desconhecido).
#: Mesmo valor da antiga sincronizacao (F10, revertida): toda a logica de
#: "custo nao informado" (has_cost_basis, coluna Origem) ja' o reconhece.
SOURCE_STEAM = "steam_sync"


def merge_steam_inventory(items: list, remove_missing: bool = True,
                          path: Path | str = _DEFAULT_PATH) -> dict:
    """Mescla o inventario publico da Steam na carteira. Devolve um resumo.

    Regras, pensadas pra nunca destruir o que o usuario digitou:
    - item novo entra com custo DESCONHECIDO (Steam nao diz quanto pagou);
    - item que ja' veio da Steam tem quantidade/icone atualizados -- e se o
      usuario definiu custo nele (update_position_cost troca a origem pra
      "manual"), ele passa a ser manual e nao e' mais tocado;
    - posicao manual (quantidade/custo/origem) NUNCA e' alterada nem
      removida, mesmo que o item suma do inventario (o usuario pode
      acompanhar algo fora dele) -- EXCETO o icone: se o nome bater com
      algo no inventario real, o icone preenche do mesmo jeito. Achado
      real: posicao que nasceu de "Colar lista" (CSV, pra contornar rate
      limit) e' manual pra sempre, mesmo sendo o MESMO item que a Steam
      devolve numa importacao de verdade depois -- sem isto a tela ficava
      sem imagem ate' o fim dos tempos pro usuario que um dia usou CSV, so'
      por causa de uma salvacao temporaria num momento de bloqueio;
    - item da Steam que saiu do inventario (vendido/trocado) so' sai da
      carteira com `remove_missing`.

    `items`: saida de steam_api.fetch_inventory -- [{name, quantity, icon,
    type, ...}].
    """
    positions = load_portfolio(path)
    inv = {}
    for it in items or []:
        nome = it.get("name") if isinstance(it, dict) else None
        if nome:
            inv[nome] = it

    nomes_manuais = {p.get("name") for p in positions
                     if p.get("source") != SOURCE_STEAM}
    vistos: set = set()
    saida: list[dict] = []
    atualizados = removidos = 0
    for p in positions:
        nome = p.get("name")
        if p.get("source") != SOURCE_STEAM:
            it = inv.get(nome)
            if it:
                if it.get("icon"):
                    p["icon"] = it["icon"]
                if it.get("type"):
                    p["type"] = it["type"]
            saida.append(p)
            continue
        if nome in inv and nome not in nomes_manuais:
            if nome in vistos:
                removidos += 1  # posicao da Steam duplicada: funde na 1a
                continue
            it = inv[nome]
            p["quantity"] = int(it.get("quantity") or 1)
            if it.get("icon"):
                p["icon"] = it["icon"]
            if it.get("type"):
                p["type"] = it["type"]
            vistos.add(nome)
            atualizados += 1
            saida.append(p)
        elif nome in inv:
            # Ainda no inventario, mas o usuario acompanha esse item numa
            # posicao manual: a da Steam e' duplicata. Sai sem contar como
            # "removido" -- o item nao saiu do inventario.
            continue
        elif remove_missing:
            removidos += 1
        else:
            saida.append(p)

    agora = time.time()
    adicionados = 0
    for nome, it in inv.items():
        if nome in vistos or nome in nomes_manuais:
            continue
        nova = {"name": nome, "cost": 0.0,
                "quantity": int(it.get("quantity") or 1),
                "added_ts": agora, "source": SOURCE_STEAM}
        if it.get("icon"):
            nova["icon"] = it["icon"]
        if it.get("type"):
            nova["type"] = it["type"]
        saida.append(nova)
        adicionados += 1

    save_portfolio(saida, path)
    return {
        "adicionados": adicionados,
        "atualizados": atualizados,
        "removidos": removidos,
        "manuais_mantidos": len(nomes_manuais & set(inv)),
        "itens_no_inventario": len(inv),
    }


def update_position_cost(name: str, cost: float,
                         path: Path | str = _DEFAULT_PATH):
    """Define o custo de uma posicao existente (entrada pela UI).

    Troca `source` pra "manual" de proposito: `has_cost_basis` trata
    posicao de sync com cost 0.0 como "custo desconhecido", e quem
    declara custo zero pelo dialogo esta' dizendo que SABE que o item
    nao custou nada (ex.: drop) -- a distincao e' origem, nao valor.
    Devolve a lista de positions, ou None se o nome nao existe.
    """
    positions = load_portfolio(path)
    alvo = [p for p in positions if p.get("name") == name]
    if not alvo:
        return None
    for p in alvo:
        p["cost"] = round(float(cost), 2)
        p["source"] = "manual"
    save_portfolio(positions, path)
    return positions


def remove_position(name: str, path: Path | str = _DEFAULT_PATH) -> bool:
    """Remove a(s) posicao(oes) com esse nome -- manual, CSV ou sincronizada
    da Steam, sem distincao: o usuario pode tirar um item indesejado direto
    da tela sem precisar reimportar/ressincronizar o inventario inteiro so'
    pra isso. Devolve False se o nome nao existia (nada foi salvo).
    """
    positions = load_portfolio(path)
    restantes = [p for p in positions if p.get("name") != name]
    if len(restantes) == len(positions):
        return False
    save_portfolio(restantes, path)
    return True


def simulate_trade(buy_price: float, sell_price: float, quantity: int = 1,
                   fee_rate: float = STEAM_FEE) -> dict:
    """Simula uma transacao buy->sell e retorna breakdown completo pra UI.

    Diferente de position_pnl, foca em campos legiveis pelo simulador:
    cost_total, gross_sale, steam_fee, net_received, pnl, roi_pct,
    break_even_price (preco minimo de listagem pra empatar).
    """
    cost_total = buy_price * quantity
    gross_sale = sell_price * quantity
    net = net_proceeds(sell_price, fee_rate) * quantity
    fee = gross_sale - net
    pnl = net - cost_total
    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "quantity": quantity,
        "cost_total": round(cost_total, 2),
        "gross_sale": round(gross_sale, 2),
        "steam_fee": round(fee, 2),
        "net_received": round(net, 2),
        "pnl": round(pnl, 2),
        "roi_pct": round((pnl / cost_total * 100) if cost_total else 0.0, 2),
        "break_even_price": round(break_even_price(buy_price, fee_rate), 2),
        "is_profit": pnl > 0.005,
        "is_loss": pnl < -0.005,
    }


def _parse_brl(raw: str) -> float:
    """Converte string de custo para float, aceitando formatos BR e US.

    "200"       -> 200.0
    "650.50"    -> 650.5
    "R$ 200"    -> 200.0
    "R$ 1.234,50" -> 1234.5
    "1.234,50"  -> 1234.5
    "1234,50"   -> 1234.5
    """
    s = raw.replace("R$", "").strip()
    if "," in s and "." in s:
        # Formato BR: "1.234,50" -> remove pontos, troca virgula por ponto
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def import_csv(text: str, path: Path | str = _DEFAULT_PATH) -> dict:
    """Importa linhas CSV: nome, custo, qtd (opcional).

    Formatos aceitos:
      AK-47 | Redline (Field-Tested), 200, 1
      AWP | Asiimov (FT), 650.50
      MAC-10 | Candy Apple (FN), , 1   -- custo em branco = desconhecido

    Campo de custo vazio vira cost=None (desconhecido -- mesma semantica
    de "+ Adicionar item", que ja aceita isso). Achado real: "0" era o
    placeholder sugerido pra quem nao sabe o preco, mas cost=0 numa
    posicao MANUAL declara "foi drop" (ver add_position) -- a tela
    mostrava "R$ 0,00" pra 22 itens que custaram aquilo, nao zero.
    Linhas com # sao ignoradas. Cost pode vir com R$.
    Retorna {imported, skipped, errors}."""
    imported = 0
    skipped = 0
    errors: list[str] = []
    for i, raw in enumerate(text.strip().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            skipped += 1
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            errors.append(f"Linha {i}: formato invalido (precisa de nome, custo) — '{line}'")
            continue
        name = parts[0]
        # Se tem mais de 3 partes, o custo BR tem virgula decimal
        # ex: "AK-47, R$ 1.234,50, 1" -> parts = [AK-47, R$ 1.234, 50, 1]
        if len(parts) > 3:
            cost_raw = ",".join(parts[1:-1])
            qty_raw = parts[-1]
        else:
            cost_raw = parts[1]
            qty_raw = parts[2] if len(parts) >= 3 and parts[2] else ""
        if not cost_raw:
            cost = None
        else:
            try:
                cost = _parse_brl(cost_raw)
            except ValueError:
                errors.append(f"Linha {i}: custo invalido '{cost_raw}' — '{line}'")
                continue
        try:
            qty = int(qty_raw) if qty_raw else 1
        except ValueError:
            errors.append(f"Linha {i}: quantidade invalida '{qty_raw}' — '{line}'")
            continue
        add_position(name, cost, max(qty, 1), path)
        imported += 1
    return {"imported": imported, "skipped": skipped, "errors": errors}


def update_costs_bulk(costs: dict, path: Path | str = _DEFAULT_PATH) -> dict:
    """Define o custo (unitario) de varias posicoes de uma vez.

    `costs`: {nome: custo}. Mesma semantica de `update_position_cost`
    (source vira "manual", custo 0 = drop), mas le e grava o arquivo UMA
    vez -- chamar a funcao unitaria em laco regravava o portfolio inteiro
    por item. Nome que nao existe no portfolio NAO cria posicao: quem
    importa uma planilha antiga nao quer itens fantasmas na carteira.
    Retorna {atualizados: [nomes], nao_encontrados: [nomes]}.
    """
    positions = load_portfolio(path)
    por_nome: dict = {}
    for p in positions:
        por_nome.setdefault(p.get("name") or "", []).append(p)
    atualizados, faltando = [], []
    for nome, custo in costs.items():
        alvo = por_nome.get(nome)
        if not alvo:
            faltando.append(nome)
            continue
        for p in alvo:
            p["cost"] = round(float(custo), 2)
            p["source"] = "manual"
        atualizados.append(nome)
    if atualizados:
        save_portfolio(positions, path)
    return {"atualizados": atualizados, "nao_encontrados": faltando}


_CSV_COLS_NOME = ("item", "nome", "name")
_CSV_COLS_CUSTO = ("custo", "cost", "custo unitario", "custo unitário")


def parse_cost_csv(text: str) -> dict:
    """Le uma planilha de custos: {custos: {nome: custo}, erros: [str]}.

    Aceita o proprio CSV exportado pelo Inventario (";" com colunas Item e
    Custo -- exportar, preencher o Custo no Excel e importar de volta) ou
    uma lista simples "nome;custo" sem cabecalho. Separador: ";" se a
    primeira linha tiver, senao tab, senao ",". Custo vazio = "nao
    informado" e a linha e' ignorada em silencio (a exportacao sai assim
    para todo item sem custo); custo invalido ou negativo vira erro.
    """
    import csv
    import io

    linhas = [ln for ln in (text or "").lstrip("﻿").splitlines()
              if ln.strip() and not ln.lstrip().startswith("#")]
    if not linhas:
        return {"custos": {}, "erros": ["Arquivo vazio."]}
    primeira = linhas[0]
    sep = ";" if ";" in primeira else ("\t" if "\t" in primeira else ",")
    reader = list(csv.reader(io.StringIO("\n".join(linhas)), delimiter=sep))
    cab = [c.strip().lower() for c in reader[0]]
    i_nome = next((i for i, c in enumerate(cab) if c in _CSV_COLS_NOME), None)
    i_custo = next((i for i, c in enumerate(cab) if c in _CSV_COLS_CUSTO),
                   None)
    if i_nome is not None and i_custo is not None:
        corpo, base = reader[1:], 2
    elif i_nome is not None or i_custo is not None:
        return {"custos": {}, "erros": [
            "Cabeçalho sem as colunas Item e Custo."]}
    else:
        corpo, base, i_nome, i_custo = reader, 1, 0, 1
    custos: dict = {}
    erros: list = []
    for n, cols in enumerate(corpo, start=base):
        if len(cols) <= max(i_nome, i_custo):
            erros.append(f"Linha {n}: faltam colunas.")
            continue
        nome = cols[i_nome].strip()
        bruto = cols[i_custo].strip()
        if not nome or not bruto or bruto in ("—", "-"):
            continue
        try:
            custo = _parse_brl(bruto)
        except ValueError:
            erros.append(f"Linha {n}: custo inválido “{bruto}”.")
            continue
        if custo < 0:
            erros.append(f"Linha {n}: custo negativo “{bruto}”.")
            continue
        custos[nome] = custo
    return {"custos": custos, "erros": erros}
