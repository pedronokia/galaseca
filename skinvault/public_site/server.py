"""Flask app factory do site público -- só leitura, sem login.

Serve só o que `worker.py` (processo separado) já escreveu em
`scan_store.json`/`rankings.json`. NUNCA fala com a Steam por requisição
de visitante -- ver AGENTS.md e o plano desta fase (Fase 1: dashboard
público, sem conta, sem dado pessoal). `recommendations.buy_candidates`
roda com `owned_names=set()`: ninguém é "dono" de nada aqui, então é
sempre a visão pública completa.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import secrets
import sqlite3
import time
import urllib.parse
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from flask import (
    Flask, Response, g, jsonify, make_response, redirect, render_template,
    request, send_from_directory, session, url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash

from skinvault import (
    __version__, ranking, recommendations, scan_store, scan_targets, signals,
)
from skinvault._paths import DATA_DIR, atomic_write_bytes
from skinvault.localization import localize_name
from skinvault.public_site import (
    buscas, changelog, charts, db_backup, erro_stats, fmt, icon_cache,
    latencia, rate_limit, scan_progress, uptime, visits,
)

_MARKET_LISTING_URL = "https://steamcommunity.com/market/listings/730/{name}"
# Ícone: CDN estático da Steam (steamstatic.com), não o market/inventory
# rate-limited -- cacheado localmente via `icon_cache.py` (2a rodada,
# 2026-10-25) pela rota `/icone/<hash>.jpg` abaixo. Esta constante
# continua servindo de FALLBACK (redirect) quando o cache falha.
_ICON_CDN_URL_2X = (
    "https://community.cloudflare.steamstatic.com/economy/image/"
    "{hash}/192fx192f"
)
_STEAMDB_SEARCH_URL = "https://steamdb.info/search/?q={name}"
from skinvault.public_site.account import bp as account_bp
from skinvault.public_site.history_routes import bp as history_bp
from skinvault.public_site.trades_routes import bp as trades_bp
from skinvault.public_site.watchlist_routes import bp as watchlist_bp

_STATIC_DIR = Path(__file__).parent / "static"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_LIMIT_CANDIDATOS = 20
_PAGINA_TAMANHO = 20
_INTERVALO_HORAS_DEFAULT = 6.0
_SECRET_KEY_PATH = DATA_DIR / "public_site_secret.key"
_ERROR_LOG_PATH = DATA_DIR / "errors.log"
# Gravado pelo Dockerfile a cada build (data/hora do build, UTC) -- sem
# isso __version__ fica preso em "1.0.0" pra sempre, sem jeito de saber
# SE um deploy novo de fato subiu. Ausente fora de Docker (dev local).
_BUILD_ID_PATH = Path(__file__).parent.parent.parent / "BUILD_ID"
_ADMIN_PASSWORD_HASH = os.environ.get("SKINVAULT_ADMIN_PASSWORD_HASH", "")


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
    """Lê um query param numérico opcional. Vazio/inválido -> None --
    nunca `or 0`, que confundiria "não informado" com "zero" (AGENTS.md
    gotcha #15)."""
    valor = request.args.get(nome)
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _parse_int_arg(nome: str, default: int) -> int:
    valor = request.args.get(nome)
    if valor is None or valor == "":
        return default
    try:
        return max(1, int(valor))
    except ValueError:
        return default


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
    # Produção seta SKINVAULT_PUBLIC_SITE_SECURE_COOKIES=1 (ver
    # skinvault/public_site/README.md).
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SKINVAULT_PUBLIC_SITE_SECURE_COOKIES") == "1")

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
        ordenar = request.args.get("ordenar") or "nota"
        if ordenar not in ("nota", "preco"):
            ordenar = "nota"
        # Prefs (compacto/agrupar/minimalista): query param manda quando
        # presente; na ausência, cai pro cookie salvo da última escolha
        # -- sem isso o visitante tinha que clicar "Modo compacto" de
        # novo em toda visita nova (pedido explícito, 2026-10-25).
        compacto = (request.args.get("compacto") == "1" if "compacto" in request.args
                   else request.cookies.get("pref_compacto") == "1")
        agrupar = (request.args.get("agrupar") == "1" if "agrupar" in request.args
                  else request.cookies.get("pref_agrupar") == "1")
        minimalista = (request.args.get("minimalista") == "1" if "minimalista" in request.args
                      else request.cookies.get("pref_minimalista") == "1")
        apresentacao = request.args.get("apresentacao") == "1"
        pagina = _parse_int_arg("pagina", 1)
        if busca:
            buscas.registrar(busca)

        todos = _candidatos_filtrados(
            scan, categoria, nota_min, preco_max, busca, ordenar)
        inicio = (pagina - 1) * _PAGINA_TAMANHO
        intervalo_horas = float(os.environ.get(
            "SKINVAULT_WORKER_INTERVAL_HORAS", _INTERVALO_HORAS_DEFAULT))
        # Banner de "dado pode estar desatualizado" -- pedido depois do
        # bloqueio real de 429 que durou horas (2026-10-25): sem isto, a
        # tabela mostra dado velho em silêncio, como se fosse de agora.
        # 2x o intervalo configurado é a margem (um ciclo atrasado não
        # é anormal; dois seguidos geralmente é bloqueio da Steam).
        scan_desatualizado = bool(
            scan and (time.time() - scan["ts"]) > intervalo_horas * 3600 * 2)
        resp = make_response(render_template(
            "index.html",
            candidatos=todos[inicio:inicio + _PAGINA_TAMANHO],
            grupos=_agrupar_por_categoria(todos) if agrupar else None,
            scan=scan,
            idade=scan_store.idade_txt(scan["ts"]) if scan else None,
            proximo_scan=(scan_store.proxima_txt(scan["ts"], intervalo_horas)
                         if scan else None),
            scan_desatualizado=scan_desatualizado,
            categorias=sorted(scan_targets.SCAN_BY_CATEGORY.keys()),
            contagem_categorias=_contagem_por_categoria(scan),
            categoria_sel=categoria,
            nota_min_sel=nota_min,
            preco_max_sel=preco_max,
            busca_sel=busca,
            ordenar_sel=ordenar,
            compacto_sel=compacto,
            agrupar_sel=agrupar,
            minimalista_sel=minimalista,
            apresentacao_sel=apresentacao,
            pagina=pagina,
            tem_proxima_pagina=len(todos) > inicio + _PAGINA_TAMANHO,
            tem_pagina_anterior=pagina > 1,
            total_candidatos=len(todos),
        ))
        _UM_ANO_S = 365 * 24 * 3600
        for nome_param, valor in (("compacto", compacto), ("agrupar", agrupar),
                                  ("minimalista", minimalista)):
            if nome_param in request.args:
                resp.set_cookie(f"pref_{nome_param}", "1" if valor else "0",
                                max_age=_UM_ANO_S, samesite="Lax")
        return resp

    @app.route("/item/<name>")
    def item_detail(name: str):
        """Página por item -- permalink compartilhável, com o histórico
        completo de preço (reaproveita `charts.line_chart_svg`, já usado
        pro gráfico de visitas) e "itens parecidos" (mesma categoria,
        nota mais próxima). Sem chamada à Steam: os mesmos dados já
        calculados em `_candidatos_filtrados`, filtrados pelo nome."""
        scan = scan_store.load_last_scan()
        candidatos = _candidatos_filtrados(scan)
        item = next((c for c in candidatos if c["name"] == name), None)
        if item is None:
            return render_template("404.html"), 404
        hist = signals.load_item_history(name)
        grafico = charts.line_chart_svg(
            [{"total": p["price"]} for p in hist[-60:] if p.get("price")])
        return render_template(
            "item.html",
            item=item,
            grafico=grafico,
            parecidos=_itens_parecidos(item, candidatos),
            tempo_aposentadoria=_tempo_desde_aposentadoria(item.get("case_retired_at")),
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
        nomes recebidos em `?nomes=A,B,C` pros dados já calculados."""
        scan = scan_store.load_last_scan()
        candidatos = _candidatos_filtrados(scan)
        nomes = [n for n in (request.args.get("nomes") or "").split(",") if n][:3]
        por_nome = {c["name"]: c for c in candidatos}
        itens = [por_nome[n] for n in nomes if n in por_nome]
        return render_template("comparar.html", itens=itens)

    @app.route("/api/recommendations")
    @rate_limit.rate_limited(rate_limit.API_MAX_HITS, rate_limit.API_WINDOW_S)
    def api_recommendations():
        scan = scan_store.load_last_scan()
        return jsonify({
            "ultimo_scan": {
                "categoria": scan["category"] if scan else None,
                "ts": scan["ts"] if scan else None,
            },
            "candidatos": _candidatos_filtrados(scan)[:_LIMIT_CANDIDATOS],
        })

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
        intervalo_horas = float(os.environ.get(
            "SKINVAULT_WORKER_INTERVAL_HORAS", _INTERVALO_HORAS_DEFAULT))
        return jsonify({
            "ok": True,
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

    @app.route("/icone/<hash_icone>.jpg")
    def icone_cache(hash_icone: str):
        """Ícone servido do próprio domínio (ver `icon_cache.py`) --
        cache em disco, só busca do CDN da Steam na primeira vez que
        aquele hash aparece. Nunca 500: cache miss + rede fora vira
        redirect pro CDN direto, nunca erro pro visitante."""
        dados = icon_cache.obter(hash_icone)
        if dados is None:
            return redirect(_ICON_CDN_URL_2X.format(hash=hash_icone))
        resp = Response(dados, mimetype="image/jpeg")
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
    def sitemap():
        base = request.url_root.rstrip("/")
        paginas = ["/", "/privacidade", "/status", "/changelog", "/api",
                  "/ranking", "/metodo", "/sobre"]
        urls_xml = "\n".join(
            f"  <url><loc>{_xml_escape(base + p)}</loc></url>" for p in paginas)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls_xml}\n"
            "</urlset>\n"
        )
        return Response(xml, mimetype="application/xml")

    @app.errorhandler(404)
    def pagina_nao_encontrada(_erro):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def erro_interno(erro):
        app.logger.error("500 em %s: %r", request.path, erro, exc_info=erro)
        return render_template("500.html"), 500

    @app.errorhandler(429)
    def limite_excedido(_erro):
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
        itens_xml = "\n".join(
            "    <item>\n"
            f"      <title>{_xml_escape(e['data'])} — {_xml_escape(e['titulo'])}</title>\n"
            f"      <description>{_xml_escape('; '.join(e['itens']))}</description>\n"
            f"      <guid isPermaLink=\"false\">{_xml_escape(e['data'])}</guid>\n"
            "    </item>"
            for e in changelog.ENTRADAS
        )
        rss = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>\n'
            "  <title>SkinVault — Mudanças</title>\n"
            f"  <link>{_xml_escape(base)}/changelog</link>\n"
            "  <description>O que mudou no site, por data.</description>\n"
            "  <language>pt-BR</language>\n"
            f"{itens_xml}\n"
            "</channel></rss>\n"
        )
        return Response(rss, mimetype="application/rss+xml")

    @app.route("/metodo")
    def metodo():
        return render_template("metodo.html")

    @app.route("/sobre")
    def sobre():
        return render_template("sobre.html")

    @app.route("/ranking")
    def ranking_page():
        snaps = ranking.load_snapshots()
        atual = snaps[-1] if snaps else None
        anterior = ranking.previous_snapshot()
        itens = []
        if atual:
            for it in atual["items"]:
                delta = ranking.position_delta(
                    it["name"], it["position"], anterior)
                itens.append({
                    "name_fmt": localize_name(it["name"]),
                    "position": it["position"],
                    "score": it["score"],
                    **delta,
                })
        return render_template(
            "ranking.html",
            itens=itens,
            quando=scan_store.idade_txt(atual["ts"]) if atual else None,
            tem_anterior=anterior is not None,
        )

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

    @app.route("/admin/logout")
    def admin_logout():
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
            grafico_erros = charts.line_chart_svg(
                [{"total": qtd} for _dia, qtd
                 in erro_stats.serie_por_dia(linhas_agregacao)])
        backups = sorted(db_backup._BACKUP_DIR.glob("public_site-*.db")) \
            if db_backup._BACKUP_DIR.exists() else []
        progresso = scan_progress.carregar()
        if progresso:
            progresso = dict(progresso, idade=scan_store.idade_txt(progresso["ts"]))
        return render_template(
            "admin.html",
            build=_build_id(),
            visitas=visits.total(),
            mais_buscados=buscas.mais_buscados(limite=20),
            erros=erros,
            erros_agregados=erros_agregados,
            grafico_erros=grafico_erros,
            backups=[b.name for b in reversed(backups)],
            ciclos=list(reversed(scan_store.load_historico_ciclos()))[:10],
            progresso=progresso,
            latencias=latencia.resumo(),
        )

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
        grafico_visitas = charts.line_chart_svg(
            [{"total": qtd} for _dia, qtd in serie])
        return render_template(
            "status.html",
            no_ar_desde_txt=scan_store.idade_txt(desde),
            visitas=visits.total(),
            ciclos=ciclos,
            grafico_visitas=grafico_visitas,
            mais_buscados=buscas.mais_buscados(limite=10),
        )

    @app.route("/feed.xml")
    def feed():
        scan = scan_store.load_last_scan()
        candidatos = _candidatos_filtrados(scan)[:_LIMIT_CANDIDATOS]
        base = request.url_root.rstrip("/")
        itens_xml = "\n".join(
            "    <item>\n"
            f"      <title>{_xml_escape(c['name_fmt'])} — nota {c['score']}</title>\n"
            f"      <link>{_xml_escape(c['market_url'])}</link>\n"
            f"      <guid isPermaLink=\"false\">{_xml_escape(c['name'])}</guid>\n"
            "      <description>"
            f"{_xml_escape(c['price_fmt'])} — "
            f"{_xml_escape('; '.join(c['reasons']) if c['reasons'] else 'Nota neutra')}"
            "</description>\n"
            "    </item>"
            for c in candidatos
        )
        rss = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0"><channel>\n'
            "  <title>SkinVault — Recomendações de skins CS2</title>\n"
            f"  <link>{_xml_escape(base)}/</link>\n"
            "  <description>Nota de 0 a 100 pra skins do CS2, com o motivo"
            " escrito.</description>\n"
            "  <language>pt-BR</language>\n"
            f"{itens_xml}\n"
            "</channel></rss>\n"
        )
        return Response(rss, mimetype="application/rss+xml")

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


def _agrupar_por_categoria(candidatos: list[dict]) -> list[tuple[str, list[dict]]]:
    """Agrupa candidatos JÁ filtrados/ordenados em (categoria, itens),
    preservando a ordem de chegada dentro de cada grupo (mesma ordenação
    escolhida pelo visitante). "Sem categoria" entra por último."""
    grupos: dict[str, list[dict]] = {}
    for c in candidatos:
        cat = c.get("category") or "Sem categoria"
        grupos.setdefault(cat, []).append(c)
    sem_categoria = grupos.pop("Sem categoria", None)
    out = [(cat, grupos[cat]) for cat in sorted(grupos)]
    if sem_categoria:
        out.append(("Sem categoria", sem_categoria))
    return out


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


def _tendencia(name: str) -> "str | None":
    """"alta"/"baixa"/None a partir dos 2 últimos preços já registrados
    pra esse item (signals.record_item_price, chamado a cada scan desde
    sempre -- zero custo novo, só reaproveita histórico que já existia).
    None sem pelo menos 2 pontos (item visto pela 1a vez, ou muito raro
    no histórico)."""
    hist = signals.load_item_history(name)
    if len(hist) < 2:
        return None
    anterior, atual = hist[-2]["price"], hist[-1]["price"]
    if atual > anterior:
        return "alta"
    if atual < anterior:
        return "baixa"
    return None


def _tempo_desde_aposentadoria(data_iso: "str | None") -> "str | None":
    """"2.3 anos"/"40 dias" desde a aposentadoria registrada (ver
    `skinvault/retirements.py` -- é o mesmo dado que já alimenta o
    score, só formatado pra leitura humana). None sem data registrada
    -- a maioria das caixas descontinuadas antigas não tem (ver
    AGENTS.md 4c/4f: a data só começou a ser registrada em 2026-10-17)."""
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


def _sparkline(name: str) -> str:
    """Mini-gráfico de preço por linha na tabela -- reaproveita
    `signals.load_item_history` (mesmo histórico que já alimenta
    `_tendencia`) e `charts.line_chart_svg` (mesmo SVG do gráfico de
    visitas, com uma classe CSS diferente pra ficar pequeno e inline)."""
    hist = signals.load_item_history(name)
    pontos = [{"total": p["price"]} for p in hist[-20:] if p.get("price")]
    return charts.line_chart_svg(
        pontos, width=120, height=28, padding=2, css_class="mini-sparkline")


def _candidatos_filtrados(
        scan: "dict | None", categoria: "str | None" = None,
        nota_min: "float | None" = None,
        preco_max: "float | None" = None,
        busca: "str | None" = None,
        ordenar: str = "nota") -> list[dict]:
    """Candidatos públicos: sem dono (sem login ainda), já filtrados.

    Sem limite aqui de propósito -- a paginação é responsabilidade de quem
    chama (a rota), não desta função. `buy_candidates` já ordena por nota
    (desc); `ordenar="preco"` reordena por preço (asc) depois.
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
        name_fmt = localize_name(c.get("name") or "")
        if not _busca_bate(name_fmt, busca):
            continue
        c["price_fmt"] = fmt.brl(c.get("price"))
        c["name_fmt"] = name_fmt
        # Mesma URL (proxy local, servindo sempre a versão 192x192) pros
        # dois tamanhos do srcset -- um cache só por item em vez de dois,
        # troca otimização de banda em tela pequena por simplicidade.
        c["icon_url"] = (
            url_for("icone_cache", hash_icone=c["icon"]) if c.get("icon") else None)
        c["icon_url_2x"] = c["icon_url"]
        c["market_url"] = _MARKET_LISTING_URL.format(
            name=urllib.parse.quote(c.get("name") or "", safe=""))
        c["steamdb_url"] = _STEAMDB_SEARCH_URL.format(
            name=urllib.parse.quote(c.get("name") or "", safe=""))
        c["descontinuada"] = "descontinuada" in (c.get("case_label") or "")
        c["tendencia"] = _tendencia(c.get("name") or "")
        c["sparkline"] = _sparkline(c.get("name") or "")
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
