"""Regressão visual do site público -- captura as telas principais e
compara com as imagens-base em `tests/visual/baseline/`.

O problema que este script resolve: o site renderiza "tempo relativo"
("há 1 h", "em ~5 h"), contador de visitas e gráficos a partir de dados
que mudam a cada ciclo do worker. Uma comparação pixel a pixel só é
estável se TODOS os insumos forem fixos. Então o script:

1. Semeia um `GALASECA_DATA_DIR` temporário com um dataset escrito à mão
   (scanner_last.json, rankings.json com 3 snapshots, item_history.json,
   visitas.json) e ícones de fixture copiados de `tests/visual/fixtures/`
   (nenhum byte vem da rede);
2. Congela o relógio por patch de módulo: `server.time` vira um shim que
   devolve `AGORA_FIXO`, `scan_store.idade_txt`/`proxima_txt` chamam o
   original com `now=` fixo, `visits.dia_local` devolve `DIA_FIXO` e
   `visits.registrar` vira no-op (o contador não se move entre capturas);
   `server._build_id` devolve None (rodapé e `?v=` estáveis).
   Nenhum item semeado tem `case_retired_at` -- essa data passa por
   `date.today()` em `_tempo_desde_aposentadoria` e variaria com o dia.
3. Sobe o Flask em thread própria (`werkzeug.make_server` na porta 0) e
   captura com Playwright: 3 páginas x 2 viewports (1280x900 e 390x844),
   contexto novo por captura (sem cookies/localStorage de uma captura
   anterior), `reduced_motion=reduce`, `device_scale_factor=1` e rota
   Playwright que ABORTA qualquer request fora do localhost -- se a
   página pedir algo externo, a captura falha alto e claro.
4. Compara contra a base com tolerância por pixel (antialiasing de fonte
   varia entre rodadas do runner) e grava diff ampliado + relatório
   em `tests/visual/diff/`.

Modos:
    python tests/visual/visual_regression.py            # compara
    python tests/visual/visual_regression.py --atualizar  # regera a base

As imagens-base SÓ valem renderizadas no Linux do CI (ubuntu-latest):
no Windows a pilha de fontes é outra e cada PNG diverge. Por isso o modo
de comparação NUNCA grava em `baseline/` -- quem regenera a base é o
modo `--atualizar`, rodado via workflow_dispatch (input
`atualizar_baselines` de .github/workflows/tests.yml), e os PNGs saem no
artefato `visual-baselines` pra serem baixados e commitados.
"""
from __future__ import annotations

import argparse
import functools
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
# Rodar como "python tests/visual/visual_regression.py" não coloca a raiz
# do repo no sys.path -- e o script só é útil com o pacote galaseca
# importável de lá.
sys.path.insert(0, str(RAIZ))
_PASTA = Path(__file__).resolve().parent
PASTA_FIXTURES = _PASTA / "fixtures"
PASTA_BASE = _PASTA / "baseline"
PASTA_CAPTURAS = _PASTA / "current"
PASTA_DIFF = _PASTA / "diff"

# Epoch fixo. Todo "há X" do site sai dele: o scan fica 1 h atrás, a
# última coleta de preço 1 h atrás e o snapshot "atual" do ranking
# 15 min atrás.
AGORA_FIXO = 1_799_000_000.0
# Dia do contador de visitas (visits.dia_local é substituído por este
# valor; visitas.json semeia exatamente esta chave).
DIA_FIXO = "2027-01-04"

TOLERANCIA_PADRAO = 16       # por canal, 0-255
FRACAO_MAX_PADRAO = 0.005    # 0,5% dos pixels acima da tolerância

_ITEM_HERO = "★ Karambit | Fade (Factory New)"

# Hashes de ícone de fixture (passam no _sanitizar de icon_cache.py:
# só letras, dígitos, "-" e "_").
ICONE_A = "fixa-galaseca"
ICONE_B = "fixb-galaseca"


# --------------------------------------------------------------- semente

