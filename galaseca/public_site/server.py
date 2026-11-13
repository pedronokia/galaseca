"""Fábrica Flask do site público.

Serve só o que `worker.py` (processo separado) já escreveu em
`scan_store.json`/`rankings.json`. NUNCA fala com a Steam por requisição
de visitante. As rotas pessoais usam autenticação e armazenamento por
conta; a página pública chama `recommendations.buy_candidates` com
`owned_names=set()` para apresentar o ranking geral.
"""
from __future__ import annotations

import logging
import logging.handlers
import math
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import time
import urllib.parse
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

# A stdlib não conhece woff2 e a fonte sairia como
# "application/octet-stream" (alguns navegadores reclamam disso no
# console). Registra o tipo certo uma vez, global.
mimetypes.add_type("font/woff2", ".woff2")

from flask import (
    Flask, Response, g, jsonify, make_response, redirect, render_template,
    request, send_from_directory, session, url_for,
)
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash

from galaseca import (
    __version__, cases, gamedata, ranking, recommendations, scan_store,
    scan_targets, signals, steam_news,
)
from galaseca._paths import DATA_DIR, atomic_write_bytes
from galaseca.localization import localize_name
from galaseca.public_site import (
    buscas, changelog, charts, db_backup, discord_notify, erro_stats, fmt,
    icon_cache, latencia, profile_fetcher, raridade, rate_limit,
    scan_progress, user_store, uptime, visits,
)
from galaseca.public_site.auth import csrf_token, csrf_valid

_MARKET_LISTING_URL = "https://steamcommunity.com/market/listings/730/{name}"
# Ícone: CDN estático da Steam (steamstatic.com), não o market/inventory
# rate-limited -- cacheado localmente via `icon_cache.py` (2a rodada,
# 2026-10-25) pela rota `/icone/<hash>.webp` abaixo. Esta constante
# continua servindo de FALLBACK (redirect) quando o cache falha.
_ICON_CDN_URL_2X = (
    "https://community.steamstatic.com/economy/image/"
    "{hash}/{tamanho}fx{tamanho}f"
)
_STEAMDB_SEARCH_URL = "https://steamdb.info/search/?q={name}"
from galaseca.public_site.account import bp as account_bp
from galaseca.public_site.history_routes import bp as history_bp
from galaseca.public_site.trades_routes import bp as trades_bp
from galaseca.public_site.watchlist_routes import bp as watchlist_bp
from galaseca._ambiente import ambiente

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_LIMIT_CANDIDATOS = 20
_PAGINA_TAMANHO = 10
_INTERVALO_HORAS_DEFAULT = 6.0
_SECRET_KEY_PATH = DATA_DIR / "public_site_secret.key"
_ERROR_LOG_PATH = DATA_DIR / "errors.log"
# Gravado pelo Dockerfile a cada build (data/hora do build, UTC) -- sem
# isso __version__ fica preso em "1.0.0" pra sempre, sem jeito de saber
# SE um deploy novo de fato subiu. Ausente fora de Docker (dev local).
_BUILD_ID_PATH = Path(__file__).parent.parent.parent / "BUILD_ID"
_ADMIN_PASSWORD_HASH = ambiente("ADMIN_PASSWORD_HASH", "")