def _item(nome, categoria, nota, preco, cor, raridade, motivo, tendencia,
          icone=ICONE_A, case_label=None, risco="low", confianca="high",
          quality_id=None):
    """Monta um item no formato que `ScannerScreen._scan_item` grava.

    `motivo` é a lista de (texto, delta) do breakdown -- a soma dos
    deltas TEM que ser `nota - 50` (base 50 de signals.raw_score), senão
    `nota_margem` aparece na tela e a captura carrega um selo a mais.
    """
    alvo = nota - 50
    soma = sum(d for _t, d in motivo)
    if soma != alvo:
        raise ValueError(
            f"{nome}: soma dos deltas ({soma}) != nota - 50 ({alvo})")
    return {
        "name": nome,
        "score": nota,
        "price": preco,
        "category": categoria,
        "case_label": case_label,
        "case": None,
        "pump_risk": {"level": risco, "reasons": []},
        "breakdown": [{"label": t, "delta": d} for t, d in motivo],
        "icon": icone,
        "name_color": cor,
        "rarity_id": raridade,
        "quality_id": quality_id,
        "data_quality": {
            "confidence": 0.95 if confianca == "high" else 0.10,
            "n": 20,
            "age_days": 1.0,
            "level": confianca,
            "label": "Confiança fixa do dataset visual",
        },
        "liquidity_depth": {
            "days": 3.2, "avg_volume": 412.0, "supply": 1320,
            "band": "liquido",
            "label": "~3d de listagens no ritmo atual (412/dia)",
        },
    }


def _dataset_itens():
    """Os 12 itens do dataset. Espalhados por categoria, nota, cor de
    raridade, tendência e selos (risco médio, dado limitado, caixa
    descontinuada, item sem motivo) pra cada estado da UI existir
    pelo menos uma vez em alguma captura."""
    return [
        _item("★ Karambit | Fade (Factory New)", "Facas", 92, 1899.00,
              "eb4b4b", "Rarity_Ancient_Weapon",
              [("Preço no maior nível de 6 meses (+18)", 18),
               ("Volume 2,1x a média (+15)", 15),
               ("Vendas frequentes (+9)", 9)],
              None, icone=ICONE_B, quality_id="unusual"),
        _item("AK-47 | Redline (Field-Tested)", "Rifles", 87, 43.50,
              "4b69ff", "Rarity_Rare_Weapon",
              [("Preço 22% abaixo do típico (+26)", 26),
               ("Volume 2,3x a média (+7)", 7),
               ("Vendas frequentes (+4)", 4)],
              "alta", case_label="Kilowatt Case"),
        _item("AWP | Asiimov (Field-Tested)", "Rifles", 78, 118.90,
              "eb4b4b", "Rarity_Ancient_Weapon",
              [("Preço 12% abaixo do típico (+18)", 18),
               ("Oferta estável (+10)", 10)],
              "baixa", case_label="Chroma 2 Case"),
        _item("AK-47 | Bloodsport (Field-Tested)", "Rifles", 74, 55.20,
              "d32ce6", "Rarity_Legendary_Weapon",
              [("Preço 9% abaixo do típico (+16)", 16),
               ("Vendas frequentes (+8)", 8)],
              "alta", case_label="Chroma 3 Case"),
        _item("M4A4 | Howl (Field-Tested)", "Rifles", 71, 1350.00,
              "eb4b4b", "Rarity_Contraband",
              [("Caixa fora do drop pool (+21)", 21)],
              None),
        _item("★ Butterfly Knife | Slaughter (Minimal Wear)", "Facas",
              66, 950.00, "8847ff", "Rarity_Mythical_Weapon",
              [("Preço estável há 30 dias (+9)", 9),
               ("Vendas frequentes (+7)", 7)],
              None, icone=ICONE_B),
        _item("USP-S | Neo-Noir (Factory New)", "Pistolas", 63, 26.00,
              "8847ff", "Rarity_Mythical_Weapon",
              [("Preço 6% abaixo do típico (+13)", 13)],
              "alta", case_label="Chroma 3 Case"),
        _item("Desert Eagle | Blaze (Factory New)", "Pistolas", 61, 520.00,
              "8847ff", "Rarity_Mythical_Weapon",
              [("Preço 4% abaixo do típico (+11)", 11)],
              "baixa"),
        _item("Glock-18 | Water Elemental (Minimal Wear)", "Pistolas",
              58, 12.40, "4b69ff", "Rarity_Rare_Weapon",
              [("Caixa fora do drop pool (+8)", 8)],
              None,
              case_label="Operation Phoenix Weapon Case (descontinuada, 2014)"),
        _item("Clutch Case", "Caixas", 55, 0.62, "b0c3d9",
              "Rarity_Rare_Weapon",
              [("Volume 1,4x a média (+5)", 5)],
              None, case_label="Clutch Case", risco="medium"),
        _item("Kilowatt Case", "Caixas", 49, 2.31, "b0c3d9",
              "Rarity_Rare_Weapon",
              [("Preço 2% acima do típico (-1)", -1)],
              None, case_label="Kilowatt Case"),
        _item("MP9 | Rose Iron (Factory New)", "SMGs", 44, 4.90,
              "5e98d9", "Rarity_Uncommon_Weapon",
              [("Preço 9% acima do típico (-6)", -6)],
              None),
    ]


def _serie_historica(preco_base, tendencia):
    """20 pontos de preço (~1 por hora) terminando `AGORA_FIXO - 3600`.

    Onda senoidal determinística; os 2 últimos pontos recebem a direção
    pedida (a variação exibida na tabela é entre exatamente esses dois).
    """
    pontos = []
    for i in range(20):
        fator = 1.0 + 0.05 * math.sin(i * 0.6)
        pontos.append({
            "ts": AGORA_FIXO - (20 - i) * 3600,
            "price": round(preco_base * fator, 2),
        })
    if tendencia == "alta":
        pontos[-2]["price"] = round(preco_base * 0.97, 2)
        pontos[-1]["price"] = round(preco_base * 1.04, 2)
    elif tendencia == "baixa":
        pontos[-2]["price"] = round(preco_base * 1.03, 2)
        pontos[-1]["price"] = round(preco_base * 0.96, 2)
    else:
        pontos[-2]["price"] = round(preco_base * 1.01, 2)
        pontos[-1]["price"] = round(preco_base * 1.01, 2)
    return pontos


def _snapshot(ts, itens):
    """Snapshot de rankings.json: [{name, score, position}] na ordem."""
    return {
        "ts": ts,
        "items": [
            {"name": n, "score": s, "position": i + 1}
            for i, (n, s) in enumerate(itens)
        ],
    }