def _build_id() -> "str | None":
    try:
        return _BUILD_ID_PATH.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _configurar_log_erros(app: Flask) -> None:
    """Grava exceções não tratadas em `DATA_DIR/errors.log`, separado do
    stdout do gunicorn -- achado de hoje (pedido do usuário): sem isso,
    um 500 em produção só aparece se alguém for catar `docker logs` na
    hora certa. Rotativo (1MB x 3 arquivos) pra nunca crescer sem limite."""
    handler = logging.handlers.RotatingFileHandler(
        _ERROR_LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setLevel(logging.ERROR)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s"))
    app.logger.addHandler(handler)


def _parse_float_arg(nome: str) -> float | None:
    """Lê um query param numérico opcional. Vazio/inválido/não-finito ->
    None -- nunca `or 0`, que confundiria "não informado" com "zero"."""
    valor = request.args.get(nome)
    if valor is None or valor == "":
        return None
    try:
        numero = float(valor)
    except ValueError:
        return None
    return numero if math.isfinite(numero) else None


def _parse_int_arg(nome: str, default: int) -> int:
    valor = request.args.get(nome)
    if valor is None or valor == "":
        return default
    try:
        return max(1, int(valor))
    except ValueError:
        return default


def _paginas_visiveis(pagina: int, total_paginas: int, janela: int = 2) -> list:
    """Números de página a mostrar na paginação: a atual +/- `janela`,
    sempre com a primeira e a última, e `None` marcando uma lacuna (vira
    reticências no template). Ex.: pagina=9, total=20 -> [1, None, 7, 8,
    9, 10, 11, None, 20]. Com poucas páginas, não cria lacuna nenhuma."""
    if total_paginas <= 1:
        return [1] if total_paginas == 1 else []
    nums = sorted(set(
        [1, total_paginas]
        + list(range(max(1, pagina - janela), min(total_paginas, pagina + janela) + 1))
    ))
    visiveis: list = []
    anterior = None
    for n in nums:
        if anterior is not None and n - anterior > 1:
            visiveis.append(None)
        visiveis.append(n)
        anterior = n
    return visiveis


def _destaques_comparar(itens: list, campo: str) -> "tuple[set, set]":
    """Nomes com o menor e o maior valor de `campo` entre os itens do
    /comparar -- conjuntos vazios com menos de 2 itens ou se todos
    empatarem (marcar um entre valores iguais seria arbitrário, não
    informativo). Puramente descritivo ("maior/menor valor desta
    linha"), nunca "melhor escolha" -- ver AGENTS.md."""
    valores = [(it.get("name"), it.get(campo)) for it in itens
               if it.get(campo) is not None]
    if len(valores) < 2:
        return set(), set()
    nums = [v for _, v in valores]
    if min(nums) == max(nums):
        return set(), set()
    minimo, maximo = min(nums), max(nums)
    return ({n for n, v in valores if v == minimo},
            {n for n, v in valores if v == maximo})


def _load_or_create_secret_key() -> bytes:
    """Chave de assinatura da sessão do Flask, gerada uma vez e persistida.

    Sem isto, toda troca de processo (ou um `app.secret_key` hardcoded no
    código) invalidaria sessões -- ou peor, usaria a mesma chave previsível
    em toda instalação. Gerada com `secrets.token_bytes` (criptográfico),
    gravada com `atomic_write_bytes` (mesma disciplina de escrita atômica
    de sempre).
    """
    if _SECRET_KEY_PATH.exists():
        return _SECRET_KEY_PATH.read_bytes()
    key = secrets.token_bytes(32)
    atomic_write_bytes(_SECRET_KEY_PATH, key)
    return key


def _admin_required(view):
    """Nega como 404 (não 403/redirect) sem hash configurado ou sem
    sessão `admin` -- mesmo padrão de `auth.login_required`, mas sem
    redirecionar pro login: estas rotas não devem nem revelar que
    existem pra quem não é o dono (achado de auditoria da skill
    flask-python, 2026-11-05: o mesmo bloco de 2 linhas estava
    duplicado em `admin_logout`, `admin_testar_webhook`,
    `admin_backup_download` e `admin_log_bruto`).

    NÃO usar em `admin()`: ali, sem sessão (mas COM hash configurado)
    redireciona pro login em vez de 404 -- comportamento diferente de
    propósito, pra guiar o dono de volta ao login em vez de escondê-lo."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _ADMIN_PASSWORD_HASH or not session.get("admin"):
            return render_template("404.html"), 404
        return view(*args, **kwargs)
    return wrapped


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=str(_STATIC_DIR),
        template_folder=str(_TEMPLATES_DIR),
    )
    app.config["JSON_AS_ASCII"] = False
    # Achado de auditoria (2026-10-24): sem isso, o CSS/favicon saiam com
    # "Cache-Control: no-cache" -- o navegador revalidava (ETag) em toda
    # visita em vez de usar o cache direto por um tempo. 1 ano agora que
    # `static_v()` (acima) faz cache-busting via `?v=<build>` -- sem o
    # cache-busting, 1 ano deixaria visitante com CSS/JS velho até expirar
    # mesmo depois de um deploy; com ele, é seguro ir longe (2026-10-25).
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600
    app.secret_key = _load_or_create_secret_key()
    _configurar_log_erros(app)
    app.register_blueprint(account_bp)
    app.register_blueprint(trades_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(history_bp)

    # Em produção, um proxy (Render/Fly.io/nginx) termina o HTTPS e fala
    # com o gunicorn em texto puro -- sem isto, `request.url_root` (usado
    # pelo login Steam OpenID pra montar `realm`/`return_to`) reportaria
    # "http://" mesmo com o visitante em "https://", e a Steam devolveria
    # a um endereço que não bate com o que foi mandado. Inócuo localmente:
    # sem cabeçalho X-Forwarded-*, não muda nada.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # "Secure" exige HTTPS -- ligar sempre quebraria o dev local (http).
    # Produção seta GALASECA_PUBLIC_SITE_SECURE_COOKIES=1 (ver
    # galaseca/public_site/README.md).
    app.config["SESSION_COOKIE_SECURE"] = (
        ambiente("PUBLIC_SITE_SECURE_COOKIES") == "1")

    @app.context_processor
    def _inject_versao():
        build = _build_id()

        def static_v(filename: str) -> str:
            """`url_for('static', ...)` + `?v=<build>` -- cache-busting pro
            `SEND_FILE_MAX_AGE_DEFAULT` de 1 ano (pedido, 2026-10-25): sem
            isso, aumentar o cache-control faria o navegador ficar com
            `style.css`/`app.js` velhos até expirar, mesmo depois de um
            deploy. Cada build muda o `?v=`, então o navegador sempre busca
            de novo quando o conteúdo de fato mudou."""
            return f"{url_for('static', filename=filename)}?v={build or 'dev'}"

        return {
            "versao": f"{__version__} ({build})" if build else __version__,
            "static_v": static_v,
        }

    @app.context_processor
    def _inject_usuario():
        """`usuario` (nome/avatar) disponível em TODO template, não só
        nas rotas que já passavam explicitamente -- sem isto,
        `_conta_link.html` mostrava "Minha conta" genérico em vez do
        nome de verdade fora de `/conta` (2026-10-26). Uma rota que já
        passa `usuario=...` explicitamente (ex. `account.conta`) apenas
        sobrescreve este valor com o mesmo dado -- sem conflito."""
        steamid = session.get("steamid")
        if not steamid:
            return {}
        return {
            "usuario": user_store.get_user(steamid),
            "avatar_local": profile_fetcher.caminho_avatar(steamid) is not None,
        }

    @app.context_processor
    def _inject_visitas_no_rodape():
        """Expõe totais de visitas pro rodapé e templates globais.

        `visits.registrar()` já soma a visita na rota `/`, então o dado de
        hoje e total está sempre disponível para todos os templates sem
        que cada rota passe isso manualmente."""
        serie = visits.serie_por_dia()
        hoje = visits.dia_local()
        visitas_hoje = next((qtd for dia, qtd in serie if dia == hoje), 0)
        return {
            "visitas_total": visits.total(),
            "visitas_hoje": visitas_hoje,
        }

    @app.context_processor
    def _inject_legenda_raridade():
        """Lista fixa (7 raridades) disponível em todo template -- só a
        home e o Ranking usam hoje (popover perto da tabela), mas é
        global pra não precisar repassar manualmente se outra tela
        quiser o mesmo popover no futuro."""
        return {"legenda_raridade": raridade.legenda_raridade()}

    # Filtros Jinja: nota_classe/risco_nivel/risco_label -- centraliza a
    # classificação de nota e o rótulo de risco, repetida em 4 templates
    # até 2026-10-26 (index/item/comparar/ranking). Um filtro só precisa
    # ser registrado uma vez pra ficar disponível em todos os templates,
    # ao contrário de uma macro Jinja (que exige `{% import %}` em cada
    # arquivo).
    app.jinja_env.filters["nota_classe"] = _nota_classe
    app.jinja_env.filters["nota_anel"] = _nota_anel
    app.jinja_env.filters["risco_nivel"] = _risco_nivel
    app.jinja_env.filters["risco_label"] = _risco_label
    app.jinja_env.filters["rotulo_caixa"] = _rotulo_caixa
    app.jinja_env.filters["motivo_fmt"] = _motivo_fmt
    app.jinja_env.filters["liquidez_label"] = _liquidez_label
    app.jinja_env.filters["titulo_sem_pipe_orfao"] = _titulo_sem_pipe_orfao
    app.jinja_env.filters["nome_pt"] = localize_name

    @app.before_request
    def _marcar_inicio_latencia():
        g.inicio_ts = time.time()

    @app.after_request
    def _registrar_latencia(resp):
        inicio = g.get("inicio_ts")
        if inicio is not None and request.endpoint:
            latencia.registrar(request.endpoint, (time.time() - inicio) * 1000)
        return resp

    @app.route("/")
    def index():
        visits.registrar()
        scan = scan_store.load_last_scan()
        categoria = request.args.get("categoria") or None
        nota_min = _parse_float_arg("nota_min")
        preco_max = _parse_float_arg("preco_max")
        busca = (request.args.get("q") or "").strip() or None
        liquidez_min = request.args.get("liquidez_min") or None
        if liquidez_min not in (None, *_LIQUIDEZ_ORDEM):
            liquidez_min = None
        # "ordenar" usa cookie de preferência: query param manda quando
        # presente, senão cai pro último escolhido (sem isso, re-ordenar
        # por preço não sobrevivia a uma nova visita).
        ordenar = (request.args.get("ordenar") if "ordenar" in request.args
                  else request.cookies.get("pref_ordenar")) or "nota"
        if ordenar not in ("nota", "preco"):
            ordenar = "nota"
        # Como mostrar a lista (revisão de direção visual 2026-11-08,
        # rodada 2): "vitrine" é a grade de cards com imagem grande;
        # "lista" é a tabela densa de sempre. Cookie guarda a escolha
        # (igual `pref_ordenar`) pra sobreviver a filtros e paginação --
        # sem isso, todo link interno voltaria pro modo padrão.
        ver = (request.args.get("ver") if "ver" in request.args
               else request.cookies.get("pref_ver")) or "vitrine"
        if ver not in ("vitrine", "lista"):
            ver = "vitrine"
        pagina = _parse_int_arg("pagina", 1)
        if busca:
            buscas.registrar(busca)

        todos = _candidatos_filtrados(
            scan, categoria, nota_min, preco_max, busca, ordenar,
            liquidez_min, com_historico=False, com_icone=False)
        # Total real da aba "Todas" -- achado 2026-10-30: `scan["results"]`
        # inclui item com risco alto de pump, que `buy_candidates` descarta
        # antes de qualquer filtro do visitante. Sem isto a aba dizia um
        # número (ex. 183) e a lista abaixo mostrava outro (176) sem
        # explicação. Sem filtro nenhum ativo, `todos` já é esse total;
        # só recalcula quando algum filtro do visitante reduziu `todos`.
        total_geral = (len(todos)
                       if not (categoria or nota_min or preco_max or busca or liquidez_min)
                       else len(_candidatos_filtrados(
                           scan, com_historico=False, com_icone=False)))
        inicio = (pagina - 1) * _PAGINA_TAMANHO
        candidatos_pagina = todos[inicio:inicio + _PAGINA_TAMANHO]
        total_paginas = max(1, -(-len(todos) // _PAGINA_TAMANHO))
        _enriquecer_com_historico(candidatos_pagina)
        _enriquecer_com_icone(candidatos_pagina)
        intervalo_horas = float(ambiente("WORKER_INTERVAL_HORAS", _INTERVALO_HORAS_DEFAULT))
        # Banner de "dado pode estar desatualizado" -- pedido depois do
        # bloqueio real de 429 que durou horas (2026-10-25): sem isto, a
        # tabela mostra dado velho em silêncio, como se fosse de agora.
        # 2x o intervalo configurado é a margem (um ciclo atrasado não
        # é anormal; dois seguidos geralmente é bloqueio da Steam).
        scan_desatualizado = bool(
            scan and (time.time() - scan["ts"]) > intervalo_horas * 3600 * 2)
        # Resumo "o que mudou hoje" (item #19 da lista de melhorias) -- só
        # na visão principal (página 1, sem filtro algum): com filtro ou
        # paginação ativos, o item citado podia nem aparecer na lista
        # abaixo, confuso. Reaproveita o MESMO snapshot do Top 20 que o
        # Ranking já usa (_resumo_do_dia) -- sem inventar uma segunda
        # fonte de comparação histórica.
        sem_filtro_ativo = not (categoria or nota_min or preco_max or busca or liquidez_min)
        resumo_do_dia = None
        if pagina == 1 and sem_filtro_ativo:
            snaps = ranking.load_snapshots()
            resumo_do_dia = _resumo_do_dia(snaps[-1] if snaps else None)
        # Hero "nota mais alta hoje" (revisão de direção visual
        # 2026-11-08) -- a home abria direto no formulário de filtro, sem
        # nenhum "rosto". Mesma condição de resumo_do_dia (só na visão
        # principal, sem filtro/busca, senão o item destacado podia nem
        # estar na lista abaixo) + ordenar == "nota": candidatos_pagina[0]
        # só é de fato "o maior nota" quando a ordenação é por nota.
        # Tom deliberadamente factual ("nota mais alta", não "melhor" ou
        # "destaque") -- é uma leitura do dado, não uma recomendação (ver
        # AGENTS.md, "não promete retorno").
        destaque_hero = None
        if pagina == 1 and sem_filtro_ativo and ordenar == "nota" and candidatos_pagina:
            destaque_hero = candidatos_pagina[0]
        resp = make_response(render_template(
            "index.html",
            candidatos=candidatos_pagina,
            destaque_hero=destaque_hero,
            scan=scan,
            resumo_do_dia=resumo_do_dia,
            idade=scan_store.idade_txt(scan["ts"]) if scan else None,
            proximo_scan=(scan_store.proxima_txt(scan["ts"], intervalo_horas)
                         if scan else None),
            scan_desatualizado=scan_desatualizado,
            categorias=sorted(scan_targets.SCAN_BY_CATEGORY.keys()),
            contagem_categorias=_contagem_por_categoria(scan),
            total_geral=total_geral,
            categoria_sel=categoria,
            nota_min_sel=nota_min,
            preco_max_sel=preco_max,
            liquidez_min_sel=liquidez_min,
            liquidez_opcoes=_LIQUIDEZ_ORDEM,
            busca_sel=busca,
            ordenar_sel=ordenar,
            ver_sel=ver,
            pagina=pagina,
            primeiro_item=inicio + 1,
            ultimo_item=inicio + len(candidatos_pagina),
            tem_proxima_pagina=len(todos) > inicio + _PAGINA_TAMANHO,
            tem_pagina_anterior=pagina > 1,
            total_candidatos=len(todos),
            total_paginas=total_paginas,
            paginas_visiveis=_paginas_visiveis(pagina, total_paginas),
        ))
        _UM_ANO_S = 365 * 24 * 3600
        if "ordenar" in request.args:
            # `secure` segue a mesma config do cookie de sessão -- fixo
            # em True quebraria o dev local (http); achado 2026-11-01:
            # esse cookie não tinha a flag nenhuma, inconsistente com
            # SESSION_COOKIE_SECURE.
            resp.set_cookie("pref_ordenar", ordenar, max_age=_UM_ANO_S,
                            samesite="Lax",
                            secure=app.config["SESSION_COOKIE_SECURE"])
        if "ver" in request.args:
            resp.set_cookie("pref_ver", ver, max_age=_UM_ANO_S,
                            samesite="Lax",
                            secure=app.config["SESSION_COOKIE_SECURE"])
        return resp

    @app.route("/item/<name>")
    def item_detail(name: str):
        """Página por item -- permalink compartilhável, com o histórico
        completo de preço (reaproveita `charts.line_chart_svg`, já usado
        pro gráfico de visitas) e "itens parecidos" (mesma categoria,
        nota mais próxima). Sem chamada à Steam: os mesmos dados já
        calculados em `_candidatos_filtrados`, filtrados pelo nome.

        `com_historico=False` (2026-10-27): esta rota nunca usou
        `tendencia`/`sparkline` dos ~150 candidatos -- o gráfico próprio
        da página vem de `hist` (linha abaixo), e `_itens_parecidos` só
        olha categoria/nota/nome. Mesmo bug que o `index()` já teve
        corrigido em 2026-10-26 (ler histórico de TODOS os candidatos
        quando só um é exibido), que não tinha se propagado pra cá."""
        scan = scan_store.load_last_scan()
        candidatos = _candidatos_filtrados(
            scan, com_historico=False, com_icone=False)
        item = next((c for c in candidatos if c["name"] == name), None)
        if item is None:
            return render_template("404.html"), 404
        # Mesmo achado de performance do index() (2026-11-09): ícone só
        # no item em destaque + nos parecidos exibidos, não nos ~150
        # candidatos inteiros cruzados só pra achar este item.
        parecidos = _itens_parecidos(item, candidatos)
        _enriquecer_com_icone([item] + parecidos)
        hist = signals.load_item_history(name)
        periodo = request.args.get("periodo") or None
        if periodo not in _PERIODOS_GRAFICO:
            periodo = None
        pontos_periodo = [
            p for p in _filtra_historico_por_periodo(hist, periodo)
            if p.get("price")]
        precos_periodo = [p["price"] for p in pontos_periodo]
        # item #8 da lista de melhorias -- tooltip por ponto (data + preço
        # exato), via <title> nativo do SVG (ver charts.line_chart_svg).
        rotulos_periodo = [
            f"{fmt.data_hora_br(p['ts'])} — {fmt.brl(p['price'])}"
            for p in pontos_periodo]
        grafico = charts.line_chart_svg(
            [{"total": v} for v in precos_periodo], area_fill=True,
            rotulos=rotulos_periodo)
        # Cor do gráfico pela direção do PERÍODO EXIBIDO (primeiro vs.
        # último ponto do recorte atual) -- mesmo critério visual do
        # mini-sparkline da listagem (achado 2026-11-06), não os 2 últimos
        # pontos crus do histórico (_tendencia_do_historico): o período
        # selecionado pelo visitante (7d/30d/90d/tudo) muda o que está na
        # tela, então a cor tem que acompanhar o que ele está vendo, não
        # um resumo de fora do recorte. None (preço estável, ou só 1
        # ponto no recorte) fica na cor neutra de sempre.
        grafico_tendencia = None
        if len(precos_periodo) >= 2:
            if precos_periodo[-1] > precos_periodo[0]:
                grafico_tendencia = "alta"
            elif precos_periodo[-1] < precos_periodo[0]:
                grafico_tendencia = "baixa"
        # A linha sozinha é normalizada entre o mínimo e o máximo do
        # próprio recorte -- sem essa legenda, uma subida de R$0,10 e uma
        # de R$100 desenham a MESMA inclinação na tela, e quem usa leitor
        # de tela não tem nenhum texto associado ao SVG (achado de
        # auditoria de acessibilidade, 2026-11-04).
        grafico_legenda = (
            f"{fmt.brl(min(precos_periodo))} – {fmt.brl(max(precos_periodo))} no período"
            if len(precos_periodo) >= 2 else None)
        # Período com poucos pontos: `grafico` pode ficar vazio mesmo
        # havendo histórico (90d filtrado demais, por exemplo). O seletor
        # continua aparecendo nesse caso -- só o gráfico some, pra deixar
        # claro que é falta de dado NESSE recorte, não no item.
        tem_historico = sum(1 for p in hist if p.get("price")) >= 2
        return render_template(
            "item.html",
            item=item,
            grafico=grafico,
            grafico_tendencia=grafico_tendencia,
            grafico_legenda=grafico_legenda,
            tem_historico=tem_historico,
            periodo_sel=periodo,
            periodo_opcoes=list(_PERIODOS_GRAFICO),
            parecidos=parecidos,
            tempo_aposentadoria=_tempo_desde_aposentadoria(item.get("case_retired_at")),
            historico_ranking=ranking.historico_do_item(
                name, dias=_DIAS_HISTORICO_RANKING, tz=fmt.FUSO_BR),
            eventos_jogo=_eventos_do_jogo(set(), so_do_item=name),
            variantes=_variantes_para_tela(
                item, {c["name"] for c in candidatos}),
            itens_da_caixa=cases.skins_in_case(item.get("case")),
            # Preço mais recente DESTE item específico -- cada item do
            # scan é coletado em instantes diferentes dentro do ciclo de
            # ~25min (ver scan_engine.run_full_scan), então isto é mais
            # preciso que a idade do scan como um todo.
            preco_coletado_txt=(
                scan_store.idade_txt(hist[-1]["ts"]) if hist else None),
        )

    @app.route("/comparar")
    def comparar():
        """Até 3 itens lado a lado -- a seleção em si vive no
        `sessionStorage` do navegador (`app.js`), isto só resolve os
        nomes recebidos em `?nomes=A,B,C` pros dados já calculados.

        `com_historico=False` + `_enriquecer_com_historico` só nos até 3
        itens exibidos (2026-10-27): `comparar.html` usa `tendencia`
        (não `sparkline`), mas só dos itens comparados -- calcular pros
        ~150 candidatos inteiros pra mostrar no máximo 3 era o mesmo
        desperdício já corrigido no `index()` em 2026-10-26."""
        scan = scan_store.load_last_scan()
        candidatos = _candidatos_filtrados(
            scan, com_historico=False, com_icone=False)
        nomes = [n for n in (request.args.get("nomes") or "").split(",") if n][:3]
        por_nome = {c["name"]: c for c in candidatos}
        itens = [por_nome[n] for n in nomes if n in por_nome]
        _enriquecer_com_historico(itens)
        _enriquecer_com_icone(itens)
        menor_preco, _ = _destaques_comparar(itens, "price")
        _, maior_nota = _destaques_comparar(itens, "score")
        for it in itens:
            it["preco_destaque"] = it.get("name") in menor_preco
            it["nota_destaque"] = it.get("name") in maior_nota
        return render_template("comparar.html", itens=itens)

    @app.route("/api/recommendations")
    @rate_limit.rate_limited(rate_limit.API_MAX_HITS, rate_limit.API_WINDOW_S)
    def api_recommendations():
        scan = scan_store.load_last_scan()
        candidatos = _candidatos_filtrados(
            scan, com_historico=False, com_icone=False)[:_LIMIT_CANDIDATOS]
        _enriquecer_com_historico(candidatos)
        _enriquecer_com_icone(candidatos)
        resp = jsonify({
            "api_version": 1,
            "ultimo_scan": {
                "categoria": scan["category"] if scan else None,
                "ts": scan["ts"] if scan else None,
            },
            "candidatos": candidatos,
        })
        # O dado só muda quando um ciclo do worker termina (até 6h) --
        # cache curto evita reprocessar `_candidatos_filtrados` (passa
        # por `recommendations.buy_candidates` + localize_name por item)
        # a cada poll de quem consome a API programaticamente.
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True})

    @app.route("/readyz")
    def readyz():
        """Diferente de `/healthz` (só "o processo está de pé"): confere
        se dá pra abrir o banco de contas (quando existe) sem exceção --
        pensado pro orquestrador saber se pode receber tráfego de
        verdade, não só se o container iniciou. `scan_store` nunca
        levanta exceção por design (ver `load_last_scan`), então só o
        banco é checado de fato."""
        motivos = []
        db_path = db_backup._DB_PATH
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                # Força ler o cabeçalho/schema de verdade -- "SELECT 1"
                # não toca em nenhuma página do arquivo, então um banco
                # corrompido passava como "pronto" (achado escrevendo o
                # teste, 2026-10-25).
                conn.execute("SELECT count(*) FROM sqlite_master")
                conn.close()
            except sqlite3.Error as e:
                motivos.append(f"banco: {e}")
        if motivos:
            return jsonify({"ready": False, "motivos": motivos}), 503
        return jsonify({"ready": True})

    @app.route("/api/health")
    def api_health():
        """Versão detalhada do /healthz -- pensada pra quem consome a API
        saber SE pode confiar no dado agora, não só se o processo web
        está de pé (achado de 2026-10-25: distinguir "site no ar" de
        "dado fresco" importa depois do incidente de hoje)."""
        scan = scan_store.load_last_scan()
        ciclos = scan_store.load_historico_ciclos()
        ultimo_ciclo = ciclos[-1] if ciclos else None
        intervalo_horas = float(ambiente("WORKER_INTERVAL_HORAS", _INTERVALO_HORAS_DEFAULT))
        return jsonify({
            "ok": True,
            "api_version": 1,
            "scan": {
                "disponivel": scan is not None,
                "idade_segundos": (
                    round(time.time() - scan["ts"], 1) if scan else None),
                "itens": len(scan["results"]) if scan else 0,
            },
            "ultimo_ciclo_worker": ultimo_ciclo,
            "intervalo_horas_configurado": intervalo_horas,
            "no_ar_desde": uptime.no_ar_desde(),
            "visitas_total": visits.total(),
        })

    @app.route("/icone/<hash_icone>.webp")
    @rate_limit.rate_limited(rate_limit.ICON_MAX_HITS, rate_limit.ICON_WINDOW_S)
    def icone_cache(hash_icone: str):
        """Ícone servido do próprio domínio (ver `icon_cache.py`) --
        cache em disco, só busca do CDN da Steam na primeira vez que
        aquele hash aparece (reencodando PNG/JPEG pra WebP, preservando
        transparência). Nunca 500: cache miss + rede fora
        vira redirect pro CDN direto, nunca erro pro visitante.

        `?tam=` (2026-11-08) escolhe entre os tamanhos de
        `icon_cache.TAMANHOS_PERMITIDOS` -- valor fora da lista (ou
        ausente) cai no padrão de 192px, nunca erro. Alimenta o
        `srcset` 2x que os templates já declaram (ver `icon_url_2x`).

        Rate limit (2026-10-27): sem login, cache miss grava arquivo
        novo em disco pra QUALQUER hash -- sem isto, um script batendo
        com hash diferente a cada chamada enche o disco sem fim (ver
        rate_limit.ICON_MAX_HITS)."""
        tamanho = _parse_int_arg("tam", icon_cache.TAMANHO_PADRAO)
        if tamanho not in icon_cache.TAMANHOS_PERMITIDOS:
            tamanho = icon_cache.TAMANHO_PADRAO
        dados = icon_cache.obter(hash_icone, tamanho)
        if dados is None:
            return redirect(
                _ICON_CDN_URL_2X.format(hash=hash_icone, tamanho=tamanho))
        resp = Response(dados, mimetype="image/webp")
        resp.headers["Cache-Control"] = "public, max-age=2592000, immutable"
        return resp

    @app.route("/sw.js")
    def service_worker():
        """Fora de `/static/` de propósito: um service worker só
        controla (scope) o diretório onde é servido, a menos que o
        servidor mande `Service-Worker-Allowed` -- rota própria na raiz
        é mais simples que configurar esse header por cima do
        `/static/` do Flask."""
        resp = send_from_directory(_STATIC_DIR, "sw.js")
        resp.headers["Service-Worker-Allowed"] = "/"
        return resp

    @app.route("/robots.txt")
    def robots():
        # Disallow /admin em defesa de profundidade (2026-10-25) -- o token
        # já nega sem ele (ver rota `admin` abaixo), isto só evita que um
        # crawler sequer tente a URL ou a indexe se alguém linkar por engano.
        texto = (
            "User-agent: *\nAllow: /\nDisallow: /admin\n"
            f"Sitemap: {request.url_root}sitemap.xml\n")
        return Response(texto, mimetype="text/plain")

    @app.route("/api/csp-report", methods=["POST"])
    @rate_limit.rate_limited(
        rate_limit.CSP_REPORT_MAX_HITS, rate_limit.CSP_REPORT_WINDOW_S)
    def csp_report():
        """Endpoint de `report-uri` do CSP (Caddyfile) -- sem isto, uma
        violação de política só aparecia se um visitante abrisse o
        DevTools e reclamasse. Registrado como erro (mesmo pipeline do
        `/admin`) pra aparecer nos "Últimos erros" sem precisar de SSH.
        Sem CSRF/sessão: é o navegador que posta isto sozinho, nunca um
        formulário."""
        try:
            corpo = request.get_data(as_text=True)[:2000]
            app.logger.error("CSP violation: %s", corpo)
        except Exception:
            pass
        return "", 204

    @app.route("/sitemap.xml")
    @rate_limit.rate_limited(rate_limit.API_MAX_HITS, rate_limit.API_WINDOW_S)
    def sitemap():
        base = request.url_root.rstrip("/")
        paginas = ["/", "/privacidade", "/status", "/changelog", "/api",
                  "/ranking", "/novidades", "/metodo", "/sobre", "/faq",
                  "/glossario"]
        urls_xml = "\n".join(
            f"  <url><loc>{_xml_escape(base + p)}</loc></url>" for p in paginas)
        # Páginas de item -- cada uma já tem título/descrição/JSON-LD
        # própria, mas sem link aqui um crawler só as acha indiretamente
        # via paginação da home (mais lento e menos confiável do que
        # listar direto). Mesma lista que `item_detail` usa -- um nome
        # fora dela dá 404, então o sitemap não pode divergir.
        scan = scan_store.load_last_scan()
        if scan:
            candidatos = _candidatos_filtrados(
                scan, com_historico=False, com_icone=False)
            itens_xml = "\n".join(
                f"  <url><loc>{_xml_escape(base + url_for('item_detail', name=c['name']))}</loc></url>"
                for c in candidatos)
            if itens_xml:
                urls_xml = urls_xml + "\n" + itens_xml
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls_xml}\n"
            "</urlset>\n"
        )
        return Response(xml, mimetype="application/xml")

    @app.route("/opensearch.xml")
    def opensearch():
        """Descrição OpenSearch -- deixa o navegador oferecer "Adicionar
        mecanismo de busca: galaseca" na barra de endereço, usando a
        própria busca por nome (`q=`) que a página inicial já tem."""
        base = request.url_root.rstrip("/")
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">\n'
            "  <ShortName>galaseca</ShortName>\n"
            "  <Description>Buscar uma skin de CS2 por nome no galaseca"
            "</Description>\n"
            f"  <Image width=\"32\" height=\"32\" type=\"image/svg+xml\">{_xml_escape(base)}/static/favicon.svg</Image>\n"
            f"  <Url type=\"text/html\" template=\"{_xml_escape(base)}/?q={{searchTerms}}\"/>\n"
            "  <InputEncoding>UTF-8</InputEncoding>\n"
            "</OpenSearchDescription>\n"
        )
        return Response(xml, mimetype="application/opensearchdescription+xml")

    @app.errorhandler(404)
    def pagina_nao_encontrada(_erro):
        if request.path.startswith("/api/"):
            return jsonify({"api_version": 1, "erro": "nao_encontrado",
                            "mensagem": "Rota não existe."}), 404
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def erro_interno(erro):
        app.logger.error("500 em %s: %r", request.path, erro, exc_info=erro)
        if request.path.startswith("/api/"):
            return jsonify({"api_version": 1, "erro": "erro_interno",
                            "mensagem": "Erro interno do servidor."}), 500
        return render_template("500.html"), 500

    @app.errorhandler(429)
    def limite_excedido(_erro):
        # Achado da skill api-and-interface-design (2026-11-05): os três
        # handlers devolviam HTML mesmo pra /api/* -- quem consome a API
        # programaticamente (ver /api) recebia uma página inteira em vez
        # de JSON num erro, quebrando qualquer client que só espera JSON.
        if request.path.startswith("/api/"):
            return jsonify({"api_version": 1, "erro": "limite_excedido",
                            "mensagem": "Muitas tentativas. Tente de novo mais tarde."}), 429
        return render_template("429.html"), 429

    @app.route("/privacidade")
    def privacidade():
        return render_template("privacidade.html")

    @app.route("/changelog")
    def changelog_page():
        return render_template("changelog.html", entradas=changelog.ENTRADAS)

    @app.route("/changelog.xml")
    def changelog_feed():
        base = request.url_root.rstrip("/")
        link_changelog = f"{base}/changelog"
        itens_xml = "\n".join(
            "    <item>\n"
            f"      <title>{_xml_escape(e['data'])} — {_xml_escape(e['titulo'])}</title>\n"
            # Opcional pela spec RSS 2.0, mas sem nenhum <link> o item não
            # tinha pra onde clicar -- achado 2026-11-01. Sem âncora por
            # entrada ainda (changelog.html não tem id por data), então
            # aponta pra página toda.
            f"      <link>{_xml_escape(link_changelog)}</link>\n"
            f"      <description>{_xml_escape('; '.join(e['itens']))}</description>\n"
            f"      <guid isPermaLink=\"false\">{_xml_escape(e['data'])}</guid>\n"
            "    </item>"
            for e in changelog.ENTRADAS
        )
        rss = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>\n'
            "  <title>Galaseca — Mudanças</title>\n"
            f"  <link>{_xml_escape(link_changelog)}</link>\n"
            "  <description>O que mudou no site, por data.</description>\n"
            "  <language>pt-BR</language>\n"
            f"{itens_xml}\n"
            "</channel></rss>\n"
        )
        return Response(rss, mimetype="application/rss+xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    @app.route("/metodo")
    def metodo():
        return render_template("metodo.html")

    @app.route("/faq")
    def faq():
        return render_template("faq.html")

    @app.route("/glossario")
    def glossario():
        return render_template("glossario.html")

    @app.route("/sobre")
    def sobre():
        return render_template("sobre.html")

    @app.route("/novidades")
    def novidades():
        """Mudanças detectadas nos arquivos do jogo + anúncios oficiais
        do CS2. Só lê o que o worker já gravou -- abrir esta página não
        faz nenhuma requisição externa."""
        # Só vira link o nome que `item_detail` aceita (mesma lista dele);
        # um nome fora dela daria 404.
        nomes = _nomes_com_pagina(scan_store.load_last_scan())
        try:
            estado = gamedata.load_state() or {}
        except Exception:
            estado = {}
        conferido_ts = estado.get("fetched_at")
        return render_template(
            "novidades.html",
            eventos=_eventos_do_jogo(nomes),
            noticias=_noticias_oficiais(),
            arquivos_conferidos_txt=(
                scan_store.idade_txt(conferido_ts)
                if isinstance(conferido_ts, (int, float)) else None),
        )

    @app.route("/ranking")
    def ranking_page():
        snaps = ranking.load_snapshots()
        atual = snaps[-1] if snaps else None
        periodo = request.args.get("periodo") or _PERIODO_RANKING_PADRAO
        if periodo not in _PERIODOS_RANKING:
            periodo = _PERIODO_RANKING_PADRAO
        # Setas, variação de nota e a frase-resumo usam a MESMA base de
        # comparação (antes as setas iam contra o scan anterior, ~6h, e a
        # frase contra ~1 dia -- dois "desde quando" na mesma tela).
        anterior = _snapshot_de_comparacao(atual, periodo)
        itens_antigos = {it["name"]: it
                         for it in (anterior or {}).get("items") or []}
        # Ícone + raridade não vêm do snapshot (ranking.py grava só
        # name/score/position, ver _icone_raridade) -- cruza pelo nome
        # com o scan atual, que já tem icon/name_color/rarity_id.
        scan = scan_store.load_last_scan()
        por_nome_scan = {r["name"]: r for r in (scan or {}).get("results") or []}
        itens = []
        if atual:
            for it in atual["items"]:
                delta = ranking.position_delta(
                    it["name"], it["position"], anterior)
                velho = itens_antigos.get(it["name"])
                nota_diff = (it.get("score", 0) - velho.get("score", 0)
                             if velho else None)
                itens.append({
                    "name": it["name"],
                    "name_fmt": localize_name(it["name"]),
                    "position": it["position"],
                    "score": it["score"],
                    "nota_diff": nota_diff,
                    **delta,
                    **_icone_raridade(por_nome_scan.get(it["name"])),
                })
        # Mesmo seletor Vitrine/Lista da home (revisão de direção visual
        # 2026-11-08) -- mesmo cookie `pref_ver`, pra uma escolha só valer
        # pro site inteiro: quem prefere Lista na home não quer vitrine de
        # novo aqui. O Top 20 não tem preço/motivo no snapshot (só name/
        # score/position), então o card da vitrine aqui é mais enxuto que
        # o da home -- ver cartao_candidato_ranking em ranking.html.
        ver = (request.args.get("ver") if "ver" in request.args
               else request.cookies.get("pref_ver")) or "vitrine"
        if ver not in ("vitrine", "lista"):
            ver = "vitrine"
        resp = make_response(render_template(
            "ranking.html",
            itens=itens,
            quando=scan_store.idade_txt(atual["ts"]) if atual else None,
            tem_anterior=anterior is not None,
            resumo_do_dia=_resumo_entre(atual, anterior),
            ver_sel=ver,
            periodo_sel=periodo,
            periodos=_PERIODOS_RANKING,
            saidas=_saidas_do_top(atual, anterior, por_nome_scan,
                                  _nomes_com_pagina(scan) if anterior else set()),
        ))
        if "ver" in request.args:
            resp.set_cookie("pref_ver", ver, max_age=365 * 24 * 3600,
                            samesite="Lax",
                            secure=app.config["SESSION_COOKIE_SECURE"])
        return resp

    @app.route("/admin/login", methods=["GET", "POST"])
    @rate_limit.rate_limited(rate_limit.LOGIN_MAX_HITS, rate_limit.LOGIN_WINDOW_S)
    def admin_login():
        """Login real (usuário único -- é literalmente o dono do site,
        não precisa de conta/"esqueci a senha"). Troca o token fixo em
        URL (vazava em log/referrer) por sessão + senha com hash
        (`werkzeug.security`, PBKDF2/scrypt, zero dependência nova --
        ver `scripts/hash_admin_password.py`). Sem hash configurado,
        a rota nem existe pro visitante: sempre 404, nunca abre
        "sem senha" por padrão."""
        if not _ADMIN_PASSWORD_HASH:
            return render_template("404.html"), 404
        erro = None
        if request.method == "POST":
            senha = request.form.get("senha") or ""
            if check_password_hash(_ADMIN_PASSWORD_HASH, senha):
                session["admin"] = True
                return redirect(url_for("admin"))
            erro = "Senha incorreta."
        return render_template("admin_login.html", erro=erro)

    @app.route("/admin/logout", methods=["POST"])
    @_admin_required
    def admin_logout():
        if not csrf_valid(request.form.get("csrf_token")):
            return "", 403
        session.pop("admin", None)
        return redirect(url_for("index"))

    @app.route("/admin")
    def admin():
        """Painel só pro dono -- ver `admin_login` pra como a sessão é
        criada. Sem hash configurado OU sem sessão válida, a rota
        sempre nega (404), nunca abre "sem senha" por padrão."""
        if not _ADMIN_PASSWORD_HASH:
            return render_template("404.html"), 404
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        erros = []
        erros_agregados = []
        grafico_erros = ""
        if _ERROR_LOG_PATH.exists():
            linhas = _ERROR_LOG_PATH.read_text(encoding="utf-8",
                                               errors="replace").splitlines()
            erros = linhas[-30:]
            # Mais linhas pra agregação (tipo/dia) que pro tail cru --
            # a tendência importa mais que as últimas 30 exatas aqui.
            linhas_agregacao = linhas[-500:]
            erros_agregados = erro_stats.agregar_por_tipo(linhas_agregacao)
            serie_erros = erro_stats.serie_por_dia(linhas_agregacao)
            # Mesmo padrão de tooltip por ponto (<title> nativo do SVG) já
            # usado em /item, /conta/historico e /status.
            grafico_erros = charts.line_chart_svg(
                [{"total": qtd} for _dia, qtd in serie_erros],
                rotulos=[
                    f"{date.fromisoformat(dia).strftime('%d/%m/%Y')} — {qtd} "
                    f"{'erro' if qtd == 1 else 'erros'}"
                    for dia, qtd in serie_erros])
        backups = sorted(db_backup._BACKUP_DIR.glob("public_site-*.db")) \
            if db_backup._BACKUP_DIR.exists() else []
        progresso = scan_progress.carregar()
        if progresso:
            progresso = dict(progresso, idade=scan_store.idade_txt(progresso["ts"]))
        # Mesmo padrão de `quando` que /status já usa pro histórico de
        # ciclos -- sem isto o admin mostrava `c.ts` cru (epoch em
        # segundos, tipo "1792500195") em vez de "há 20 min" (achado
        # 2026-10-27: os dois templates leem a mesma lista, só o /status
        # formatava).
        ciclos_admin = list(reversed(scan_store.load_historico_ciclos()))[:10]
        for c in ciclos_admin:
            c["quando"] = scan_store.idade_txt(c["ts"])
        return render_template(
            "admin.html",
            build=_build_id(),
            visitas=visits.total(),
            mais_buscados=buscas.mais_buscados(limite=20),
            erros=erros,
            erros_agregados=erros_agregados,
            grafico_erros=grafico_erros,
            backups=[b.name for b in reversed(backups)],
            ciclos=ciclos_admin,
            progresso=progresso,
            latencias=latencia.resumo(),
            disco=_disco_info(),
            usuarios=_contagem_usuarios(),
            webhook_configurado=bool(
                ambiente("ADMIN_DISCORD_WEBHOOK")),
            teste_webhook_msg=request.args.get("teste_webhook"),
            csrf_token=csrf_token(),
        )

    @app.route("/admin/testar-webhook", methods=["POST"])
    @rate_limit.rate_limited(rate_limit.LOGIN_MAX_HITS, rate_limit.LOGIN_WINDOW_S)
    @_admin_required
    def admin_testar_webhook():
        # CSRF checado aqui dentro (não via @csrf_protect) de propósito:
        # @_admin_required já roda antes do corpo da view (mais perto
        # de `def`, executa por último entre os decorators, logo antes
        # da função); um @csrf_protect precisaria ficar ENTRE
        # @_admin_required e `def` pra manter essa ordem, e inline é
        # mais simples que empilhar mais um decorator só pra isso. Sem
        # essa ordem, uma visita anônima sem csrf_token nenhum na sessão
        # levaria 403 em vez de 404 -- vazando que a rota existe pra
        # quem não é admin.
        if not csrf_valid(request.form.get("csrf_token")):
            return "", 403
        webhook = ambiente("ADMIN_DISCORD_WEBHOOK", "")
        enviado = discord_notify.enviar(
            webhook, "🔧 GalaSeca: mensagem de teste do painel admin.")
        flash_msg = "Enviado -- confira o canal." if enviado else \
            "Falhou (webhook ausente ou Discord recusou)."
        return redirect(url_for("admin", teste_webhook=flash_msg))

    @app.route("/admin/backup/<nome>")
    @_admin_required
    def admin_backup_download(nome: str):
        """Download de um backup do SQLite -- o painel já lista os nomes
        (`backups=`, acima) desde a rodada anterior, mas sem link nenhum
        pra baixar nenhum deles. Valida `nome` contra o formato EXATO que
        `db_backup.fazer_backup_se_necessario` gera (whitelist por regex,
        não só confiar no `send_from_directory` resolver o path)."""
        if not re.fullmatch(r"public_site-\d{8}-\d{6}\.db", nome):
            return render_template("404.html"), 404
        caminho = db_backup._BACKUP_DIR / nome
        if not caminho.is_file():
            return render_template("404.html"), 404
        return send_from_directory(
            db_backup._BACKUP_DIR, nome,
            as_attachment=True, mimetype="application/octet-stream")

    @app.route("/admin/log-bruto")
    @_admin_required
    def admin_log_bruto():
        """Download do errors.log completo -- as 30 últimas linhas no
        painel bastam pro dia a dia, mas investigar um padrão (quantas
        vezes um erro específico apareceu ao longo de dias) pede o
        arquivo inteiro."""
        if not _ERROR_LOG_PATH.exists():
            return render_template("404.html"), 404
        return send_from_directory(
            _ERROR_LOG_PATH.parent, _ERROR_LOG_PATH.name,
            as_attachment=True, mimetype="text/plain")

    @app.route("/api")
    def api_docs():
        return render_template(
            "api_docs.html",
            exemplo_url=f"{request.url_root}api/recommendations")

    @app.route("/status")
    def status():
        ciclos = list(reversed(scan_store.load_historico_ciclos()))
        for c in ciclos:
            c["quando"] = scan_store.idade_txt(c["ts"])
        desde = uptime.no_ar_desde()
        serie = visits.serie_por_dia()
        valores_visitas = [qtd for _dia, qtd in serie]
        # Mesmo padrão de tooltip por ponto (<title> nativo do SVG) já
        # usado no gráfico de preço de /item/<name> e no de /conta/historico
        # -- sem área/tendência aqui (visita subir ou cair não é "bom" nem
        # "ruim" como preço, então fica sem a cor verde/vermelha).
        rotulos_visitas = [
            f"{date.fromisoformat(dia).strftime('%d/%m/%Y')} — {qtd} "
            f"{'visita' if qtd == 1 else 'visitas'}"
            for dia, qtd in serie]
        grafico_visitas = charts.line_chart_svg(
            [{"total": v} for v in valores_visitas], rotulos=rotulos_visitas)
        grafico_visitas_legenda = (
            f"{min(valores_visitas)} – {max(valores_visitas)} visitas por dia no período"
            if len(valores_visitas) >= 2 else None)
        ciclos_ok = sum(1 for c in ciclos if c.get("sucesso"))
        return render_template(
            "status.html",
            estado_scan=_estado_do_scan(
                scan_progress.carregar(), ciclos,
                float(ambiente("WORKER_INTERVAL_HORAS",
                               _INTERVALO_HORAS_DEFAULT))),
            no_ar_desde_txt=scan_store.idade_txt(desde),
            visitas=visits.total(),
            ciclos=ciclos,
            ciclos_sucesso_txt=(
                f"{ciclos_ok} de {len(ciclos)} ciclos com sucesso"
                if ciclos else None),
            grafico_visitas=grafico_visitas,
            grafico_visitas_legenda=grafico_visitas_legenda,
            mais_buscados=buscas.mais_buscados(limite=10),
        )

    @app.route("/feed.xml")
    @rate_limit.rate_limited(rate_limit.API_MAX_HITS, rate_limit.API_WINDOW_S)
    def feed():
        categoria = request.args.get("categoria") or None
        if categoria and categoria not in scan_targets.SCAN_BY_CATEGORY:
            categoria = None
        scan = scan_store.load_last_scan()
        # O RSS não exibe tendência nem sparkline -- ler o histórico dos
        # ~150 candidatos custava ~3s por request (medido 2026-10-29).
        candidatos = _candidatos_filtrados(
            scan, categoria, com_historico=False,
            com_icone=False)[:_LIMIT_CANDIDATOS]
        base = request.url_root.rstrip("/")
        itens_xml = "\n".join(
            "    <item>\n"
            f"      <title>{_xml_escape(c['name_fmt'])} — nota {c['score']}</title>\n"
            # Pra página do item no próprio site, não pra listagem da
            # Steam -- achado 2026-11-01: quem clicava a partir do feed
            # pulava direto pra Steam, sem ver a nota/motivo que é o
            # diferencial do feed.
            f"      <link>{_xml_escape(base + url_for('item_detail', name=c['name']))}</link>\n"
            f"      <guid isPermaLink=\"false\">{_xml_escape(c['name'])}</guid>\n"
            "      <description>"
            f"{_xml_escape(c['price_fmt'])} — "
            f"{_xml_escape('; '.join(c['reasons']) if c['reasons'] else 'Nota neutra')}"
            "</description>\n"
            "    </item>"
            for c in candidatos
        )
        titulo = (f"Galaseca — Preços e notas de {_xml_escape(categoria)}"
                  if categoria else "Galaseca — Preços e notas de skins CS2")
        link_self = f"{base}/feed.xml" + (
            f"?categoria={urllib.parse.quote(categoria)}" if categoria else "")
        rss = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>\n'
            f"  <title>{titulo}</title>\n"
            f"  <link>{_xml_escape(link_self)}</link>\n"
            "  <description>Nota de 0 a 100 pra skins do CS2, com o motivo"
            " escrito.</description>\n"
            "  <language>pt-BR</language>\n"
            f"{itens_xml}\n"
            "</channel></rss>\n"
        )
        return Response(rss, mimetype="application/rss+xml",
                        headers={"Cache-Control": "public, max-age=300"})

    return app


def _contagem_por_categoria(scan: "dict | None") -> dict:
    """{categoria: quantidade} a partir do scan cru -- alimenta os rótulos
    do dropdown de filtro ("Facas (12)"). Conta `scan["results"]` direto
    (não `buy_candidates`), então é uma aproximação -- itens filtrados por
    pump_risk no dropdown continuam contados aqui. Suficiente pra dar
    noção de tamanho, não precisa ser exato."""
    if not scan:
        return {}
    contagem: dict = {}
    for r in scan["results"]:
        cat = r.get("category")
        if cat:
            contagem[cat] = contagem.get(cat, 0) + 1
    return contagem


def _busca_bate(name_fmt: str, busca: "str | None") -> bool:
    """Suporta "termo1 OR termo2" (qualquer um presente já basta). Sem
    "OR", é substring simples -- comportamento de antes, preservado."""
    if not busca:
        return True
    alvo = name_fmt.lower()
    termos = [t.strip() for t in busca.lower().split(" or ") if t.strip()]
    if not termos:
        return True
    return any(t in alvo for t in termos)


def _tendencia_do_historico(hist: list) -> "str | None":
    if len(hist) < 2:
        return None
    anterior, atual = hist[-2]["price"], hist[-1]["price"]
    if atual > anterior:
        return "alta"
    if atual < anterior:
        return "baixa"
    return None


def _variacao_pct_do_historico(hist: list) -> "float | None":
    """Variação % entre os 2 últimos preços registrados -- o mesmo par que
    `_tendencia_do_historico` compara. Só "Subiu"/"Caiu" não dizia quanto:
    uma oscilação de centavos e uma de 30% apareciam iguais na tabela."""
    if len(hist) < 2:
        return None
    anterior, atual = hist[-2]["price"], hist[-1]["price"]
    if not anterior or atual == anterior:
        return None
    return (atual - anterior) / anterior * 100


_PONTOS_NO_FIM_RE = re.compile(r"\s*\(([+-]\d+(?:\.\d+)?)\)\s*$")


def _motivo_fmt(texto: "str | None") -> str:
    """"Preço 22% abaixo do típico (+26)" -> "... · +26 pts". O número
    entre parênteses é a contribuição do fator pra nota, mas solto assim
    lia como outra porcentagem. Só reformata a exibição; o rótulo
    original continua vindo de `signals` (compartilhado com o app).

    Casa decimal opcional no número -- `signals.enhanced_score` usa uma
    casa (em vez de arredondar pra "0") quando a contribuição de um
    fator é pequena o bastante pra virar "(+0)"/"(-0)" no inteiro, que
    lia como contradição (0 pontos, mas pintado de verde/vermelho).

    Espaços fixos (\\u00a0) entre "·", o número e "pts" -- achado
    2026-10-30: com espaço normal, a quebra de linha na coluna "Por
    quê" às vezes deixava só "pts" sozinho numa linha. O espaço antes
    de "·" continua normal, pra quebra poder acontecer ali."""
    if not texto:
        return ""
    return _PONTOS_NO_FIM_RE.sub(" · \\1 pts", texto)


def _tamanho_fmt(bytes_: int) -> str:
    """"1.2 MB"/"340 KB" -- só pro painel admin, não precisa de precisão."""
    valor = float(bytes_)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{valor:.1f} {unidade}" if unidade != "B" else f"{int(valor)} B"
        valor /= 1024
    return f"{valor:.1f} GB"


def _disco_info() -> dict:
    """Espaço em disco da partição de `DATA_DIR` + tamanho dos arquivos
    de registro -- pensado pra avisar ANTES de faltar espaço pros
    backups, não depois (achado: numa VM pequena, 1-2GB livres somem
    rápido com `ssr_cache`/backups acumulando)."""
    try:
        uso = shutil.disk_usage(DATA_DIR)
        livre_pct = round(100 * uso.free / uso.total, 1) if uso.total else 0.0
    except OSError:
        uso = None
        livre_pct = None
    db_tamanho = (db_backup._DB_PATH.stat().st_size
                 if db_backup._DB_PATH.exists() else 0)
    backups_tamanho = sum(
        p.stat().st_size for p in db_backup._BACKUP_DIR.glob("*")
    ) if db_backup._BACKUP_DIR.exists() else 0
    return {
        "livre_fmt": _tamanho_fmt(uso.free) if uso else "—",
        "total_fmt": _tamanho_fmt(uso.total) if uso else "—",
        "livre_pct": livre_pct,
        "db_fmt": _tamanho_fmt(db_tamanho),
        "backups_fmt": _tamanho_fmt(backups_tamanho),
    }


def _contagem_usuarios() -> int:
    """Quantas contas Steam já logaram ao menos uma vez -- 0 se o banco
    ainda não existe (site sem nenhum login ainda)."""
    if not db_backup._DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_backup._DB_PATH))
        n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return int(n)
    except sqlite3.Error:
        return 0


_RISCO_LABELS = {"low": "Baixo", "medium": "Médio", "high": "Alto"}

# `signals.liquidity_depth()` já calcula isto em todo scan (dias de
# listagens no ritmo atual) mas não aparecia em lugar nenhum da UI até
# 2026-11-02 -- achado numa pesquisa de como outros sites de skin
# expõem liquidez. Rótulo só pra exibição; a lógica/faixas já vêm
# prontas de `signals.py`.
_LIQUIDEZ_LABELS = {
    "muito_liquido": "Muito líquida",
    "liquido": "Líquida",
    "moderado": "Moderada",
    "fino": "Baixa liquidez",
    "iliquido": "Ilíquida",
}


def _liquidez_label(band: "str | None") -> str:
    return _LIQUIDEZ_LABELS.get(band or "", "")


def _rotulo_caixa(case_label: "str | None",
                  item_name: "str | None" = None) -> str:
    """Traduz o nome da caixa em "X Case (descontinuada, 2014)" com o mesmo
    `localize_name` da coluna Item -- sem isso a linha mostrava "Caixa
    CS:GO Weapon" no nome e "CS:GO Weapon Case" ao lado.

    Com `item_name` igual à própria caixa/cápsula, devolve só o status
    ("Descontinuada · 2024"): repetir o nome que já está na
    coluna Item ocupava a célula sem dizer nada novo."""
    if not case_label:
        return ""
    nome, sep, resto = case_label.partition(" (")
    if item_name and nome == item_name and resto:
        status, _, ano = resto.rstrip(")").partition(", ")
        texto = status[:1].upper() + status[1:]
        return f"{texto} · {ano}" if ano else texto
    return localize_name(nome) + sep + resto


# Maior palavra real conhecida logo após o "|" num nome de item (ex.
# "Asiimov", "Redline", "Doppler") fica bem abaixo disto -- serve só de
# limite de segurança (ver docstring de `_titulo_sem_pipe_orfao`).
_PIPE_COLADO_MAX = 20


def _titulo_sem_pipe_orfao(nome_fmt: "str | None") -> Markup:
    """Cola o "|" na palavra seguinte -- só pros títulos grandes (hero
    da home, h1 da página do item). Sem isso, o nome quebra de linha
    logo depois do separador "|" (ex. "Five-SeveN |" numa linha,
    "Monkey Business" na outra): a barra sozinha no fim da linha lê
    mal. Espaço duro (\xa0) sozinho NÃO resolve -- testado ao vivo: o
    motor de layout ainda abre uma quebra bem ali, com ou sem
    text-wrap:balance/overflow-wrap:anywhere na regra. Só um <span>
    com white-space:nowrap (.pipe-colado no CSS) prende os dois de
    verdade -- mas `white-space:nowrap` NÃO tem fallback de overflow
    (testado: nem `overflow-wrap:break-word` o destrava), então um
    nome fora do padrão (sem espaço nenhum ali) vazaria da caixa.
    `_PIPE_COLADO_MAX` existe só por isso: fora do comum, cai pro texto
    normal (ainda quebra mal, mas não estoura layout). Escopado nesta
    função, não em `localize_name`, de propósito -- name_fmt alimenta a
    API JSON e o texto que "Copiar nome" cola na área de transferência;
    HTML ali mudaria o contrato dos dois sem necessidade."""
    if not nome_fmt:
        return Markup("")
    antes, sep, depois = nome_fmt.partition("| ")
    if not sep:
        return Markup.escape(nome_fmt)
    palavra, _, resto = depois.partition(" ")
    if len(palavra) > _PIPE_COLADO_MAX:
        return Markup.escape(nome_fmt)
    pedaco = Markup('<span class="pipe-colado">|\xa0{}</span>').format(palavra)
    return Markup("{}{}{}{}").format(antes, pedaco, " " if resto else "", resto)


def _nota_classe(score: "int | float | None") -> str:
    """"alta"/"media"/"baixa" -- mesma faixa repetida em 4 templates
    (index/item/comparar/ranking) até 2026-10-26; centralizado aqui como
    filtro Jinja pra não divergir se a faixa mudar um dia."""
    score = score or 0
    if score >= 70:
        return "alta"
    if score >= 45:
        return "media"
    return "baixa"


# Raridade (cor da borda no ícone) fatorada em raridade.py 2026-11-07,
# pra watchlist/trades reusarem sem importar o módulo inteiro de rotas
# -- watchlist_routes.py e trades_routes.py cruzam pelo nome com o scan
# atual do mesmo jeito que ranking_page() já fazia.
_raridade_classe = raridade.raridade_classe
_raridade_titulo = raridade.raridade_titulo
_icone_raridade = raridade.icone_raridade


# Anel de progresso da nota (0-100) em SVG, gerado no servidor (mesmo
# padrão do sparkline) -- `stroke-dasharray` é atributo de apresentação do
# SVG, não `style=""`, então passa no CSP `style-src 'self'` sem problema.
_NOTA_ANEL_RAIO = 16


def _nota_anel(score) -> str:
    s = max(0, min(100, round(score or 0)))
    circ = 2 * math.pi * _NOTA_ANEL_RAIO
    dash = circ * s / 100
    return (
        f'<svg class="nota-anel" viewBox="0 0 40 40" aria-hidden="true" '
        f'focusable="false">'
        f'<circle class="nota-anel-fundo" cx="20" cy="20" r="{_NOTA_ANEL_RAIO}">'
        f'</circle>'
        f'<circle class="nota-anel-progresso" cx="20" cy="20" r="{_NOTA_ANEL_RAIO}" '
        f'stroke-dasharray="{dash:.2f} {circ:.2f}"></circle></svg>'
    )


def _risco_nivel(pump_risk: "dict | None") -> str:
    return (pump_risk or {}).get("level", "low")


def _risco_label(pump_risk: "dict | None") -> str:
    return _RISCO_LABELS[_risco_nivel(pump_risk)]


def _tempo_desde_aposentadoria(data_iso: "str | None") -> "str | None":
    """"2.3 anos"/"40 dias" desde a aposentadoria registrada (ver
    `galaseca/retirements.py` -- é o mesmo dado que já alimenta o
    score, só formatado pra leitura humana). None sem data registrada
    -- a maioria das caixas descontinuadas antigas não tem; o registro
    só começou em 2026-10-17."""
    if not data_iso:
        return None
    try:
        dia = date.fromisoformat(data_iso)
    except ValueError:
        return None
    dias = (date.today() - dia).days
    if dias < 0:
        return None
    anos = dias / 365.25
    return f"{anos:.1f} anos" if anos >= 1 else f"{dias} dia{'s' if dias != 1 else ''}"


def _itens_parecidos(item: dict, candidatos: list[dict], limite: int = 5) -> list[dict]:
    """Mesma categoria, nota mais próxima primeiro (nunca o próprio item).
    [] sem categoria -- sem isso o item.html teria que checar na mão."""
    cat = item.get("category")
    if not cat:
        return []
    mesma_cat = [c for c in candidatos
                if c.get("category") == cat and c["name"] != item["name"]]
    mesma_cat.sort(key=lambda c: abs((c.get("score") or 0) - (item.get("score") or 0)))
    return mesma_cat[:limite]


# Quantos itens aparecem nos cards de "maiores mudanças de nota" (home).
_MOVIMENTOS_DESTAQUE = 3


# Períodos de comparação do /ranking: chave da URL -> (horas, rótulo).
# `None` = scan imediatamente anterior. Com o worker de 6 em 6h, 30 dias
# são ~120 snapshots -- cabe no `ranking._SNAPSHOT_CAP`.
_PERIODOS_RANKING = {
    "scan": (None, "Último scan"),
    "24h": (24, "24 horas"),
    "7d": (7 * 24, "7 dias"),
    "30d": (30 * 24, "30 dias"),
}
_PERIODO_RANKING_PADRAO = "24h"
# Janela do "histórico no ranking" da página do item.
_DIAS_HISTORICO_RANKING = 30
# Folga pra um ciclo que terminou um pouco mais cedo ainda contar como
# "de 24h atrás" (é a mesma régua de 20h que `_resumo_do_dia` já usava).
_FOLGA_PERIODO_H = 4


def _snapshot_de_comparacao(atual: "dict | None",
                            periodo: str) -> "dict | None":
    """Snapshot contra o qual o /ranking compara. None quando ainda não
    existe um velho o suficiente pro período -- a tela diz isso em vez de
    comparar com um mais recente e chamar de "7 dias"."""
    if not atual:
        return None
    horas = _PERIODOS_RANKING[periodo][0]
    if horas is None:
        return ranking.previous_snapshot()
    return ranking.latest_before(
        atual["ts"] - (horas - _FOLGA_PERIODO_H) * 3600)


def _resumo_do_dia(atual: "dict | None") -> "dict | None":
    """Resumo factual do Top 20 comparado com o snapshot de ~1 dia atrás
    (nunca previsão). None sem
    snapshot velho o suficiente (site novo ou só 1 scan até agora)."""
    if not atual:
        return None
    return _resumo_entre(atual, _snapshot_de_comparacao(atual, "24h"))


def _resumo_entre(atual: "dict | None",
                  antigo: "dict | None") -> "dict | None":
    """Resumo factual (nunca previsão) do Top 20 `atual` contra `antigo`."""
    if not atual or not antigo:
        return None
    itens_antigos = {it["name"]: it for it in antigo.get("items", [])}
    novos = [it for it in atual["items"] if it["name"] not in itens_antigos]
    maior_alta = None
    maior_queda = None
    # `movimentos` alimenta os mini-cards da home (item #19 da lista de
    # melhorias): os maiores vaivens de nota, pra alta E pra baixa, sem
    # escolher "vencedor". Fica só com o que realmente mudou -- item que
    # repetiu a mesma nota não é notícia e só gastaria card.
    movimentos = []
    for it in atual["items"]:
        velho = itens_antigos.get(it["name"])
        if not velho:
            continue
        diff = it.get("score", 0) - velho.get("score", 0)
        if diff:
            movimentos.append({
                "name": it["name"],
                "name_fmt": localize_name(it["name"]),
                "diff": diff,
                "de": velho.get("score"),
                "para": it.get("score"),
            })
        if diff > 0 and (maior_alta is None or diff > maior_alta["diff"]):
            maior_alta = {
                "name_fmt": localize_name(it["name"]),
                "diff": diff,
                "de": velho.get("score"),
                "para": it.get("score"),
            }
        if diff < 0 and (maior_queda is None or diff < maior_queda["diff"]):
            maior_queda = {
                "name_fmt": localize_name(it["name"]),
                "diff": diff,
                "de": velho.get("score"),
                "para": it.get("score"),
            }
    # Maior mudança primeiro (em módulo); empate resolvido pelo nome só
    # pra ordem ser estável entre renders com os mesmos dados.
    movimentos.sort(key=lambda m: (-abs(m["diff"]), m["name"]))
    return {
        "novos_no_top": len(novos),
        "maior_alta": maior_alta,
        "maior_queda": maior_queda,
        "movimentos": movimentos[:_MOVIMENTOS_DESTAQUE],
        "quando": scan_store.idade_txt(antigo["ts"]),
    }


_logger = logging.getLogger("galaseca.site")

# Eventos detectados nos arquivos do jogo (gamedata.py, gravados pelo
# worker) em português de quem está começando: o que mudou + o que isso
# quer dizer na prática. Descreve o fato, não prevê preço.
_EVENTOS_JOGO = {
    "drop_pool_added": (
        "entrou no drop semanal",
        "Jogadores voltam a receber itens desta coleção nos drops "
        "semanais, então novas unidades entram no jogo por esse caminho."),
    "drop_pool_removed": (
        "saiu do drop semanal",
        "A coleção deixou de cair nos drops semanais: novas unidades "
        "param de entrar no jogo por esse caminho."),
    "xpshop_added": (
        "entrou no Armory",
        "Passou a poder ser resgatado no Armory, a loja de recompensas "
        "do passe."),
    "xpshop_removed": (
        "saiu do Armory",
        "Deixou de poder ser resgatado no Armory. Quando é uma caixa, "
        "o galaseca passa a tratá-la como aposentada nesta data."),
    "new_container": (
        "apareceu nos arquivos do jogo",
        "Caixa nova nos arquivos do jogo. Pode ainda não estar à venda "
        "no Market."),
}
_EVENTOS_JOGO_MAX = 30


def _data_do_evento(ev: dict) -> "float | None":
    """Data do commit dos arquivos (quando a Valve mudou), com a data da
    detecção como reserva."""
    bruto = ev.get("commit_date")
    if isinstance(bruto, str) and bruto:
        try:
            return datetime.fromisoformat(bruto.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    ts = ev.get("ts")
    return float(ts) if isinstance(ts, (int, float)) else None


def _eventos_do_jogo(nomes_no_site: "set[str]",
                     so_do_item: "str | None" = None) -> "list[dict]":
    """Eventos de `gamedata.load_events_log()` prontos pro template, do
    mais novo pro mais antigo. Só vira link o nome que o site acompanha."""
    try:
        brutos = gamedata.load_events_log()
    except Exception:
        _logger.warning("log de eventos do jogo ilegível", exc_info=True)
        return []
    out = []
    for ev in brutos:
        if not isinstance(ev, dict) or ev.get("type") not in _EVENTOS_JOGO:
            continue
        nome = str(ev.get("name") or "")
        if not nome or (so_do_item is not None and nome != so_do_item):
            continue
        ts = _data_do_evento(ev)
        verbo, explicacao = _EVENTOS_JOGO[ev["type"]]
        out.append({
            "nome": nome,
            "nome_fmt": localize_name(nome),
            "verbo": verbo,
            "explicacao": explicacao,
            "ts": ts or 0.0,
            "data": (datetime.fromtimestamp(ts, tz=fmt.FUSO_BR).strftime("%d/%m/%Y")
                     if ts else None),
            "no_site": nome in nomes_no_site,
        })
    out.sort(key=lambda e: -e["ts"])
    return out[:_EVENTOS_JOGO_MAX]


def _noticias_oficiais() -> "list[dict]":
    try:
        itens = steam_news.carregar_noticias()
    except Exception:
        _logger.warning("cache de notícias ilegível", exc_info=True)
        return []
    out = []
    for n in itens:
        if not isinstance(n, dict) or not n.get("titulo"):
            continue
        ts = n.get("ts")
        out.append({
            "titulo": n["titulo"],
            "resumo": n.get("resumo") or "",
            "url": n.get("url"),
            "data": (datetime.fromtimestamp(ts, tz=fmt.FUSO_BR).strftime("%d/%m/%Y")
                     if isinstance(ts, (int, float)) else None),
        })
    return out


def _variantes_para_tela(item: dict,
                         com_pagina: "set[str]") -> "list[dict]":
    """Outras versões da skin (ver `scan_engine._resumo_variantes`) com
    nome em português, preço formatado e link: pra página do galaseca
    quando o site acompanha aquela versão, senão pro Market."""
    out = []
    for v in item.get("variantes") or []:
        if not isinstance(v, dict) or not v.get("name"):
            continue
        nome = v["name"]
        ts = v.get("ts")
        out.append({
            "name": nome,
            "name_fmt": localize_name(nome),
            "mediana_fmt": (fmt.brl(v["mediana"])
                            if isinstance(v.get("mediana"), (int, float))
                            else "—"),
            "compras_24h": v.get("compras_24h"),
            "quando": (scan_store.idade_txt(ts)
                       if isinstance(ts, (int, float)) else None),
            "tem_pagina": nome in com_pagina,
            "market_url": _MARKET_LISTING_URL.format(
                name=urllib.parse.quote(nome, safe="")),
        })
    return out


# Progresso gravado há mais que isto não é "agora": o worker grava a cada
# item (~9 s), então 3 min sem atualizar = ciclo parado ou já terminou.
_PROGRESSO_VIVO_S = 180


def _estado_do_scan(progresso: "dict | None", ciclos: "list[dict]",
                    intervalo_horas: float,
                    now: "float | None" = None) -> dict:
    """O que o /status diz do scan agora: em andamento (item N de M, com
    previsão pelo ritmo do último ciclo) ou a próxima rodada prevista.
    `ciclos` vem do mais novo pro mais antigo (como em /status)."""
    agora = time.time() if now is None else now
    if (progresso and agora - float(progresso.get("ts") or 0) <= _PROGRESSO_VIVO_S
            and int(progresso.get("indice") or 0) < int(progresso.get("total") or 0)):
        indice, total = int(progresso["indice"]), int(progresso["total"])
        faltam_txt = None
        ultimo = next((c for c in ciclos if c.get("sucesso")
                       and c.get("itens")), None)
        if ultimo and ultimo.get("duracao_min"):
            por_item_s = float(ultimo["duracao_min"]) * 60 / max(
                1, int(ultimo.get("alvos") or ultimo["itens"]))
            faltam_min = max(1, round((total - indice) * por_item_s / 60))
            faltam_txt = f"~{faltam_min} min"
        return {"rodando": True, "indice": indice, "total": total,
                "item_fmt": localize_name(str(progresso.get("item") or "")),
                "faltam_txt": faltam_txt}
    if not ciclos:
        return {"rodando": False, "proximo_txt": None}
    return {"rodando": False,
            "proximo_txt": scan_store.proxima_txt(
                ciclos[0]["ts"], intervalo_horas, now=agora)}


def _nomes_com_pagina(scan: "dict | None") -> "set[str]":
    """Nomes que têm página em /item/<nome> -- a mesma lista filtrada
    que `item_detail` usa."""
    if not scan:
        return set()
    return {c["name"] for c in _candidatos_filtrados(
        scan, com_historico=False, com_icone=False)}


def _saidas_do_top(atual: "dict | None", anterior: "dict | None",
                   por_nome_scan: dict,
                   com_pagina: "set[str]") -> "list[dict]":
    """Quem estava no Top 20 de `anterior` e não está no `atual`, na
    ordem da posição antiga -- a outra metade do selo NOVO."""
    if not atual or not anterior:
        return []
    nomes_atuais = {it["name"] for it in atual.get("items", [])}
    out = []
    for it in sorted(anterior.get("items", []),
                     key=lambda i: i.get("position") or 0):
        if it["name"] in nomes_atuais:
            continue
        agora = por_nome_scan.get(it["name"])
        out.append({
            "name": it["name"],
            "name_fmt": localize_name(it["name"]),
            "prev_pos": it.get("position"),
            "prev_score": it.get("score"),
            "score": agora.get("score") if agora else None,
            "tem_pagina": it["name"] in com_pagina,
        })
    return out


_HISTORICO_CURTO_LIMIAR = 5


def _sparkline_do_historico(hist: list) -> str:
    pontos = [{"total": p["price"]} for p in hist[-20:] if p.get("price")]
    return charts.line_chart_svg(
        pontos, width=120, height=28, padding=2, css_class="mini-sparkline")


# Dias de cada opção do seletor de período do gráfico em `/item/<name>`
# (achado 2026-11-02, pesquisa de sites de skin: um período fixo de 60
# pontos não deixa claro se o visitante está vendo a tendência real ou só
# ruído de curto prazo). "tudo" (sem entrada aqui) mantém o recorte
# padrão de sempre, pra não mudar o comportamento de quem não escolhe nada.
_PERIODOS_GRAFICO = {"7d": 7, "30d": 30, "90d": 90}


def _filtra_historico_por_periodo(hist: list, periodo: "str | None") -> list:
    """Recorta `hist` pelos últimos N dias de `_PERIODOS_GRAFICO`.

    `ts` é sempre um timestamp Unix (float) gravado por
    `signals.record_item_price` -- mesmo formato que `scan_store.idade_txt`
    já espera. Período desconhecido ou "tudo" caem no recorte padrão de
    sempre (os últimos 60 pontos), sem filtrar por data.
    """
    dias = _PERIODOS_GRAFICO.get(periodo or "")
    if not dias:
        return hist[-60:]
    corte = time.time() - dias * 86400
    return [p for p in hist if (p.get("ts") or 0) >= corte]


def _enriquecer_com_icone(candidatos: list[dict]) -> None:
    """Preenche `icon_url`/`icon_url_2x` -- feito à parte de
    `_candidatos_filtrados` (mesma ideia de `_enriquecer_com_historico`,
    acima) de propósito: cada `url_for` aqui builda uma URL via o
    roteador do Flask, caro à toa pros ~150-180 candidatos quando só
    uma fatia pequena é exibida de verdade. Profiling 2026-11-09: 42%
    do tempo de `/` inteiro vinha dessas duas chamadas rodando pra
    TODOS os candidatos, mesmo só 10 aparecendo na página -- mesmo
    desperdício que `_enriquecer_com_historico` já corrigiu pro
    histórico em 2026-10-26, nunca estendido ao ícone. Só chamar com a
    fatia que vai renderizar de verdade."""
    for c in candidatos:
        c["icon_url"] = (
            url_for("icone_cache", hash_icone=c["icon"], v=2)
            if c.get("icon") else None)
        c["icon_url_2x"] = (
            url_for("icone_cache", hash_icone=c["icon"], v=2, tam=384)
            if c.get("icon") else None)


def _enriquecer_com_historico(candidatos: list[dict]) -> None:
    """Preenche `tendencia`/`sparkline` -- feito à parte de
    `_candidatos_filtrados` (acima) de propósito: ler o histórico de
    TODOS os candidatos (até ~150) quando só 10 aparecem na página é
    caro à toa (2 leituras de disco por item, uma pra cada campo, antes
    desta função existir). Só chamar com a fatia que vai renderizar de
    verdade (a página atual, ou o grupo aberto)."""
    for c in candidatos:
        hist = signals.load_item_history(c.get("name") or "")
        c["tendencia"] = _tendencia_do_historico(hist)
        c["variacao_pct"] = _variacao_pct_do_historico(hist)
        c["sparkline"] = _sparkline_do_historico(hist)
        # Com poucos pontos a linha fica tão "confiante" quanto uma de
        # 20 -- sem aviso, parece preço estável em vez de "ainda não
        # temos dado suficiente" (achado 2026-11-02, pesquisa de
        # padrões de sites de skin). Não esconde o gráfico, só avisa.
        n_pontos = sum(1 for p in hist[-20:] if p.get("price"))
        c["historico_curto"] = 0 < n_pontos < _HISTORICO_CURTO_LIMIAR
        c["historico_pontos"] = n_pontos


_LIQUIDEZ_ORDEM = ["iliquido", "fino", "moderado", "liquido", "muito_liquido"]


def _candidatos_filtrados(
        scan: "dict | None", categoria: "str | None" = None,
        nota_min: "float | None" = None,
        preco_max: "float | None" = None,
        busca: "str | None" = None,
        ordenar: str = "nota",
        liquidez_min: "str | None" = None,
        com_historico: bool = True,
        com_icone: bool = True) -> list[dict]:
    """Candidatos públicos: sem dono (sem login ainda), já filtrados.

    Sem limite aqui de propósito -- a paginação é responsabilidade de quem
    chama (a rota), não desta função. `buy_candidates` já ordena por nota
    (desc); `ordenar="preco"` reordena por preço (asc) depois.

    `com_historico=False` pula tendência/sparkline (2 leituras de disco
    por item) -- usar quando quem chama só vai exibir uma FATIA do
    resultado (ex. uma página de 10 em até ~150 candidatos) e vai chamar
    `_enriquecer_com_historico` só nessa fatia depois. Achado 2026-10-26:
    o `index()` lia o histórico de TODOS os candidatos em toda visita,
    mesmo mostrando só uma página por vez.

    `com_icone=False` pula `icon_url`/`icon_url_2x` (2 `url_for` por
    item, caro -- envolve o roteador do Flask) pelo mesmo motivo; usar
    `_enriquecer_com_icone` só na fatia exibida depois. Achado
    2026-11-09 (profiling ao vivo): essas duas chamadas pra TODOS os
    candidatos eram 42% do tempo da home inteira.

    `liquidez_min` usa a mesma faixa nomeada de `signals.liquidity_depth`
    (pedido numa pesquisa de como outros sites de skin expõem liquidez,
    2026-11-02) -- item sem o dado (volume/histórico insuficiente) fica
    de fora quando o filtro está ativo: não dá pra confirmar que atende
    o mínimo pedido, mesmo critério "não promete o que não sabe" do
    resto do site.
    """
    if not scan:
        return []
    candidatos = recommendations.buy_candidates(
        scan["results"], owned_names=set(), limit=len(scan["results"]) or 1)
    out = []
    for c in candidatos:
        if categoria and c.get("category") != categoria:
            continue
        if nota_min is not None and (c.get("score") or 0) < nota_min:
            continue
        if preco_max is not None and (c.get("price") or 0) > preco_max:
            continue
        if liquidez_min:
            band = (c.get("liquidity_depth") or {}).get("band")
            if band not in _LIQUIDEZ_ORDEM:
                continue
            if _LIQUIDEZ_ORDEM.index(band) < _LIQUIDEZ_ORDEM.index(liquidez_min):
                continue
        name_fmt = localize_name(c.get("name") or "")
        if not _busca_bate(name_fmt, busca):
            continue
        c["price_fmt"] = fmt.brl(c.get("price"))
        c["name_fmt"] = name_fmt
        c["raridade_classe"] = _raridade_classe(c)
        c["raridade_titulo"] = _raridade_titulo(c)
        # Nota crua (signals.raw_score) sem o corte em [0, 100] -- achado
        # 2026-11-04: a soma dos fatores passa de 100 (ou de 0) com
        # frequência pra item muito bom (ou muito ruim), e o corte faz
        # vários itens diferentes mostrarem o mesmo "100"/"0" na tela,
        # mesmo a ORDEM deles já sendo correta por dentro (buy_candidates
        # já desempata por isto). margem != 0 só quando o corte realmente
        # aconteceu -- pra nota normal (1-99) a nota crua bate exatamente
        # com a exibida, margem sempre 0, não aparece nada. Exige
        # `breakdown` não-vazio: sem ele não dá pra confiar que bate com
        # `score` (ex.: dado sintético de teste que só define `score`).
        c["nota_margem"] = None
        if c.get("breakdown"):
            margem = round(signals.raw_score(c["breakdown"])) - (c.get("score") or 0)
            c["nota_margem"] = margem if margem != 0 else None
        # Confiança do dado por trás da nota (signals.data_quality) --
        # achado 2026-11-04: calculada a cada scan, nunca exibida em
        # lugar nenhum (a própria função já dizia "Util para... UI
        # badge: mostrar ao usuário quando confiar no score"). Um item
        # com poucos pontos de histórico (ou histórico velho) calcula a
        # MESMA nota que um com dado rico -- vários fatores (momentum,
        # drawdown, rel_ath, pump_risk) são gateados por tamanho mínimo
        # de amostra, mas isso não aparece pro visitante hoje. Mostra só
        # quando a confiança é baixa -- caso raro é o esperado (como
        # risco baixo não vira coluna), então sem selo nenhum na maioria
        # das linhas.
        dq = c.get("data_quality") or {}
        c["confianca_baixa"] = dq.get("level") in ("low", "very_low", "none")
        if c["confianca_baixa"]:
            n = dq.get("n") or 0
            age = dq.get("age_days")
            if age is not None:
                c["confianca_baixa_titulo"] = (
                    f"Nota calculada com só {n} ponto{'s' if n != 1 else ''} de "
                    f"histórico da Steam, o mais recente de {age:.0f} dia"
                    f"{'s' if round(age) != 1 else ''} atrás -- alguns fatores "
                    "podem não ter tido dado suficiente pra entrar no cálculo.")
            else:
                c["confianca_baixa_titulo"] = (
                    "Nota calculada sem histórico de preço da Steam pra esse "
                    "item -- a maioria dos fatores não tinha dado suficiente "
                    "pra entrar no cálculo.")
        # icon_url_2x pede 384px (2x de 192) -- até 2026-11-08 era cópia
        # do icon_url de 192px (achado da revisão de direção visual: o
        # hero/vitrine mostra esse ícone bem maior que o nativo, perda
        # de nitidez visível). Mesmo hash, cache separado por tamanho
        # (ver icon_cache.py) -- o navegador já escolhe sozinho qual
        # usar pelo density do visitante, sem mudar nenhum template.
        if com_icone:
            c["icon_url"] = (
                url_for("icone_cache", hash_icone=c["icon"], v=2)
                if c.get("icon") else None)
            c["icon_url_2x"] = (
                url_for("icone_cache", hash_icone=c["icon"], v=2, tam=384)
                if c.get("icon") else None)
        else:
            c["icon_url"] = None
            c["icon_url_2x"] = None
        c["market_url"] = _MARKET_LISTING_URL.format(
            name=urllib.parse.quote(c.get("name") or "", safe=""))
        c["steamdb_url"] = _STEAMDB_SEARCH_URL.format(
            name=urllib.parse.quote(c.get("name") or "", safe=""))
        # achado 2026-10-30: quando tem data exata registrada em
        # retirements.py, cases.py gera "aposentada em DD/MM/AAAA" em
        # vez de "descontinuada" -- esse rótulo (o mais confiável, por
        # ter fonte factual) ficava sem o selo .selo-descontinuada.
        _rotulo_cx = c.get("case_label") or ""
        c["descontinuada"] = (
            "descontinuada" in _rotulo_cx or "aposentada" in _rotulo_cx)
        if com_historico:
            _enriquecer_com_historico([c])
        out.append(c)
    if ordenar == "preco":
        out.sort(key=lambda c: c.get("price") if c.get("price") is not None
                 else float("inf"))
    return out


def run(host: str = "127.0.0.1", port: int = 5050) -> None:
    """Dev server do Flask. Produção troca por gunicorn/waitress (Fase 3)."""
    create_app().run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