def _semear(data_dir: Path) -> None:
    """Escreve todos os arquivos de dado do dataset em `data_dir`."""
    data_dir.mkdir(parents=True, exist_ok=True)

    itens = _dataset_itens()
    scanner = {
        "ts": AGORA_FIXO - 3600,          # "Dados coletados ... há 1 h"
        "category": "Rifles",
        "results": itens,
    }
    (data_dir / "scanner_last.json").write_text(
        json.dumps(scanner, ensure_ascii=False), encoding="utf-8")

    # Histórico por item (item_history.json: {name: [{ts, price}]}).
    historico = {
        it["name"]: _serie_historica(it["price"], tend)
        for it, tend in zip(itens, [
            None, "alta", "baixa", "alta", None,
            None, "alta", "baixa", None, None, None, None,
        ])
    }
    (data_dir / "item_history.json").write_text(
        json.dumps(historico, ensure_ascii=False), encoding="utf-8")

    # 3 snapshots do ranking: -3 dias, -2 dias (vira previous_snapshot) e
    # o atual. O resumo "o que mudou hoje" usa latest_before(ts - 20h) ->
    # cai no de -2 dias. Sem "USP-S | Neo-Noir" e "MP9 | Rose Iron" no
    # antigo: vira 2 "NOVO" no Top 20 e variados subiu/caiu.
    ordem_atual = sorted(((it["name"], it["score"]) for it in itens),
                         key=lambda p: -p[1])
    snaps = [
        _snapshot(AGORA_FIXO - 3 * 86400 - 900, [
            ("★ Karambit | Fade (Factory New)", 90),
            ("AK-47 | Redline (Field-Tested)", 84),
            ("AWP | Asiimov (Field-Tested)", 79),
            ("AK-47 | Bloodsport (Field-Tested)", 72),
            ("M4A4 | Howl (Field-Tested)", 70),
            ("★ Butterfly Knife | Slaughter (Minimal Wear)", 64),
            ("Desert Eagle | Blaze (Factory New)", 60),
        ]),
        _snapshot(AGORA_FIXO - 2 * 86400 - 900, [
            ("★ Karambit | Fade (Factory New)", 92),
            ("AK-47 | Bloodsport (Field-Tested)", 76),
            ("AWP | Asiimov (Field-Tested)", 80),
            ("M4A4 | Howl (Field-Tested)", 71),
            ("Desert Eagle | Blaze (Factory New)", 62),
            ("Glock-18 | Water Elemental (Minimal Wear)", 57),
            ("Clutch Case", 58),
            ("Kilowatt Case", 47),
            ("★ Butterfly Knife | Slaughter (Minimal Wear)", 62),
            ("AK-47 | Redline (Field-Tested)", 85),
        ]),
        _snapshot(AGORA_FIXO - 900, ordem_atual),  # "Atualizado há 15 min"
    ]
    (data_dir / "rankings.json").write_text(
        json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8")

    # Contador de visitas: total e dia fixos -- o rodapé mostra
    # "Hoje: 7 acessos · Total: 1234 acessos" em toda captura.
    visitas = {"total": 1234, "por_dia": {DIA_FIXO: 7}}
    (data_dir / "visitas.json").write_text(
        json.dumps(visitas), encoding="utf-8")

    # Ícones de fixture -> DATA_DIR/icon_cache/<hash>.v3.<tam>.webp,
    # o caminho que icon_cache.obter() serve sem tocar na rede.
    cache_dir = data_dir / "icon_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for hash_icone in (ICONE_A, ICONE_B):
        for tamanho in (192, 384):
            origem = PASTA_FIXTURES / f"{hash_icone}-{tamanho}.webp"
            shutil.copyfile(
                origem, cache_dir / f"{hash_icone}.v3.{tamanho}.webp")


# ---------------------------------------------------------- determinismo

def _congelar_relogio():
    """Patches de módulo pro site renderizar sempre a mesma coisa."""
    import galaseca.public_site.server as server
    import galaseca.scan_store as scan_store
    import galaseca.public_site.visits as visits

    class _TempoFixo:
        """Substituto do módulo `time` dentro de server.py -- cobre o
        banner de scan desatualizado, o recorte por período do gráfico,
        a latência e /api/health."""

        @staticmethod
        def time():
            return AGORA_FIXO

    server.time = _TempoFixo
    server._build_id = lambda: None

    _idade_txt_real = scan_store.idade_txt
    scan_store.idade_txt = functools.partial(_idade_txt_real, now=AGORA_FIXO)
    _proxima_txt_real = scan_store.proxima_txt
    scan_store.proxima_txt = functools.partial(
        _proxima_txt_real, now=AGORA_FIXO)

    visits.dia_local = lambda ts=None: DIA_FIXO
    visits.registrar = lambda *args, **kwargs: 0


def _subir_servidor():
    """Flask em thread (porta aleatória); devolve (servidor, porta)."""
    from werkzeug.serving import make_server

    import galaseca.public_site.server as server

    app = server.create_app()
    servidor = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(
        target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor, servidor.server_port


# --------------------------------------------------------------- captura

# (nome do PNG, caminho da URL, largura, altura)
CAPTURAS = [
    ("home-desktop", "/", 1280, 900),
    ("ranking-desktop", "/ranking", 1280, 900),
    ("item-desktop", "/item/" + urllib.parse.quote(_ITEM_HERO, safe=""),
     1280, 900),
    ("home-celular", "/", 390, 844),
    ("ranking-celular", "/ranking", 390, 844),
    ("item-celular", "/item/" + urllib.parse.quote(_ITEM_HERO, safe=""),
     390, 844),
]


def _capturar(porta: int, destino: Path) -> None:
    """Captura as 6 telas com Playwright, um contexto novo por captura."""
    from playwright.sync_api import sync_playwright

    hosts_locais = ("127.0.0.1", "localhost")

    def _segurar_rede(route):
        host = urllib.parse.urlparse(route.request.url).hostname
        if host in hosts_locais:
            route.continue_()
        else:
            # Qualquer request externo (fonte, CDN, o que for) aborta --
            # o dataset promete página 100% local.
            route.abort()

    destino.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        try:
            for nome, caminho, largura, altura in CAPTURAS:
                contexto = navegador.new_context(
                    viewport={"width": largura, "height": altura},
                    device_scale_factor=1,
                    locale="pt-BR",
                    timezone_id="America/Sao_Paulo",
                    reduced_motion="reduce",
                )
                contexto.route("**/*", _segurar_rede)
                pagina = contexto.new_page()
                url = f"http://127.0.0.1:{porta}{caminho}"
                pagina.goto(url, wait_until="networkidle", timeout=30000)
                pagina.wait_for_timeout(300)
                pagina.screenshot(path=str(destino / f"{nome}.png"))
                contexto.close()
        finally:
            navegador.close()


# ------------------------------------------------------------ comparação

def _comparar_um(atual: Path, base: Path, tolerancia: int, fracao_max: float,
                 saida_diff: Path) -> dict:
    """Compara uma captura com a base. Devolve o resultado em dict e
    grava um diff ampliado (12x) pra inspeção."""
    from PIL import Image, ImageChops

    imagem_atual = Image.open(atual).convert("RGB")
    imagem_base = Image.open(base).convert("RGB")
    if imagem_atual.size != imagem_base.size:
        return {
            "status": "tamanho",
            "detalhe": f"captura {imagem_atual.size} x base {imagem_base.size}",
        }
    diff = ImageChops.difference(imagem_atual, imagem_base)
    if diff.getbbox() is None:
        return {"status": "ok", "fracao": 0.0, "limite": fracao_max}
    r, g, b = diff.split()
    maximo_canal = ImageChops.lighter(ImageChops.lighter(r, g), b)
    histograma = maximo_canal.histogram()
    total = imagem_atual.size[0] * imagem_atual.size[1]
    mudados = sum(histograma[tolerancia + 1:])
    fracao = mudados / total
    ampliado = maximo_canal.point(lambda v: min(255, v * 12))
    ampliado.save(saida_diff)
    return {
        "status": "ok" if fracao <= fracao_max else "diferente",
        "fracao": fracao,
        "limite": fracao_max,
        "pixels_mudados": mudados,
    }


def _rodar_comparacao(tolerancia: int, fracao_max: float) -> int:
    """Modo padrão: compara `current/` com `baseline/`. Falha (exit 1)
    quando uma captura diverge além da tolerância; base ausente não
    falha -- só avisa (a base se gera no CI Linux, com --atualizar)."""
    resultados = []
    falhas = 0
    sem_base = 0
    for nome, _caminho, _largura, _altura in CAPTURAS:
        atual = PASTA_CAPTURAS / f"{nome}.png"
        base = PASTA_BASE / f"{nome}.png"
        resultado = {"nome": nome}
        if not base.exists():
            resultado["status"] = "sem-base"
            sem_base += 1
            print(f"AVISO: sem base para {nome} -- gere com --atualizar "
                  "no CI (Linux) e commite os PNGs.")
        else:
            resultado.update(_comparar_um(
                atual, base, tolerancia, fracao_max,
                PASTA_DIFF / f"{nome}-diff.png"))
            if resultado["status"] == "diferente":
                falhas += 1
                print(f"DIFERENTE: {nome} -- "
                      f"{resultado['fracao']:.3%} dos pixels mudaram "
                      f"(limite {fracao_max:.3%}). "
                      f"Diff ampliado: {PASTA_DIFF / (nome + '-diff.png')}")
            elif resultado["status"] == "tamanho":
                falhas += 1
                print(f"TAMANHO DIFERENTE: {nome} -- {resultado['detalhe']}")
            else:
                print(f"OK: {nome}")
        resultados.append(resultado)

    PASTA_DIFF.mkdir(parents=True, exist_ok=True)
    (PASTA_DIFF / "relatorio.json").write_text(
        json.dumps({
            "tolerancia": tolerancia,
            "fracao_max": fracao_max,
            "falhas": falhas,
            "sem_base": sem_base,
            "resultados": resultados,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    if sem_base:
        print(f"\n{sem_base} captura(s) sem imagem-base -- compare "
              "manualmente e gere a base no CI (--atualizar).")
    if falhas:
        print(f"\nFALHOU: {falhas} tela(s) mudaram além da tolerância.")
        return 1
    print("\nVisual estável: nenhuma mudança além da tolerância.")
    return 0


def _rodar_atualizacao(tolerancia: int, fracao_max: float) -> int:
    """Modo --atualizar: a captura nova VIRA a base. Só pra CI Linux
    (via workflow_dispatch) -- no Windows a fonte é outra e a base
    ficaria com pixels que o CI nunca reproduz."""
    PASTA_BASE.mkdir(parents=True, exist_ok=True)
    for nome, _caminho, _largura, _altura in CAPTURAS:
        shutil.copyfile(
            PASTA_CAPTURAS / f"{nome}.png", PASTA_BASE / f"{nome}.png")
    print(f"Bases regeradas em {PASTA_BASE} "
          f"(tolerância {tolerancia}, fração {fracao_max:.3%}). "
          "Baixe o artefato visual-baselines e commite os PNGs.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regressão visual do site público (captura + compara).")
    parser.add_argument("--atualizar", action="store_true",
                        help="regera as imagens-base a partir das capturas")
    parser.add_argument("--tolerancia", type=int, default=TOLERANCIA_PADRAO,
                        help="diff máximo por canal (0-255)")
    parser.add_argument("--fracao-max", type=float,
                        default=FRACAO_MAX_PADRAO,
                        help="fração máxima de pixels mudados (0-1)")
    args = parser.parse_args()

    if args.tolerancia < 0 or not 0 <= args.fracao_max <= 1:
        parser.error("tolerancia/fracao-max fora da faixa")

    if not (PASTA_FIXTURES / f"{ICONE_A}-192.webp").exists():
        print("Faltam os ícones de fixture em tests/visual/fixtures/ -- "
              "são comitados junto com o script.")
        return 2

    # O dataset precisa existir ANTES do primeiro import de galaseca
    # (os módulos resolvem DATA_DIR a partir da env var no import).
    temp = Path(tempfile.mkdtemp(prefix="galaseca-visual-"))
    try:
        _semear(temp)
        os.environ["GALASECA_DATA_DIR"] = str(temp)
        os.environ.pop("SKINVAULT_DATA_DIR", None)  # fallback nunca vaza

        _congelar_relogio()
        servidor, porta = _subir_servidor()
        try:
            _capturar(porta, PASTA_CAPTURAS)
        finally:
            servidor.shutdown()
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    if args.atualizar:
        return _rodar_atualizacao(args.tolerancia, args.fracao_max)
    return _rodar_comparacao(args.tolerancia, args.fracao_max)


if __name__ == "__main__":
    sys.exit(main())
